import sys, os
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image
from ocr import extract_ticket_data

img_path = Path("docs/client_research/Info provided/Images/pdf_ticket_p1_Im1.jpg")
orig_img = Image.open(img_path)
print(f"Original image size: width={orig_img.width}, height={orig_img.height}")

# Rotate 90 degrees clockwise
rot_90 = orig_img.rotate(90, expand=True)
temp_path = Path("scratch/temp_rot_90.jpg")
rot_90.save(temp_path)

fields, conf, provider = extract_ticket_data(temp_path)
print(f"90° Clockwise Rotation Test:")
print(f"  Provider  : {provider} (conf: {conf})")
print(f"  Ticket #  : {fields.get('ticket_id')}")
print(f"  Date      : {fields.get('ticket_date')}")
print(f"  Quarry    : {fields.get('quarry_name')}")
print(f"  Customer  : {fields.get('sold_to')}")
print(f"  Gross     : {fields.get('gross_weight')}")
print(f"  Tare      : {fields.get('tare_weight')}")
print(f"  Net       : {fields.get('net_weight')}")
