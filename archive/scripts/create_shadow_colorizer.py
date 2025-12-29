#!/usr/bin/env python3
"""
Modify OAM SHADOW buffer (0xC000) instead of actual OAM (0xFE00).
The game uses OAM DMA to copy from shadow to actual OAM.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

def create_shadow_sprite_loop() -> bytes:
    """
    Modify shadow OAM at 0xC000 instead of actual OAM at 0xFE00.
    The game's OAM DMA will then copy our changes to actual OAM.
    """
    code = bytearray()

    # PUSH AF, BC, DE, HL
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # LD HL, 0xC003 (first sprite's flags byte in shadow OAM)
    code.extend([0x21, 0x03, 0xC0])

    # LD B, 40 (sprite count)
    code.extend([0x06, 0x28])

    # .loop:
    loop_start = len(code)

    # LD A, [HL] - get flags
    code.append(0x7E)

    # AND 0xF8 - clear palette bits
    code.extend([0xE6, 0xF8])

    # OR 0x01 - set palette 1
    code.extend([0xF6, 0x01])

    # LD [HL], A - write back
    code.append(0x77)

    # LD DE, 4 - offset to next sprite
    code.extend([0x11, 0x04, 0x00])

    # ADD HL, DE
    code.append(0x19)

    # DEC B
    code.append(0x05)

    # JR NZ, loop
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    # POP HL, DE, BC, AF
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])

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

    # Create sprite loop (targeting shadow OAM)
    sprite_loop = create_shadow_sprite_loop()

    # Combined function: palettes → original input → sprite loop (modifies shadow before DMA)
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
    print(f"  Targeting shadow OAM at 0xC000")
    print(f"  Sprite loop size: {len(sprite_loop)} bytes")

if __name__ == "__main__":
    main()
