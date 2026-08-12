"""
Examine the ACTUAL pixel orientation of fresh PDF pages by:
1. Checking if image is landscape (width > height) — tickets should be portrait
2. Using EXIF orientation if present
3. Using pytesseract OSD (Orientation & Script Detection) to determine rotation
"""
import sys, os
sys.path.insert(0, ".")
from pathlib import Path
from PIL import Image
import subprocess

scratch = Path("scratch/fresh_pages")

# Check if tesseract is available for OSD
try:
    result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True)
    has_tesseract = True
    print(f"Tesseract available: {result.stdout.splitlines()[0]}")
except FileNotFoundError:
    has_tesseract = False
    print("Tesseract not found")

for img_path in sorted(scratch.glob("fresh_p*.jpg")):
    pil = Image.open(img_path)
    print(f"\n=== {img_path.name} ===")
    print(f"  Size: {pil.width}x{pil.height}  ({'landscape' if pil.width > pil.height else 'portrait'})")
    
    # Check EXIF
    exif = pil.getexif()
    orient_tag = exif.get(274)  # 274 = Orientation tag
    print(f"  EXIF Orientation tag: {orient_tag}")
    
    if has_tesseract:
        # Use tesseract OSD to detect page rotation
        result = subprocess.run(
            ["tesseract", str(img_path), "-", "--psm", "0"],
            capture_output=True, text=True
        )
        print(f"  Tesseract OSD output:")
        for line in result.stdout.strip().split("\n"):
            if "Rotate" in line or "Orientation" in line or "rotate" in line.lower():
                print(f"    {line}")
        if result.stderr and "Error" in result.stderr:
            print(f"    (stderr): {result.stderr.strip()[:200]}")

    # Also just manually look at whether the header text appears on the right side
    # by splitting the image into quadrants and checking density
    import numpy as np
    arr = np.array(pil.convert("L"))
    h, w = arr.shape
    
    # Check ink density in each quarter
    top = arr[:h//2, :]
    bottom = arr[h//2:, :]
    left = arr[:, :w//2]
    right = arr[:, w//2:]
    
    # Dark pixels (ink) have lower values
    threshold = 200
    top_ink = (top < threshold).sum() / top.size
    bottom_ink = (bottom < threshold).sum() / bottom.size
    left_ink = (left < threshold).sum() / left.size
    right_ink = (right < threshold).sum() / right.size
    
    print(f"  Ink density: top={top_ink:.3f}, bottom={bottom_ink:.3f}, left={left_ink:.3f}, right={right_ink:.3f}")
