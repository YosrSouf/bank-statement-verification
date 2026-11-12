import os
import cv2
import pytesseract
import jiwer
import re

from config import ocr_data, ground_truth_path
from Evaluation import load_text, save_alignment_errors


def clean_account_number(text):
    # Fix ** misread as ° followed by " or ' (e.g. °" or °*)
    text = re.sub(r'°["\'*]', '**', text)

    return text


# Returns: A string in TSV (tab-separated values) format by default. This
# is essentially a table encoded as text, where each row contains OCR
# metadata: level (page/block/paragraph/line/word) page_num block_num
# par_num line_num word_num left, top, width, height (bounding box)
# conf (confidence score) text (recognized word)

def extract_text_ordered(img, max_space_between_words, psm=3):
    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config=f'--psm {psm}'
    )

    words = []

    ## Build a clean list of (word, left, top) tuples, skipping empty detections
    for i in range(len(data['text'])):
        word = data['text'][i].strip()

        if word:  # only add non-empty words (the same as word !="")
            word = clean_account_number(word)  
            ## Save the word and its left and top coordinates.
            words.append((word, data['left'][i], data['top'][i]))

    #Sort words by their vertical position, from top to bottom
    words.sort(key=lambda x: x[2])  # sort by top coordinate

    # Start a row with the first detected word
    rows = []
    current_row = [words[0]]  # start the first row with the first word

    # Group nearby words into rows based on their top coordinates
    for word in words[1:]:
        if abs(word[2] - current_row[-1][2]) <= max_space_between_words:
            current_row.append(word) # same row
        else:
            rows.append(current_row) # row is comlete, save it
            current_row = [word] # start a new row with that word

    rows.append(current_row) # add the last row

    # For each row, sort left-to-right, then join words into one line of text
    lines = []

    for row in rows:
        row.sort(key=lambda w: w[1])
        lines.append(" ".join(w[0] for w in row))

    # Join the lines with newline characters and return the result
    final_text = "\n".join(lines)

    return(final_text)


ground_truth = load_text(ground_truth_path)


def save_and_ocr(name, img, psm=3):
    # Create a folder for this image's files inside the OCR data folder
    folder = os.path.join(ocr_data, name)
    os.makedirs(folder, exist_ok=True)

    # save image
    img_path = os.path.join(folder, f"{name}.jpg")
    cv2.imwrite(img_path, img)

    # extract text
    text = extract_text_ordered(img, max_space_between_words=10, psm=psm)

    # path for the file that will store the OCR text
    txt_path = os.path.join(folder, f"output_{name}.txt")

    # calculate WER and CER
    wer = jiwer.wer(ground_truth, text)
    cer = jiwer.cer(ground_truth, text)

    # Write the extracted text to a file
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    # path for the file that will store the alignment error details
    errors_path = os.path.join(folder, f"alignment_errors_{name}.txt")

    #Save the OCR errors and the WER/CER results
    save_alignment_errors(ground_truth, text, errors_path, wer, cer)

    output = jiwer.process_words(ground_truth, text)

    return text  # return the extracted text for further processing or testing if needed