import sys, os
sys.path.insert(0, ".")
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMG1 = ROOT / "docs" / "client_research" / "Info provided" / "Images" / "Ticket example 1.jpg"
IMG2 = ROOT / "docs" / "client_research" / "Info provided" / "Images" / "Ticket example 2.jpg"

# 1. Pytesseract returns real per-word confidence
from ocr import _extract_with_pytesseract
_, conf = _extract_with_pytesseract(IMG1)
print(f"Tesseract confidence (computed): {conf}")
assert conf != 0.55, "STILL HARDCODED 0.55"
assert 0.0 <= conf <= 1.0
print("PASS: real per-word confidence, not hardcoded")

# 2. No hardcoded dummy values remain in source
import ocr as _ocr
src = open(_ocr.__file__).read()
assert "0.78" not in src, "HARDCODED 0.78 REMAINS"
assert "0.55" not in src, "HARDCODED 0.55 REMAINS"
print("PASS: 0.78 and 0.55 fully removed from source")

# 3. Google Vision end-to-end
os.environ["OCR_PROVIDER"] = "google_vision"
from ocr import extract_ticket_data
fields, conf2, provider = extract_ticket_data(IMG2)
print(f"Vision: conf={conf2}, provider={provider}")
print(f"  ticket_id={fields['ticket_id']}  tare={fields['tare_weight']}  net={fields['net_weight']}")
assert provider == "google_vision"
assert fields["tare_weight"] == "9800", f"Wrong tare: {fields['tare_weight']}"
assert fields["net_weight"] == "15200", f"Wrong net: {fields['net_weight']}"
print("PASS: Vision live, weights correct")

print("\nAll checks passed.")
