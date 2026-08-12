import sys, os
sys.path.insert(0, ".")
from pathlib import Path
from ocr import extract_ticket_data

os.environ["OCR_PROVIDER"] = "google_vision"
out_dir = Path("data/uploads")
ticket_imgs = sorted([p for p in out_dir.glob("pdf_ticket_p*.jpg")])

with open("scratch/results_utf8.txt", "w", encoding="utf-8") as out:
    for img in ticket_imgs:
        fields, conf, provider = extract_ticket_data(img)
        raw_text = fields.get("__raw_text", "")
        out.write("=" * 70 + "\n")
        out.write(f"FILE: {img.name} | provider={provider} | conf={conf}\n")
        out.write(f"  Ticket No : {fields.get('ticket_id')}\n")
        out.write(f"  Date      : {fields.get('ticket_date')}\n")
        out.write(f"  Job No    : {fields.get('job_no')}\n")
        out.write(f"  Quarry    : {fields.get('quarry_name')}\n")
        out.write(f"  Customer  : {fields.get('sold_to')}\n")
        out.write(f"  Deliver To: {fields.get('deliver_to')}\n")
        out.write(f"  Material  : {fields.get('material_type')}\n")
        out.write(f"  Gross     : {fields.get('gross_weight')}\n")
        out.write(f"  Tare      : {fields.get('tare_weight')}\n")
        out.write(f"  Net       : {fields.get('net_weight')}\n")
        out.write(f"  Trucker   : {fields.get('trucker')}\n")
        out.write(f"  Plate     : {fields.get('truck_or_plate')}\n")
        out.write(f"  Recv By   : {fields.get('received_by')}\n")
        out.write(f"\n  --- RAW TEXT ---\n")
        out.write(raw_text + "\n\n")

print("Done writing results_utf8.txt")
