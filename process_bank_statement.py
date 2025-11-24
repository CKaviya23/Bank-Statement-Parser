#!/usr/bin/env python3
"""
Windows-friendly Bank Statement Parser (Gemini-friendly + local OCR fallback)

Usage:
  python process_bank_statement.py <file_path> [--test]

Put .env beside this script (no quotes) with:
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.0-flash   # optional
"""
from __future__ import annotations
import argparse, dataclasses, io, json, os, re, time, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

# Optional libs (local fallback & PDF rendering)
try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

try:
    import pytesseract
except Exception:
    pytesseract = None

# ---------------- utils & constants ----------------
CURRENCY_PATTERN = re.compile(r"[₹$€£]\s?")
NON_NUMERIC = re.compile(r"[^0-9.\-]")
DATE_GUESS = re.compile(
    r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})|(?:(\d{1,2})[-/](\d{1,2})[-/](\d{4}))"
)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}

# New: code-block JSON capture (```json ... ```)
CODE_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)

@dataclass
class Quality:
    ocr_confidence: Optional[float] = None
    page_rotation_warnings: bool = False
    missing_sections: List[str] = dataclasses.field(default_factory=list)
    duplicate_entries: bool = False
    gemini_used: bool = False
    gemini_error: Optional[str] = None
    notes: List[str] = dataclasses.field(default_factory=list)

# ---------------- helpers ----------------
def _to_float(x):
    if x is None:
        return None
    s = str(x)
    s = CURRENCY_PATTERN.sub("", s).replace(",", "")
    s = NON_NUMERIC.sub(lambda m: "" if m.group(0) in ["-", "."] else "", s)
    try:
        return float(s)
    except Exception:
        return None

def _normalize_date(s):
    if not s:
        return None
    m = DATE_GUESS.search(s)
    if not m:
        return s
    if m.group(1):
        y, mm, dd = m.group(1), m.group(2), m.group(3)
    else:
        dd, mm, y = m.group(4), m.group(5), m.group(6)
    try:
        return f"{int(y):04d}-{int(mm):02d}-{int(dd):02d}"
    except Exception:
        return s

def _mask_account(v):
    if not v:
        return v
    digits = re.findall(r"\d", str(v))
    if len(digits) < 4:
        return v
    return f"XXXX-XXXX-XXXX-{''.join(digits[-4:])}"

TXN_LINE_RE = re.compile(
    r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}).{1,120}(?P<amt>[-]?\d[\d,]*\.?\d{0,2})"
)

# ---------------- prompt helpers ----------------
_DEFAULT_EXTRACTION_PROMPT = (
    "Extract JSON only, EXACTLY with keys: Account Info, Summary Values, Transactions.\n"
    "Transactions entries must include: date (YYYY-MM-DD ideally), description, amount (number), balance (number|null), category (string|null).\n"
    "Return VALID JSON and nothing else."
)

# ---------------- local OCR helpers ----------------
def _ensure_tesseract_cmd():
    # If pytesseract available but tesseract not found, try common Windows path
    if not pytesseract:
        return
    try:
        # calling get_tesseract_version is not always available; attempt to use the command
        pytesseract.get_tesseract_version()
        return
    except Exception:
        # set common Windows default if exists
        common = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if Path(common).exists():
            pytesseract.pytesseract.tesseract_cmd = common
            try:
                pytesseract.get_tesseract_version()
                return
            except Exception:
                pass
        # fallback: we leave it as-is; caller will handle missing binary

def _image_to_text_bytes(img_bytes: bytes) -> str:
    if not pytesseract or not Image:
        raise RuntimeError("pytesseract or Pillow not installed for local OCR")
    _ensure_tesseract_cmd()
    try:
        img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise RuntimeError(f"pytesseract OCR failed: {e}")

def _extract_text_from_pdf(pdf_path: str) -> str:
    if not fitz:
        raise RuntimeError("PyMuPDF (fitz) not installed for PDF->image fallback")
    if not pytesseract or not Image:
        raise RuntimeError("pytesseract/Pillow required for PDF OCR fallback")
    _ensure_tesseract_cmd()
    doc = fitz.open(pdf_path)
    out = []
    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes(output="png")))
        out.append(pytesseract.image_to_string(img))
    return "\n".join(out)

def _local_parse_text_for_txns(text: str) -> List[Dict[str, Any]]:
    txns = []
    for m in TXN_LINE_RE.finditer(text):
        date = _normalize_date(m.group("date"))
        amt = _to_float(m.group("amt"))
        desc = m.string[m.start():m.end()]
        if date and amt is not None:
            txns.append({"date": date, "description": desc.strip(), "amount": float(amt), "balance": None, "category": None})
    return txns

# ---------------- Gemini helpers ----------------
def _pick_gemini_model_from_list():
    """If genai available, list models and choose best candidate (prefer flash/pro)."""
    if genai is None:
        return None
    try:
        models = list(genai.list_models())
        names = [getattr(m, "name", str(m)) for m in models]
        # prefer keywords
        prefs = ["flash", "pro", "vision", "2.5", "1.5", "2.0"]
        for pref in prefs:
            for n in names:
                if pref in n.lower():
                    return n
        # fallback to first model
        return names[0] if names else None
    except Exception:
        return None

def _extract_json_from_text(text: str) -> Optional[dict]:
    if not text:
        return None
    # try code block
    m = CODE_BLOCK.search(text)
    candidate = m.group(1) if m else text
    # try exact load
    try:
        return json.loads(candidate)
    except Exception:
        # try to find first { ... } block
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(candidate[start:end+1])
            except Exception:
                pass
    return None

def _try_gemini_generate_once(model_name: str, prompt_parts, gen_config=None):
    """Call model.generate_content once and return (ok, text_or_error)."""
    if genai is None:
        return False, "google-generativeai library not installed"
    try:
        model = genai.GenerativeModel(model_name)
        gen_config = gen_config or {"response_mime_type": "application/json"}
        resp = model.generate_content(prompt_parts, generation_config=gen_config)
        # try .text or traverse candidates
        txt = getattr(resp, "text", None)
        if txt:
            return True, txt
        out = []
        for cand in getattr(resp, "candidates", []) or []:
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                t = getattr(part, "text", None)
                if t:
                    out.append(t)
        return True, "\n".join(out).strip()
    except Exception as e:
        return False, str(e)

# ---------------- Main pipeline ----------------
def process_bank_statement(file_path: str, test_mode: bool = False) -> Dict[str, Any]:
    file_path = str(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    if test_mode:
        return _mock_output()

    # load .env from script folder (not cwd)
    try:
        script_dir = Path(__file__).resolve().parent
        if load_dotenv:
            load_dotenv(script_dir / ".env")
    except Exception:
        pass

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model_override = os.getenv("GEMINI_MODEL")
    quality = Quality()

    # configure genai if key present
    if api_key and genai:
        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            quality.gemini_error = f"gemini configure failed: {e}"

    # pick model
    model_name = model_override
    if not model_name and genai:
        model_name = _pick_gemini_model_from_list()
    if not model_name:
        model_name = os.getenv("GEMINI_DEFAULT_MODEL") or "gemini-2.0-flash"

    # quick info
    print(f"[Gemini] Using model: {model_name}")

    extraction_prompt = _DEFAULT_EXTRACTION_PROMPT

    extracted = None
    # Try Gemini if configured
    if api_key and genai:
        quality.gemini_used = True
        ext = Path(file_path).suffix.lower()
        gen_config = {"response_mime_type": "application/json"}
        try:
            if ext in IMG_EXTS:
                with open(file_path, "rb") as f:
                    img_bytes = f.read()
                ok, resp_text = _try_gemini_generate_once(model_name, [extraction_prompt, {"mime_type":"image/png","data":img_bytes}], gen_config)
            else:
                # try file upload (if supported)
                try:
                    uploaded = genai.upload_file(file_path)
                    ok, resp_text = _try_gemini_generate_once(model_name, [extraction_prompt, uploaded], gen_config)
                except Exception:
                    # fallback: try with prompt only (may fail for PDF)
                    ok, resp_text = _try_gemini_generate_once(model_name, [extraction_prompt], gen_config)
        except Exception as e:
            ok, resp_text = False, str(e)

        if not ok:
            quality.gemini_used = False
            quality.gemini_error = resp_text
            print(f"[Gemini] call failed: {resp_text}")
        else:
            parsed = _extract_json_from_text(resp_text)
            if parsed:
                extracted = parsed
            else:
                quality.gemini_used = False
                quality.gemini_error = f"gemini returned non-JSON or parse failed"
                # keep resp_text in notes for debugging
                quality.notes.append(("gemini_resp_preview", (resp_text[:200] + "...") if resp_text else ""))

    # Local OCR fallback
    if not extracted:
        quality.notes.append("Local OCR/heuristic parsing used.")
        all_text = ""
        suffix = Path(file_path).suffix.lower()
        try:
            if suffix in IMG_EXTS:
                if not Image or not pytesseract:
                    raise RuntimeError("Pillow or pytesseract not installed for local OCR")
                with open(file_path, "rb") as f:
                    img_bytes = f.read()
                all_text = _image_to_text_bytes(img_bytes)
            elif suffix == ".pdf":
                if fitz and pytesseract and Image:
                    all_text = _extract_text_from_pdf(file_path)
                else:
                    raise RuntimeError("PyMuPDF/Pillow/pytesseract required for PDF OCR fallback")
            else:
                try:
                    all_text = Path(file_path).read_text(encoding="utf-8")
                except Exception:
                    all_text = ""
        except Exception as ex:
            quality.notes.append(f"Local OCR error: {ex}")
            all_text = ""

        txns = _local_parse_text_for_txns(all_text)
        extracted = {"Account Info": {}, "Summary Values": {}, "Transactions": txns}

    # Postprocess
    fields = _post_process_extracted(extracted, quality)
    insights = []
    # If Gemini used earlier, try to run a separate insights prompt (if gemini still available)
    if quality.gemini_used and api_key and genai:
        try:
            insight_prompt = (
                "Given JSON below (FIELDS), return a JSON object {\"insights\": [ ... ]} with 3-8 concise bullets.\n\nFIELDS:\n"
            )
            payload = json.dumps(fields, ensure_ascii=False)
            full_prompt = insight_prompt + payload
            ok, resp_text = _try_gemini_generate_once(model_name, [full_prompt], {"response_mime_type":"application/json"})
            if ok:
                parsed = _extract_json_from_text(resp_text)
                if isinstance(parsed, dict) and "insights" in parsed:
                    insights = [str(x) for x in parsed["insights"] if isinstance(x, (str, int, float))]
                elif isinstance(parsed, list):
                    insights = [str(x) for x in parsed]
                else:
                    # fallback: split lines
                    insights = [l.strip("-• \t") for l in (resp_text or "").splitlines() if l.strip()]
        except Exception as e:
            quality.notes.append(f"Gemini insights failed: {e}")

    # If no insights from Gemini, fallback local heuristics
    if not insights:
        insights = _insights_local_fallback(fields)

    return {"fields": fields, "insights": insights[:8], "quality": dataclasses.asdict(quality)}

# ---------------- reuse & postprocess ----------------
def _coerce_extracted(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict) and "fields" in data and isinstance(data["fields"], dict):
        data = data["fields"]
    if isinstance(data, dict):
        return {
            "Account Info": data.get("Account Info") or data.get("account_info") or {},
            "Summary Values": data.get("Summary Values") or data.get("summary_values") or {},
            "Transactions": data.get("Transactions") or data.get("transactions") or [],
        }
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return {"Account Info": {}, "Summary Values": {}, "Transactions": data}
    return {"Account Info": {}, "Summary Values": {}, "Transactions": []}

def _post_process_extracted(extracted: Dict[str, Any], quality: Quality) -> Dict[str, Any]:
    extracted = _coerce_extracted(extracted)
    acct = extracted.get("Account Info") or {}
    summary = extracted.get("Summary Values") or {}
    raw_txns = extracted.get("Transactions") or []
    txns = []
    seen = set()
    dup = False
    for t in raw_txns or []:
        if not isinstance(t, dict):
            continue
        date = _normalize_date(t.get("date") or t.get("Date") or t.get("date_str"))
        desc = str(t.get("description") or t.get("Description") or "").strip()
        amt = _to_float(t.get("amount") or t.get("Amount"))
        bal = _to_float(t.get("balance") or t.get("Balance"))
        if date and desc and amt is not None:
            key = (date, desc.lower(), float(amt))
            if key in seen:
                dup = True
                continue
            seen.add(key)
            txns.append({"date": date, "description": desc, "amount": float(amt), "balance": bal, "category": t.get("category")})
    quality.duplicate_entries = dup
    try:
        txns.sort(key=lambda x: x["date"])
    except Exception:
        pass
    fields = {
        "Account Info": {
            "Bank name": acct.get("Bank name") or acct.get("bank_name"),
            "Account holder name": acct.get("Account holder name") or acct.get("account_holder_name"),
            "Account number": _mask_account(acct.get("Account number") or acct.get("account_number")),
            "Statement month": acct.get("Statement month") or acct.get("statement_month"),
            "Account type": acct.get("Account type") or acct.get("account_type"),
        },
        "Summary Values": {
            "Opening balance": _to_float(summary.get("Opening balance") or summary.get("opening_balance")),
            "Closing balance": _to_float(summary.get("Closing balance") or summary.get("closing_balance")),
            "Total credits": _to_float(summary.get("Total credits") or summary.get("total_credits")),
            "Total debits": _to_float(summary.get("Total debits") or summary.get("total_debits")),
            "Average daily balance": _to_float(summary.get("Average daily balance") or summary.get("average_daily_balance")),
        },
        "Transactions": txns,
    }
    missing = []
    if not fields["Transactions"]:
        missing.append("transactions")
    if fields["Summary Values"]["Opening balance"] is None:
        missing.append("opening_balance")
    if fields["Summary Values"]["Closing balance"] is None:
        missing.append("closing_balance")
    quality.missing_sections = missing
    return fields

def _insights_local_fallback(fields: Dict[str, Any]) -> List[str]:
    tips = []
    sv = fields.get("Summary Values", {})
    txns = fields.get("Transactions", [])
    opening = sv.get("Opening balance")
    closing = sv.get("Closing balance")
    credits = sv.get("Total credits") or 0.0
    debits = sv.get("Total debits") or 0.0
    if opening is not None and closing is not None:
        avg = round((float(opening) + float(closing)) / 2.0, 2)
        tips.append(f"Approx average balance ₹{avg:,.2f}.")
    atm_cnt = sum(1 for t in txns if "atm" in t["description"].lower())
    if atm_cnt:
        tips.append(f"ATM withdrawals: {atm_cnt}×.")
    upi_cnt = sum(1 for t in txns if "upi" in t["description"].lower())
    if upi_cnt:
        tips.append(f"UPI transactions: {upi_cnt}×.")
    if credits and debits and credits > debits:
        tips.append("Net positive inflow; consider saving/investing surplus.")
    if not tips:
        tips.append("No strong insights from parsed data.")
    return tips

def _mock_output():
    return {
        "fields": {
            "Account Info": {
                "Bank name": "HDFC Bank",
                "Account holder name": "Test User",
                "Account number": "XXXX-XXXX-XXXX-7890",
                "Statement month": "October 2025",
                "Account type": "Savings",
            },
            "Summary Values": {
                "Opening balance": 15000.0,
                "Closing balance": 17500.0,
                "Total credits": 12000.0,
                "Total debits": 9500.0,
                "Average daily balance": 16200.0,
            },
            "Transactions": [
                {"date":"2025-10-01","description":"Salary Credit","amount":25000.0,"balance":40000.0,"category":"Salary"},
                {"date":"2025-10-05","description":"ATM WITHDRAWAL","amount":-2000.0,"balance":38000.0,"category":"ATM Cash"},
            ],
        },
        "insights": ["Account maintained > ₹10,000 average balance during October."],
        "quality": {},
    }

# ---------------- CLI ----------------
def main(argv=None):
    parser = argparse.ArgumentParser(description="Bank Statement Parser (Gemini + local OCR fallback)")
    parser.add_argument("file_path", help="Path to statement (PDF or image)")
    parser.add_argument("--test", action="store_true", help="Run in test/mock mode (no network)")
    args = parser.parse_args(argv)
    try:
        out = process_bank_statement(args.file_path, test_mode=args.test)
    except Exception as e:
        print("ERROR:", e, file=sys.stderr)
        raise
    # write result next to script
    script_dir = Path(__file__).resolve().parent
    stem = Path(args.file_path).stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = script_dir / f"{stem}_parsed_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nSaved JSON -> {out_path}")

if __name__ == "__main__":
    main()
