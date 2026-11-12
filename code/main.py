import cv2
import numpy as np
import pdfplumber

from pdf2image import convert_from_path

from config import pdftest_path, poppler_path
from preprocessing import grayscale, noise_removal
from extraction import extract_data


def process_statement(pdf_path):
    """
    Process a PDF locally and save the JSON files through extract_data().

    pdf_path:
        The path to the PDF being processed.

    This function does not call the OpenAI API.
    """

    # --------------------------------------------------
    # 1. Check the first page for embedded text.
    #
    # This preserves your original first-page behavior.
    # --------------------------------------------------

    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text()

    # --------------------------------------------------
    # 2. If readable text exists, pass it to your local
    #    extraction function.
    # --------------------------------------------------

    if text and text.strip():
        extract_data(text=text)

    # --------------------------------------------------
    # 3. Otherwise, prepare the scanned page for OCR.
    # --------------------------------------------------

    else:
        # Convert the PDF pages into images using Poppler.
        pages = convert_from_path(
            pdf_path,
            poppler_path=poppler_path,
            dpi=300,
        )

        # Use the first page, as in your original code.
        page = np.array(pages[0])

        # Invert the image colors.
        inverted_page = cv2.bitwise_not(page)

        # Convert the inverted image to grayscale.
        inverted_gray_page = grayscale(inverted_page)

        # Apply your existing noise-removal function.
        inverted_gray_no_noise_page = noise_removal(
            inverted_gray_page
        )

        # Your extract_data() function performs OCR locally,
        # extracts the fields, and saves the JSON files.
        extract_data(
            inverted_gray_no_noise_page=inverted_gray_no_noise_page
        )


# Run the extraction only when main.py is executed directly.
# Importing process_statement into Flask will not run it automatically.
if __name__ == "__main__":
    process_statement(pdftest_path)