import sys, os
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
from ocr import extract_ticket_data

os.environ["OCR_PROVIDER"] = "google_vision"
out_dir = Path("docs/client_research/Info provided/Images")
ticket_imgs = sorted([p for p in out_dir.glob("pdf_ticket_p*.jpg")])

print("=" * 80)
print(f"EMPIRICAL LIVE OCR TEST RESULTS ON ALL {len(ticket_imgs)} PDF TICKET IMAGES:")
print("=" * 80)

for img in ticket_imgs:
    fields, conf, provider = extract_ticket_data(img)
    t_id = fields.get("ticket_id")
    t_date = fields.get("ticket_date")
    q_name = fields.get("quarry_name")
    gross = fields.get("gross_weight")
    tare = fields.get("tare_weight")
    net = fields.get("net_weight")
    cust = fields.get("sold_to")
    
    print(f"FILE: {img.name}")
    print(f"  Provider  : {provider} (conf: {conf})")
    print(f"  Ticket #  : {t_id}")
    print(f"  Date      : {t_date}")
    print(f"  Quarry    : {q_name}")
    print(f"  Customer  : {cust}")
    print(f"  Gross     : {gross}")
    print(f"  Tare      : {tare}")
    print(f"  Net       : {net}")
    print("-" * 50)
