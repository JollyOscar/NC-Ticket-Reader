"""
Focused test: check exact coordinates of NOVA/QUARRY words from Google Vision
on a FRESH PDF page to understand the coordinate space mismatch.
"""
import sys, os
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image as PilImage
from google.cloud import vision

img_path = Path("scratch/fresh_pages/fresh_p1.jpg")
pil = PilImage.open(img_path)
print(f"PIL reports: {pil.width}x{pil.height} (width x height)")
print(f"PIL mode: {pil.mode}")
print(f"File size: {img_path.stat().st_size} bytes")

content = img_path.read_bytes()
client = vision.ImageAnnotatorClient()
g_img = vision.Image(content=content)
response = client.document_text_detection(image=g_img)

# Check full_text_annotation page dimensions
if response.full_text_annotation and response.full_text_annotation.pages:
    page = response.full_text_annotation.pages[0]
    print(f"\nVision page dimensions: {page.width}x{page.height}")
    if page.property:
        print(f"Page property: {page.property}")

# Find NOVA, QUARRY, SEABROOK keywords and report positions
print("\nKeyword bounding boxes:")
for anno in response.text_annotations[1:]:
    word = anno.description.upper()
    if word in ["NOVA", "CONSTRUCTION", "QUARRY", "SEABROOK", "ANTIGONISH"]:
        verts = anno.bounding_poly.vertices
        xs = [v.x for v in verts]
        ys = [v.y for v in verts]
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        norm_x = avg_x / pil.width
        norm_y = avg_y / pil.height
        print(f"  {word}: raw=({avg_x:.0f},{avg_y:.0f}) normalized_by_PIL=({norm_x:.2f},{norm_y:.2f}) verts={[(v.x,v.y) for v in verts]}")
