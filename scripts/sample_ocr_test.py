#!/usr/bin/env python3
"""
Sample a few screenshots to debug OCR issues
"""

from pathlib import Path
from PIL import Image, ImageEnhance
import pytesseract

def test_single_image(image_path, index=0):
    """Test OCR on a single image with debug info"""
    print(f"\n{'='*60}")
    print(f"Screenshot #{index}: {image_path.name}")
    print(f"{'='*60}")
    
    try:
        img = Image.open(image_path)
        
        print(f"Original size: {img.size}")
        print(f"Mode: {img.mode}")
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        width, height = img.size
        
        # Upscale for better OCR
        scale_factor = 8
        img_scaled = img.resize((width * scale_factor, height * scale_factor), Image.Resampling.NEAREST)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img_scaled)
        img_enhanced = enhancer.enhance(2.5)
        
        print(f"Scaled size: {img_enhanced.size}")
        
        # Try full image first
        print("\n--- Full Image OCR (all characters) ---")
        text_full = pytesseract.image_to_string(img_enhanced, config='--psm 6')
        print(repr(text_full))
        
        # Try with uppercase only
        print("\n--- Full Image OCR (uppercase only) ---")
        text_upper = pytesseract.image_to_string(
            img_enhanced, 
            config='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        )
        print(repr(text_upper))
        
        # Try center region
        w, h = img_enhanced.size
        crop_top = int(h * 0.4)
        crop_bottom = int(h * 0.65)
        center_crop = img_enhanced.crop((0, crop_top, w, crop_bottom))
        
        print("\n--- Center Region OCR (uppercase only) ---")
        text_center = pytesseract.image_to_string(
            center_crop, 
            config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ '
        )
        print(repr(text_center))
        
        # Save debug image
        debug_path = Path(__file__).parent.parent / f"debug_screenshot_{index}.png"
        img_enhanced.save(debug_path)
        print(f"\nDebug image saved to: {debug_path}")
        
    except Exception as e:
        print(f"ERROR: {e}")

def main():
    screenshot_dir = Path(__file__).parent.parent / "rom" / "working.bak"
    
    # Test a few different screenshots
    test_indices = [500, 1000, 2000, 3000, 5000, 8000]
    
    for i in test_indices:
        screenshot = screenshot_dir / f"verify_screenshot_{i}.png"
        if screenshot.exists():
            test_single_image(screenshot, i)

if __name__ == "__main__":
    main()
