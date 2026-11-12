from pydoc import text

import pytesseract
import re
import json
import os
from ocr import save_and_ocr

from datetime import date

script_dir = os.path.dirname(os.path.abspath(__file__))

def parse_transactions(text):
    # Split the whole extracted text into individual lines
    lines = text.split("\n")

    transactions = []  # to hold one dictionary per parsed transaction

    # to match dates
    date_pattern = r'\d{2}-[A-Za-z]{3}-\d{4}'

    # Matches amounts like "1,234.56" or "719.97"
    amount_pattern = r'[\d,]+\.\d{2}'

    for line in lines:
        # Find all dates and amounts present on this line
        dates = re.findall(date_pattern, line)
        amounts = re.findall(amount_pattern, line)

        # Only treat this as a transaction line if it has both dates AND both amounts
        # (matches your row format: Trans.Date, Value.Date, Debit/Credit, Balance)
        if len(dates) >= 2 and len(amounts) >= 2:
            trans_date = dates[0]  # first date = transaction date
            value_date = dates[1]  # second date = value date
            amount = amounts[0]  # first amount = debit/credit
            balance = amounts[1]  # second amount = running balance

            # Build "remarks" by removing the dates/amounts we already extracted,
            # leaving whatever text remains on the line
            remarks = line

            for d in dates:
                remarks = remarks.replace(d, "")

            for a in amounts:
                remarks = remarks.replace(a, "")

            remarks = remarks.strip()  # clean up leftover spaces

            # Save this transaction as a structured record
            transactions.append({
                "trans_date": trans_date,
                "value_date": value_date,
                "amount": amount,
                "balance": balance,
                "remarks": remarks,
            })

    return transactions  # list of all parsed transactions


def extract_data(inverted_gray_no_noise_page=None, text=None):
    if text is None:
        # Image page: extract using OCR
        data = pytesseract.image_to_data(
            inverted_gray_no_noise_page,
            output_type=pytesseract.Output.DICT,
            config="--psm 6"
        )

        # Build rows from Tesseract output
        table_rows = {}

        for i in range(len(data["text"])):
            word = data["text"][i].strip()

            if word:
                row_id = (
                    data["block_num"][i],
                    data["par_num"][i],
                    data["line_num"][i]
                )

                if row_id not in table_rows:
                    table_rows[row_id] = []

                table_rows[row_id].append(word)

        table_rows = list(table_rows.values())

        text = save_and_ocr(
            "inverted_gray_no_noise",
            inverted_gray_no_noise_page
        )

    else:
        # Text page: build rows from the existing text
        table_rows = [
            line.split()
            for line in text.split("\n")
            if line.strip()
        ]

    # print(table_rows)

    date_patterns = [
        # 07/01/2026
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",

        # 07/01/26
        r"\b\d{1,2}/\d{1,2}/\d{2}\b",

        # 07-01-2026
        r"\b\d{1,2}-\d{1,2}-\d{4}\b",

        # 07-01-26
        r"\b\d{1,2}-\d{1,2}-\d{2}\b",

        # 2026/07/01
        r"\b\d{4}/\d{1,2}/\d{1,2}\b",

        # 2026-07-01
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",

        # 01-Oct-2026
        r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-\d{4}\b",

        # 01-Oct-26
        r"\b\d{1,2}-(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*-\d{2}\b",

        # Jul 1, 2026 / July 1, 2026
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",

        # 1 Jul 2026 / 1 July 2026
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b",

        # Jul 1 / July 1
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}\b",

        # 1 Jul / 1 July
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\b",
    ]

    dates = []

    for row in table_rows:
        for cell in row:
            for pattern in date_patterns:
                matches = re.findall(pattern, cell, re.IGNORECASE)
                dates.extend(matches)



    output = {
        "table_rows": table_rows,
        "dates": dates
    }


    # BALANCE EXTRACTION

    balance_keywords = [
        "ending balance",
        "current balance",
        "available balance",
        "available funds",
        "closing balance",
        "balance"
    ]

    amount_pattern = r"[$€£]?\s?\d{1,3}(?:,\d{3})*(?:\.\d{2})?"
    balances = []
    for row in table_rows:
        row_text = " ".join(row)

        for keyword in balance_keywords:
            if keyword in row_text.lower():
                amounts = re.findall(amount_pattern, row_text)
                balances.append({
                    "keyword": keyword,
                    "row_text": row_text,
                    "amounts": amounts
                })
                print(row_text, amounts)


    # bank_info extraction
    match = re.search(r"(?i)\b(?:financial institution|bank|branch|bank of)\s*:?\s*([^\r\n]+)", text)
    bank_name = match.group(1).strip() if match else "UNCLEAR"

    #bank address extraction
    match = re.search(r"(?i)\b(?:bank\s+address|branch\s+address|address)\b\s*:?\s*([^\r\n]+)", text)
    bank_address = match.group(1).strip() if match else "UNCLEAR"

    #currency extraction
    match = re.search(r"(?im)\bcurrency\s*:?\s*([^\r\n]+)", text)
    currency = match.group(1).strip() if match else "UNCLEAR"

    # Account type
    account_type_match = re.search(r"(?i)\baccount\s+type\b\s*:?\s*([^\r\n]+)", text, re.IGNORECASE)
    account_type = account_type_match.group(1) if account_type_match else "UNCLEAR"

    # Personal clues
    personal_matches = re.findall(r"(?i)\b(personal|individual|checking|savings)\b", text)
    personal_clues = personal_matches if personal_matches else ["UNCLEAR"]

    # Business clues
    business_matches = re.findall(r"(?i)\b(business|company|corporation|llc|inc\.?)\b", text)
    business_clues = business_matches if business_matches else ["UNCLEAR"]

    # account_holder = find_clues(text, account_holder_keywords)
    # bank_name = find_clues(text, bank_name_keywords)
    # account_type = find_clues(text, account_type_keywords)
    # personal = find_clues(text, personal_clues)
    # business = find_clues(text, business_clues)


    AI_data = os.path.join(script_dir, "..", "AI_data")
    os.makedirs(AI_data, exist_ok=True)

    json_files = {
        "dates.json": {
            "today's date": str(date.today()),
            "dates": dates
        },

        "balances.json": {
            "balances": balances,
            "required_amount_USD": 44416
        },

        "account_details.json": {
            "bank_name_clues": bank_name,
            "bank_address_clues": bank_address,           
            "currency": currency
        },

        "account_classification.json": {
            "account_type_clues": account_type,
            "personal_clues": personal_clues,
            "business_clues": business_clues,
        }
    }

    for filename, data in json_files.items():
        filepath = os.path.join(AI_data, filename)

        with open(filepath, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)