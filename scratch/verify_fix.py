"""
Verify the Windows file lock fix by running extract_ticket_data on a fresh copy.
"""
import sys, os, shutil
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image as PilImage

# Fresh copy
src = Path("scratch/fresh_pages/fresh_p1.jpg")
test_copy = Path("scratch/verify_fix.jpg")
shutil.copy2(src, test_copy)

print(f"Original file size: {test_copy.stat().st_size}")
before = PilImage.open(test_copy)
before.load()
# Check bottom-center pixel (where NOVA header is in upside-down image)
bottom_pixel = before.getpixel((before.width // 2, before.height - 100))
top_pixel = before.getpixel((before.width // 2, 100))
print(f"BEFORE: top_pixel={top_pixel}, bottom_pixel={bottom_pixel}")
before.close()

from ocr import extract_ticket_data
fields, conf, prov = extract_ticket_data(test_copy)

print(f"\nAfter file size: {test_copy.stat().st_size}")
after = PilImage.open(test_copy)
after.load()
bottom_pixel2 = after.getpixel((after.width // 2, after.height - 100))
top_pixel2 = after.getpixel((after.width // 2, 100))
print(f"AFTER:  top_pixel={top_pixel2}, bottom_pixel={bottom_pixel2}")
after.close()

size_changed = src.stat().st_size != test_copy.stat().st_size
print(f"\nFile size changed: {size_changed} ({src.stat().st_size} -> {test_copy.stat().st_size})")

print(f"\nExtracted fields:")
for k, v in fields.items():
    if v and not k.startswith("__"):
        print(f"  {k}: {v}")
print(f"Confidence: {conf:.2f}, Provider: {prov}")
