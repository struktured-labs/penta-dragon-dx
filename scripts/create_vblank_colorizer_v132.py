#!/usr/bin/env python3
"""
v1.32: Fixed address layout + hardcoded palette initialization

Key fixes:
1. Colorizer at 0x6C00 (required for savestate compatibility)
2. Hardcoded palette initialization before loop loading (required for palette hardware)
3. Other routines can be at any address

Address layout:
- 0x6800: Palette data (128 bytes)
- 0x6880: Boss palettes (16 bytes)
- 0x6890: Palette loader routine (with hardcoded init)
- 0x6C00: Tile-based colorizer (MUST BE HERE)
- 0x6C80: Shadow colorizer main
- 0x6CC0: Combined function
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes, bytes, bytes]:
    """Load BG, OBJ, and boss palettes from YAML file."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors: list[str]) -> bytes:
        result = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)

    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_tile_based_colorizer() -> bytes:
    """
    Tile-based colorizer with boss/miniboss override.
    MUST BE PLACED AT 0x6C00 for savestate compatibility.
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # LD B, 40
    code.extend([0x06, 0x28])
    labels['loop_start'] = len(code)

    # Check if Sara slot (0-3)
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B
    code.extend([0xFE, 0x04])        # CP 4
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])        # JR C, sara_palette

    # Read tile
    code.append(0x2B)                # DEC HL
    code.append(0x7E)                # LD A, [HL]
    code.append(0x23)                # INC HL
    code.append(0x4F)                # LD C, A

    # Check projectile
    code.extend([0xFE, 0x10])        # CP 0x10
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])        # JR C, projectile_palette

    # Check boss mode
    code.append(0x7B)                # LD A, E
    code.append(0xB7)                # OR A
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])        # JR NZ, boss_palette

    # Normal mode: tile-based
    code.append(0x79)                # LD A, C

    # Hornets 0x40-0x4F
    code.extend([0xFE, 0x50])
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])

    # Orcs 0x50-0x5F
    code.extend([0xFE, 0x60])
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])

    # Humanoids 0x60-0x6F
    code.extend([0xFE, 0x70])
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])

    # Miniboss 0x70-0x7F
    code.extend([0xFE, 0x80])
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])

    # Default palette 4
    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # check_hornet
    labels['check_hornet'] = len(code)
    code.append(0x79)
    code.extend([0xFE, 0x40])
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # sara_palette
    labels['sara_palette'] = len(code)
    code.append(0x7A)
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # projectile_palette
    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # boss_palette
    labels['boss_palette'] = len(code)
    code.extend([0x3E, 0x07])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # hornet_palette
    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # orc_palette
    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # humanoid_palette
    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # miniboss_palette
    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])

    # apply_palette
    labels['apply_palette'] = len(code)
    code.append(0x4F)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.append(0xB1)
    code.append(0x77)

    # Next sprite
    code.extend([0x23, 0x23, 0x23, 0x23])
    code.append(0x05)
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)

    # Fix jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Colorizes BOTH shadow buffers."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Determine Sara palette
    code.extend([0xF0, 0xBE])
    code.append(0xB7)
    code.extend([0x20, 0x04])
    code.extend([0x16, 0x02])
    code.extend([0x18, 0x02])
    code.extend([0x16, 0x01])

    # Boss flag
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x28, 0x08])
    code.extend([0xFE, 0x02])
    code.extend([0x28, 0x06])
    code.extend([0x1E, 0x00])
    code.extend([0x18, 0x06])
    code.extend([0x1E, 0x06])
    code.extend([0x18, 0x02])
    code.extend([0x1E, 0x07])

    # Colorize buffers
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)
    return bytes(code)


def create_palette_loader_with_init(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """
    Palette loader with HARDCODED INITIALIZATION before loop loading.
    This is required for palette hardware to work correctly.
    """
    code = bytearray()

    # === HARDCODED BG INITIALIZATION (zeros) ===
    code.extend([0x3E, 0x80])        # LD A, 0x80
    code.extend([0xE0, 0x68])        # LDH [BCPS], A
    for _ in range(64):
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x69])

    # === HARDCODED OBJ INITIALIZATION (grayscale) ===
    code.extend([0x3E, 0x80])        # LD A, 0x80
    code.extend([0xE0, 0x6A])        # LDH [OCPS], A
    for _ in range(8):
        code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])  # trans
        code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0xFF]); code.extend([0xE0, 0x6B])  # white
        code.extend([0x3E, 0x7F]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x94]); code.extend([0xE0, 0x6B])  # gray
        code.extend([0x3E, 0x52]); code.extend([0xE0, 0x6B])
        code.extend([0x3E, 0x08]); code.extend([0xE0, 0x6B])  # dark
        code.extend([0x3E, 0x21]); code.extend([0xE0, 0x6B])

    # === NOW LOOP-BASED LOADING OF ACTUAL PALETTES ===

    # Load BG palettes (64 bytes)
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x0E, 0x40])
    loop1_start = len(code)
    code.append(0x2A)
    code.extend([0xE0, 0x69])
    code.append(0x0D)
    code.extend([0x20, (loop1_start - len(code) - 2) & 0xFF])

    # Load OBJ palettes 0-5 (48 bytes)
    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x30])
    loop2_start = len(code)
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x0D)
    code.extend([0x20, (loop2_start - len(code) - 2) & 0xFF])

    # Palette 6: Check for Gargoyle
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x03])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    loop3_start = len(code)
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x0D)
    code.extend([0x20, (loop3_start - len(code) - 2) & 0xFF])

    # Palette 7: Check for Spider
    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x03])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    loop4_start = len(code)
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x0D)
    code.extend([0x20, (loop4_start - len(code) - 2) & 0xFF])

    code.append(0xC9)
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int) -> bytes:
    """Combined function: load palettes, colorize shadows, run DMA."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook at 0x0824."""
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
    output_rom = Path("rom/working/penta_dragon_dx_v132.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.32: Fixed Address Layout + Hardcoded Init ===")
    print("  Key fixes:")
    print("    1. Colorizer at 0x6C00 (savestate compatibility)")
    print("    2. Hardcoded palette init before loop loading")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Address layout - colorizer MUST be at 0x6C00
    palette_data_addr = 0x6800      # BG + OBJ palettes
    gargoyle_addr = 0x6880          # Boss palettes
    spider_addr = 0x6888
    palette_loader_addr = 0x6890    # Before colorizer
    colorizer_addr = 0x6C00         # MUST BE HERE
    shadow_main_addr = 0x6C80       # After colorizer
    combined_addr = 0x6CC0          # After shadow_main

    colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    palette_loader = create_palette_loader_with_init(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Check sizes
    if len(colorizer) > 0x80:
        print(f"WARNING: Colorizer too large ({len(colorizer)} bytes), max 128")
    if palette_loader_addr + len(palette_loader) > colorizer_addr:
        print(f"ERROR: Palette loader overlaps colorizer!")
        return

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr: int, data: bytes):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    # Write palette data
    write_to_bank13(palette_data_addr, bg_data)
    write_to_bank13(palette_data_addr + 64, obj_data)
    write_to_bank13(gargoyle_addr, gargoyle)
    write_to_bank13(spider_addr, spider)

    # Write code
    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(colorizer_addr, colorizer)
    write_to_bank13(shadow_main_addr, shadow_main)
    write_to_bank13(combined_addr, combined)

    # NOP out original DMA
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])

    # Write VBlank hook
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    # Set CGB flag
    rom[0x143] = 0x80

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.32 Build Complete ===")


if __name__ == "__main__":
    main()
