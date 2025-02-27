import pandas as pd
from pathlib import Path
import sqlite3
from tqdm import tqdm
from classifier import process_batch
import argparse

def process_excel_file(input_path, output_path=None, batch_size=10):
    """Process an Excel file and add SITC classifications"""
    # Handle input/output paths
    input_path = Path("data") / input_path
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_classified{input_path.suffix}"

    # Read Excel file
    xl = pd.ExcelFile(input_path)
    output_dict = {}
    conn = sqlite3.connect("sitc.db")

    for sheet_name in xl.sheet_names:
        print(f"\nProcessing sheet: {sheet_name}")
        df = pd.read_excel(input_path, sheet_name=sheet_name)

        # Find description column
        desc_col = None
        for col in ['Description', 'Descriptions']:
            if col in df.columns:
                desc_col = col
                break

        if not desc_col:
            print(f"No description column found in sheet: {sheet_name}")
            continue

        # Add classification columns
        df['SITC_Code'] = ''
        df['SITC_Description'] = ''

        # Process in batches
        descriptions = df[desc_col].astype(str).tolist()
        for i in tqdm(range(0, len(descriptions), batch_size),
                     desc=f"Processing {sheet_name}",
                     unit="batch"):
            batch = descriptions[i:i + batch_size]
            results = process_batch(batch, conn)

            # Update DataFrame with results
            for j, result in enumerate(results):
                idx = i + j
                df.at[idx, 'SITC_Code'] = result['code']
                df.at[idx, 'SITC_Description'] = result['sitc_description']

        output_dict[sheet_name] = df

    conn.close()

    # Save to Excel
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in output_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path

if __name__ == "__main__":
    # Add command-line argument parsing
    parser = argparse.ArgumentParser(description='Process Excel file and add SITC classifications')
    parser.add_argument('input_file', help='Name of the Excel file to process (should be in the data folder)')
    args = parser.parse_args()

    output_file = process_excel_file(args.input_file)
    print(f"\nClassification complete. Results saved to: {output_file}")
