import os
import sqlite3
from dotenv import load_dotenv
from openai import OpenAI
import string

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def get_examples_for_level(cursor, level, parent_code=None):
    """Get training examples for a specific level/parent code"""
    if parent_code:
        cursor.execute("""
            SELECT t.description, t.sitc_code, s.description
            FROM training_examples t
            JOIN sitc_codes s ON t.sitc_code = s.code
            WHERE t.level = ? AND s.parent_code = ?
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

def get_options_for_level(cursor, level, parent_code=None):
    """Get available SITC codes for the current level"""
    if parent_code:
        cursor.execute("""
            SELECT code, description
            FROM sitc_codes
            WHERE level = ? AND parent_code = ?
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

def create_gpt_prompt(description, options, examples):
    prompt = f"""You are a trade classification expert. Your task is to classify the following description into the most appropriate SITC category:

Description to classify: {description}

Available options:
"""
    # Add lettered options (A, B, C, etc.)
    letters = list(string.ascii_uppercase)
    option_map = {}  # Store letter to option mapping

    for i, (code, desc) in enumerate(options):
        letter = letters[i]
        prompt += f"{letter}. {code}: {desc}\n"
        option_map[letter] = i

    if examples:
        prompt += "\nHere are some examples of previous classifications:\n"
        for ex_desc, ex_code, ex_sitc_desc in examples:
            prompt += f"- '{ex_desc}' was classified as {ex_code}: {ex_sitc_desc}\n"

    prompt += f"\nRespond with ONLY the letter (A-{letters[len(options)-1]}) of the most appropriate category. Do not explain your choice."

    return prompt, option_map

def classify_description():
    conn = sqlite3.connect("sitc.db")
    cursor = conn.cursor()

    current_level = 1
    history = []

    description = input("\nEnter the description to classify: ")

    while True:
        parent_code = history[-1] if history else None

        # Get available options and examples
        options = get_options_for_level(cursor, current_level, parent_code)
        examples = get_examples_for_level(cursor, current_level, parent_code)

        # Create and send prompt to GPT
        prompt, option_map = create_gpt_prompt(description, options, examples)

        # Debug: Print the current level and prompt being sent
        print("\n" + "="*50)
        print(f"Current Level: {current_level}")
        print(f"Parent Code: {parent_code}")
        print("\nPrompt being sent to GPT:")
        print("-"*50)
        print(prompt)
        print("="*50)

        try:
            completion = client.chat.completions.create(
                model="gpt-4",  # Fixed model name
                messages=[
                    {"role": "system", "content": "You are a trade classification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )

            # Debug: Print raw GPT response
            print("\nRaw GPT Response:")
            print("-"*50)
            print(f"Full message content: {completion.choices[0].message.content}")
            print("-"*50)

            choice = completion.choices[0].message.content.strip().upper()

            # Debug: Print parsed choice
            print(f"\nParsed choice: '{choice}'")

            # Convert GPT's letter choice to index using option_map
            if choice in option_map:
                choice_idx = option_map[choice]
                print(f"Converted to index: {choice_idx}")
                print(f"Number of available options: {len(options)}")

                selected_code = options[choice_idx][0]
                print(f"\nSelected: {selected_code}: {options[choice_idx][1]}")

                # Check if we can go deeper
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM sitc_codes
                    WHERE level = ? AND parent_code = ?
                """, (current_level + 1, selected_code))

                next_level_count = cursor.fetchone()[0]
                print(f"Number of subcategories at next level: {next_level_count}")

                if next_level_count > 0:
                    history.append(selected_code)
                    current_level += 1
                    print(f"Moving to level {current_level}")
                else:
                    print(f"\nFinal classification: {selected_code}")
                    break
            else:
                print(f"Invalid selection from GPT. Choice '{choice}' is not a valid option")
                break

        except Exception as e:
            print(f"Error in GPT request: {str(e)}")
            print(f"Error type: {type(e)}")
            break

    conn.close()

if __name__ == "__main__":
    classify_description()