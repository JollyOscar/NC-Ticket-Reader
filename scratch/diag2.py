import os
os.environ["OCR_PROVIDER"] = "google_vision"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ocr import extract_ticket_data

for name in ["retest_p2.jpg", "retest_p3.jpg", "retest_p6.jpg"]:
    p = Path("scratch") / name
    fields, conf, provider = extract_ticket_data(p)
    print(f"=== {name} ===")
    for k in ["ticket_id", "ticket_date", "quarry_name", "sold_to", "trucker",
              "truck_or_plate", "deliver_to", "material_type",
              "gross_weight", "tare_weight", "net_weight", "received_by"]:
        print(f"  {k}: {fields.get(k)!r}")
    print()
