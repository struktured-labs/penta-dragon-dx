#!/usr/bin/env python3
"""
Display a color reference showing all available color names
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from create_dx_rom import COLOR_NAMES, parse_color

def bgr555_to_rgb(bgr555):
    """Convert BGR555 to RGB888 for display"""
    r = (bgr555 & 0x1F) << 3
    g = ((bgr555 >> 5) & 0x1F) << 3
    b = ((bgr555 >> 10) & 0x1F) << 3
    # Expand 5-bit to 8-bit properly
    r |= r >> 5
    g |= g >> 5
    b |= b >> 5
    return (r, g, b)

def main():
    print("=" * 80)
    print("Game Boy Color - Available Color Names")
    print("=" * 80)
    print()
    
    # Basic colors
    print("BASIC COLORS:")
    print("-" * 80)
    print(f"{'Name':<20} {'BGR555':<10} {'RGB':<20} {'Usage Example'}")
    print("-" * 80)
    
    for name in sorted(COLOR_NAMES.keys()):
        if name == 'grey':  # Skip duplicate
            continue
        bgr555 = COLOR_NAMES[name]
        r, g, b = bgr555_to_rgb(bgr555)
        print(f"{name:<20} {bgr555:04X}       RGB({r:3}, {g:3}, {b:3})    colors: [\"{name}\"]")
    
    print()
    print("MODIFIERS:")
    print("-" * 80)
    print("You can prefix any color with 'dark ' or 'light ' to adjust brightness:")
    print()
    
    example_colors = ['red', 'green', 'blue', 'yellow', 'purple', 'orange']
    
    for base in example_colors:
        dark = parse_color(f"dark {base}")
        normal = parse_color(base)
        light = parse_color(f"light {base}")
        
        dark_rgb = bgr555_to_rgb(dark)
        normal_rgb = bgr555_to_rgb(normal)
        light_rgb = bgr555_to_rgb(light)
        
        print(f"  {base.capitalize()}:")
        print(f"    dark {base:<12} {dark:04X}  RGB{dark_rgb}")
        print(f"    {base:<17} {normal:04X}  RGB{normal_rgb}")
        print(f"    light {base:<11} {light:04X}  RGB{light_rgb}")
        print()
    
    print("=" * 80)
    print("USAGE IN YAML:")
    print("=" * 80)
    print("""
Example palette using color names:
  
  obj_palettes:
    MainCharacter:
      colors: ["transparent", "yellow", "orange", "brown"]
      
  bg_palettes:
    WaterZone:
      colors: ["white", "light blue", "blue", "dark blue"]
    
Mix hex and names freely:
      colors: ["0000", "red", "dark red", "7FFF"]
""")
    
    print("=" * 80)

if __name__ == "__main__":
    main()
