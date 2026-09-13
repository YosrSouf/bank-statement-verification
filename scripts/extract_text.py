import pdfplumber

def extract_text_from_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() + '\n'
    return text

#text = extract_text_from_pdf(r"C:\Users\yosse\Desktop\School_OneDrive\OneDrive - East Tennessee State University\Fall 2026\Dr.Roach_Independent_Study\data\Bank_Statement_Sample_3Month.pdf")
#text = extract_text_from_pdf(r"C:\Users\yosse\Desktop\School_OneDrive\OneDrive - East Tennessee State University\Fall 2026\Dr.Roach_Independent_Study\data\bank statement (15)_Redacted.pdf")
#text = extract_text_from_pdf(r"C:\Users\yosse\Desktop\School_OneDrive\OneDrive - East Tennessee State University\Fall 2026\Dr.Roach_Independent_Study\data\Sponsor's Statement of Bank Account - Adekola Adeshola_Redacted.pdf")

print(text)