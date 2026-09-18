import os
import pikepdf

script_dir = os.path.dirname(os.path.abspath(__file__))
#pdftest_path = os.path.join(script_dir, "..", "data", "bank statement (15)_Redacted.pdf")
pdftest_path = os.path.join(script_dir, "..", "data", "Bank_Statement_Sample_3Month.pdf")
#pdftest_path = os.path.join(script_dir, "..", "data", "I-20_image.pdf")

pdf = pikepdf.open(pdftest_path) #openeing the pdf file using 

# 1. Info dictionary (CreationDate, ModDate, Producer, Creator, Author, etc.)
doc_metadata = pdf.docinfo
for key, value in doc_metadata.items():
    print(key, ":", value)


page_num = 0
for page in pdf.pages:
    # page["/Resources"] the page's Resources dictionary
     # ["/Font"]  the fonts section of Resources
    fonts = page["/Resources"]["/Font"] #dictionary of font objects used on the page (key: font label, value: font object)
    for font_name in fonts.keys():
        font_obj = fonts[font_name]
        base_font = font_obj["/BaseFont"]
        print(f"Page {page_num}: {font_name} -> {base_font}")
    page_num += 1