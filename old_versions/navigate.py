import sqlite3

def display_codes_with_examples(cursor, level, parent_code=None):
    """Display all codes at the given level with examples"""
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

    results = cursor.fetchall()
    for code, description in results:
        print(f"\n{code}: {description}")

        # Get examples for this code
        cursor.execute("""
            SELECT description
            FROM training_examples
            WHERE sitc_code = ?
            LIMIT 3
        """, (code,))

        examples = cursor.fetchall()
        if examples:
            print("Examples:")
            for i, (example,) in enumerate(examples, 1):
                print(f"  {i}. {example}")

    return results

def navigate_sitc():
    conn = sqlite3.connect("sitc.db")
    cursor = conn.cursor()

    current_level = 1
    history = []

    while True:
        print("\n" + "="*50)
        print(f"Current Level: {current_level}")
        print("="*50)

        parent_code = history[-1] if history else None
        available_codes = display_codes_with_examples(cursor, current_level, parent_code)
        available_code_list = [code for code, _ in available_codes]

        print("\nOptions:")
        print("- Enter a code to drill down")
        print("- 'b' to go back")
        print("- 'q' to quit")

        choice = input("\nEnter your choice: ").strip()

        if choice.lower() == 'q':
            break
        elif choice.lower() == 'b':
            if history:
                history.pop()
                current_level -= 1
            continue
        elif choice in available_code_list:
            history.append(choice)
            current_level += 1
            cursor.execute("""
                SELECT COUNT(*)
                FROM sitc_codes
                WHERE level = ? AND parent_code = ?
            """, (current_level, choice))
            if cursor.fetchone()[0] == 0:
                print("\nNo further subdivisions available.")
                history.pop()
                current_level -= 1
        else:
            print("\nInvalid choice. Please try again.")

    conn.close()

if __name__ == "__main__":
    navigate_sitc()