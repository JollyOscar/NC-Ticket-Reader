"""
Migration script: Fix all existing uploaded ticket images.
1. Find all ticket image files in the database
2. Check if they're upside down (NOVA at bottom)
3. Rotate them 180° and save
4. Re-run OCR and update the database row
"""
import sys, os, sqlite3, datetime as dt
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["OCR_PROVIDER"] = "google_vision"

from pathlib import Path
from PIL import Image as PilImage
from google.cloud import vision
from ocr import extract_ticket_data

DB_PATH = Path("data/prototype.db")
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

rows = conn.execute(
    "SELECT id, image_path, ticket_id, review_status FROM tickets ORDER BY id"
).fetchall()

print(f"Found {len(rows)} tickets in database\n")

client = vision.ImageAnnotatorClient()
fixed_count = 0
skipped = 0

for row in rows:
    img_path = Path(row["image_path"])
    tid = row["ticket_id"]
    row_id = row["id"]
    
    if not img_path.exists():
        print(f"  [SKIP] Row {row_id} (ticket={tid}): image not found at {img_path}")
        skipped += 1
        continue
    
    # Check orientation: send to Vision and look for NOVA position
    content = img_path.read_bytes()
    g_img = vision.Image(content=content)
    response = client.document_text_detection(image=g_img)
    
    if not response.text_annotations or len(response.text_annotations) < 2:
        print(f"  [SKIP] Row {row_id} (ticket={tid}): no text detected")
        skipped += 1
        continue
    
    pil_img = PilImage.open(img_path)
    pil_img.load()  # Force full decode, release file handle
    w_img, h_img = pil_img.width, pil_img.height
    
    needs_rotation = None
    for anno in response.text_annotations[1:]:
        w_str = anno.description.upper()
        if w_str in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
            verts = anno.bounding_poly.vertices
            if verts:
                avg_x = sum(v.x for v in verts) / len(verts) / max(1, w_img)
                avg_y = sum(v.y for v in verts) / len(verts) / max(1, h_img)
                if avg_y > 0.60:
                    needs_rotation = 180
                elif avg_x > 0.65:
                    needs_rotation = 270
                elif avg_x < 0.35 and avg_y > 0.35:
                    needs_rotation = 90
                break
    
    if needs_rotation:
        print(f"  [FIX] Row {row_id} (ticket={tid}): rotating {needs_rotation}°...", end=" ", flush=True)
        rotated = pil_img.rotate(needs_rotation, expand=True)
        pil_img.close()
        rotated.convert("RGB").save(img_path, format="JPEG")
        rotated.close()
        
        # Re-run OCR on the now-corrected image
        fields, confidence, provider = extract_ticket_data(img_path)
        raw_text = fields.pop("__raw_text", "")
        fields.pop("__ocr_warning", None)
        
        # Update the database row with new OCR results
        now = dt.datetime.utcnow().isoformat()
        conn.execute("""
            UPDATE tickets SET
                ticket_id = ?, ticket_date = ?, job_no = ?, quarry_name = ?,
                truck_or_plate = ?, trucker = ?, sold_to = ?, deliver_to = ?,
                material_type = ?, received_by = ?,
                gross_weight = ?, tare_weight = ?, net_weight = ?,
                source_site = ?, destination_site = ?,
                confidence_score = ?, ocr_provider = ?, raw_ocr_text = ?,
                updated_at = ?, review_status = 'needs_review'
            WHERE id = ?
        """, (
            fields.get("ticket_id", ""),
            fields.get("ticket_date", ""),
            fields.get("job_no", ""),
            fields.get("quarry_name", ""),
            fields.get("truck_or_plate", ""),
            fields.get("trucker", ""),
            fields.get("sold_to", ""),
            fields.get("deliver_to", ""),
            fields.get("material_type", ""),
            fields.get("received_by", ""),
            fields.get("gross_weight", ""),
            fields.get("tare_weight", ""),
            fields.get("net_weight", ""),
            fields.get("source_site", ""),
            fields.get("destination_site", ""),
            confidence,
            provider,
            raw_text,
            now,
            row_id,
        ))
        conn.commit()
        
        new_tid = fields.get("ticket_id", "")
        print(f"done. ticket={new_tid}, quarry={fields.get('quarry_name','')}, gross={fields.get('gross_weight','')}")
        fixed_count += 1
    else:
        pil_img.close()
        print(f"  [OK] Row {row_id} (ticket={tid}): already upright")

conn.close()
print(f"\nDone. Fixed {fixed_count}, skipped {skipped}, already OK {len(rows) - fixed_count - skipped} out of {len(rows)} total.")
