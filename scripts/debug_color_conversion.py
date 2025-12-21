#!/usr/bin/env python3
"""Debug color conversion: RGB to BGR555 and vice versa"""
import sys

def bgr555_to_rgb(bgr555):
    """Convert BGR555 to RGB888"""
    r5 = bgr555 & 0x1F
    g5 = (bgr555 >> 5) & 0x1F
    b5 = (bgr555 >> 10) & 0x1F
    
    # Scale up from 5-bit to 8-bit
    r = (r5 << 3) | (r5 >> 2)
    g = (g5 << 3) | (g5 >> 2)
    b = (b5 << 3) | (b5 >> 2)
    
    return (r, g, b)

def rgb_to_bgr555(r, g, b):
    """Convert RGB888 to BGR555"""
    r5 = (r >> 3) & 0x1F
    g5 = (g >> 3) & 0x1F
    b5 = (b >> 3) & 0x1F
    
    bgr555 = (b5 << 10) | (g5 << 5) | r5
    return bgr555

def rgb_to_hex(r, g, b):
    return f"#{r:02X}{g:02X}{b:02X}"

print("=" * 60)
print("Color Conversion Debug")
print("=" * 60)

# Expected colors from reference
print("\n1. Expected colors (from reference sprite):")
orange_rgb = (255, 132, 0)
green_rgb = (0, 255, 0)

print(f"   Orange: RGB{orange_rgb} = {rgb_to_hex(*orange_rgb)}")
print(f"   Green:  RGB{green_rgb} = {rgb_to_hex(*green_rgb)}")

# Convert to BGR555
orange_bgr555 = rgb_to_bgr555(*orange_rgb)
green_bgr555 = rgb_to_bgr555(*green_rgb)

print(f"\n2. Expected BGR555 values:")
print(f"   Orange: {orange_bgr555:04X} (from RGB{orange_rgb})")
print(f"   Green:  {green_bgr555:04X} (from RGB{green_rgb})")

# Check what's currently in the palette
print(f"\n3. Current palette values (from parse_color):")
print(f"   'orange': 0x021F")
print(f"   'green':  0x03E0")

# Convert current palette values back to RGB
orange_current_rgb = bgr555_to_rgb(0x021F)
green_current_rgb = bgr555_to_rgb(0x03E0)

print(f"\n4. What current palette values actually render as:")
print(f"   0x021F -> RGB{orange_current_rgb} = {rgb_to_hex(*orange_current_rgb)}")
print(f"   0x03E0 -> RGB{green_current_rgb} = {rgb_to_hex(*green_current_rgb)}")

# Actual colors from screenshot
print(f"\n5. Actual colors from screenshot:")
actual_red_rgb = (255, 0, 0)
actual_green_rgb = (0, 255, 0)

print(f"   Red:   RGB{actual_red_rgb} = {rgb_to_hex(*actual_red_rgb)}")
print(f"   Green: RGB{actual_green_rgb} = {rgb_to_hex(*actual_green_rgb)}")

# Check what BGR555 would produce red
red_bgr555 = rgb_to_bgr555(*actual_red_rgb)
print(f"\n6. BGR555 for red (what we're seeing):")
print(f"   Red RGB{actual_red_rgb} -> BGR555: {red_bgr555:04X}")

# Compare
print(f"\n7. Comparison:")
print(f"   Expected orange BGR555: {orange_bgr555:04X}")
print(f"   Current 'orange' BGR555: 0x021F")
print(f"   Actual red BGR555:      {red_bgr555:04X}")
print(f"")
print(f"   Expected green BGR555:  {green_bgr555:04X}")
print(f"   Current 'green' BGR555:  0x03E0")
print(f"   Actual green BGR555:    {rgb_to_bgr555(*actual_green_rgb):04X}")

print(f"\n8. Recommendation:")
if orange_bgr555 != 0x021F:
    print(f"   ❌ Orange mismatch! Update palette:")
    print(f"      Change 'orange' from 0x021F to {orange_bgr555:04X}")
else:
    print(f"   ✅ Orange value is correct")

if green_bgr555 != 0x03E0:
    print(f"   ❌ Green mismatch! Update palette:")
    print(f"      Change 'green' from 0x03E0 to {green_bgr555:04X}")
else:
    print(f"   ✅ Green value is correct")

