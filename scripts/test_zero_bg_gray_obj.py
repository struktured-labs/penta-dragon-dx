#!/usr/bin/env python3
"""
Test: Zero BG init + Grayscale OBJ init + loop overwrite palette 4.
If this fails, the issue is grayscale OBJ init.
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palette4_from_yaml(yaml_path: Path) -> bytes:
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    hornets = data.get('obj_palettes', {}).get('Hornets', {})
    if hornets:
        result = bytearray()
        for c in hornets['colors']:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)
    return bytes([0x00, 0x00, 0xFF, 0x03, 0xDF, 0x00, 0x00, 0x00])


def create_test_loader(data_addr: int) -> bytes:
    code = bytearray()

    # BG palettes - ZEROS (like OVERWRITE_YAML)
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    for _ in range(64):
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x69])

    # OBJ palettes - GRAYSCALE (like LOOP8)
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    for _ in range(8):
        code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])  # trans
        code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0xFF]); code.extend([0xE0, 0x6B])  # white
        code.extend([0x3E, 0x7F]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x94]); code.extend([0xE0, 0x6B])  # gray
        code.extend([0x3E, 0x52]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x08]); code.extend([0xE0, 0x6B])  # dark
        code.extend([0x3E, 0x21]); code.extend([0xE0, 0x6B])

    # Loop overwrite palette 4
    code.extend([0x21, data_addr & 0xFF, (data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0xA0])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x08])
    loop_start = len(code)
    code.append(0x7E)
    code.extend([0xE0, 0x6B])
    code.append(0x23)
    code.append(0x0D)
    code.extend([0x20, (loop_start - len(code) - 2) & 0xFF])

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
    code.extend([0x20, (loop_start - len(code) - 2) & 0xFF])
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


def create_combined(palette_loader: int, colorizer_main: int) -> bytes:
    code = bytearray()
    code.extend([0xCD, palette_loader & 0xFF, palette_loader >> 8])
    code.extend([0xCD, colorizer_main & 0xFF, colorizer_main >> 8])
    code.extend([0xCD, 0x80, 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook(combined_addr: int) -> bytes:
    input_code = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, combined_addr & 0xFF, combined_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    return bytes(input_code + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_ZEROBG_GRAYOBJ.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print("=== Test: Zero BG + Grayscale OBJ init ===")

    pal4_data = load_palette4_from_yaml(palette_path)

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    data_addr = 0x0200
    rom[data_addr:data_addr + len(pal4_data)] = pal4_data

    # Use SAME addresses as OVERWRITE_YAML
    palette_loader_addr = 0x6800
    colorizer_addr = 0x6C00
    colorizer_main_addr = 0x6C20
    combined_addr = 0x6C50

    palette_loader = create_test_loader(data_addr)
    colorizer = create_force_palette4_colorizer()
    colorizer_main = create_shadow_colorizer_main(colorizer_addr)
    combined = create_combined(palette_loader_addr, colorizer_main_addr)
    vblank_hook = create_vblank_hook(combined_addr)

    print(f"Palette loader: {len(palette_loader)} bytes")

    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr: int, data: bytes):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(colorizer_addr, colorizer)
    write_to_bank13(colorizer_main_addr, colorizer_main)
    write_to_bank13(combined_addr, combined)

    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook
    rom[0x143] = 0x80

    output_rom.write_bytes(rom)
    print(f"Wrote: {output_rom}")
    print()
    print("If YELLOW: Grayscale OBJ init is OK, issue was elsewhere")
    print("If GRAY: Grayscale OBJ init breaks the loop")


if __name__ == "__main__":
    main()
