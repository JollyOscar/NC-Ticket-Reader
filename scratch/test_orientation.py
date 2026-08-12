import sys, os
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image
from ocr import extract_ticket_data

img_path = Path("docs/client_research/Info provided/Images/pdf_ticket_p1_Im1.jpg")
orig_img = Image.open(img_path)
print(f"Original image size: width={orig_img.width}, height={orig_img.height}")

# Test 4 rotation angles (0, 90, 180, 270)
for angle in [0, 90, 180, 270]:
    rotated = orig_img.rotate(angle, expand=True)
    temp_path = Path(f"scratch/temp_rot_{angle}.jpg")
    rotated.save(temp_path)
    fields, conf, provider = extract_ticket_data(temp_path)
    tid = fields.get("ticket_id")
    date = fields.get("ticket_date")
    quarry = fields.get("quarry_name")
    print(f"Angle {angle}°: provider={provider}, conf={conf}, ticket_id={tid}, date={date}, quarry={quarry}")
