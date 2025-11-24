🏦 Bank Statement Parser (Gemini Vision)

This project extracts structured financial data and actionable insights from bank statements (PDF or image format) using Google Gemini 2.5 Pro.

🚀 Features

✅ Supports PDFs and images (auto-detects format)
✅ Uses Gemini Vision API for data extraction
✅ Derives structured JSON:

Account Info (bank, holder, number, type)

Summary Values (opening, closing, credits, debits)

Transactions (date, description, amount, balance, category)
✅ Runs a second Gemini prompt to generate concise financial insights
✅ Post-processing: masks account numbers, normalizes amounts/dates, infers missing totals, checks balance consistency
✅ Quality metadata: missing sections, duplicates, validation notes
✅ Privacy: no sensitive source files stored; only parsed JSON output saved
✅ Offline test mode (--test) produces deterministic mock data
✅ Saves result as *_parsed_<timestamp>.json in the same folder


📂 Project Structure

bank_statement_parser/
├── process_bank_statement.py         # Main pipeline (Gemini + JSON output)
├── prompts/
│   ├── prompt_extraction.txt         # Schema and extraction instructions
│   └── prompt_insights.txt           # Financial insights generation prompt
├── sample_data/
│   ├── my_statement.pdf              # Example PDF statement
│   └── my_statement.jpg              # Example image statement
└── README.md


⚙️ Installation

1️⃣ Clone / unzip the folder
2️⃣ Create a virtual environment (recommended):
python3 -m venv venv
source venv/bin/activate  # (Mac/Linux)
venv\Scripts\activate     # (Windows)


3️⃣ Install dependencies:
pip install google-generativeai python-dotenv Pillow PyMuPDF

4️⃣ Set your Gemini API key:
export GEMINI_API_KEY="your_api_key_here"   # Mac/Linux
setx GEMINI_API_KEY "your_api_key_here"     # Windows

▶️ Usage
Process a "PDF"
python process_bank_statement.py sample_data/my_statement.pdf
Process an "image"
python process_bank_statement.py sample_data/my_statement.jpg
Test mode (no API calls)
python process_bank_statement.py sample_data/anything.pdf --test

✅ Output will be printed in the console and saved as:
my_statement_parsed_YYYYMMDD_HHMMSS.json

🧩 Prompt Files

prompt_extraction.txt - Guides Gemini to output structured JSON (schema, parsing rules, date/amount format).
prompt_insights.txt	- Guides Gemini to generate 3–8 clear, actionable insights based only on the extracted JSON.

🧠 Example Output (Shortened)
{
  "fields": {
    "Account Info": {
      "Bank name": "Standard Chartered",
      "Account holder name": "MR SEENIVASAN",
      "Account number": "XXXX-XXXX-XXXX-0422",
      "Statement month": "June-July 2019",
      "Account type": "SMART BANKING SAVINGS ACCOUNT"
    },
    "Summary Values": {
      "Opening balance": 114453.65,
      "Closing balance": 116149.46,
      "Total credits": 70986.83,
      "Total debits": 69291.02
    },
    "Transactions": [...]
  },
  "insights": [
    "Net positive cash flow this period, increasing balance by over ₹13,000.",
    "A consistent salary of ₹65,000 was received at the start of the month.",
    "Frequent ATM withdrawals observed — consider fee-free options."
  ],
  "quality": {
    "missing_sections": [],
    "duplicate_entries": false
  }
}

✅ Task-2 Compliance Summary
Requirement	Status
Gemini-based extraction (Vision + JSON)	✅ Done
Gemini insights prompt	✅ Done
Test mode	✅ Done
Privacy & masking	✅ Done
JSON output (fields + insights + quality)	✅ Done
PDF & image support	✅ Done
Prompt files (.txt)	✅ Done






