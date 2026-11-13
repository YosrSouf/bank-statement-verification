"""Original extraction workflow, compatible with the current main.py."""

import json
import re

from datetime import date
from pathlib import Path

import pytesseract

from config import AI_data_folder
from ocr import extract_text_ordered, save_and_ocr


# Support several date formats because statements use different writing styles.
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

# Different banks use different labels for the funds shown on a statement.
BALANCE_KEYWORDS = (
    "ending balance",
    "current balance",
    "available balance",
    "available funds",
    "closing balance",
    "balance",
)

# Allow amounts with or without a currency symbol, commas, or decimal places.
AMOUNT_PATTERN = r"[$€£]?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"


def parse_transactions(text):
    transactions = []

    # These patterns expect the transaction format used by the original sample.
    date_pattern = r"\d{2}-[A-Za-z]{3}-\d{4}"
    amount_pattern = r"[\d,]+\.\d{2}"

    for line in text.split("\n"):
        dates = re.findall(date_pattern, line)
        amounts = re.findall(amount_pattern, line)

        # Require enough values to fill both date fields and both amount fields.
        if len(dates) >= 2 and len(amounts) >= 2:
            remarks = line

            # Remove dates and amounts to leave the transaction description.
            for matched_date in dates:
                remarks = remarks.replace(matched_date, "")

            for matched_amount in amounts:
                remarks = remarks.replace(matched_amount, "")

            # Assume the matched values follow the sample's column order.
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
    """Find date matches in individual cells."""

    dates = []

    for row in table_rows:
        for cell in row:
            for pattern in DATE_PATTERNS:
                # Ignore capitalization so month names such as JAN and Jan both match.
                matches = re.findall(
                    pattern,
                    cell,
                    re.IGNORECASE,
                )
                dates.extend(matches)

    return dates


def extract_balances(table_rows):
    """Find amounts in rows containing balance labels."""

    balances = []

    for row in table_rows:
        # Join cells so labels such as "closing balance" can match across words.
        row_text = " ".join(row)

        for keyword in BALANCE_KEYWORDS:
            if keyword in row_text.lower():
                amounts = re.findall(
                    AMOUNT_PATTERN,
                    row_text,
                )

                # Keep the full row so the amounts can be reviewed in context.
                balances.append(
                    {
                        "keyword": keyword,
                        "row_text": row_text,
                        "amounts": amounts,
                    }
                )

    return balances


def extract_periods(text):
    """Find explicitly labeled statement periods."""

    # A labeled period provides context that individual transaction dates may lack.
    return [
        {"period": value.strip()}
        for value in re.findall(
            r"(?im)^\s*(?:statement\s+(?:period|dates?)|period\s+covered)"
            r"\s*[:\-]?\s*([^\r\n]+)",
            text,
        )
    ]


def extract_fields(
    text,
    table_rows,
    *,
    today=None,
    required_amount=44416,
):
    """Collect extracted fields without saving files."""

    # Allow labels without a colon or a fixed position on the line.
    bank_match = re.search(
        r"(?i)\b(?:financial institution|bank|branch|bank of)"
        r"\s*:?\s*([^\r\n]+)",
        text,
    )

    # Accept several address labels because statement layouts vary.
    address_match = re.search(
        r"(?i)\b(?:bank\s+address|branch\s+address|address)"
        r"\b\s*:?\s*([^\r\n]+)",
        text,
    )

    # Use the currency label rather than guessing from symbols or bank location.
    currency_match = re.search(
        r"(?im)\bcurrency\s*:?\s*([^\r\n]+)",
        text,
    )

    # Preserve the stated account type as evidence for later review.
    account_match = re.search(
        r"(?i)\baccount\s+type\b\s*:?\s*([^\r\n]+)",
        text,
    )

    # Collect clues separately because keywords alone do not prove account ownership.
    personal_matches = re.findall(
        r"(?i)\b(personal|individual|checking|savings)\b",
        text,
    )

    business_matches = re.findall(
        r"(?i)\b(business|company|corporation|llc|inc\.?)\b",
        text,
    )

    # Keep a separate branch field because main.py expects it.
    branch_match = re.search(
        r"(?im)^\s*branch(?:\s+name)?\s*:\s*([^\r\n]+)",
        text,
    )

    # Group results by output filename for the later saving step.
    return {
        "dates.json": {
            # Allow a supplied date for repeatable checks; otherwise use today's date.
            "today's date": str(
                today if today is not None else date.today()
            ),
            "dates": extract_dates(table_rows),
            "statement_periods": extract_periods(text),
        },
        "balances.json": {
            "balances": extract_balances(table_rows),
            "required_amount_USD": required_amount,
        },
        "account_details.json": {
            # Mark missing matches as UNCLEAR instead of inventing field values.
            "bank_name_clues": (
                bank_match.group(1).strip()
                if bank_match
                else "UNCLEAR"
            ),
            "bank_address_clues": (
                address_match.group(1).strip()
                if address_match
                else "UNCLEAR"
            ),
            "currency": (
                currency_match.group(1).strip()
                if currency_match
                else "UNCLEAR"
            ),
            "branch_name": (
                branch_match.group(1).strip()
                if branch_match
                else "UNCLEAR"
            ),
            # A generic "address" label could refer to the account holder.
            # Check whether the label explicitly identifies a bank or branch address.
            "bank_address_label_confirmed": bool(
                address_match
                and re.match(
                    r"(?i)(?:bank|branch)\s+address\b",
                    address_match.group(0).lstrip(),
                )
            ),
        },
        "account_classification.json": {
            "account_type_clues": (
                account_match.group(1)
                if account_match
                else "UNCLEAR"
            ),
            "personal_clues": (
                personal_matches or ["UNCLEAR"]
            ),
            "business_clues": (
                business_matches or ["UNCLEAR"]
            ),
        },
    }


def extract_statement(
    inverted_gray_no_noise_page=None,
    text=None,
    *,
    required_amount=44416,
    benchmark=True,
):
    """Extract statement text, rows, and fields."""

    # Run OCR only when extracted text has not already been supplied.
    if text is None:
        if inverted_gray_no_noise_page is None:
            raise ValueError(
                "Provide text or a preprocessed page image."
            )

        # Request word and line information so OCR words can be grouped into rows.
        # PSM 6 tells Tesseract to treat the image as one block of text.
        data = pytesseract.image_to_data(
            inverted_gray_no_noise_page,
            output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )

        rows = {}

        for index in range(len(data["text"])):
            word = data["text"][index].strip()

            # Ignore empty OCR entries so rows contain only recognized text.
            if word:
                # Include block and paragraph numbers because line numbers can repeat.
                row_id = (
                    data["block_num"][index],
                    data["par_num"][index],
                    data["line_num"][index],
                )

                if row_id not in rows:
                    rows[row_id] = []

                rows[row_id].append(word)

        table_rows = list(rows.values())

        # Keep the original OCR route as the default for existing callers.
        if benchmark:
            text = save_and_ocr(
                "inverted_gray_no_noise",
                inverted_gray_no_noise_page,
            )
        else:
            text = extract_text_ordered(
                inverted_gray_no_noise_page,
                10,
            )

    else:
        # Give existing text the same row structure used by the OCR route.
        table_rows = [
            line.split()
            for line in text.split("\n")
            if line.strip()
        ]

    # Keep text and rows alongside the fields so extraction results can be inspected.
    return {
        "text": text,
        "table_rows": table_rows,
        "fields": extract_fields(
            text,
            table_rows,
            required_amount=required_amount,
        ),
    }


def save_extracted_data(json_files, output_directory):
    """Write the extracted dictionaries to their JSON files."""

    # Create missing folders so saving also works on the first run.
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)

    for filename, data in json_files.items():
        filepath = directory / filename

        with filepath.open(
            "w",
            encoding="utf-8",
        ) as file:
            # Make the JSON readable and preserve characters such as currency symbols.
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False,
            )


def extract_data(inverted_gray_no_noise_page=None, text=None):
    """Keep the existing combined extraction and saving function."""

    # Let existing callers extract and save through a single function.
    statement = extract_statement(
        inverted_gray_no_noise_page,
        text,
        benchmark=True,
    )

    # Show matched rows and amounts for a quick check of the extraction results.
    for balance in statement["fields"]["balances.json"]["balances"]:
        print(
            balance["row_text"],
            balance["amounts"],
        )

    save_extracted_data(
        statement["fields"],
        AI_data_folder,
    )