import sys
sys.path.insert(0, "scripts/radio_monitoring")
from compliance_report import generate_pdf_report, generate_excel_report

pdf_path = generate_pdf_report()
print("PDF genere:", pdf_path)

xlsx_path = generate_excel_report()
print("Excel genere:", xlsx_path)
