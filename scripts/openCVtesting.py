#inverted images
import os
import cv2
import pytesseract
import numpy as np
from matplotlib import pyplot as plt # to display the image
from pdf2image import convert_from_path



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


#point pytesseract to the tesseract exe
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


#get the folder this script lives in
script_dir = os.path.dirname(os.path.abspath(__file__))  
print("script_dir: ", script_dir)

#path to poppler binaries needed by pdf2image
poppler_path = os.path.join(script_dir, "..", "poppler-26.07.0", "Library", "bin")

#getting the I-20 file
pdf_I20_path = os.path.join(script_dir, "..", "data", "I-20_image.pdf") #getting the I-20 file
print("pdf_I20: ", pdf_I20_path)

pages = convert_from_path(pdf_I20_path, poppler_path=poppler_path) #invert the I-20 PDF to images and store it in a list of pages
#raw_text = pytesseract.image_to_string(pages[0]) #extracting the text

image = np.array(pages[0])
inverted_I20 = cv2.bitwise_not(image) #invert the colors of the first page
cv2.imwrite("ocr_data/inverted_I20.jpg", inverted_I20) #save the inverted image to disk


display("ocr_data/inverted_I20.jpg") #show the saved inverted image
