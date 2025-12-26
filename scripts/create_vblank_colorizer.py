#!/usr/bin/env python3
"""
VBlank-based colorization with tile-to-palette lookup table.
Based on OAM analysis showing:
- First demo monster: tiles 0x08-0x0F (8-15) 
- Second demo monster: tiles 0x00-0x07 (0-7)
- Third demo monster: tiles 0x20-0x2F (32-47)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

def create_lookup_table() -> bytes:
    """Create 256-byte tile-to-palette lookup table"""
    table = bytearray([0xFF] * 256)  # 0xFF = don't modify
    
    # Based on OAM analysis of demo sequence:
    # First monster (tiles 8-15): Palette 1 (Sara W - Green/Orange)
    for tile in range(8, 16):
        table[tile] = 1
    
    # Second monster (tiles 0-7): Palette 0 (Sara D - Red/Black) 
    for tile in range(0, 8):
        table[tile] = 0
    
    # Third monster (tiles 32-47): Palette 2 (DragonFly - Blue/White)
    for tile in range(32, 48):
        table[tile] = 2
        
    # Additional monsters observed in tile_ids.txt
    # tiles 20-31 seen
    for tile in range(20, 32):
        table[tile] = 3
    
    # tiles 48-63 seen  
    for tile in range(48, 64):
        table[tile] = 4
        
    # tiles 64-79
    for tile in range(64, 80):
        table[tile] = 5
        
    # tiles 80-95
    for tile in range(80, 96):
        table[tile] = 6
        
    # tiles 96-127
    for tile in range(96, 128):
        table[tile] = 7
    
    return bytes(table)

def create_sprite_loop_code(lookup_table_addr: int) -> bytes:
    """Create optimized sprite loop assembly code"""
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF
    
    return bytes([
        # PUSH AF, BC, DE, HL
        0xF5, 0xC5, 0xD5, 0xE5,
        
        # LD HL, 0xFE00 (OAM base)
        0x21, 0x00, 0xFE,
        
        # LD B, 40 (sprite count)
        0x06, 0x28,
        
        # .loop:
        # LD A, [HL] (Y position)
        0x7E,
        # AND A
        0xA7,
        # JR Z, .skip (Y=0 means unused)
        0x28, 0x1C,  # +28 bytes forward
        # CP 160
        0xFE, 0xA0,
        # JR NC, .skip (off screen)
        0x30, 0x18,  # +24 bytes forward
        
        # INC HL (skip X)
        0x23,
        # INC HL (point to tile ID)
        0x23,
        # LD A, [HL] (get tile ID)
        0x7E,
        # INC HL (point to flags)
        0x23,
        # PUSH HL (save flags address)
        0xE5,
        
        # Lookup: HL = table + tile_id
        # LD E, A
        0x5F,
        # LD D, 0
        0x16, 0x00,
        # LD HL, lookup_table_addr
        0x21, lo, hi,
        # ADD HL, DE
        0x19,
        # LD A, [HL] (get palette)
        0x7E,
        
        # CP 0xFF (check if should modify)
        0xFE, 0xFF,
        # JR Z, .no_modify
        0x28, 0x09,  # +9 bytes forward
        
        # Apply palette to flags
        # LD D, A (save palette)
        0x57,
        # POP HL (get flags address)
        0xE1,
        # LD A, [HL] (get flags)
        0x7E,
        # AND 0xF8 (clear palette bits)
        0xE6, 0xF8,
        # OR D (set palette)
        0xB2,
        # LD [HL], A (write back)
        0x77,
        # JR .next
        0x18, 0x01,  # +1 byte forward
        
        # .no_modify:
        # POP HL
        0xE1,
        
        # .skip / .next:
        # LD HL, 0xFE00 (reset to base)
        0x21, 0x00, 0xFE,
        # LD A, 40
        0x3E, 0x28,
        # SUB B (A = sprite index)
        0x90,
        # INC A
        0x3C,
        # ADD A, A (x2)
        0x87,
        # ADD A, A (x4)
        0x87,
        # LD E, A
        0x5F,
        # LD D, 0
        0x16, 0x00,
        # ADD HL, DE
        0x19,
        
        # DEC B
        0x05,
        # JR NZ, .loop
        0x20, 0xD2,  # jump back
        
        # POP HL, DE, BC, AF
        0xE1, 0xD1, 0xC1, 0xF1,
        # RET
        0xC9,
    ])

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    
    if not input_rom.exists():
        print(f"ERROR: ROM not found: {input_rom}")
        sys.exit(1)
    
    rom = bytearray(input_rom.read_bytes())
    
    # Apply display patches (prevents white screen freeze)
    print("Applying display patches...")
    rom, _ = apply_all_display_patches(rom)
    
    # Set CGB flag
    rom[0x143] = 0x80
    
    # Palette data in Bank 13 @ 0x6C80 (file offset 0x036C80)
    PALETTE_DATA_OFFSET = 0x036C80
    
    # Define palettes (BGR555 format)
    def pal(colors):
        data = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            data.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(data)
    
    # BG palettes (8 x 8 bytes = 64 bytes)
    bg_palettes = (
        pal(["7FFF", "03E0", "0280", "0000"]) +  # 0: Dungeon - green
        pal(["7FFF", "5294", "2108", "0000"]) +  # 1-7: Default grayscale
        pal(["7FFF", "5294", "2108", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"])
    )
    
    # OBJ palettes with distinct colors per monster type
    obj_palettes = (
        pal(["0000", "001F", "0010", "0008"]) +  # 0: Sara D - RED
        pal(["0000", "03E0", "03FF", "021F"]) +  # 1: Sara W - GREEN/ORANGE  
        pal(["0000", "7C00", "5000", "7FFF"]) +  # 2: DragonFly - BLUE/WHITE
        pal(["0000", "7FE0", "03E0", "0010"]) +  # 3: Yellow/Green
        pal(["0000", "7C1F", "5010", "3008"]) +  # 4: Magenta
        pal(["0000", "03FF", "021F", "0010"]) +  # 5: Cyan/Orange
        pal(["0000", "6318", "4210", "2108"]) +  # 6: Gray tones
        pal(["0000", "7FFF", "5294", "2108"])    # 7: Default
    )
    
    # Write palette data
    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes
    
    # Create lookup table
    lookup_table = create_lookup_table()
    
    # Layout in Bank 13:
    # 0x6C80: Palette data (128 bytes)
    # 0x6D00: Combined function
    # 0x6E00: Lookup table (256 bytes)
    
    LOOKUP_TABLE_OFFSET = 0x036E00
    LOOKUP_TABLE_ADDR = 0x6E00  # Bank 13 address
    
    rom[LOOKUP_TABLE_OFFSET:LOOKUP_TABLE_OFFSET+256] = lookup_table
    
    # Save original input handler (46 bytes at 0x0824)
    original_input = bytes(rom[0x0824:0x0824+46])
    
    # Create sprite loop code
    sprite_loop = create_sprite_loop_code(LOOKUP_TABLE_ADDR)
    
    # Combined function: Load palettes + sprite loop + original input
    combined = bytes([
        # Load BG palettes
        0x21, 0x80, 0x6C,  # LD HL, 0x6C80
        0x3E, 0x80,        # LD A, 0x80 (auto-increment)
        0xE0, 0x68,        # LDH [FF68], A (BCPS)
        0x0E, 0x40,        # LD C, 64
        # .bg_loop:
        0x2A,              # LD A, [HL+]
        0xE0, 0x69,        # LDH [FF69], A (BCPD)
        0x0D,              # DEC C
        0x20, 0xFA,        # JR NZ, .bg_loop
        
        # Load OBJ palettes
        0x3E, 0x80,        # LD A, 0x80
        0xE0, 0x6A,        # LDH [FF6A], A (OCPS)
        0x0E, 0x40,        # LD C, 64
        # .obj_loop:
        0x2A,              # LD A, [HL+]
        0xE0, 0x6B,        # LDH [FF6B], A (OCPD)
        0x0D,              # DEC C  
        0x20, 0xFA,        # JR NZ, .obj_loop
    ]) + sprite_loop + original_input + bytes([0xC9])
    
    COMBINED_OFFSET = 0x036D00
    rom[COMBINED_OFFSET:COMBINED_OFFSET+len(combined)] = combined
    
    # Trampoline at 0x0824
    trampoline = bytes([
        0xF5,              # PUSH AF
        0x3E, 0x0D,        # LD A, 13
        0xEA, 0x00, 0x20,  # LD [2000], A (switch to bank 13)
        0xF1,              # POP AF
        0xCD, 0x00, 0x6D,  # CALL 0x6D00
        0xF5,              # PUSH AF
        0x3E, 0x01,        # LD A, 1
        0xEA, 0x00, 0x20,  # LD [2000], A (restore bank 1)
        0xF1,              # POP AF
        0xC9,              # RET
    ])
    
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    # Pad with NOPs
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    # Fix header checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    # Write output
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    
    mapped_tiles = sum(1 for x in lookup_table if x != 0xFF)
    print(f"\n✓ Created: {output_rom}")
    print(f"  Lookup table: {mapped_tiles}/256 tiles mapped")
    print(f"  Combined function: {len(combined)} bytes")
    print(f"  Tile mappings:")
    print(f"    Tiles 0-7   → Palette 0 (RED)")
    print(f"    Tiles 8-15  → Palette 1 (GREEN/ORANGE)")  
    print(f"    Tiles 32-47 → Palette 2 (BLUE/WHITE)")
    print(f"    Tiles 20-31 → Palette 3")
    print(f"    Tiles 48-127 → Palettes 4-7")

if __name__ == "__main__":
    main()
