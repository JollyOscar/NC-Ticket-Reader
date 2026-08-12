"""
Full verification: run extract_ticket_data on fresh copies of all 7 PDF pages
and verify each one gets rotated and produces reasonable OCR output.
"""
import sys, os, shutil
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path

scratch = Path("scratch/fresh_pages")
verify_dir = Path("scratch/verify_all")
verify_dir.mkdir(parents=True, exist_ok=True)

from ocr import extract_ticket_data

for img_path in sorted(scratch.glob("fresh_p*.jpg")):
    test_copy = verify_dir / img_path.name
    shutil.copy2(img_path, test_copy)
    
    orig_size = test_copy.stat().st_size
    fields, conf, prov = extract_ticket_data(test_copy)
    new_size = test_copy.stat().st_size
    
    rotated = "ROTATED" if orig_size != new_size else "NOT ROTATED"
    tid = fields.get("ticket_id", "")
    tdate = fields.get("ticket_date", "")
    quarry = fields.get("quarry_name", "")
    gross = fields.get("gross_weight", "")
    tare = fields.get("tare_weight", "")
    net = fields.get("net_weight", "")
    
    print(f"{img_path.name}: {rotated} | ticket={tid} date={tdate} quarry={quarry} gross={gross} tare={tare} net={net} conf={conf:.2f}")
