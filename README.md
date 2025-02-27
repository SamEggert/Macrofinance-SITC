# Macrofinance-SITC

A tool for classifying trade descriptions into Standard International Trade Classification (SITC) categories using OpenAI's language models.

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create a `.env` file with your OpenAI API key: `OPENAI_API_KEY=your_key_here`
4. Prepare the SITC database:
   * Place SITC-classification.xlsx in the project root
   * Run `python old_versions/convert.py` to create the database
   * Optional: Add training examples with `python old_versions/convert_training.py`

## Usage

### Classify Excel Files

Place your Excel file in the `data` directory and run:

```
python3 xlsx_classifier.py "your_file.xlsx"
```

The script will process each sheet, looking for a "Description" column, and add "SITC_Code" and "SITC_Description" columns to the output file.

### Custom Classification

```python
import sqlite3
from classifier import classify_description

conn = sqlite3.connect("sitc.db")
description = "Your product description here"
code, desc = classify_description(description, conn)
print(f"Classification: {code} - {desc}")
conn.close()
```

## Project Structure

```
Macrofinance-SITC
├── classifier.py         # Core classification logic
├── xlsx_classifier.py    # Excel batch processing
├── sitc.db               # SQLite database of SITC codes
└── old_versions/         # Previous implementations
```

## Parameters

* `num_attempts`: Classification attempts to make (default: 3)
* `max_depth`: Maximum SITC level to classify to (default: 5)
* `batch_size`: Descriptions to process at once (default: 10)
