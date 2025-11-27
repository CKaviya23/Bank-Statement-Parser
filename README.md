Bank Statement Parser (AI-Powered · Gemini 2.5 Pro Vision)

A powerful AI-driven tool that automatically extracts structured financial data and generates intelligent spending insights from bank statements (PDF or image).
Built using Google Gemini 2.5 Pro Vision, PyMuPDF, Tesseract OCR, and Python.

 Features:
1.Smart Document Understanding

2.Supports PDFs, scanned images, and photos of statements

3.Auto-detects document type

4.Handles multiple pages

🤖 AI-Powered Data Extraction

Extracts clean JSON with:

Account Info (bank name, holder, account number, type)

Summary Values (opening balance, closing balance, credits, debits)

Transactions (date, description, amount, balance, category)

🧠 Insight Generation (Using Gemini)

Detects salary patterns

Identifies spending categories

Highlights account risks (low balance, high spending)

Flags ATM withdrawals, subscriptions & financial patterns

🛡️ Privacy First

Masks account numbers (XXXX-XXXX-XXXX-1234)

No sensitive files stored

All processing happens locally + Gemini API call

 Additional Capabilities:

Offline mode (--test) – no API required

Local OCR fallback using Tesseract

Saves parsed output as JSON

Includes quality metadata, missing fields, OCR notes

📂 Project Structure
bank_statement_parser/
├── process_bank_statement.py      # Main pipeline (Gemini + OCR)
├── prompts/
│   ├── prompt_extraction.txt      # Gemini extraction instructions
│   └── prompt_insights.txt        # Insight generation instructions
├── sample_data/
│   ├── my_statement.pdf           # Example PDF
│   └── my_statement.jpg           # Example image
└── README.md

🔧 Installation
1️⃣ Clone the repository
git clone https://github.com/<your-username>/bank-statement-parser.git
cd bank-statement-parser

2️⃣ Create a virtual environment
python -m venv venv

3️⃣ Activate the environment

Windows

venv\Scripts\activate


Mac / Linux

source venv/bin/activate

4️⃣ Install dependencies
pip install google-generativeai python-dotenv Pillow PyMuPDF pytesseract

5️⃣ Install Tesseract OCR

Windows: Download installer
👉 https://github.com/UB-Mannheim/tesseract/wiki

Mac

brew install tesseract

6️⃣ Set your Gemini API key

Windows

setx GEMINI_API_KEY "your_api_key_here"


Mac/Linux

export GEMINI_API_KEY="your_api_key_here"

▶️ Usage
Parse a PDF
python process_bank_statement.py sample_data/my_statement.pdf

Parse an image
python process_bank_statement.py sample_data/my_statement.jpg

Offline test mode (no API)
python process_bank_statement.py sample_data/test.pdf --test


Output saved as:

my_statement_parsed_YYYYMMDD_HHMMSS.json

 Example Output (Shortened)
{
  "fields": {
    "Account Info": {
      "Bank name": "Standard Chartered",
      "Account holder name": "MR SEENIVASAN",
      "Account number": "XXXX-XXXX-XXXX-0422",
      "Statement month": "June-July 2019",
      "Account type": "Savings"
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
    "Net positive cash flow this period (+₹13,000).",
    "Salary credited consistently at the start of the month.",
    "Multiple ATM withdrawals detected — consider fee-free options."
  ]
}

🧩 How the Pipeline Works

Detect document type (PDF or image)

Attempt Gemini 2.5 Pro Vision extraction

Sends document securely

Gets structured JSON

If Gemini fails → Use local OCR (Tesseract)

Clean & normalize:

Dates → YYYY-MM-DD

Amounts → float

Mask sensitive info

Run insight prompt → Generate financial summary

Combine everything into final JSON output

🛠️ Tech Stack
Component	Technology
AI Model	Gemini 2.5 Pro Vision
OCR	Tesseract OCR
PDF Rendering	PyMuPDF
Language	Python
Validation	Custom parsers + regex
Output	JSON
🧪 Test Mode (No Gemini Required)

Run:

python process_bank_statement.py dummy.pdf --test


Output:

Fake transactions

Fake account data

Perfect for demos & offline use

🛡️ Quality Metadata Included

Each output includes:

❗ Missing fields

⚠️ Duplicate transaction detection

📉 OCR confidence

🔄 Page rotation warnings

🤖 Whether Gemini was used

📝 Notes from fallback OCR

📌  Compliance Summary
Requirement	Status
Gemini Vision extraction	✅ Done
Insight generation	✅ Done
Test mode	✅ Done
Mask account numbers	✅ Done
JSON output	✅ Done
PDF + Image support	✅ Done
Prompt files	✅ Done
