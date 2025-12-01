#!/usr/bin/env python3
"""
Palette color converter and helper tool
Converts between different color formats for Game Boy Color palette editing
"""
import sys


def rgb888_to_bgr555(r: int, g: int, b: int) -> str:
    """Convert RGB888 (0-255) to BGR555 hex string"""
    # Scale down from 8-bit (0-255) to 5-bit (0-31)
    r5 = (r >> 3) & 0x1F
    g5 = (g >> 3) & 0x1F
    b5 = (b >> 3) & 0x1F
    
    # Pack as BGR555
    bgr555 = (b5 << 10) | (g5 << 5) | r5
    return f"{bgr555:04X}"


def bgr555_to_rgb888(hex_str: str) -> tuple[int, int, int]:
    """Convert BGR555 hex string to RGB888 (0-255)"""
    bgr555 = int(hex_str, 16)
    
    # Unpack BGR555
    r5 = bgr555 & 0x1F
    g5 = (bgr555 >> 5) & 0x1F
    b5 = (bgr555 >> 10) & 0x1F
    
    # Scale up from 5-bit (0-31) to 8-bit (0-255)
    r = (r5 << 3) | (r5 >> 2)
    g = (g5 << 3) | (g5 >> 2)
    b = (b5 << 3) | (b5 >> 2)
    
    return (r, g, b)


def hex_to_rgb888(hex_color: str) -> tuple[int, int, int]:
    """Convert web-style hex color (#RRGGBB) to RGB888"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def print_palette_examples():
    """Print common color examples"""
    print("\nCommon GBC Colors (BGR555 format):")
    print("=" * 60)
    
    colors = [
        ("Black", "0000", (0, 0, 0)),
        ("White", "7FFF", (255, 255, 255)),
        ("Red", "001F", (255, 0, 0)),
        ("Green", "03E0", (0, 255, 0)),
        ("Blue", "7C00", (0, 0, 255)),
        ("Yellow", "03FF", (255, 255, 0)),
        ("Cyan", "7FE0", (0, 255, 255)),
        ("Magenta", "7C1F", (255, 0, 255)),
        ("Dark Red", "0010", (130, 0, 0)),
        ("Dark Green", "0200", (0, 130, 0)),
        ("Dark Blue", "4000", (0, 0, 130)),
        ("Orange", "021F", (255, 130, 0)),
        ("Purple", "6010", (130, 0, 130)),
        ("Brown", "0215", (165, 82, 0)),
        ("Gray", "4210", (130, 130, 130)),
        ("Light Gray", "6318", (195, 195, 195)),
    ]
    
    for name, bgr555, (r, g, b) in colors:
        print(f"  {name:15} BGR555: {bgr555}    RGB: ({r:3}, {g:3}, {b:3})")


def interactive_mode():
    """Interactive palette color converter"""
    print("\n" + "=" * 60)
    print("GBC Palette Color Converter")
    print("=" * 60)
    
    while True:
        print("\nOptions:")
        print("  1. Convert RGB (0-255) to BGR555")
        print("  2. Convert hex color (#RRGGBB) to BGR555")
        print("  3. Convert BGR555 to RGB")
        print("  4. Show common colors")
        print("  5. Generate gradient")
        print("  q. Quit")
        
        choice = input("\nChoice: ").strip().lower()
        
        if choice == 'q':
            break
        elif choice == '1':
            try:
                r = int(input("  Red (0-255): "))
                g = int(input("  Green (0-255): "))
                b = int(input("  Blue (0-255): "))
                bgr555 = rgb888_to_bgr555(r, g, b)
                print(f"\n  BGR555: {bgr555}")
                print(f"  Use in YAML: \"{bgr555}\"")
            except ValueError as e:
                print(f"  Error: {e}")
        
        elif choice == '2':
            try:
                hex_color = input("  Hex color (#RRGGBB): ").strip()
                r, g, b = hex_to_rgb888(hex_color)
                bgr555 = rgb888_to_bgr555(r, g, b)
                print(f"\n  RGB: ({r}, {g}, {b})")
                print(f"  BGR555: {bgr555}")
                print(f"  Use in YAML: \"{bgr555}\"")
            except ValueError as e:
                print(f"  Error: {e}")
        
        elif choice == '3':
            try:
                bgr555 = input("  BGR555 (4-digit hex): ").strip().upper()
                r, g, b = bgr555_to_rgb888(bgr555)
                print(f"\n  RGB: ({r}, {g}, {b})")
                print(f"  Hex: #{r:02X}{g:02X}{b:02X}")
            except ValueError as e:
                print(f"  Error: {e}")
        
        elif choice == '4':
            print_palette_examples()
        
        elif choice == '5':
            try:
                start = input("  Start color (BGR555): ").strip().upper()
                end = input("  End color (BGR555): ").strip().upper()
                steps = int(input("  Number of steps (2-4): "))
                
                if steps < 2 or steps > 4:
                    print("  Error: Steps must be 2-4 for GBC palettes")
                    continue
                
                start_r, start_g, start_b = bgr555_to_rgb888(start)
                end_r, end_g, end_b = bgr555_to_rgb888(end)
                
                print(f"\n  Gradient palette ({steps} colors):")
                gradient = []
                for i in range(steps):
                    t = i / (steps - 1) if steps > 1 else 0
                    r = int(start_r + (end_r - start_r) * t)
                    g = int(start_g + (end_g - start_b) * t)
                    b = int(start_b + (end_b - start_b) * t)
                    bgr555 = rgb888_to_bgr555(r, g, b)
                    gradient.append(bgr555)
                    print(f"    {i}: {bgr555}  RGB({r:3}, {g:3}, {b:3})")
                
                print(f"\n  YAML format:")
                print(f"    colors: [{', '.join(f'\"{c}\"' for c in gradient)}]")
                
            except ValueError as e:
                print(f"  Error: {e}")


def main():
    if len(sys.argv) > 1:
        # Command-line mode
        if sys.argv[1] == '--examples':
            print_palette_examples()
        elif sys.argv[1] == '--rgb':
            if len(sys.argv) < 5:
                print("Usage: palette_tool.py --rgb R G B")
                sys.exit(1)
            r, g, b = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
            print(rgb888_to_bgr555(r, g, b))
        elif sys.argv[1] == '--hex':
            if len(sys.argv) < 3:
                print("Usage: palette_tool.py --hex #RRGGBB")
                sys.exit(1)
            r, g, b = hex_to_rgb888(sys.argv[2])
            print(rgb888_to_bgr555(r, g, b))
        elif sys.argv[1] == '--bgr':
            if len(sys.argv) < 3:
                print("Usage: palette_tool.py --bgr BGR555")
                sys.exit(1)
            r, g, b = bgr555_to_rgb888(sys.argv[2])
            print(f"RGB: ({r}, {g}, {b})")
            print(f"Hex: #{r:02X}{g:02X}{b:02X}")
        else:
            print("Usage:")
            print("  palette_tool.py              # Interactive mode")
            print("  palette_tool.py --examples   # Show common colors")
            print("  palette_tool.py --rgb R G B  # Convert RGB to BGR555")
            print("  palette_tool.py --hex #RRGGBB  # Convert hex to BGR555")
            print("  palette_tool.py --bgr BGR555 # Convert BGR555 to RGB")
    else:
        # Interactive mode
        interactive_mode()


if __name__ == "__main__":
    main()
