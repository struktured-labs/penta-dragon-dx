#!/usr/bin/env python3
"""
Stable tile-based palette colorizer.
Reads the active shadow buffer flag and only modifies the correct buffer.
This should eliminate flickering caused by race conditions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

def create_lookup_table() -> bytes:
    """Create 256-byte tile-to-palette lookup table."""
    table = bytearray([0xFF] * 256)  # 0xFF = don't modify

    # Monster 1 - SARA W (tiles 8-15): Palette 1 (GREEN)
    for tile in range(8, 16):
        table[tile] = 1

    # Monster 2 - SARA D (tiles 0-7): Palette 0 (RED)
    for tile in range(0, 8):
        table[tile] = 0

    # Monster 3 - DRAGONFLY (tiles 32-47): Palette 2 (BLUE)
    for tile in range(32, 48):
        table[tile] = 2

    # Additional tile ranges
    for tile in range(16, 20):
        table[tile] = 3
    for tile in range(20, 32):
        table[tile] = 4
    for tile in range(48, 64):
        table[tile] = 5
    for tile in range(64, 96):
        table[tile] = 6
    for tile in range(96, 128):
        table[tile] = 7

    return bytes(table)

def create_stable_sprite_loop(lookup_table_addr: int) -> bytes:
    """
    Create sprite loop that only modifies actual OAM (0xFE00).
    Since we run AFTER DMA in VBlank, modifying actual OAM should be stable.
    The game won't touch actual OAM until the next frame's DMA.
    """
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    code = bytearray()

    # PUSH AF, BC, DE, HL
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Only modify actual OAM at 0xFE00 (not shadow buffers)
    # This runs after DMA, so our changes persist until next frame's DMA

    # LD HL, 0xFE00 (actual OAM)
    code.extend([0x21, 0x00, 0xFE])

    # LD B, 40
    code.extend([0x06, 0x28])

    # .loop:
    loop_start = len(code)

    # LD A, [HL] - Y position
    code.append(0x7E)

    # AND A - check if 0
    code.append(0xA7)

    # JR Z, .next_sprite
    skip_jrz = len(code)
    code.extend([0x28, 0x00])

    # CP 160
    code.extend([0xFE, 0xA0])

    # JR NC, .next_sprite
    skip_jrnc = len(code)
    code.extend([0x30, 0x00])

    # Sprite visible - get tile ID
    code.append(0x23)  # INC HL (X)
    code.append(0x23)  # INC HL (tile)
    code.append(0x5E)  # LD E, [HL] - tile ID
    code.append(0x23)  # INC HL (flags)

    # Save flags address
    code.append(0xE5)  # PUSH HL

    # Lookup palette
    code.extend([0x16, 0x00])  # LD D, 0
    code.extend([0x21, lo, hi])  # LD HL, lookup_table
    code.append(0x19)  # ADD HL, DE
    code.append(0x7E)  # LD A, [HL]

    # Restore flags address
    code.append(0xE1)  # POP HL

    # Check if 0xFF
    code.extend([0xFE, 0xFF])
    skip_modify = len(code)
    code.extend([0x28, 0x00])

    # Apply palette
    code.append(0x57)  # LD D, A
    code.append(0x7E)  # LD A, [HL]
    code.extend([0xE6, 0xF8])  # AND 0xF8
    code.append(0xB2)  # OR D
    code.append(0x77)  # LD [HL], A

    # .skip_modify:
    skip_modify_target = len(code)
    code[skip_modify + 1] = (skip_modify_target - skip_modify - 2) & 0xFF

    # INC HL to next Y
    code.append(0x23)

    # JR .dec_b
    jr_to_dec = len(code)
    code.extend([0x18, 0x00])

    # .next_sprite:
    next_sprite = len(code)
    code[skip_jrz + 1] = (next_sprite - skip_jrz - 2) & 0xFF
    code[skip_jrnc + 1] = (next_sprite - skip_jrnc - 2) & 0xFF

    # Skip 4 bytes
    code.extend([0x23, 0x23, 0x23, 0x23])

    # .dec_b:
    dec_b = len(code)
    code[jr_to_dec + 1] = (dec_b - jr_to_dec - 2) & 0xFF

    code.append(0x05)  # DEC B
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    # Now also update the CURRENT shadow buffer (the one that will be used next frame)
    # Read FFCB to determine which buffer (0 = 0xC000, 1 = 0xC100)
    code.extend([0xF0, 0xCB])  # LDH A, [FFCB]
    code.extend([0xE6, 0x01])  # AND 1
    code.extend([0xC6, 0xC0])  # ADD 0xC0 (A = 0xC0 or 0xC1)
    code.append(0x67)  # LD H, A (H = 0xC0 or 0xC1)
    code.extend([0x2E, 0x00])  # LD L, 0

    # LD B, 40
    code.extend([0x06, 0x28])

    # Second loop for shadow buffer
    loop2_start = len(code)

    code.append(0x7E)  # LD A, [HL]
    code.append(0xA7)  # AND A
    skip2_jrz = len(code)
    code.extend([0x28, 0x00])

    code.extend([0xFE, 0xA0])  # CP 160
    skip2_jrnc = len(code)
    code.extend([0x30, 0x00])

    code.append(0x23)  # INC HL
    code.append(0x23)  # INC HL
    code.append(0x5E)  # LD E, [HL]
    code.append(0x23)  # INC HL

    code.append(0xE5)  # PUSH HL
    code.extend([0x16, 0x00])
    code.extend([0x21, lo, hi])
    code.append(0x19)
    code.append(0x7E)
    code.append(0xE1)  # POP HL

    code.extend([0xFE, 0xFF])
    skip2_modify = len(code)
    code.extend([0x28, 0x00])

    code.append(0x57)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.append(0xB2)
    code.append(0x77)

    skip2_modify_target = len(code)
    code[skip2_modify + 1] = (skip2_modify_target - skip2_modify - 2) & 0xFF

    code.append(0x23)
    jr2_to_dec = len(code)
    code.extend([0x18, 0x00])

    next2_sprite = len(code)
    code[skip2_jrz + 1] = (next2_sprite - skip2_jrz - 2) & 0xFF
    code[skip2_jrnc + 1] = (next2_sprite - skip2_jrnc - 2) & 0xFF

    code.extend([0x23, 0x23, 0x23, 0x23])

    dec2_b = len(code)
    code[jr2_to_dec + 1] = (dec2_b - jr2_to_dec - 2) & 0xFF

    code.append(0x05)
    loop2_offset = loop2_start - len(code) - 2
    code.extend([0x20, loop2_offset & 0xFF])

    # POP HL, DE, BC, AF
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)

    return bytes(code)

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")

    rom = bytearray(input_rom.read_bytes())
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80

    def pal(colors):
        data = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            data.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(data)

    PALETTE_DATA_OFFSET = 0x036C80

    bg_palettes = (
        pal(["7FFF", "03E0", "0280", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) * 7
    )

    obj_palettes = (
        pal(["0000", "001F", "0010", "7FFF"]) +  # 0: RED
        pal(["0000", "03E0", "01A0", "7FFF"]) +  # 1: GREEN
        pal(["0000", "7C00", "5000", "7FFF"]) +  # 2: BLUE
        pal(["0000", "03FF", "021F", "7FFF"]) +  # 3: CYAN
        pal(["0000", "7C1F", "5010", "7FFF"]) +  # 4: MAGENTA
        pal(["0000", "7FE0", "3CC0", "7FFF"]) +  # 5: YELLOW
        pal(["0000", "6318", "4210", "7FFF"]) +  # 6: GRAY
        pal(["0000", "7FFF", "5294", "2108"])    # 7: Default
    )

    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes

    lookup_table = create_lookup_table()
    LOOKUP_TABLE_OFFSET = 0x036E00
    LOOKUP_TABLE_ADDR = 0x6E00
    rom[LOOKUP_TABLE_OFFSET:LOOKUP_TABLE_OFFSET+256] = lookup_table

    sprite_loop = create_stable_sprite_loop(LOOKUP_TABLE_ADDR)
    print(f"Sprite loop size: {len(sprite_loop)} bytes")

    combined = bytes([
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40,
        0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40,
        0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
    ]) + original_input + sprite_loop + bytes([0xC9])

    COMBINED_OFFSET = 0x036D00
    rom[COMBINED_OFFSET:COMBINED_OFFSET+len(combined)] = combined

    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xF1, 0xCD, 0x00, 0x6D,
        0xF5, 0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xF1, 0xC9
    ])

    rom[0x0824:0x0824+len(trampoline)] = trampoline
    rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))

    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    print(f"✓ Created: {output_rom}")
    print(f"  Stable approach: actual OAM + active shadow buffer only")
    print(f"  Combined function: {len(combined)} bytes")

if __name__ == "__main__":
    main()
