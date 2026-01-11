#!/usr/bin/env python3
"""
Test: Write hardcoded BLUE palette, then try to overwrite with loop-based YELLOW.
If result is BLUE: loop writes don't work at all.
If result is YELLOW: loop writes work!
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def create_overwrite_loader(yellow_data_addr: int) -> bytes:
    """
    Step 1: Write BLUE to palette 4 (hardcoded)
    Step 2: Overwrite palette 4 with YELLOW (loop from memory)
    """
    code = bytearray()

    # First write BG palettes (required based on FULLHARD)
    code.extend([0x3E, 0x80])  # LD A, 0x80
    code.extend([0xE0, 0x68])  # LDH [BCPS], A
    for _ in range(64):  # 64 bytes of BG palette data
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x69])

    # STEP 1: Write BLUE to ALL OBJ palettes (hardcoded)
    code.extend([0x3E, 0x80])  # LD A, 0x80 (OCPS auto-increment, start at 0)
    code.extend([0xE0, 0x6A])  # LDH [OCPS], A

    for pal in range(8):
        # Color 0: transparent (00 00)
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x6B])
        # Color 1: BLUE (E0 7F = 0x7FE0 = pure blue in BGR555)
        code.extend([0x3E, 0xE0])
        code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x7F])
        code.extend([0xE0, 0x6B])
        # Color 2: dark blue (C0 3C)
        code.extend([0x3E, 0xC0])
        code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x3C])
        code.extend([0xE0, 0x6B])
        # Color 3: black (00 00)
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x6B])

    # STEP 2: Try to overwrite with YELLOW using loop
    # Point HL to yellow palette data (8 bytes for palette 4)
    code.extend([0x21, yellow_data_addr & 0xFF, (yellow_data_addr >> 8) & 0xFF])

    # Set OCPS to palette 4 start (4 * 8 = 32 = 0x20, with auto-inc = 0xA0)
    code.extend([0x3E, 0xA0])  # OCPS = 0xA0 (auto-increment + index 32)
    code.extend([0xE0, 0x6A])

    # Write 8 bytes (palette 4 only)
    code.extend([0x0E, 0x08])  # LD C, 8
    loop_start = len(code)
    code.append(0x7E)          # LD A, [HL]
    code.extend([0xE0, 0x6B])  # LDH [OCPD], A
    code.append(0x23)          # INC HL
    code.append(0x0D)          # DEC C
    offset = loop_start - len(code) - 2
    code.extend([0x20, offset & 0xFF])

    code.append(0xC9)
    return bytes(code)


def create_force_palette4_colorizer() -> bytes:
    code = bytearray()
    code.extend([0x06, 0x28])
    loop_start = len(code)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.extend([0xF6, 0x04])
    code.append(0x77)
    code.extend([0x23, 0x23, 0x23, 0x23])
    code.append(0x05)
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int) -> bytes:
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook(combined_func_addr: int) -> bytes:
    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    return bytes(simplified_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_OVERWRITE.gb")

    print("=== Overwrite test: Hardcoded BLUE -> Loop YELLOW ===")
    print("If BLUE: loop doesn't work. If YELLOW: loop works!")

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Yellow palette data (8 bytes for palette 4)
    # Colors: trans, yellow, orange, black
    yellow_data = bytes([
        0x00, 0x00,  # Color 0: transparent
        0xFF, 0x03,  # Color 1: YELLOW (0x03FF)
        0xDF, 0x00,  # Color 2: orange (0x00DF)
        0x00, 0x00,  # Color 3: black
    ])

    bank0_data_addr = 0x0200
    rom[bank0_data_addr:bank0_data_addr + len(yellow_data)] = yellow_data

    palette_loader_addr = 0x6800
    colorizer_addr = 0x6C00  # After the larger palette loader
    shadow_main_addr = 0x6C20
    combined_addr = 0x6C50

    palette_loader = create_overwrite_loader(bank0_data_addr)
    colorizer = create_force_palette4_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr)
    vblank_hook = create_vblank_hook(combined_addr)

    print(f"Palette loader: {len(palette_loader)} bytes")

    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr: int, data: bytes):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(colorizer_addr, colorizer)
    write_to_bank13(shadow_main_addr, shadow_main)
    write_to_bank13(combined_addr, combined)

    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook
    rom[0x143] = 0x80

    output_rom.write_bytes(rom)
    print(f"Wrote: {output_rom}")


if __name__ == "__main__":
    main()
