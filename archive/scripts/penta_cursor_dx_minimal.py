#!/usr/bin/env python3
"""
MINIMAL STABLE VERSION - CGB FLAG ONLY
Based on CGB_COLORIZATION_FINDINGS.md: "CGB Flag Only" is the only stable version
"""
import sys
from pathlib import Path

def main():
    input_rom_path = Path("rom/Penta Dragon (J).gb")
    output_rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")

    rom = bytearray(input_rom_path.read_bytes())
    
    # ONLY CGB FLAG - This is the only known stable configuration
    rom[0x143] = 0xC0  # CGB-only
    
    # Update checksums
    chk = 0
    for i in range(0x134, 0x14D): chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    output_rom_path.write_bytes(rom)
    print(f"✅ MINIMAL STABLE ROM: {output_rom_path}")
    print("")
    print("Features:")
    print("  ✓ CGB-only mode enabled")
    print("  ✓ No code modifications (100% stable)")
    print("")
    print("Note: This uses hardware default colors (white/beige)")
    print("      All palette injection attempts have caused crashes")

if __name__ == "__main__":
    main()

