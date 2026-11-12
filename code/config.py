import os
import pytesseract
from pathlib import Path

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe" # point pytesseract to the tesseract exe


# GETTING THE PATHS
#############################################################################################

# get the folder this script lives in
script_dir = os.path.dirname(os.path.abspath(__file__))

# path to poppler binaries needed by pdf2image
poppler_path = os.path.join(
    script_dir, "..", "poppler-26.07.0", "Library", "bin"
)

# get the path to the pdf file to be processed
pdftest_path = os.path.join(
    script_dir, "..", "data", "scanned_bank_st_4.pdf"
)

# pdftest_path = os.path.join(
#     script_dir, "..", "data", "scanned_bank_st_2.pdf"
# )

# pdftest_path = os.path.join(
#     script_dir, "..", "data", "scanned_bank_st_3.pdf"
# )

## path to the folder where the AI data is be stored
AI_data_folder = os.path.join(
    script_dir, "..", "AI_data"
)
#AI_data_folder_path = Path(r"C:\Users\yosse\Desktop\School_OneDrive\OneDrive - East Tennessee State University\Fall 2026\Dr.Roach_Independent_Study\AI_data")


# ocr_data is the folder where the output will be saved
ocr_data = os.path.join(script_dir, "..", "ocr_data")

os.makedirs(ocr_data, exist_ok=True) # make sure the folder exists

# ground truth path
ground_truth_path = os.path.join(
    script_dir, "..", "data", "writtenPage.txt"
)

#############################################################################################