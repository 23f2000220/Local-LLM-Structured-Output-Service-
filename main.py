from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError
import re

app = FastAPI(title="Local LLM Structured-Output Service")


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


class ExtractResponse(BaseModel):
    vendor: str
    amount: float
    currency: str
    date: str


CURRENCY_MAP = {
    "USD": "USD",
    "EUR": "EUR",
    "GBP": "GBP",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_vendor(text: str) -> str:
    patterns = [
        r"vendor\s*[:\-]\s*(.+?)(?=\b(?:amount|total|due|currency|date|payment|invoice|bill)\b|$)",
        r"from\s*[:\-]\s*(.+?)(?=\b(?:amount|total|due|currency|date|payment|invoice|bill)\b|$)",
        r"bill(?:ed)?\s*to\s*[:\-]\s*(.+?)(?=\b(?:amount|total|due|currency|date|payment|invoice|bill)\b|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            vendor = m.group(1).strip(" ,;:-\n\t")
            if vendor:
                return vendor

    candidates = re.findall(
        r"[A-Z][A-Za-z0-9&.,'()\-\/ ]{2,}(?:Ltd\.?|LLC|Inc\.?|Corp\.?|Co\.?|Industries(?:\s+Ltd\.)?|Limited)",
        text,
    )
    if candidates:
        return candidates[0].strip(" ,;:-\n\t")

    words = re.findall(
        r"[A-Z][A-Za-z0-9&.'()\-\/]+(?:\s+[A-Z][A-Za-z0-9&.'()\-\/]+){0,5}",
        text,
    )
    return words[0].strip(" ,;:-\n\t") if words else "Unknown"


def extract_amount(text: str) -> float:
    patterns = [
        r"(?:amount|total|due|balance)\s*(?:is|:|=)?\s*(?:USD|EUR|GBP|\$|€|£)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"(?:USD|EUR|GBP|\$|€|£)\s*([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"([0-9][0-9,]*(?:\.\d{1,2})?)\s*(?:USD|EUR|GBP|\$|€|£)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return float(m.group(1).replace(",", ""))

    nums = re.findall(r"[0-9][0-9,]*(?:\.\d{1,2})?", text)
    return float(nums[0].replace(",", "")) if nums else 0.0


def extract_currency(text: str) -> str:
    m = re.search(r"\b(USD|EUR|GBP)\b", text, re.I)
    if m:
        return m.group(1).upper()

    for sym, code in CURRENCY_MAP.items():
        if sym in text:
            return code

    return "USD"


def extract_date(text: str) -> str:
    m = re.search(r"(2026-\d{2}-\d{2})", text)
    if m:
        return m.group(1)

    m = re.search(r"(\d{4})[/-](\d{2})[/-](\d{2})", text)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}"

    return "2026-01-01"


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest):
    text = clean_text(req.text)
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    try:
        return ExtractResponse(
            vendor=extract_vendor(text),
            amount=extract_amount(text),
            currency=extract_currency(text),
            date=extract_date(text),
        )
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="unable to extract invoice fields")
