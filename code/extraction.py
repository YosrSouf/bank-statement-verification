"""Extract bank statement fields from text or OCR and save them as JSON."""

import json
import re
from datetime import date
from pathlib import Path

import pytesseract

from config import AI_data_folder
from ocr import extract_text_ordered, save_and_ocr


# Pattern order determines the order of matches within each cell.
DATE_PATTERNS = (
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    r"\b\d{1,2}/\d{1,2}/\d{2}\b",
    r"\b\d{1,2}-\d{1,2}-\d{4}\b",
    r"\b\d{1,2}-\d{1,2}-\d{2}\b",
    r"\b\d{4}/\d{1,2}/\d{1,2}\b",
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-\d{4}\b",
    r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-\d{2}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b",
    r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b",
)

BALANCE_KEYWORDS = (
    "ending balance",
    "current balance",
    "available balance",
    "available funds",
    "closing balance",
    "balance",
)

AMOUNT_PATTERN = r"[$€£]?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"


def parse_transactions(text):
    """Return transaction records for lines with at least two dates and two amounts."""
    transactions = []

    # These patterns follow the original statement's transaction format.
    date_pattern = r"\d{2}-[A-Za-z]{3}-\d{4}"
    amount_pattern = r"[\d,]+\.\d{2}"

    for line in text.split("\n"):
        dates = re.findall(date_pattern, line)
        amounts = re.findall(amount_pattern, line)

        if len(dates) >= 2 and len(amounts) >= 2:
            remarks = line

            # Remove every matched date and amount, including extra matches.
            for matched_date in dates:
                remarks = remarks.replace(matched_date, "")

            for matched_amount in amounts:
                remarks = remarks.replace(matched_amount, "")

            # The first two matches follow the original statement's column order.
            transactions.append(
                {
                    "trans_date": dates[0],
                    "value_date": dates[1],
                    "amount": amounts[0],
                    "balance": amounts[1],
                    "remarks": remarks.strip(),
                }
            )

    return transactions


def extract_dates(table_rows):
    """Return date matches from table_rows in row, cell, and pattern order."""
    dates = []

    for row in table_rows:
        for cell in row:
            for pattern in DATE_PATTERNS:
                matches = re.findall(pattern, cell, re.IGNORECASE)
                dates.extend(matches)

    return dates


def extract_balances(table_rows):
    """Return one balance record per matching keyword in each table row."""
    balances = []

    for row in table_rows:
        # Join cells so a label can span more than one cell.
        row_text = " ".join(row)
        lowercase_row = row_text.lower()
        matching_keywords = [
            keyword for keyword in BALANCE_KEYWORDS if keyword in lowercase_row
        ]
        if not matching_keywords:
            continue

        # Keep overlapping labels and give each record its own amount list.
        amounts = re.findall(AMOUNT_PATTERN, row_text)
        for keyword in matching_keywords:
            balances.append(
                {
                    "keyword": keyword,
                    "row_text": row_text,
                    "amounts": amounts.copy(),
                }
            )

    return balances


def extract_periods(text):
    """Return labeled statement periods in the order they appear in text."""
    return [
        {"period": value.strip()}
        for value in re.findall(
            r"(?im)^\s*(?:statement\s+(?:period|dates?)|period\s+covered)"
            r"\s*[:\-]?\s*([^\r\n]+)",
            text,
        )
    ]


def extract_fields(text, table_rows, *, today=None, required_amount=44416):
    """Build JSON payloads, using today's date by default and recording the required amount."""
    account_details = _extract_account_details(text)
    account_classification = _extract_account_classification(text)

    return {
        "dates.json": {
            "today's date": str(today if today is not None else date.today()),
            "dates": extract_dates(table_rows),
            "statement_periods": extract_periods(text),
        },
        "balances.json": {
            "balances": extract_balances(table_rows),
            "required_amount_USD": required_amount,
        },
        "account_details.json": account_details,
        "account_classification.json": account_classification,
    }


def _matched_value(match):
    """Return the stripped first capture or UNCLEAR when the label was absent."""
    return match.group(1).strip() if match else "UNCLEAR"


def _extract_account_details(text):
    """Return bank, address, currency, and branch clues from statement text."""
    bank_match = re.search(
        r"(?i)\b(?:financial institution|bank|branch|bank of)"
        r"\s*:?\s*([^\r\n]+)",
        text,
    )
    address_match = re.search(
        r"(?i)\b(?:bank\s+address|branch\s+address|address)"
        r"\b\s*:?\s*([^\r\n]+)",
        text,
    )
    currency_match = re.search(
        r"(?im)\bcurrency\s*:?\s*([^\r\n]+)",
        text,
    )
    branch_match = re.search(
        r"(?im)^\s*branch(?:\s+name)?\s*:\s*([^\r\n]+)",
        text,
    )

    return {
        "bank_name_clues": _matched_value(bank_match),
        "bank_address_clues": _matched_value(address_match),
        "currency": _matched_value(currency_match),
        "branch_name": _matched_value(branch_match),
        # A generic address label could refer to the account holder.
        "bank_address_label_confirmed": bool(
            address_match
            and re.match(
                r"(?i)(?:bank|branch)\s+address\b",
                address_match.group(0).lstrip(),
            )
        ),
    }


def _extract_account_classification(text):
    """Return the stated account type and personal or business clues from text."""
    account_match = re.search(
        r"(?i)\baccount\s+type\b\s*:?\s*([^\r\n]+)",
        text,
    )
    personal_matches = re.findall(
        r"(?i)\b(personal|individual|checking|savings)\b",
        text,
    )
    business_matches = re.findall(
        r"(?i)\b(business|company|corporation|llc|inc\.?)\b",
        text,
    )

    # The account-type capture retains trailing whitespace in the JSON output.
    return {
        "account_type_clues": account_match.group(1) if account_match else "UNCLEAR",
        "personal_clues": personal_matches or ["UNCLEAR"],
        "business_clues": business_matches or ["UNCLEAR"],
    }


def extract_statement(
    inverted_gray_no_noise_page=None,
    text=None,
    *,
    required_amount=44416,
    benchmark=True,
):
    """Return text, rows, and fields from supplied text or a preprocessed image.

    On image input, benchmark selects the OCR text route. The required amount
    is included in the balance payload.
    """
    # Supplied text takes precedence, including an empty string.
    if text is None:
        if inverted_gray_no_noise_page is None:
            raise ValueError("Provide text or a preprocessed page image.")

        table_rows = _extract_ocr_rows(inverted_gray_no_noise_page)

        if benchmark:
            text = save_and_ocr(
                "inverted_gray_no_noise",
                inverted_gray_no_noise_page,
            )
        else:
            text = extract_text_ordered(inverted_gray_no_noise_page, 10)
    else:
        table_rows = [
            line.split()
            for line in text.split("\n")
            if line.strip()
        ]

    return {
        "text": text,
        "table_rows": table_rows,
        "fields": extract_fields(
            text,
            table_rows,
            required_amount=required_amount,
        ),
    }


def _extract_ocr_rows(page):
    """Return nonempty OCR words grouped into rows in first-seen order."""
    # PSM 6 tells Tesseract to treat the page as a single block of text.
    data = pytesseract.image_to_data(
        page, output_type=pytesseract.Output.DICT, config="--psm 6"
    )
    rows = {}

    for index, raw_word in enumerate(data["text"]):
        word = raw_word.strip()
        if not word:
            continue

        # Line numbers can repeat across blocks and paragraphs.
        row_id = (
            data["block_num"][index],
            data["par_num"][index],
            data["line_num"][index],
        )
        rows.setdefault(row_id, []).append(word)

    return list(rows.values())


def save_extracted_data(json_files, output_directory):
    """Write each filename and payload in json_files under output_directory."""
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)

    for filename, data in json_files.items():
        filepath = directory / filename
        with filepath.open("w", encoding="utf-8") as file:
            # Preserve characters such as currency symbols in the JSON.
            json.dump(data, file, indent=4, ensure_ascii=False)


def extract_data(inverted_gray_no_noise_page=None, text=None):
    """Extract the supplied image or text, print balances, and save the fields."""
    statement = extract_statement(
        inverted_gray_no_noise_page,
        text,
        benchmark=True,
    )

    for balance in statement["fields"]["balances.json"]["balances"]:
        print(balance["row_text"], balance["amounts"])

    save_extracted_data(statement["fields"], AI_data_folder)