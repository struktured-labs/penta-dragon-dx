#!/usr/bin/env python3
"""
Surgical Palette Patching for Penta Dragon DX

This script applies targeted NOPs to centralized palette write functions,
preventing DMG palette register writes (FF47/FF48/FF49) while preserving
all other game logic. This allows CGB palette registers to control colors.

Strategy:
- Replace "LDH [FF47-49],A" (E0 47/48/49) with NOPs (00 00)
- Target 10 centralized functions containing 40 of 50 total writes
- Preserve surrounding code, animations, state changes

Author: GitHub Copilot & struktured
"""

import sys
sys.path.insert(0, 'src')
from penta_dragon_dx.display_patcher import apply_all_display_patches

def pal(c0, c1, c2, c3):
    """Convert 4 BGR555 colors to 8-byte palette data."""
    return bytes([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        c2 & 0xFF, (c2 >> 8) & 0xFF,
        c3 & 0xFF, (c3 >> 8) & 0xFF,
    ])

def apply_surgical_patches(rom):
    """
    Apply NOPs to centralized palette write functions.
    
    Target clusters identified:
    - 0x0A0F-0x0A13: Set all palettes (BGP, OBP0, OBP1)
    - 0x5021-0x5035: Initialization (writes all palettes twice)
    - 0xB8DE-0xB8F5: Mirror initialization
    - 0x0949-0x0997: Palette animation (7 BGP writes)
    - Plus 6 more clusters
    """
    patches = []
    
    # Find all E0 47/48/49 (LDH [FF47-49],A) instructions
    for addr in range(len(rom) - 1):
        if rom[addr] == 0xE0 and rom[addr+1] in [0x47, 0x48, 0x49]:
            reg = {0x47: "BGP", 0x48: "OBP0", 0x49: "OBP1"}[rom[addr+1]]
            patches.append((addr, reg))
    
    print(f"🔍 Found {len(patches)} DMG palette writes to patch")
    
    # Apply NOPs
    for addr, reg in patches:
        rom[addr] = 0x00  # NOP
        rom[addr+1] = 0x00  # NOP
        print(f"  ✓ 0x{addr:04X}: LDH [{reg}],A → NOP NOP")
    
    return rom

def create_boot_loader(rom):
    """Create boot-time CGB palette loader."""
    # BG palettes: green dungeon theme
    bg_data = bytearray()
    bg_data.extend(pal(0x7FFF, 0x03E0, 0x0280, 0x0000))  # Green
    bg_data.extend(pal(0x7FFF, 0x7C00, 0x5000, 0x2000))  # Red
    bg_data.extend(pal(0x7FFF, 0x001F, 0x0014, 0x0008))  # Blue
    bg_data.extend(pal(0x7FFF, 0x7FE0, 0x5CC0, 0x2980))  # Yellow
    bg_data.extend(pal(0x7FFF, 0x03FF, 0x02BF, 0x015F))  # Cyan
    bg_data.extend(pal(0x7FFF, 0x7C1F, 0x5010, 0x2808))  # Magenta
    bg_data.extend(pal(0x7FFF, 0x5EF7, 0x3DEF, 0x1CE7))  # Light cyan
    bg_data.extend(pal(0x7FFF, 0x6F7B, 0x4E73, 0x2D6B))  # Pink
    
    # OBJ palettes: RED=player, MAGENTA=monsters
    obj_data = bytearray()
    obj_data.extend(pal(0x0000, 0x001F, 0x0014, 0x0008))  # 0: Trans→RED (player)
    obj_data.extend(pal(0x0000, 0x7C1F, 0x5010, 0x2808))  # 1: Trans→MAGENTA (monsters)
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))  # 2-7: White/gray
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))
    obj_data.extend(pal(0x0000, 0x7FFF, 0x5AD6, 0x318C))
    
    # Write palette data to bank 13
    rom[0x036C80:0x036C80+len(bg_data)] = bg_data
    rom[0x036C80+len(bg_data):0x036C80+len(bg_data)+len(obj_data)] = obj_data
    
    # Boot-time palette loader (goes in bank 13)
    loader = bytes([
        0xF5, 0xC5, 0xE5,              # PUSH AF, BC, HL
        0x3E, 0x0D,                    # LD A,13
        0xEA, 0x00, 0x20,              # LD [2000],A
        0x21, 0x80, 0x6C,              # LD HL,6C80
        0x3E, 0x80,                    # LD A,80h
        0xE0, 0x68,                    # LDH [FF68],A (BCPS)
        0x0E, 0x40,                    # LD C,64
        0x2A, 0xE0, 0x69,              # loop: LD A,[HL+]; LDH [FF69],A
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ,loop
        0x3E, 0x80,                    # LD A,80h
        0xE0, 0x6A,                    # LDH [FF6A],A (OCPS)
        0x0E, 0x40,                    # LD C,64
        0x2A, 0xE0, 0x6B,              # loop: LD A,[HL+]; LDH [FF6B],A
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ,loop
        0x3E, 0x01,                    # LD A,1
        0xEA, 0x00, 0x20,              # LD [2000],A
        0xE1, 0xC1, 0xF1,              # POP HL, BC, AF
        0xC3, 0x53, 0x01,              # JP 0x0153 (continue)
    ])
    
    rom[0x036D00:0x036D00+len(loader)] = loader
    
    # Boot entry hook at 0x0150
    entry = bytes([
        0x3E, 0x0D,                    # LD A,13
        0xEA, 0x00, 0x20,              # LD [2000],A
        0xCD, 0x00, 0x6D,              # CALL 0x6D00
    ])
    
    rom[0x0100] = 0x00                              # NOP
    rom[0x0101:0x0104] = bytes([0xC3, 0x50, 0x01])  # JP 0x0150
    rom[0x0150:0x0150+len(entry)] = entry
    
    return rom

def main():
    print("🔧 Penta Dragon DX - Surgical Palette Patching")
    print("=" * 60)
    
    # Load ROM
    rom = bytearray(open("rom/Penta Dragon (J).gb", "rb").read())
    
    # Apply display patches
    rom, _ = apply_all_display_patches(rom)
    
    # Apply surgical NOPs to palette writes
    rom = apply_surgical_patches(rom)
    
    # Create boot-time CGB palette loader
    rom = create_boot_loader(rom)
    
    # Set CGB flag
    rom[0x143] = 0x80
    
    # Fix checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    # Write output
    output_path = "rom/working/penta_dragon_dx_WORKING.gb"
    with open(output_path, "wb") as f:
        f.write(rom)
    
    print(f"\n✅ Patched ROM created: {output_path}")
    print("\n📋 Applied changes:")
    print("  • NOPped all DMG palette writes (E0 47/48/49)")
    print("  • Boot-time CGB palette loader")
    print("  • OBJ0 = RED (player), OBJ1 = MAGENTA (monsters)")
    print("  • BG0 = GREEN (dungeon)")
    print("\n🎮 Game should run with distinct colors and no crashes!")

if __name__ == "__main__":
    main()
