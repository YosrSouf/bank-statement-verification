<div align="center">Bank Statement Verification
AI-assisted document review for international admissions

Turn bank-statement data into structured findings, supporting evidence, and clear next steps for advisors.
</div>

Overview
Reviewing financial documents for international admissions involves more than reading an account balance. Advisors must check statement dates, account type, currency, bank details, and whether the available funds meet the required amount. Different document layouts and scanned PDFs make this process harder to perform consistently.

This independent-study project explores how OCR, PDF analysis, and AI can support that review. It extracts information from bank statements, organizes the evidence, and provides a structured assessment against defined requirements. The advisor makes the final decision.

Features
- PDF extraction: Read embedded text or process a scanned page with Tesseract OCR.
- Image preprocessing: Use OpenCV to prepare scanned content for extraction.
- Structured evidence: Save extracted dates, balances, account details, and account-classification clues as JSON.
- Metadata analysis: Inspect PDF properties, XMP consistency, fonts, images, annotations, syntax, and attachments.
- AI-assisted assessment: Generate schema-constrained findings with explanations and evidence through the OpenAI API.
- Advisor interface: Provide account registration, login, PDF upload, and report templates through Flask.
- Administrator controls: Approve or decline staff account requests before they can sign in.
Workflow
The intended integrated workflow combines two sources of evidence:

RE DO AND INSERT MY GRAPH

