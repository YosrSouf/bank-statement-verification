import os
import cv2
import pytesseract
import numpy as np
from matplotlib import image, pyplot as plt # to display the image
from pdf2image import convert_from_path #takes a PDF file path and returns a list of images (one per page).


pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe" #point pytesseract to the tesseract exe

###################################################
#function to display the image
def display(im_path):
    dpi = 80
    im_data = plt.imread(im_path)

    height, width  = im_data.shape[:2]
    
    # What size does the figure need to be in inches to fit the image?
    figsize = width / float(dpi), height / float(dpi)

    # Create a figure of the right size with one axes that takes up the full figure
    fig = plt.figure(figsize=figsize)
    ax = fig.add_axes([0, 0, 1, 1])

    # Hide spines, ticks, etc.
    ax.axis('off')

    # Display the image.
    ax.imshow(im_data, cmap='gray')

    plt.show()
###################################################

#GETTING THE PATHS
#############################################################################################
#get the folder this script lives in
script_dir = os.path.dirname(os.path.abspath(__file__))
#path to poppler binaries needed by pdf2image
poppler_path = os.path.join(script_dir, "..", "poppler-26.07.0", "Library", "bin")
#get the path to the pdf file to be processed
pdftest_path = os.path.join(script_dir, "..", "data", "bank statement (15)_Redacted.pdf")
#ocr_data is the folder where the output will be saved
ocr_data = os.path.join(script_dir, "..", "ocr_data")
os.makedirs(ocr_data, exist_ok=True) #make sure the folder exists
#############################################################################################

#convert the PDF into a list of pages
pages = convert_from_path(pdftest_path, poppler_path=poppler_path) 
#getting the inverted image of the first page of the pdf
page = np.array(pages[1])


# FUNCTIONS FOR IMAGE PREPROCESSING
def grayscale(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def noise_removal(img):
    kernel = np.ones((2, 2), np.uint8)
    img = cv2.dilate(img, kernel, iterations=1)
    img = cv2.erode(img, kernel, iterations=1)
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel)
    img = cv2.medianBlur(img, 3)
    return img

# IMAGE PREPROCESSING
inverted_page = cv2.bitwise_not(page)
gray_page = grayscale(page)
no_noise_page = noise_removal(page)
inverted_gray_page = grayscale(inverted_page)
inverted_no_noise_page = noise_removal(inverted_page)
gray_no_noise_page = noise_removal(gray_page)
inverted_gray_no_noise_page = noise_removal(inverted_gray_page)


def save_and_ocr(name, img):
    img_path = os.path.join(ocr_data, f"{name}.jpg")
    cv2.imwrite(img_path, img)

    text = pytesseract.image_to_string(img)
    txt_path = os.path.join(ocr_data, f"output_{name}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"--- {name} ({len(text)} chars) ---")

save_and_ocr("raw", page)
save_and_ocr("inverted", inverted_page)
save_and_ocr("gray", gray_page)
save_and_ocr("no_noise", no_noise_page)
save_and_ocr("inverted_gray", inverted_gray_page)
save_and_ocr("inverted_no_noise", inverted_no_noise_page)
save_and_ocr("gray_no_noise", gray_no_noise_page)
save_and_ocr("inverted_gray_no_noise", inverted_gray_no_noise_page)