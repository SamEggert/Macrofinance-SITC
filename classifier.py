import os
import sqlite3
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import string
from collections import Counter
import re

# Load environment variables and initialize LangChain
load_dotenv()
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.getenv('OPENAI_API_KEY')
)

def is_terminal_code(cursor, code):
    """Check if a code has no deeper children"""
    cursor.execute("""
        SELECT COUNT(*)
        FROM sitc_codes
        WHERE code LIKE ? || '%' AND code != ?
    """, (code, code))
    return cursor.fetchone()[0] == 0



def get_options_for_level(cursor, level, parent_code=None):
    """Get available SITC codes for the current level (removing 4-digit limitation)"""
    if parent_code:
        cursor.execute("""
            SELECT code, description
            FROM sitc_codes
            WHERE level = ? AND code LIKE ? || '%'
            ORDER BY code
        """, (level, parent_code))
    else:
        cursor.execute("""
            SELECT code, description
            FROM sitc_codes
            WHERE level = ?
            ORDER BY code
        """, (level,))
    return cursor.fetchall()

def get_examples_for_level(cursor, level, parent_code=None):
    """Get training examples for a specific level/parent code"""
    if parent_code:
        cursor.execute("""
            SELECT t.description, t.sitc_code, s.description
            FROM training_examples t
            JOIN sitc_codes s ON t.sitc_code = s.code
            WHERE t.level = ? AND t.sitc_code LIKE ? || '%'
            LIMIT 5
        """, (level, parent_code))
    else:
        cursor.execute("""
            SELECT t.description, t.sitc_code, s.description
            FROM training_examples t
            JOIN sitc_codes s ON t.sitc_code = s.code
            WHERE t.level = ?
            LIMIT 5
        """, (level,))
    return cursor.fetchall()

def create_gpt_prompt(description, options, examples, previous_classifications=None, excluded_options=None, recent_classifications=None):
    """Create a prompt for GPT classification with context from recent classifications"""
    template = """You are a trade classification expert. Your task is to classify the following Spanish description into the most appropriate SITC category at the current level:

Description to classify: {description}

{recent_context}

Available options:
{formatted_options}

{examples_section}

{previous_section}

{attempt_guidance}

IMPORTANT:
1. Items that appear close to each other in the list often have similar classifications, especially in their first two digits.
2. Respond with ONLY a single letter from A-{last_letter}.
Do not include any explanations, colons, periods, or the category description."""

    letters = list(string.ascii_uppercase)
    option_map = {}
    formatted_options = ""

    # Filter out excluded options more strictly
    available_options = []
    for code, desc in options:
        if excluded_options and any(code.startswith(excluded) for excluded in excluded_options):
            continue
        available_options.append((code, desc))

    if not available_options:
        # If all options were excluded, use original options (failsafe)
        available_options = options

    for i, (code, desc) in enumerate(available_options):
        if i >= len(letters):
            break
        letter = letters[i]
        formatted_options += f"{letter}. {code}: {desc}\n"
        option_map[letter] = i

    # Format recent classifications context
    recent_context = ""
    if recent_classifications:
        recent_context = "Recent classifications from the same list:\n"
        for rc in recent_classifications:
            recent_context += f"- '{rc['description']}' was classified as {rc['code']}: {rc['sitc_description']}\n"
        recent_context += "\nNote: Items in the same list often have similar classifications, especially in their first two digits.\n"

    examples_section = ""
    if examples:
        examples_section = "Here are some examples of previous classifications:\n"
        for ex_desc, ex_code, ex_sitc_desc in examples:
            examples_section += f"- '{ex_desc}' was classified as {ex_code}: {ex_sitc_desc}\n"

    previous_section = ""
    if previous_classifications:
        previous_section = "Your classification path so far:\n"
        for level, (code, desc) in enumerate(previous_classifications, 1):
            previous_section += f"Level {level}: {code}: {desc}\n"

    attempt_guidance = ""
    if excluded_options:
        attempt_guidance = "Since some options were previously selected, please choose your next best classification from the remaining options."

    prompt = ChatPromptTemplate.from_template(template)

    formatted_prompt = prompt.format(
        description=description,
        formatted_options=formatted_options,
        examples_section=examples_section,
        previous_section=previous_section,
        attempt_guidance=attempt_guidance,
        last_letter=letters[min(len(available_options)-1, len(letters)-1)],
        recent_context=recent_context
    )

    return formatted_prompt, option_map


def clean_gpt_response(response):
    """Clean GPT response to get only the letter"""
    cleaned = re.sub(r'[^A-Za-z]', '', response).upper()
    if cleaned:
        return cleaned[0]  # Return only the first letter to avoid multiple letters
    return ""

def clean_code_for_level(code):
    """Remove periods from code and return the length as the level"""
    return code.replace('.', '')

def classify_description(description, conn, num_attempts=3, max_depth=4, recent_classifications=None):
    cursor = conn.cursor()
    full_attempts = []
    first_attempt_codes = set()  # Store ALL codes from first attempt's path
    terminal_codes = set()  # Store terminal codes that haven't reached max depth

    print(f"\nClassifying: {description}")

    # If we have recent classifications, print them for debugging
    if recent_classifications:
        print("\nRecent classifications:")
        for rc in recent_classifications:
            print(f"- {rc['description']}: {rc['code']}")

    for attempt_num in range(num_attempts):
        current_level = 1
        history = []
        attempt_path = []

        try:
            max_iterations = 10
            iteration = 0

            while iteration < max_iterations:
                iteration += 1

                parent_code = history[-1][0] if history else None
                options = get_options_for_level(cursor, current_level, parent_code)

                if not options:
                    break

                examples = get_examples_for_level(cursor, current_level, parent_code)

                # For subsequent attempts, exclude both first attempt codes and terminal codes
                excluded_options = None
                if attempt_num > 0:
                    excluded_options = first_attempt_codes.union(terminal_codes)

                prompt, option_map = create_gpt_prompt(
                    description,
                    options,
                    examples,
                    history,
                    excluded_options=excluded_options,
                    recent_classifications=recent_classifications
                )

                response = llm.invoke(prompt)
                choice = clean_gpt_response(response.content)

                if choice and choice in option_map:
                    choice_idx = option_map[choice]
                    selected_code = options[choice_idx][0]
                    selected_description = options[choice_idx][1]

                    # Store codes from first attempt's path
                    if attempt_num == 0:
                        first_attempt_codes.add(selected_code)

                    history.append((selected_code, selected_description))
                    attempt_path.append((selected_code, selected_description))

                    clean_code = clean_code_for_level(selected_code)

                    # Check if this is a terminal code and hasn't reached max depth
                    if is_terminal_code(cursor, selected_code) and len(clean_code) < max_depth:
                        terminal_codes.add(selected_code)
                        print(f"Found terminal code below max depth: {selected_code}")

                    # Stop if we've reached the max depth
                    if current_level >= max_depth:
                        break

                    current_level += 1
                else:
                    break

            if attempt_path:
                deepest = max(attempt_path, key=lambda x: len(x[0]))
                full_attempts.append(deepest)
                print(f"Attempt {attempt_num + 1}: {deepest[0]} - {deepest[1]}")
            else:
                print(f"Attempt {attempt_num + 1}: Failed")

        except Exception as e:
            print(f"Error in attempt {attempt_num + 1}: {str(e)}")
            continue

    # Replace the consistency check with a final GPT decision
    if not full_attempts:
        return "IDK", "Unable to classify"

    if len(full_attempts) == 1:
        return full_attempts[0]

    # Create a prompt for the final decision
    template = """You are a trade classification expert. Given multiple classification attempts for the same description, choose the most appropriate one:

Description to classify: {description}

Available classifications:
{formatted_options}

Choose the most appropriate classification. IMPORTANT: Respond with ONLY a single letter from A-{last_letter}.
Do not include any explanations, colons, periods, or the category description."""

    letters = list(string.ascii_uppercase)
    formatted_options = ""
    option_map = {}

    for i, (code, desc) in enumerate(full_attempts):
        letter = letters[i]
        formatted_options += f"{letter}. {code}: {desc}\n"
        option_map[letter] = i

    prompt = ChatPromptTemplate.from_template(template)
    formatted_prompt = prompt.format(
        description=description,
        formatted_options=formatted_options,
        last_letter=letters[len(full_attempts)-1]
    )

    response = llm.invoke(formatted_prompt)
    choice = clean_gpt_response(response.content)

    if choice and choice in option_map:
        choice_idx = option_map[choice]
        return full_attempts[choice_idx]

    # Fallback to first attempt if something goes wrong
    return full_attempts[0]


def process_batch(descriptions, conn, num_attempts=3, max_depth=4):
    """Process a batch of descriptions and return results"""
    results = []
    recent_classifications = []  # Store recent classifications for context
    context_window = 3  # Number of previous classifications to consider

    for idx, description in enumerate(descriptions, 1):
        print(f"\n\n==== Processing item {idx}/{len(descriptions)} ====")
        print(f"Description: {description}")

        code, desc = classify_description(
            description,
            conn,
            num_attempts,
            max_depth,
            recent_classifications
        )

        # Update recent classifications
        recent_classifications.append({
            "description": description,
            "code": code,
            "sitc_description": desc
        })
        # Keep only the most recent classifications
        if len(recent_classifications) > context_window:
            recent_classifications.pop(0)

        results.append({
            "description": description,
            "code": code,
            "sitc_description": desc
        })

    return results


if __name__ == "__main__":
    # Example usage
    description = "Almonds"
    conn = sqlite3.connect("sitc.db")

    code, desc = classify_description(description, conn, num_attempts=3, max_depth=4)
    print("\n=== FINAL RESULT ===")
    print(f"Description: {description}")
    print(f"Classification: {code}")
    print(f"Description: {desc}")
    conn.close()