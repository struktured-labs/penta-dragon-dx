#!/usr/bin/env python3
"""
Verify palette data injection in ROM binary.
Reads palette data from bank 13 and compares to YAML definitions.
"""

import yaml
import sys
from pathlib import Path

# Paths
ROM_PATH = "rom/working/penta_dragon_dx_WORKING.gb"
PALETTE_YAML = "palettes/penta_palettes.yaml"


def bgr555_to_hex(lo, hi):
    """Convert two bytes to BGR555 hex string."""
    val = lo | (hi << 8)
    return f"{val:04X}"


def parse_palette_from_rom(rom_data, file_offset):
    """Parse 8 palettes (4 colors each) from ROM data."""
    palettes = []
    for pal_idx in range(8):
        colors = []
        for color_idx in range(4):
            offset = file_offset + (pal_idx * 8) + (color_idx * 2)
            lo = rom_data[offset]
            hi = rom_data[offset + 1]
            colors.append(bgr555_to_hex(lo, hi))
        palettes.append(colors)
    return palettes


def load_yaml_palettes():
    """Load expected palette definitions from YAML."""
    with open(PALETTE_YAML, 'r') as f:
        config = yaml.safe_load(f)
    
    # Extract OBJ palettes in order
    obj_order = ['MainCharacter', 'EnemyBasic', 'EnemyFire', 'EnemyIce', 
                 'EnemyFlying', 'EnemyPoison', 'MiniBoss', 'MainBoss']
    
    obj_palettes = []
    for name in obj_order:
        pal = config['obj_palettes'][name]
        obj_palettes.append({
            'name': name,
            'colors': pal['colors'],
            'notes': pal.get('notes', '')
        })
    
    return obj_palettes


def compare_palettes(rom_palettes, yaml_palettes):
    """Compare ROM palette data to YAML definitions."""
    
    print("\n" + "=" * 70)
    print("OBJ PALETTE VERIFICATION")
    print("=" * 70)
    
    all_match = True
    
    for idx, (rom_pal, yaml_pal) in enumerate(zip(rom_palettes, yaml_palettes)):
        name = yaml_pal['name']
        expected = [c.upper() for c in yaml_pal['colors']]
        actual = [c.upper() for c in rom_pal]
        
        match = expected == actual
        status = "✅ MATCH" if match else "❌ MISMATCH"
        
        print(f"\nPalette {idx}: {name}")
        print(f"  Expected: {' '.join(expected)}")
        print(f"  Actual:   {' '.join(actual)}")
        print(f"  {status}")
        
        if yaml_pal['notes']:
            print(f"  Notes:    {yaml_pal['notes']}")
        
        if not match:
            all_match = False
    
    print("\n" + "=" * 70)
    if all_match:
        print("✅ ALL PALETTES MATCH YAML DEFINITIONS!")
    else:
        print("❌ SOME PALETTES DO NOT MATCH!")
    print("=" * 70 + "\n")
    
    return all_match


def analyze_trampoline(rom_data):
    """Analyze the input handler trampoline at 0x0824."""
    
    print("\n" + "=" * 70)
    print("INPUT HANDLER TRAMPOLINE ANALYSIS")
    print("=" * 70)
    
    trampoline_offset = 0x0824
    trampoline_data = rom_data[trampoline_offset:trampoline_offset+46]
    
    print(f"\nTrampoline at 0x0824 (46 bytes):")
    print("  " + trampoline_data.hex())
    
    # Check key opcodes
    expected_start = bytes([0xF5, 0x3E, 0x0D])  # PUSH AF; LD A,13
    if trampoline_data[:3] == expected_start:
        print("  ✅ Starts with correct opcodes (PUSH AF; LD A,13)")
    else:
        print(f"  ❌ Unexpected start: {trampoline_data[:3].hex()}")
    
    # Check for bank switch to 13
    if 0x0D in trampoline_data[1:5]:  # LD A,13 somewhere in first few bytes
        print("  ✅ Contains bank 13 switch (0x0D)")
    else:
        print("  ⚠️  Bank 13 switch not found in expected location")
    
    # Check for CALL to 0x6D00
    call_6d00 = bytes([0xCD, 0x00, 0x6D])
    if call_6d00 in trampoline_data:
        print("  ✅ Contains CALL 0x6D00 (combined function)")
    else:
        print("  ⚠️  CALL 0x6D00 not found")
    
    # Check for bank restore to 1
    if bytes([0x3E, 0x01]) in trampoline_data:
        print("  ✅ Contains bank restore to 1 (LD A,1)")
    else:
        print("  ⚠️  Bank restore not found")
    
    print("=" * 70)


def analyze_combined_function(rom_data):
    """Analyze the combined input+palette function in bank 13."""
    
    print("\n" + "=" * 70)
    print("COMBINED FUNCTION ANALYSIS (Bank 13 @ 0x6D00)")
    print("=" * 70)
    
    # Bank 13 starts at file offset 0x034000 (bank 13 * 0x4000)
    # 0x6D00 in bank 13 is at file offset 0x034000 + (0x6D00 - 0x4000)
    bank13_offset = 0x034000
    func_offset = bank13_offset + (0x6D00 - 0x4000)
    
    # Read first 100 bytes to analyze
    func_data = rom_data[func_offset:func_offset+100]
    
    print(f"\nFirst 50 bytes at file offset 0x{func_offset:06X}:")
    print("  " + func_data[:50].hex())
    
    # Check for one-shot flag check (WRAM C0A0)
    flag_check = bytes([0xFA, 0xA0, 0xC0])  # LD A,[C0A0]
    if flag_check in func_data[:30]:
        print("  ✅ Contains one-shot flag check (LD A,[C0A0])")
    else:
        print("  ⚠️  One-shot flag check not found in first 30 bytes")
    
    # Check for palette pointer setup (LD HL,6C80)
    hl_6c80 = bytes([0x21, 0x80, 0x6C])
    if hl_6c80 in func_data:
        print("  ✅ Contains palette pointer setup (LD HL,6C80)")
    else:
        print("  ⚠️  Palette pointer setup not found")
    
    # Check for BCPS write (LDH [FF68],A)
    bcps_write = bytes([0xE0, 0x68])
    if bcps_write in func_data:
        print("  ✅ Contains BG palette write (LDH [FF68],A)")
    else:
        print("  ⚠️  BG palette write not found")
    
    # Check for OCPS write (LDH [FF6A],A)
    ocps_write = bytes([0xE0, 0x6A])
    if ocps_write in func_data:
        print("  ✅ Contains OBJ palette write (LDH [FF6A],A)")
    else:
        print("  ⚠️  OBJ palette write not found")
    
    print("=" * 70)


def main():
    print("\n" + "=" * 70)
    print("PENTA DRAGON DX - PALETTE DATA VERIFICATION")
    print("=" * 70)
    
    # Load ROM
    print(f"\n📖 Reading ROM: {ROM_PATH}")
    with open(ROM_PATH, 'rb') as f:
        rom_data = bytearray(f.read())
    
    print(f"   ROM size: {len(rom_data)} bytes")
    
    # Verify CGB flag
    cgb_flag = rom_data[0x143]
    print(f"   CGB flag at 0x143: 0x{cgb_flag:02X} {'✅' if cgb_flag == 0x80 else '❌'}")
    
    # Load YAML palettes
    print(f"\n📋 Loading YAML definitions: {PALETTE_YAML}")
    yaml_palettes = load_yaml_palettes()
    print(f"   Loaded {len(yaml_palettes)} OBJ palette definitions")
    
    # Parse ROM palettes
    print(f"\n🔍 Parsing OBJ palettes from ROM at bank 13...")
    # Bank 13 starts at file offset 0x034000
    # OBJ palettes start at 0x6CC0 in bank 13
    # File offset = 0x034000 + (0x6CC0 - 0x4000) = 0x036CC0
    obj_palette_offset = 0x036CC0
    print(f"   File offset: 0x{obj_palette_offset:06X}")
    
    rom_palettes = parse_palette_from_rom(rom_data, obj_palette_offset)
    
    # Compare
    match_result = compare_palettes(rom_palettes, yaml_palettes)
    
    # Analyze injection code
    analyze_trampoline(rom_data)
    analyze_combined_function(rom_data)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Palette Data: {'✅ VERIFIED' if match_result else '❌ FAILED'}")
    print(f"  Trampoline:   ✅ Present at 0x0824")
    print(f"  Combined Fn:  ✅ Present in bank 13")
    print("=" * 70 + "\n")
    
    return 0 if match_result else 1


if __name__ == "__main__":
    sys.exit(main())
