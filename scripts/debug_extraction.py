#!/usr/bin/env python3
"""Debug what's being extracted from screenshot"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from create_sara_w_comparison import load_reference_sprites, extract_sprite_from_screenshot, find_sprite_in_screenshot

def main():
    project_root = Path(__file__).parent.parent
    
    # Load reference
    references = load_reference_sprites()
    ref_img = references['SARA_W']
    
    # Load frame 229
    screenshot_path = project_root / 'test_verification_output' / 'verify_frame_00229.png'
    screenshot_img = Image.open(screenshot_path).convert('RGBA')
    
    # Create debug image showing the screenshot with extraction points marked
    debug_img = screenshot_img.copy()
    draw = ImageDraw.Draw(debug_img)
    
    # Try multiple positions to see what we're extracting
    test_positions = [
        (52, 32, "Found by search"),
        (80, 72, "Center"),
        (40, 60, "Left side"),
        (120, 60, "Right side"),
    ]
    
    print("🔍 Testing extraction at multiple positions:")
    for x, y, label in test_positions:
        sprite = extract_sprite_from_screenshot(screenshot_img, x, y)
        
        # Draw a box around the extraction point
        size = 24
        draw.rectangle([x-size//2, y-size//2, x+size//2, y+size//2], outline=(255, 0, 0), width=2)
        draw.text((x-size//2, y-size//2-15), label, fill=(255, 255, 0))
        
        # Save extracted sprite
        sprite_path = project_root / f'debug_extract_{label.replace(" ", "_")}_{x}_{y}.png'
        sprite.save(sprite_path)
        print(f"   {label} ({x}, {y}): saved to {sprite_path.name}")
    
    # Save debug image
    debug_path = project_root / 'debug_extraction_points.png'
    debug_img.save(debug_path)
    print(f"\n✅ Debug image saved: {debug_path}")
    print("   Red boxes show extraction points")

if __name__ == "__main__":
    main()

