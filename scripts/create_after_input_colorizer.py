#!/usr/bin/env python3
"""
Run sprite palette assignment AFTER input handler only.
This ensures our OAM modifications happen last.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

def create_lookup_table() -> bytes:
    """Create 256-byte tile-to-palette lookup table"""
    table = bytearray([0xFF] * 256)
    
    # Demo monster 1 (tiles 8-15): Palette 1 (GREEN/ORANGE)
    for tile in range(8, 16):
        table[tile] = 1
    
    # Demo monster 2 (tiles 0-7): Palette 0 (RED)
    for tile in range(0, 8):
        table[tile] = 0
    
    # Demo monster 3 (tiles 32-47): Palette 2 (BLUE)
    for tile in range(32, 48):
        table[tile] = 2
        
    # Additional ranges
    for tile in range(20, 32):
        table[tile] = 3
    for tile in range(48, 64):
        table[tile] = 4
    for tile in range(64, 80):
        table[tile] = 5
    for tile in range(80, 96):
        table[tile] = 6
    for tile in range(96, 128):
        table[tile] = 7
    
    return bytes(table)

def create_sprite_loop_code(lookup_table_addr: int) -> bytes:
    """Create sprite loop that modifies OAM palette bits based on tile ID"""
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF
    
    code = bytearray()
    
    # PUSH all registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL
    
    # LD HL, 0xFE00 (OAM)
    code.extend([0x21, 0x00, 0xFE])
    
    # LD B, 40 (sprite count)
    code.extend([0x06, 0x28])
    
    # Loop start offset
    loop_start = len(code)
    
    # Get Y position
    code.append(0x7E)  # LD A, [HL]
    code.append(0xA7)  # AND A (check if 0)
    
    # Calculate skip offset (will be filled in)
    skip_jrz_pos = len(code)
    code.extend([0x28, 0x00])  # JR Z, skip (placeholder)
    
    code.extend([0xFE, 0xA0])  # CP 160
    skip_jrnc_pos = len(code)
    code.extend([0x30, 0x00])  # JR NC, skip (placeholder)
    
    # HL points to Y, advance to tile
    code.append(0x23)  # INC HL (X)
    code.append(0x23)  # INC HL (tile)
    code.append(0x7E)  # LD A, [HL] (get tile ID)
    code.append(0x23)  # INC HL (flags)
    code.append(0xE5)  # PUSH HL (save flags addr)
    
    # Look up palette from table
    code.append(0x5F)  # LD E, A (tile ID)
    code.extend([0x16, 0x00])  # LD D, 0
    code.extend([0x21, lo, hi])  # LD HL, lookup_table
    code.append(0x19)  # ADD HL, DE
    code.append(0x7E)  # LD A, [HL] (palette)
    
    # Check if 0xFF (no modify)
    code.extend([0xFE, 0xFF])  # CP 0xFF
    nomod_jr_pos = len(code)
    code.extend([0x28, 0x00])  # JR Z, no_modify (placeholder)
    
    # Apply palette
    code.append(0x57)  # LD D, A (save palette)
    code.append(0xE1)  # POP HL (flags addr)
    code.append(0x7E)  # LD A, [HL] (flags)
    code.extend([0xE6, 0xF8])  # AND 0xF8 (clear palette bits)
    code.append(0xB2)  # OR D (set palette)
    code.append(0x77)  # LD [HL], A
    next_jr_pos = len(code)
    code.extend([0x18, 0x00])  # JR next (placeholder)
    
    # no_modify:
    nomod_offset = len(code) - nomod_jr_pos - 2
    code[nomod_jr_pos + 1] = nomod_offset & 0xFF
    code.append(0xE1)  # POP HL
    
    # next/skip:
    skip_offset = len(code) - skip_jrz_pos - 2
    code[skip_jrz_pos + 1] = skip_offset & 0xFF
    skip_offset2 = len(code) - skip_jrnc_pos - 2
    code[skip_jrnc_pos + 1] = skip_offset2 & 0xFF
    next_offset = len(code) - next_jr_pos - 2
    code[next_jr_pos + 1] = next_offset & 0xFF
    
    # Calculate next sprite address
    code.extend([0x21, 0x00, 0xFE])  # LD HL, 0xFE00
    code.extend([0x3E, 0x28])  # LD A, 40
    code.append(0x90)  # SUB B
    code.append(0x3C)  # INC A
    code.append(0x87)  # ADD A, A (x2)
    code.append(0x87)  # ADD A, A (x4)
    code.append(0x5F)  # LD E, A
    code.extend([0x16, 0x00])  # LD D, 0
    code.append(0x19)  # ADD HL, DE
    
    # Loop back
    code.append(0x05)  # DEC B
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop
    
    # POP all registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET
    
    return bytes(code)

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    
    rom = bytearray(input_rom.read_bytes())
    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80  # CGB flag
    
    # Palette data
    def pal(colors):
        data = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            data.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(data)
    
    PALETTE_DATA_OFFSET = 0x036C80
    
    bg_palettes = (
        pal(["7FFF", "03E0", "0280", "0000"]) +  # Green theme
        pal(["7FFF", "5294", "2108", "0000"]) * 7
    )
    
    obj_palettes = (
        pal(["0000", "001F", "0010", "7FFF"]) +  # 0: RED - bright red, dark red, white
        pal(["0000", "03E0", "01A0", "7FFF"]) +  # 1: GREEN - bright green, dark green, white  
        pal(["0000", "7C00", "5000", "7FFF"]) +  # 2: BLUE
        pal(["0000", "03FF", "021F", "7FFF"]) +  # 3: CYAN/ORANGE
        pal(["0000", "7C1F", "5010", "7FFF"]) +  # 4: MAGENTA
        pal(["0000", "7FE0", "3CC0", "7FFF"]) +  # 5: YELLOW
        pal(["0000", "6318", "4210", "7FFF"]) +  # 6: GRAY
        pal(["0000", "7FFF", "5294", "2108"])    # 7: Default
    )
    
    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes
    
    # Lookup table at 0x6E00
    lookup_table = create_lookup_table()
    LOOKUP_TABLE_OFFSET = 0x036E00
    rom[LOOKUP_TABLE_OFFSET:LOOKUP_TABLE_OFFSET+256] = lookup_table
    
    # Save original input handler
    original_input = bytes(rom[0x0824:0x0824+46])
    
    # Create sprite loop
    sprite_loop = create_sprite_loop_code(0x6E00)
    
    # Combined function: palettes → original input → sprite loop (AFTER)
    combined = bytes([
        # Load BG palettes
        0x21, 0x80, 0x6C,  # LD HL, 0x6C80
        0x3E, 0x80,        # LD A, 0x80
        0xE0, 0x68,        # LDH [FF68], A
        0x0E, 0x40,        # LD C, 64
        0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,  # loop
        
        # Load OBJ palettes
        0x3E, 0x80,        # LD A, 0x80
        0xE0, 0x6A,        # LDH [FF6A], A
        0x0E, 0x40,        # LD C, 64
        0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,  # loop
    ]) + original_input + sprite_loop + bytes([0xC9])
    
    COMBINED_OFFSET = 0x036D00
    rom[COMBINED_OFFSET:COMBINED_OFFSET+len(combined)] = combined
    
    # Trampoline
    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20,  # switch to bank 13
        0xF1, 0xCD, 0x00, 0x6D,               # call combined
        0xF5, 0x3E, 0x01, 0xEA, 0x00, 0x20,  # restore bank 1
        0xF1, 0xC9
    ])
    
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    # Fix checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    
    print(f"✓ Created: {output_rom}")
    print(f"  Sprite loop runs AFTER original input handler")
    print(f"  Combined size: {len(combined)} bytes")

if __name__ == "__main__":
    main()
