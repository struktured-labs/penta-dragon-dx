#!/usr/bin/env python3
"""
Modify ACTUAL OAM (0xFE00) after DMA runs.
Since our code runs AFTER OAM DMA in VBlank, modifying 0xFE00 should persist
until the next frame's DMA.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

def create_actual_oam_sprite_loop() -> bytes:
    """
    Modify actual OAM at 0xFE00 (not shadow at 0xC000).
    Force ALL visible sprites to palette 1 unconditionally.
    """
    code = bytearray()

    # PUSH AF, BC, HL
    code.extend([0xF5, 0xC5, 0xE5])

    # LD HL, 0xFE00 (actual OAM, start at Y of sprite 0)
    code.extend([0x21, 0x00, 0xFE])

    # LD B, 40 (sprite count)
    code.extend([0x06, 0x28])

    # .loop:
    loop_start = len(code)

    # Check if sprite visible (Y != 0 and Y < 160)
    # LD A, [HL] - get Y
    code.append(0x7E)

    # AND A - test if 0
    code.append(0xA7)

    # JR Z, .next (skip if Y=0)
    skip_jrz = len(code)
    code.extend([0x28, 0x00])  # placeholder

    # CP 160
    code.extend([0xFE, 0xA0])

    # JR NC, .next (skip if Y >= 160)
    skip_jrnc = len(code)
    code.extend([0x30, 0x00])  # placeholder

    # Visible sprite - modify palette in flags byte
    # INC HL (X)
    code.append(0x23)
    # INC HL (tile)
    code.append(0x23)
    # INC HL (flags)
    code.append(0x23)

    # LD A, [HL] - get flags
    code.append(0x7E)

    # AND 0xF8 - clear palette bits
    code.extend([0xE6, 0xF8])

    # OR 0x01 - set palette 1
    code.extend([0xF6, 0x01])

    # LD [HL], A - write back
    code.append(0x77)

    # Now advance to next sprite (HL points to flags, need to add 1 to get to next Y)
    # INC HL
    code.append(0x23)

    # JR .dec_b
    jr_to_dec = len(code)
    code.extend([0x18, 0x00])  # placeholder

    # .next (for skipped sprites):
    next_pos = len(code)
    # Fix jump offsets for skip jumps
    code[skip_jrz + 1] = (next_pos - skip_jrz - 2) & 0xFF
    code[skip_jrnc + 1] = (next_pos - skip_jrnc - 2) & 0xFF

    # Advance HL by 4 to next sprite
    # INC HL (X)
    code.append(0x23)
    # INC HL (tile)
    code.append(0x23)
    # INC HL (flags)
    code.append(0x23)
    # INC HL (next Y)
    code.append(0x23)

    # .dec_b:
    dec_b_pos = len(code)
    code[jr_to_dec + 1] = (dec_b_pos - jr_to_dec - 2) & 0xFF

    # DEC B
    code.append(0x05)

    # JR NZ, .loop
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    # POP HL, BC, AF
    code.extend([0xE1, 0xC1, 0xF1])

    # RET
    code.append(0xC9)

    return bytes(code)

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")

    rom = bytearray(input_rom.read_bytes())

    # Save original input handler BEFORE any patches
    original_input = bytes(rom[0x0824:0x0824+46])

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
        pal(["7FFF", "03E0", "0280", "0000"]) +
        pal(["7FFF", "5294", "2108", "0000"]) * 7
    )

    obj_palettes = (
        pal(["0000", "001F", "0010", "7FFF"]) +  # 0: RED
        pal(["0000", "03E0", "01A0", "7FFF"]) +  # 1: GREEN - target
        pal(["0000", "7C00", "5000", "7FFF"]) +  # 2: BLUE
        pal(["0000", "03FF", "021F", "7FFF"]) +  # 3: CYAN
        pal(["0000", "7C1F", "5010", "7FFF"]) +  # 4: MAGENTA
        pal(["0000", "7FE0", "3CC0", "7FFF"]) +  # 5: YELLOW
        pal(["0000", "6318", "4210", "7FFF"]) +  # 6: GRAY
        pal(["0000", "7FFF", "5294", "2108"])    # 7: Default
    )

    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes

    # Create sprite loop (targeting ACTUAL OAM)
    sprite_loop = create_actual_oam_sprite_loop()

    print(f"Sprite loop bytes: {sprite_loop.hex()}")
    print(f"Sprite loop size: {len(sprite_loop)}")

    # Combined function: palettes → original input → sprite loop
    combined = bytes([
        # Load BG palettes
        0x21, 0x80, 0x6C,
        0x3E, 0x80,
        0xE0, 0x68,
        0x0E, 0x40,
        0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,

        # Load OBJ palettes
        0x3E, 0x80,
        0xE0, 0x6A,
        0x0E, 0x40,
        0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
    ]) + original_input + sprite_loop + bytes([0xC9])

    COMBINED_OFFSET = 0x036D00
    rom[COMBINED_OFFSET:COMBINED_OFFSET+len(combined)] = combined

    # Trampoline
    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xF1, 0xCD, 0x00, 0x6D,
        0xF5, 0x3E, 0x01, 0xEA, 0x00, 0x20,
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
    print(f"  Targeting ACTUAL OAM at 0xFE00")
    print(f"  Combined function: {len(combined)} bytes")

if __name__ == "__main__":
    main()
