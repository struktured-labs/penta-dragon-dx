#!/usr/bin/env python3
"""Show full screenshot with extraction points and search areas marked"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import load_reference_sprites, extract_sprite_from_screenshot

def main():
    project_root = Path(__file__).parent.parent
    
    # Load reference
    references = load_reference_sprites()
    ref_img = references['SARA_W']
    
    # Try frame 229 (ideal)
    screenshot_path = project_root / 'test_verification_output' / 'verify_frame_00229.png'
    if not screenshot_path.exists():
        print(f"❌ Screenshot not found: {screenshot_path}")
        return
    
    screenshot_img = Image.open(screenshot_path).convert('RGBA')
    w, h = screenshot_img.size
    
    # Create visualization
    vis_img = screenshot_img.copy()
    draw = ImageDraw.Draw(vis_img)
    
    # Mark screen center
    screen_center = (w // 2, h // 2)
    draw.ellipse([screen_center[0]-5, screen_center[1]-5, screen_center[0]+5, screen_center[1]+5], 
                 fill=(255, 0, 0), outline=(255, 255, 0), width=2)
    draw.text((screen_center[0]+10, screen_center[1]-10), "SCREEN CENTER", fill=(255, 255, 0))
    
    # Mark gameplay area center (usually offset from screen center)
    # Game Boy screens: 160x144, gameplay is usually centered but may have UI offset
    gameplay_center_x = w // 2
    gameplay_center_y = h // 2  # May need adjustment
    
    # Try different gameplay center estimates
    gameplay_centers = [
        (w // 2, h // 2, "Screen center"),
        (w // 2, h // 2 - 10, "Screen center - 10px"),
        (w // 2, h // 2 + 10, "Screen center + 10px"),
        (w // 2 - 20, h // 2, "Left of center"),
        (w // 2 + 20, h // 2, "Right of center"),
    ]
    
    # Mark all extraction attempts
    extraction_points = [
        (37, 32, "Grid search best"),
        (44, 77, "Template match"),
        (52, 32, "Template match 2"),
        (80, 72, "Screen center"),
    ]
    
    for x, y, label in extraction_points:
        # Draw extraction box
        size = 24
        draw.rectangle([x-size//2, y-size//2, x+size//2, y+size//2], 
                      outline=(0, 255, 0), width=2)
        draw.text((x-size//2, y-size//2-15), label, fill=(0, 255, 0))
        draw.ellipse([x-3, y-3, x+3, y+3], fill=(0, 255, 0))
    
    # Mark gameplay area estimates
    for x, y, label in gameplay_centers:
        draw.ellipse([x-3, y-3, x+3, y+3], fill=(0, 0, 255))
        draw.text((x+5, y-10), label, fill=(0, 0, 255))
    
    # Save
    output_path = project_root / 'full_frame_with_extraction_points.png'
    vis_img.save(output_path)
    print(f"✅ Saved visualization: {output_path}")
    print(f"   Green boxes: extraction attempts")
    print(f"   Blue dots: gameplay center estimates")
    print(f"   Red dot: screen center")
    
    # Also extract sprites at all points for comparison
    print("\n📸 Extracted sprites:")
    for x, y, label in extraction_points:
        sprite = extract_sprite_from_screenshot(screenshot_img, x, y)
        sprite_path = project_root / f'extract_{label.replace(" ", "_")}_{x}_{y}.png'
        sprite.save(sprite_path)
        print(f"   {label} ({x}, {y}): {sprite_path.name}")

if __name__ == "__main__":
    main()

