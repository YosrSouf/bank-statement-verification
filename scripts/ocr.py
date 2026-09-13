import os
import pytesseract
from pdf2image import convert_from_path #takes a PDF file path and returns a list of images (one per page).


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe" #point pytesseract to the tesseract exe



script_dir = os.path.dirname(os.path.abspath(__file__)) #get the folder this script lives in
print  ("script_dir: ", script_dir)

poppler_path = os.path.join(script_dir, "..", "poppler-26.07.0", "Library", "bin") #path to poppler binaries needed by pdf2image
print  ("poppler_path: ", poppler_path)


#pdftest_path = os.path.join(script_dir, "..", "data", "bank statement (15)_Redacted.pdf")
pdftest_path = os.path.join(script_dir, "..", "data", "I-20_image.pdf")

pages = convert_from_path(pdftest_path, poppler_path=poppler_path) #convert the PDF into a list of page images

raw_text = pytesseract.image_to_string(pages[0])
print(raw_text)

output_path = os.path.join(script_dir, "..", "ocr_data") #ocr_data is the folder where the output will be saved
# print("output_path: ", output_path)
os.makedirs(output_path, exist_ok=True) #make sure the folder exists

output_file_path = os.path.join(output_path, "output.txt")

# write the ocr output in a file and save it in the ocr_data folder
with open(output_file_path, "w", encoding="utf-8") as f:
    f.write(raw_text)