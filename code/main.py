"""Process all PDF pages, save JSON, then review those saved files."""

import re

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import cv2
import numpy as np
import pdfplumber

from pdf2image import convert_from_path

from config import AI_data_folder, pdftest_path, poppler_path

from extraction import (
    extract_fields,
    extract_statement,
    save_extracted_data,
)

from preprocessing import grayscale, noise_removal


def prepare_scanned_page(pdf_path, page_number):
    # Render only the needed page to limit memory use.
    # Use 300 DPI to give OCR a detailed image of the text.
    images = convert_from_path(
        pdf_path,
        poppler_path=poppler_path,
        dpi=300,
        first_page=page_number,
        last_page=page_number,
    )

    if not images:
        raise ValueError(
            f"Could not render page {page_number}."
        )

    try:
        # Convert the image into the array format used by OpenCV.
        image = np.array(images[0])
    finally:
        # Release rendered images even if the conversion fails.
        for rendered_image in images:
            rendered_image.close()

    # Apply the image preparation sequence used by the OCR workflow.
    return noise_removal(
        grayscale(cv2.bitwise_not(image))
    )


def merge_page_fields(page_results, required_amount):
    # Start with the standard field structure so the merged output stays consistent.
    combined = extract_fields(
        "",
        [],
        required_amount=required_amount,
    )

    combined["dates.json"]["pages"] = []
    combined["dates.json"]["statement_periods"] = []

    for page_number, fields in page_results:
        dates = fields["dates.json"]["dates"]

        combined["dates.json"]["dates"].extend(dates)

        # Keep page references so extracted evidence can be located in the PDF.
        combined["dates.json"]["pages"].append(
            {
                "page_number": page_number,
                "dates": dates,
            }
        )

        combined["dates.json"]["statement_periods"].extend(
            {
                **period,
                "page_number": page_number,
            }
            for period in fields["dates.json"].get(
                "statement_periods",
                [],
            )
        )

        combined["balances.json"]["balances"].extend(
            {
                **balance,
                "page_number": page_number,
            }
            for balance in fields["balances.json"]["balances"]
        )

    # These fields need one combined value rather than a list of page values.
    scalar_fields = {
        "account_details.json": (
            "bank_name_clues",
            "branch_name",
            "bank_address_clues",
            "currency",
        ),
        "account_classification.json": (
            "account_type_clues",
        ),
    }

    for filename, field_names in scalar_fields.items():
        # Preserve page-level findings even when the combined value is UNCLEAR.
        combined[filename]["pages"] = [
            {
                "page_number": page_number,
                **fields[filename],
            }
            for page_number, fields in page_results
        ]

        for name in field_names:
            # Ignore missing values and remove exact duplicates across pages.
            values = list(
                dict.fromkeys(
                    fields[filename][name].strip()
                    for _, fields in page_results
                    if fields[filename][name].strip()
                    and fields[filename][name].strip().upper()
                    != "UNCLEAR"
                )
            )

            # Avoid choosing arbitrarily when pages contain different values.
            combined[filename][name] = (
                values[0]
                if len(values) == 1
                else "UNCLEAR"
            )

    for name in ("personal_clues", "business_clues"):
        # Keep distinct clues from all pages for the later account review.
        values = list(
            dict.fromkeys(
                value
                for _, fields in page_results
                for value in fields[
                    "account_classification.json"
                ][name]
                if value.strip()
                and value.strip().upper() != "UNCLEAR"
            )
        )

        combined["account_classification.json"][name] = (
            values or ["UNCLEAR"]
        )

    return combined


def extract_full_pdf(pdf_path, required_amount=44416):
    page_results = []
    pages_without_text = []
    page_methods = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        if not total_pages:
            raise ValueError("The PDF contains no pages.")

        # Use page numbers starting at 1 to match the PDF's displayed page order.
        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):
            text = page.extract_text()

            # Use existing text when available to avoid unnecessary OCR.
            if text and text.strip():
                statement = extract_statement(
                    text=text,
                    required_amount=required_amount,
                )
                method = "embedded_text"

            else:
                # Check each page separately because a PDF can mix text and scans.
                image = prepare_scanned_page(
                    pdf_path,
                    page_number,
                )

                statement = extract_statement(
                    inverted_gray_no_noise_page=image,
                    required_amount=required_amount,
                )

                method = "ocr"

                # Release the page image before processing the next page.
                del image

            # Record empty results so missing text is visible during review.
            if not statement["text"].strip():
                pages_without_text.append(page_number)

            page_results.append(
                (page_number, statement["fields"])
            )

            # Record how each page was read to help investigate extraction problems.
            page_methods.append(
                {
                    "page_number": page_number,
                    "method": method,
                }
            )

            # Only the extracted fields are needed for merging.
            del statement

    # Describe processing coverage without claiming that extraction was complete.
    context = {
        "total_pages": total_pages,
        "processed_pages": [
            number for number, _ in page_results
        ],
        "page_methods": page_methods,
        "pages_without_text": pages_without_text,
        "account_holder_check": "advisor",
        "coverage_note": (
            "Every page was attempted. Pages without extracted "
            "text may be blank or unreadable. Processing all pages "
            "does not establish complete transaction coverage "
            "or extraction accuracy."
        ),
    }

    return (
        merge_page_fields(page_results, required_amount),
        context,
    )


def save_statement_files(
    pdf_path,
    output_directory,
    required_amount=44416,
):
    fields, context = extract_full_pdf(
        pdf_path,
        required_amount,
    )

    save_extracted_data(fields, output_directory)

    # Save processing details alongside the evidence for the later review.
    save_extracted_data(
        {"review_context.json": context},
        output_directory,
    )


def process_statement(pdf_path):
    # Keep a simple extraction-only entry point using the configured output folder.
    save_statement_files(
        pdf_path,
        AI_data_folder,
    )


def create_review_directory(pdf_path):
    """Readable names; separate runs cannot overwrite each other."""

    # Remove special characters and limit length to keep folder names manageable.
    # Use a fallback if no usable characters remain.
    name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        Path(pdf_path).stem,
    ).strip("_")[:60] or "statement"

    # Use a fixed time zone so folder timestamps follow the same local convention.
    stamp = datetime.now(
        ZoneInfo("America/New_York")
    ).strftime("%Y-%m-%d_%H-%M-%S")

    root = Path(AI_data_folder)
    root.mkdir(parents=True, exist_ok=True)

    counter = 1

    while True:
        suffix = "" if counter == 1 else f"_{counter}"
        folder = root / f"{name}_{stamp}{suffix}"

        try:
            # Creating the folder directly also detects collisions between simultaneous runs.
            folder.mkdir()
            return folder

        except FileExistsError:
            # Add a number if another review already uses the same name and timestamp.
            counter += 1


def verify_statement(pdf_path, required_amount):
    # Load review dependencies only when a full verification is requested.
    from metadataExtraction import extract_metadata
    from openAI import generate_report_from_files

    fields, context = extract_full_pdf(
        pdf_path,
        required_amount,
    )

    # Keep each review's evidence separate from earlier runs.
    output_directory = create_review_directory(pdf_path)

    save_extracted_data(
        fields,
        output_directory,
    )

    save_extracted_data(
        {"review_context.json": context},
        output_directory,
    )

    metadata_path = output_directory / "pdf_analysis.json"

    try:
        extract_metadata(
            pdf_path,
            metadata_path,
        )
    except Exception:
        # Remove any partial metadata file so the report cannot use incomplete output.
        metadata_path.unlink(missing_ok=True)

    # Build the report from the saved evidence so its inputs remain available for inspection.
    return generate_report_from_files(
        output_directory,
        required_amount,
    )


# Run extraction when launched directly, but not when imported by the Flask app.
if __name__ == "__main__":
    process_statement(pdftest_path)