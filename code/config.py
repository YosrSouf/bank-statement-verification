"""Paths and external-program configuration shared by the scripts."""

import os
from pathlib import Path

import pytesseract

# Find folders relative to this file, so paths still work if you move the project.
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PROJECT_DIRECTORY = SCRIPT_DIRECTORY.parent

# Keep these names and strings because other scripts already use them.
script_dir = str(SCRIPT_DIRECTORY)
pdftest_path = str(PROJECT_DIRECTORY / "data" / "scanned_bank_st_4.pdf")
AI_data_folder = str(PROJECT_DIRECTORY / "AI_data")
ocr_data = str(PROJECT_DIRECTORY / "ocr_data")
ground_truth_path = str(PROJECT_DIRECTORY / "data" / "writtenPage.txt")

bundled_poppler = PROJECT_DIRECTORY / "poppler-26.07.0" / "Library" / "bin"

# Use the Poppler location saved on computer's settings, if provided.
# Otherwise, use the copy inside the project if that folder exists.
poppler_path = os.getenv("POPPLER_PATH") or (
    str(bundled_poppler) if bundled_poppler.is_dir() else None
)

windows_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

# Check whether a custom Tesseract location is saved on computer's settings.
tesseract_command = os.getenv("TESSERACT_CMD")

if tesseract_command:
    # Tell pytesseract to use your custom location.
    pytesseract.pytesseract.tesseract_cmd = tesseract_command
elif windows_tesseract.is_file():
    # If no custom location was given, use the usual Windows location if it exists.
    pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)

# If neither location is available, leave pytesseract's default setting unchanged.