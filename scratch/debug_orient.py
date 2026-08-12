"""
Direct auto-orient debugging: replicate the exact auto-orient logic
with print statements to trace the failure.
"""
import sys, os, shutil
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image as PilImage
from google.cloud import vision

# Fresh copy
src = Path("scratch/fresh_pages/fresh_p1.jpg")
test_copy = Path("scratch/debug_orient.jpg")
shutil.copy2(src, test_copy)

pil_img = PilImage.open(test_copy)
w_img, h_img = pil_img.width, pil_img.height
print(f"Image: {w_img}x{h_img}")

content = test_copy.read_bytes()
client = vision.ImageAnnotatorClient()
image = vision.Image(content=content)
response = client.document_text_detection(image=image)

print(f"text_annotations count: {len(response.text_annotations)}")
print(f"Condition check: response.text_annotations={bool(response.text_annotations)}, len>1={len(response.text_annotations) > 1}")

needs_rotation = None
for anno in response.text_annotations[1:]:
    w_str = anno.description.upper()
    if w_str in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
        verts = anno.bounding_poly.vertices
        if verts:
            avg_x = sum(v.x for v in verts) / len(verts) / max(1, w_img)
            avg_y = sum(v.y for v in verts) / len(verts) / max(1, h_img)
            print(f"  Found '{w_str}' at avg_x={avg_x:.2f}, avg_y={avg_y:.2f}")
            if avg_y > 0.60:
                needs_rotation = 180
                print(f"  -> avg_y > 0.60, setting rotation to 180")
            elif avg_x > 0.65:
                needs_rotation = 270
                print(f"  -> avg_x > 0.65, setting rotation to 270")
            elif avg_x < 0.35 and avg_y > 0.35:
                needs_rotation = 90
                print(f"  -> avg_x < 0.35 and avg_y > 0.35, setting rotation to 90")
            else:
                print(f"  -> No rotation condition met")
            break
    # Also check if any iteration is happening
    
print(f"\nFinal needs_rotation: {needs_rotation}")

if needs_rotation:
    rotated_img = pil_img.rotate(needs_rotation, expand=True)
    rotated_img.convert("RGB").save(test_copy, format="JPEG")
    print(f"Rotated and saved. New size: {PilImage.open(test_copy).size}")
else:
    print("NOT rotating.")
    # Check what words were iterated
    keywords_found = []
    for anno in response.text_annotations[1:]:
        w_str = anno.description.upper()
        if w_str in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH", "SEABROOK"]:
            keywords_found.append(w_str)
    print(f"Keywords found in annotations: {keywords_found}")
