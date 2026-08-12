"""
E2E test with exception tracing in the auto-orient try/except block.
"""
import sys, os, shutil, traceback
sys.path.insert(0, ".")
os.environ["OCR_PROVIDER"] = "google_vision"
from pathlib import Path
from PIL import Image as PilImage

# Patch the auto-orient to print exceptions
import ocr
orig_extract = ocr._extract_with_google_vision

def patched_extract(image_path):
    from google.cloud import vision
    import logging
    
    logger = ocr.logger
    logger.info("google_vision_request_start image=%s", image_path)
    client = vision.ImageAnnotatorClient()
    content = image_path.read_bytes()
    image = vision.Image(content=content)
    detect_fn = getattr(client, "document_text_detection")
    response = detect_fn(image=image)
    
    if response.error.message:
        raise RuntimeError(response.error.message)
    
    # Auto-orient with VERBOSE error printing
    if response.text_annotations and len(response.text_annotations) > 1:
        try:
            pil_img = PilImage.open(image_path)
            w_img, h_img = pil_img.width, pil_img.height
            needs_rotation = None
            print(f"[AUTO-ORIENT] Starting for {image_path.name} ({w_img}x{h_img})")
            for anno in response.text_annotations[1:]:
                w_str = anno.description.upper()
                if w_str in ["NOVA", "CONSTRUCTION", "QUARRY", "ANTIGONISH"]:
                    verts = anno.bounding_poly.vertices
                    if verts:
                        avg_x = sum(v.x for v in verts) / len(verts) / max(1, w_img)
                        avg_y = sum(v.y for v in verts) / len(verts) / max(1, h_img)
                        print(f"[AUTO-ORIENT] Found '{w_str}' at ({avg_x:.2f}, {avg_y:.2f})")
                        if avg_y > 0.60:
                            needs_rotation = 180
                        elif avg_x > 0.65:
                            needs_rotation = 270
                        elif avg_x < 0.35 and avg_y > 0.35:
                            needs_rotation = 90
                        break
            if needs_rotation:
                print(f"[AUTO-ORIENT] Rotating {needs_rotation}°")
                rotated_img = pil_img.rotate(needs_rotation, expand=True)
                rotated_img.convert("RGB").save(image_path, format="JPEG")
                content = image_path.read_bytes()
                image = vision.Image(content=content)
                response = detect_fn(image=image)
                print(f"[AUTO-ORIENT] Re-sent rotated image to Vision")
            else:
                print(f"[AUTO-ORIENT] No rotation needed")
        except Exception as o_exc:
            print(f"[AUTO-ORIENT] *** EXCEPTION: {o_exc}")
            traceback.print_exc()
    else:
        print(f"[AUTO-ORIENT] Skipped: text_annotations={len(response.text_annotations) if response.text_annotations else 0}")
    
    # Now call the rest of the extraction logic using the response
    # But we can't easily call the rest, so just return the original function's result
    # Actually let's just call the original which will redo the API call
    pass

# Instead, let's just directly test by adding explicit print to the try/except
src = Path("scratch/fresh_pages/fresh_p1.jpg")
test_copy = Path("scratch/e2e_test2.jpg")
shutil.copy2(src, test_copy)

before = PilImage.open(test_copy)
print(f"BEFORE: {before.size}")
# Read the pixel at center to verify rotation
center_pixel_before = before.getpixel((before.width // 2, 50))
print(f"Top-center pixel (y=50): {center_pixel_before}")

fields, conf, prov = ocr.extract_ticket_data(test_copy)

after = PilImage.open(test_copy)
print(f"AFTER:  {after.size}")
center_pixel_after = after.getpixel((after.width // 2, 50))
print(f"Top-center pixel (y=50): {center_pixel_after}")
print(f"Pixels changed: {center_pixel_before != center_pixel_after}")

print(f"\nFields:")
for k, v in fields.items():
    if v and not k.startswith("__"):
        print(f"  {k}: {v}")
