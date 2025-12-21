#!/usr/bin/env python3
"""Analyze actual colors in SARA_W screenshot vs expected colors"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from create_sara_w_comparison import find_sprite_in_screenshot, load_reference_sprites, extract_sprite_from_screenshot

def get_dominant_colors(img, n=2):
    """Get the n most common non-transparent colors"""
    pixels = np.array(img)
    colors = []
    
    for row in pixels:
        for pixel in row:
            r, g, b, a = pixel
            if a > 128:  # Non-transparent
                colors.append((r, g, b))
    
    if not colors:
        return []
    
    # Count colors (with some tolerance for similar colors)
    color_counts = Counter(colors)
    # Get top n colors
    top_colors = color_counts.most_common(n)
    return [color for color, count in top_colors]

def rgb_to_hex(rgb):
    """Convert RGB tuple to hex"""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"

def main():
    project_root = Path(__file__).parent.parent
    
    # Load reference
    print("📸 Loading reference SARA_W sprite...")
    references = load_reference_sprites()
    if 'SARA_W' not in references:
        print("❌ SARA_W reference not found!")
        return
    
    ref_img = references['SARA_W']
    
    # Get expected colors from reference
    print("\n🎨 Expected colors (from reference):")
    expected_colors = get_dominant_colors(ref_img, n=3)
    for i, (r, g, b) in enumerate(expected_colors, 1):
        print(f"   Color {i}: RGB({r}, {g}, {b}) = {rgb_to_hex((r, g, b))}")
    
    # Load screenshot
    screenshot_path = project_root / 'test_verification_output' / 'verify_frame_00216.png'
    if not screenshot_path.exists():
        print(f"❌ Screenshot not found: {screenshot_path}")
        return
    
    print(f"\n📸 Loading screenshot: {screenshot_path.name}")
    screenshot_img = Image.open(screenshot_path).convert('RGBA')
    
    # Find SARA_W
    search_region = (0, 0, screenshot_img.width // 2, screenshot_img.height)
    result = find_sprite_in_screenshot(ref_img, screenshot_img, search_region=search_region)
    
    if not result:
        result = find_sprite_in_screenshot(ref_img, screenshot_img)
    
    if result:
        sprite_pos, match_score = result
        print(f"   ✅ Found SARA_W at ({sprite_pos[0]}, {sprite_pos[1]})")
        
        # Extract sprite
        candidate_sprite = extract_sprite_from_screenshot(screenshot_img, sprite_pos[0], sprite_pos[1])
        
        # Get actual colors
        print("\n🎨 Actual colors (from screenshot):")
        actual_colors = get_dominant_colors(candidate_sprite, n=3)
        for i, (r, g, b) in enumerate(actual_colors, 1):
            print(f"   Color {i}: RGB({r}, {g}, {b}) = {rgb_to_hex((r, g, b))}")
        
        # Compare
        print("\n🔍 Color Analysis:")
        if len(expected_colors) >= 2 and len(actual_colors) >= 2:
            exp1, exp2 = expected_colors[0], expected_colors[1]
            act1, act2 = actual_colors[0], actual_colors[1]
            
            print(f"   Expected primary: {rgb_to_hex(exp1)}")
            print(f"   Actual primary:   {rgb_to_hex(act1)}")
            print(f"   Expected secondary: {rgb_to_hex(exp2)}")
            print(f"   Actual secondary:   {rgb_to_hex(act2)}")
            
            # Check if colors match expected orange/green theme
            print("\n📊 Color Theme Check:")
            exp_has_orange = any(r > 200 and g > 100 and g < 200 and b < 100 for r, g, b in expected_colors)
            exp_has_green = any(g > 150 and r < 150 and b < 150 for r, g, b in expected_colors)
            act_has_blue = any(b > 150 and r < 150 and g < 200 for r, g, b in actual_colors)
            act_has_green = any(g > 150 and r < 150 and b < 150 for r, g, b in actual_colors)
            
            print(f"   Reference has orange: {exp_has_orange}")
            print(f"   Reference has green: {exp_has_green}")
            print(f"   Screenshot has blue: {act_has_blue}")
            print(f"   Screenshot has green: {act_has_green}")
            
            if act_has_blue and not exp_has_orange:
                print("\n   ❌ PROBLEM: Screenshot shows blue instead of orange!")
                print("      This means the palette injection is using wrong colors.")
    else:
        print("   ❌ Could not find SARA_W in screenshot")

if __name__ == "__main__":
    main()

