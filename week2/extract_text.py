import pdfplumber

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() + '\n'
    return text

text = extract_text_from_pdf(r"C:\Users\yosse\Desktop\School_OneDrive\OneDrive - East Tennessee State University\Fall 2026\Dr.Roach_Independent_Study\week2\Bank_Statement_Sample_3Month.pdf")
print(text )