#!/usr/bin/env python3
"""Manually search for SARA_W by trying different positions"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from verify_palette_injection import load_reference_sprites, extract_sprite_from_screenshot, compare_sprites

def main():
    project_root = Path(__file__).parent.parent
    
    # Load reference
    references = load_reference_sprites()
    ref_img = references['SARA_W']
    
    # Load frame 229
    screenshot_path = project_root / 'test_verification_output' / 'verify_frame_00229.png'
    screenshot_img = Image.open(screenshot_path).convert('RGBA')
    h, w = screenshot_img.size
    
    print(f"📸 Screenshot size: {w}x{h}")
    print(f"🔍 Searching for SARA_W systematically...")
    print("   (Trying grid of positions in gameplay area)")
    
    # Gameplay area: skip top/bottom 20%, avoid center 30% (where text might be)
    gameplay_top = int(h * 0.2)
    gameplay_bottom = int(h * 0.8)
    gameplay_left = int(w * 0.15)
    gameplay_right = int(w * 0.85)
    
    # Search in a grid
    step = 8
    best_match = None
    best_score = 0
    best_pos = None
    
    for y in range(gameplay_top, gameplay_bottom, step):
        for x in range(gameplay_left, gameplay_right, step):
            # Skip center area where text might be
            if abs(x - w // 2) < w * 0.15:
                continue
            
            sprite = extract_sprite_from_screenshot(screenshot_img, x, y)
            stats = compare_sprites(ref_img, sprite, threshold=50)
            
            # Score based on accuracy and pixel count
            if stats['total_pixels'] > 20:  # Need enough pixels to be a real sprite
                score = stats['accuracy'] * (stats['total_pixels'] / 100.0)
                if score > best_score:
                    best_score = score
                    best_match = sprite
                    best_pos = (x, y)
                    print(f"   Found better match at ({x}, {y}): accuracy={stats['accuracy']:.1f}%, pixels={stats['total_pixels']}, score={score:.2f}")
    
    if best_pos:
        print(f"\n✅ Best match at ({best_pos[0]}, {best_pos[1]}) with score {best_score:.2f}")
        
        # Save the best match
        best_match.save(project_root / 'sara_w_best_match.png')
        print(f"   Saved best match to: sara_w_best_match.png")
        
        # Create comparison
        stats = compare_sprites(ref_img, best_match, threshold=50)
        print(f"\n📊 Comparison stats:")
        print(f"   Accuracy: {stats['accuracy']:.1f}%")
        print(f"   Avg Distance: {stats['avg_color_distance']:.1f}")
        print(f"   Total Pixels: {stats['total_pixels']}")
        
        return best_pos
    else:
        print("❌ Could not find SARA_W")
        return None

if __name__ == "__main__":
    main()

