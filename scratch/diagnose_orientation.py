"""
Re-extract FRESH page images from the PDF and analyze their actual text orientation
using Google Vision bounding polygon geometry.
"""
import sys, os, math
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image
from google.cloud import vision
import pypdf

# 1. Re-extract FRESH images from original PDF
pdf_path = Path("docs/client_research/Info provided/Images/20260717102354642.pdf")
scratch = Path("scratch/fresh_pages")
scratch.mkdir(parents=True, exist_ok=True)

reader = pypdf.PdfReader(pdf_path)
fresh_imgs = []
for i, page in enumerate(reader.pages):
    for j, img in enumerate(page.images):
        name = f"fresh_p{i+1}.jpg"
        p = scratch / name
        p.write_bytes(img.data)
        fresh_imgs.append(p)

print(f"Extracted {len(fresh_imgs)} fresh images from PDF\n")

# 2. For each fresh image, analyze the text orientation from Vision bounding polygon
client = vision.ImageAnnotatorClient()

for img_path in fresh_imgs:
    pil = Image.open(img_path)
    print(f"=== {img_path.name} ({pil.width}x{pil.height}) ===")
    
    content = img_path.read_bytes()
    g_img = vision.Image(content=content)
    response = client.document_text_detection(image=g_img)
    
    if not response.text_annotations:
        print("  No text detected\n")
        continue
    
    # The first annotation is the full text block. Its bounding_poly vertices
    # go in reading order: v0=top-left, v1=top-right, v2=bottom-right, v3=bottom-left
    # of the TEXT (not the image). The direction from v0 to v1 reveals the text rotation.
    verts = response.text_annotations[0].bounding_poly.vertices
    dx = verts[1].x - verts[0].x
    dy = verts[1].y - verts[0].y
    angle = math.degrees(math.atan2(dy, dx))
    
    print(f"  Full text bounding poly vertices:")
    for k, v in enumerate(verts):
        print(f"    v{k}: ({v.x}, {v.y})")
    print(f"  Text top-edge vector: dx={dx}, dy={dy}")
    print(f"  Text orientation angle: {angle:.1f}°")
    
    # Determine needed rotation
    if -45 < angle < 45:
        fix = None
        print(f"  -> Text is UPRIGHT, no rotation needed")
    elif 45 <= angle < 135:
        fix = 90  # text is 90° CW, rotate image 90° CCW to fix
        print(f"  -> Text is 90° CW, need rotate(90) CCW to fix")
    elif angle >= 135 or angle <= -135:
        fix = 180
        print(f"  -> Text is UPSIDE DOWN, need rotate(180) to fix")
    else:  # -135 < angle <= -45
        fix = 270  # text is 90° CCW, rotate image 90° CW to fix
        print(f"  -> Text is 90° CCW, need rotate(270) to fix")
    
    # Apply rotation and test OCR
    if fix:
        rotated = pil.rotate(fix, expand=True)
        fixed_path = scratch / f"fixed_{img_path.name}"
        rotated.convert("RGB").save(fixed_path, format="JPEG")
    else:
        fixed_path = img_path
    
    from ocr import extract_ticket_data
    fields, conf, prov = extract_ticket_data(fixed_path)
    tid = fields.get("ticket_id", "")
    tdate = fields.get("ticket_date", "")
    quarry = fields.get("quarry_name", "")
    gross = fields.get("gross_weight", "")
    tare = fields.get("tare_weight", "")
    net = fields.get("net_weight", "")
    print(f"  OCR result: ticket={tid}, date={tdate}, quarry={quarry}, gross={gross}, tare={tare}, net={net}")
    print()
