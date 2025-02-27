import pandas as pd
import sqlite3

def add_training_data(xlsx_path, db_path):
    # Read the training data and print raw info
    print(f"\nReading Excel file: {xlsx_path}")
    df = pd.read_excel(xlsx_path, dtype={
        'Description': str,
        'SITC code': str
    })

    print("\nFirst few rows of raw data:")
    print(df.head().to_string())

    print("\nData types of columns:")
    print(df.dtypes)

    print("Column names:", df.columns.tolist())

    # Connect to existing database
    conn = sqlite3.connect(db_path)

    # Drop existing table if it exists
    conn.execute('DROP TABLE IF EXISTS training_examples')

    # Create new table for training examples
    conn.execute('''
        CREATE TABLE IF NOT EXISTS training_examples (
            description TEXT,
            sitc_code TEXT,
            level INTEGER,
            FOREIGN KEY (sitc_code) REFERENCES sitc_codes (code)
        )
    ''')

    # Process each row with more debugging
    for index, row in df.iterrows():
        raw_description = row['Description']
        description = str(row['Description']).strip()
        code = str(row['SITC code']).strip()

        if description in ['.', ''] or description.isspace():
            print(f"\nPotential issue found:")
            print(f"Raw description: '{raw_description}'")
            print(f"Processed description: '{description}'")
            print(f"Type of raw description: {type(raw_description)}")
            print(f"For code: {code}")
            continue

        # Determine the level based on the code format
        if '.' in code:
            base, decimal = code.split('.')
            if len(decimal) == 1:
                level = 4
            else:
                level = 5
        else:
            level = len(code)

        try:
            conn.execute('''
                INSERT INTO training_examples (description, sitc_code, level)
                VALUES (?, ?, ?)
            ''', (description, code, level))
        except sqlite3.IntegrityError as e:
            print(f"Error inserting training example: {code} - {description[:50]}...")
            continue

    conn.commit()

    # Verify the data
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM training_examples")
    total = cursor.fetchone()[0]
    print(f"\nTotal training examples added: {total}")

    # Show some examples from each level
    for level in range(1, 6):
        cursor.execute("""
            SELECT sitc_code, description
            FROM training_examples
            WHERE level = ?
            LIMIT 2
        """, (level,))
        results = cursor.fetchall()
        if results:
            print(f"\nLevel {level} examples:")
            for code, desc in results:
                print(f"{code}: {desc}")

    conn.close()

if __name__ == "__main__":
    add_training_data("Training.xlsx", "sitc.db")