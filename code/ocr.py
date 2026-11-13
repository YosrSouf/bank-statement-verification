"""OCR text extraction, with an explicit benchmark-writing helper."""

import re
from pathlib import Path

import cv2
import pytesseract

from config import ground_truth_path, ocr_data


def clean_account_number(text):
    # Replace specific OCR character combinations with the expected masking symbols.
    return re.sub(r'°["\'*]', "**", text)


def extract_table_rows(img, psm=6):
    """Group detected words using Tesseract's block/paragraph/line IDs."""

    # Request word positions and line information instead of plain text.
    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config=f"--psm {psm}",
    )

    rows = {}

    for index, detected_text in enumerate(data["text"]):
        word = detected_text.strip()

        # Skip empty entries so they do not create empty words or rows.
        if word:
            # Line numbers can repeat, so include block and paragraph IDs.
            row_id = tuple(
                data[key][index]
                for key in ("block_num", "par_num", "line_num")
            )

            # Create each row when its first word appears.
            rows.setdefault(row_id, []).append(word)

    return list(rows.values())


def extract_text_ordered(img, max_space_between_words, psm=3):
    """Preserve the original coordinate-based grouping and word cleanup."""

    # Coordinates allow words to be reordered according to their page positions.
    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config=f"--psm {psm}",
    )

    # Keep only recognized words and the coordinates needed to arrange them.
    words = [
        (
            clean_account_number(word.strip()),
            data["left"][index],
            data["top"][index],
        )
        for index, word in enumerate(data["text"])
        if word.strip()
    ]

    # Avoid accessing the first word when OCR found no text.
    if not words:
        return ""

    # Process words from top to bottom before grouping them into rows.
    words.sort(key=lambda word: word[2])

    rows = []
    current_row = [words[0]]

    for word in words[1:]:
        # Allow small vertical differences between words on the same printed line.
        # Despite its name, this setting controls vertical distance, not horizontal spacing.
        if abs(word[2] - current_row[-1][2]) <= max_space_between_words:
            current_row.append(word)
        else:
            rows.append(current_row)
            current_row = [word]

    # The final row has no following word to trigger its addition inside the loop.
    rows.append(current_row)

    # Arrange each row left to right, then separate rows with line breaks.
    return "\n".join(
        " ".join(
            word[0]
            for word in sorted(row, key=lambda word: word[1])
        )
        for row in rows
    )


def save_and_ocr(name, img, psm=3):
    """Keep the original image/text/accuracy artifacts for OCR experiments."""

    # Load evaluation dependencies only when benchmarking is requested.
    import jiwer

    from Evaluation import load_text, save_alignment_errors

    # Compare OCR output with reference text to measure recognition errors.
    ground_truth = load_text(ground_truth_path)

    # Group each named experiment's image, text, and error report together.
    folder = Path(ocr_data) / name
    folder.mkdir(parents=True, exist_ok=True)

    image_path = folder / f"{name}.jpg"

    # Stop if saving fails so the experiment does not silently lose its image.
    if not cv2.imwrite(str(image_path), img):
        raise OSError(f"Could not write OCR image: {image_path}")

    text = extract_text_ordered(
        img,
        max_space_between_words=10,
        psm=psm,
    )

    # Save recognized text so the result can be inspected without rerunning OCR.
    (folder / f"output_{name}.txt").write_text(
        text,
        encoding="utf-8",
    )

    # Record both word and character error rates to show errors at different levels.
    save_alignment_errors(
        ground_truth,
        text,
        folder / f"alignment_errors_{name}.txt",
        jiwer.wer(ground_truth, text),
        jiwer.cer(ground_truth, text),
    )

    return text