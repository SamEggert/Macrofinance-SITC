import pandas as pd
import sqlite3
from pathlib import Path

def determine_sitc_level(code):
    """
    Determine SITC level based on code format:
    1: single digit
    2: two digits
    3: three digits
    4: three digits + decimal + one digit
    5: three digits + decimal + two digits
    """
    code = str(code).strip()
    if '.' in code:
        base, decimal = code.split('.')
        if len(decimal) == 1:
            return 4
        return 5
    else:
        return len(code)

def create_sitc_database(xlsx_path, db_path):
    # Read the Excel file, treating the SITC code column as string
    df = pd.read_excel(xlsx_path, dtype={'SITC code': str})

    print("Column names:", df.columns.tolist())

    # Connect to SQLite database
    conn = sqlite3.connect(db_path)

    # Drop the table if it exists
    conn.execute('DROP TABLE IF EXISTS sitc_codes')

    # Create the table with composite primary key
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sitc_codes (
            code TEXT,
            clean_code TEXT,
            description TEXT,
            level INTEGER,
            parent_code TEXT,
            FOREIGN KEY (parent_code) REFERENCES sitc_codes (code),
            PRIMARY KEY (code, level)
        )
    ''')

    # Process each row
    for index, row in df.iterrows():
        # Get the original code
        original_code = str(row['SITC code']).strip()

        # Skip empty rows
        if not original_code or original_code == 'nan':
            continue

        # Store the original code format
        clean_code = original_code
        if clean_code.endswith('.0'):
            clean_code = clean_code[:-2]

        description = str(row['Description']).strip()
        level = determine_sitc_level(original_code)

        # Determine parent code based on level
        if level == 1:
            parent_code = None
        elif level == 2:
            parent_code = clean_code[0]
        elif level == 3:
            parent_code = clean_code[:2]
        elif level == 4:
            parent_code = clean_code[:3]
        elif level == 5:
            parent_code = clean_code.split('.')[0] + '.' + clean_code.split('.')[1][0]

        try:
            # Insert into database
            conn.execute('''
                INSERT INTO sitc_codes (code, clean_code, description, level, parent_code)
                VALUES (?, ?, ?, ?, ?)
            ''', (original_code, clean_code, description, level, parent_code))
        except sqlite3.IntegrityError as e:
            print(f"Error inserting: {original_code} (level {level}) with description: {description[:50]}...")
            continue

    conn.commit()
    conn.close()

# Example usage:
if __name__ == "__main__":
    create_sitc_database("SITC-classification.xlsx", "sitc.db")

    # Verify the data
    conn = sqlite3.connect("sitc.db")
    cursor = conn.cursor()

    # Check total number of entries
    cursor.execute("SELECT COUNT(*) FROM sitc_codes")
    print(f"\nTotal entries: {cursor.fetchone()[0]}")

    # Check entries at different levels
    for level in range(1, 6):
        cursor.execute("SELECT COUNT(*) FROM sitc_codes WHERE level = ?", (level,))
        count = cursor.fetchone()[0]
        print(f"Level {level} entries: {count}")

    # Show some examples from each level
    print("\nSample entries from each level:")
    for level in range(1, 6):
        cursor.execute("""
            SELECT code, description, level, parent_code
            FROM sitc_codes
            WHERE level = ?
            LIMIT 2
        """, (level,))
        print(f"\nLevel {level}:")
        for row in cursor.fetchall():
            print(row)

    conn.close()