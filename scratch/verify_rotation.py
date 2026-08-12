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
        
    for anno in response.text_annotations[1:]:
        word = anno.description.upper()
        if word in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
            vertices = anno.bounding_poly.vertices
            if not vertices:
                continue
            w_img, h_img = pil_img.width, pil_img.height
            avg_x = sum(v.x for v in vertices) / len(vertices) / max(1, w_img)
            avg_y = sum(v.y for v in vertices) / len(vertices) / max(1, h_img)
            
            # If header is on right side (x > 0.65), rotate 90° (Pillow rotate(90))
            if avg_x > 0.65:
                return pil_img.rotate(90, expand=True)
            elif avg_y > 0.65:
                return pil_img.rotate(180, expand=True)
            elif avg_x < 0.35 and avg_y > 0.35:
                return pil_img.rotate(270, expand=True)
            else:
                return pil_img
    return pil_img

for img_p in ticket_imgs:
    orient_img = auto_orient_image(img_p)
    temp_p = Path(f"scratch/orient_correct_{img_p.name}")
    orient_img.save(temp_p)
    fields, conf, provider = extract_ticket_data(temp_p)
    print(f"CORRECT ORIENTATION {img_p.name}: ticket_id={fields.get('ticket_id')}, date={fields.get('ticket_date')}, quarry={fields.get('quarry_name')}, gross={fields.get('gross_weight')}, tare={fields.get('tare_weight')}, net={fields.get('net_weight')}")
