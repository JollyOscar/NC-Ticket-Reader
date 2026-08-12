import sys, os
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image
from ocr import extract_ticket_data
from google.cloud import vision

client = vision.ImageAnnotatorClient()
out_dir = Path("docs/client_research/Info provided/Images")
ticket_imgs = sorted([p for p in out_dir.glob("pdf_ticket_p*.jpg")])

def auto_orient_image(img_path: Path) -> Image.Image:
    pil_img = Image.open(img_path)
    with open(img_path, "rb") as f:
        content = f.read()
    g_img = vision.Image(content=content)
    response = client.text_detection(image=g_img)
    
    if not response.text_annotations:
        return pil_img
        
    full_text = response.text_annotations[0].description
    # Find position of 'NOVA' or header words in annotations
    for anno in response.text_annotations[1:]:
        word = anno.description.upper()
        if word in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
            vertices = anno.bounding_poly.vertices
            if not vertices:
                continue
            w_img, h_img = pil_img.width, pil_img.height
            avg_x = sum(v.x for v in vertices) / len(vertices) / max(1, w_img)
            avg_y = sum(v.y for v in vertices) / len(vertices) / max(1, h_img)
            
            print(f"{img_path.name}: header word '{word}' found at relative x={avg_x:.2f}, y={avg_y:.2f} (img {w_img}x{h_img})")
            
            # If header is at bottom (y > 0.65), rotate 180°
            if avg_y > 0.65:
                print(f" -> Rotating 180°")
                return pil_img.rotate(180, expand=True)
            # If header is on right side (x > 0.65), rotate 90° counter-clockwise (270° PIL)
            elif avg_x > 0.65:
                print(f" -> Rotating 90° counter-clockwise (270°)")
                return pil_img.rotate(270, expand=True)
            # If header is on left side (x < 0.35 and y > 0.35), rotate 90° clockwise (90° PIL)
            elif avg_x < 0.35 and avg_y > 0.35:
                print(f" -> Rotating 90° clockwise")
                return pil_img.rotate(90, expand=True)
            else:
                print(f" -> Already upright (0°)")
                return pil_img
    return pil_img

for img_p in ticket_imgs:
    orient_img = auto_orient_image(img_p)
    temp_p = Path(f"scratch/orient_{img_p.name}")
    orient_img.save(temp_p)
    fields, conf, provider = extract_ticket_data(temp_p)
    print(f"RESULT {img_p.name}: ticket_id={fields.get('ticket_id')}, date={fields.get('ticket_date')}, quarry={fields.get('quarry_name')}, gross={fields.get('gross_weight')}, tare={fields.get('tare_weight')}, net={fields.get('net_weight')}")
    print("=" * 60)
