"""
End-to-end test: Call extract_ticket_data on a FRESH copy of a PDF page
and verify:
1. Does auto-orient fire?
2. Is the image rotated afterward?
3. Are the fields correct?
"""
import sys, os, shutil, logging
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"

# Enable debug logging to see auto_orient messages
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(name)s %(levelname)s %(message)s")

from pathlib import Path
from PIL import Image as PilImage

# Make a fresh copy to avoid modifying originals
src = Path("scratch/fresh_pages/fresh_p1.jpg")
test_copy = Path("scratch/test_orient_copy.jpg")
shutil.copy2(src, test_copy)

pil_before = PilImage.open(test_copy)
print(f"\nBEFORE: {test_copy.name} size={pil_before.width}x{pil_before.height}")

from ocr import extract_ticket_data
fields, conf, prov = extract_ticket_data(test_copy)

pil_after = PilImage.open(test_copy)
print(f"\nAFTER:  {test_copy.name} size={pil_after.width}x{pil_after.height}")
print(f"Image was {'ROTATED' if pil_before.size != pil_after.size else 'NOT rotated'}")
print(f"\nExtracted fields:")
for k, v in fields.items():
    if v and not k.startswith("__"):
        print(f"  {k}: {v}")
print(f"\nConfidence: {conf:.2f}, Provider: {prov}")
