#!/usr/bin/env python3
"""
Test script for color name parsing
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the parse_color function
from create_dx_rom import parse_color

def test_color_parsing():
    """Test various color name formats"""
    
    test_cases = [
        # Hex values
        ("7FFF", 0x7FFF, "White (hex)"),
        ("0000", 0x0000, "Black (hex)"),
        ("001F", 0x001F, "Red (hex)"),
        
        # Basic color names
        ("red", 0x001F, "Red (name)"),
        ("green", 0x03E0, "Green (name)"),
        ("blue", 0x7C00, "Blue (name)"),
        ("yellow", 0x03FF, "Yellow (name)"),
        ("cyan", 0x7FE0, "Cyan (name)"),
        ("magenta", 0x7C1F, "Magenta (name)"),
        ("white", 0x7FFF, "White (name)"),
        ("black", 0x0000, "Black (name)"),
        ("orange", 0x021F, "Orange (name)"),
        ("purple", 0x6010, "Purple (name)"),
        ("brown", 0x0215, "Brown (name)"),
        ("gray", 0x4210, "Gray (name)"),
        ("grey", 0x4210, "Grey (alternative spelling)"),
        ("pink", 0x5C1F, "Pink (name)"),
        
        # Modified colors
        ("dark red", None, "Dark Red (modifier)"),
        ("light red", None, "Light Red (modifier)"),
        ("dark green", None, "Dark Green (modifier)"),
        ("light blue", None, "Light Blue (modifier)"),
        ("dark gray", None, "Dark Gray (modifier)"),
        ("light yellow", None, "Light Yellow (modifier)"),
    ]
    
    print("=" * 80)
    print("Color Name Parser Test")
    print("=" * 80)
    print()
    
    passed = 0
    failed = 0
    
    for color_input, expected, description in test_cases:
        try:
            result = parse_color(color_input)
            
            if expected is None:
                # Just check it doesn't error
                print(f"✓ {description:30} '{color_input:15}' → 0x{result:04X}")
                passed += 1
            elif result == expected:
                print(f"✓ {description:30} '{color_input:15}' → 0x{result:04X}")
                passed += 1
            else:
                print(f"✗ {description:30} '{color_input:15}' → 0x{result:04X} (expected 0x{expected:04X})")
                failed += 1
        except Exception as e:
            print(f"✗ {description:30} '{color_input:15}' → ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 80)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 80)
    
    return failed == 0

if __name__ == "__main__":
    success = test_color_parsing()
    sys.exit(0 if success else 1)
