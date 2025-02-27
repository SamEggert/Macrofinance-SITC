import os
import sqlite3
import logging
from dotenv import load_dotenv
from openai import OpenAI
import string
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import time
import re

# Set up logging - only file, no console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler('classification.log'),
    ]
)

# Load environment variables
load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

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


def create_gpt_prompt(description, options, examples):
    prompt = f"""You are a trade classification expert. Your task is to classify the following Spanish description into the most appropriate SITC category:

Description to classify: {description}

Available options:
"""
    letters = list(string.ascii_uppercase)
    option_map = {}

    for i, (code, desc) in enumerate(options):
        if i >= len(letters):
            break
        letter = letters[i]
        prompt += f"{letter}. {code}: {desc}\n"
        option_map[letter] = i

    if examples:
        prompt += "\nHere are some examples of previous classifications:\n"
        for ex_desc, ex_code, ex_sitc_desc in examples:
            prompt += f"- '{ex_desc}' was classified as {ex_code}: {ex_sitc_desc}\n"

    prompt += f"""\nIMPORTANT: Respond with ONLY a single letter from A-{letters[len(options)-1]}.
Do not include any explanations, colons, periods, or the category description.
For example, respond with just 'A' or 'B', not 'A.' or 'B: category name'."""

    logging.info(f"Description: {description}\n{prompt}\nValid options: {list(option_map.keys())}")

    return prompt, option_map


def clean_gpt_response(response):
    """Clean GPT response to get only the letter"""
    # Extract only alphabetic characters and convert to uppercase
    cleaned = re.sub(r'[^A-Za-z]', '', response).upper()
    return cleaned

def classify_single_description(description, conn):
    """Classify a single description and return the final code and its description"""
    cursor = conn.cursor()
    current_level = 1
    history = []
    final_code = None
    final_description = None

    while True:
        parent_code = history[-1] if history else None
        options = get_options_for_level(cursor, current_level, parent_code)
        examples = get_examples_for_level(cursor, current_level, parent_code)
        prompt, option_map = create_gpt_prompt(description, options, examples)

        try:
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a trade classification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0
            )

            raw_choice = completion.choices[0].message.content.strip()
            choice = clean_gpt_response(raw_choice)
            logging.info(f"GPT raw response: {raw_choice}, cleaned: {choice}")

            if choice in option_map:
                choice_idx = option_map[choice]
                selected_code = options[choice_idx][0]
                selected_description = options[choice_idx][1]

                final_code = selected_code
                final_description = selected_description

                cursor.execute("""
                    SELECT COUNT(*)
                    FROM sitc_codes
                    WHERE level = ? AND parent_code = ?
                """, (current_level + 1, selected_code))

                if cursor.fetchone()[0] > 0:
                    history.append(selected_code)
                    current_level += 1
                else:
                    break
            else:
                logging.info(f"Invalid choice '{choice}' for options {list(option_map.keys())}")
                break

        except Exception as e:
            logging.info(f"Error: {str(e)}")
            break

    return final_code, final_description

def process_excel_file(input_path, output_path=None):
    """Process an Excel file and add SITC classifications"""
    if output_path is None:
        p = Path(input_path)
        output_path = p.parent / f"{p.stem}_classified{p.suffix}"

    xl = pd.ExcelFile(input_path)
    output_dict = {}
    conn = sqlite3.connect("sitc.db")

    for sheet_name in xl.sheet_names:
        print(f"\nProcessing sheet: {sheet_name}")
        df = pd.read_excel(input_path, sheet_name=sheet_name)

        desc_col = None
        for col in ['Description', 'Descriptions']:
            if col in df.columns:
                desc_col = col
                break

        if not desc_col:
            continue

        df['SITC_Code'] = ''
        df['SITC_Description'] = ''

        for idx, row in tqdm(df.iterrows(),
                           total=len(df),
                           desc=f"Processing {sheet_name}",
                           unit="rows"):
            description = str(row[desc_col])
            code, desc = classify_single_description(description, conn)
            if code and desc:
                df.at[idx, 'SITC_Code'] = code
                df.at[idx, 'SITC_Description'] = desc

        output_dict[sheet_name] = df

    conn.close()

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in output_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path

if __name__ == "__main__":
    input_path = 'test 250212.xlsx'
    process_excel_file(input_path)