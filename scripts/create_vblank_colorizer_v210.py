#!/usr/bin/env python3
"""
v2.10: Tile-Based BG Colorization

Builds on v2.09's working VBK mechanism.
Instead of filling all attributes with one palette, we now:
1. Read each tile from VBK 0 (tile map at 0x9800)
2. Look up the tile's palette in a 256-byte lookup table
3. Write the palette to VBK 1 (attributes)

This gives each tile type its own color palette!
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes, bytes, bytes]:
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


def create_tile_palette_lookup() -> bytes:
    """
    256-byte lookup table: tile_id -> BG palette

    Based on observed tile usage in Level 1:
    - 0x00-0x0F: Floor/platform tiles -> Palette 0 (blue dungeon)
    - 0x10-0x1F: Floor variants -> Palette 0
    - 0x20-0x3F: Wall tiles -> Palette 2 (purple walls)
    - 0x40-0x5F: Decorations -> Palette 2
    - 0x60-0x7F: Borders/edges -> Palette 2
    - 0x80-0x9F: Items/pickups -> Palette 1 (gold - makes items stand out!)
    - 0xA0-0xBF: More items -> Palette 1
    - 0xC0-0xDF: Special tiles -> Palette 1
    - 0xE0-0xFE: Edge/border tiles -> Palette 2
    - 0xFF: Empty/void -> Palette 0
    """
    lookup = bytearray(256)

    for i in range(256):
        if i < 0x20:
            # Floor tiles - palette 0 (blue dungeon)
            lookup[i] = 0
        elif i < 0x80:
            # Walls, decorations, borders - palette 2 (purple)
            lookup[i] = 2
        elif i < 0xE0:
            # Items, pickups, special - palette 1 (gold)
            lookup[i] = 1
        elif i == 0xFF:
            # Empty - palette 0
            lookup[i] = 0
        else:
            # Edge tiles - palette 2
            lookup[i] = 2

    return bytes(lookup)


def create_tile_based_colorizer() -> bytes:
    """OBJ colorizer from v1.09."""
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])
    labels['loop_start'] = len(code)
    code.extend([0x3E, 0x28])
    code.append(0x90)
    code.extend([0xFE, 0x04])
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])
    code.append(0x2B)
    code.append(0x7E)
    code.append(0x23)
    code.append(0x4F)
    code.extend([0xFE, 0x10])
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])
    code.append(0x7B)
    code.append(0xB7)
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])
    code.append(0x79)
    code.extend([0xFE, 0x50])
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x60])
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x70])
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x80])
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])
    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['check_hornet'] = len(code)
    code.append(0x79)
    code.extend([0xFE, 0x40])
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['sara_palette'] = len(code)
    code.append(0x7A)
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['boss_palette'] = len(code)
    code.extend([0x3E, 0x07])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])
    labels['apply_palette'] = len(code)
    code.append(0x4F)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.append(0xB1)
    code.append(0x77)
    code.extend([0x23, 0x23, 0x23, 0x23])
    code.append(0x05)
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)

    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])
    code.extend([0xF0, 0xBE])
    code.append(0xB7)
    code.extend([0x20, 0x04])
    code.extend([0x16, 0x02])
    code.extend([0x18, 0x02])
    code.extend([0x16, 0x01])
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
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)
    return bytes(code)


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Palette loader from v1.09."""
    code = bytearray()
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x0E, 0x40])
    code.extend([0x2A])
    code.extend([0xE0, 0x69])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])
    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x30])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x03])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])
    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x03])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])
    code.append(0xC9)
    return bytes(code)


def create_bg_colorizer(lookup_table_addr: int) -> bytes:
    """
    Tile-based BG colorization.

    For each tile in the visible screen area (20x18 = 360 tiles):
    1. Read tile ID from VBK 0 at 0x9800
    2. Look up palette in lookup table
    3. Write palette to VBK 1 at same address

    To fit in VBlank, we process a limited number of tiles per frame.
    For now, process just the first 256 tiles (first 8 rows) as a test.
    """
    code = bytearray()

    # HL = 0x9800 (VRAM tilemap)
    # DE = lookup table (in current bank)
    # BC = counter

    code.extend([0x21, 0x00, 0x98])        # LD HL, 0x9800
    code.extend([0x01, 0x00, 0x01])        # LD BC, 0x0100 (256 tiles = 8 rows)

    # Main loop - process each tile
    loop_start = len(code)

    # Make sure VBK = 0 before reading tile
    code.extend([0xAF])                    # XOR A
    code.extend([0xE0, 0x4F])              # LDH [VBK], A

    # Read tile ID
    code.append(0x7E)                      # LD A, [HL]

    # Save HL (VRAM address)
    code.append(0xE5)                      # PUSH HL

    # Look up palette: HL = lookup_table + tile_id
    code.extend([0x26, (lookup_table_addr >> 8) & 0xFF])  # LD H, high(lookup_table)
    code.append(0x6F)                      # LD L, A  (tile_id)
    code.append(0x7E)                      # LD A, [HL]  (palette from lookup)

    # Save palette in E
    code.append(0x5F)                      # LD E, A

    # Restore VRAM address
    code.append(0xE1)                      # POP HL

    # Switch to VBK 1 to write attribute
    code.extend([0x3E, 0x01])              # LD A, 1
    code.extend([0xE0, 0x4F])              # LDH [VBK], A

    # Write palette (from E)
    code.append(0x73)                      # LD [HL], E

    # Advance to next tile
    code.append(0x23)                      # INC HL

    # Decrement counter
    code.append(0x0B)                      # DEC BC
    code.append(0x78)                      # LD A, B
    code.append(0xB1)                      # OR C
    offset = loop_start - len(code) - 2
    code.extend([0x20, offset & 0xFF])     # JR NZ, loop_start

    # Switch back to VBK 0
    code.extend([0xAF])                    # XOR A
    code.extend([0xE0, 0x4F])              # LDH [VBK], A

    code.append(0xC9)                      # RET

    return bytes(code)


def create_combined_with_dma(
    palette_loader_addr: int,
    shadow_main_addr: int,
    bg_colorizer_addr: int
) -> bytes:
    """v1.09 combined + BG colorization."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # Sprite DMA
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
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
    output_rom = Path("rom/working/penta_dragon_dx_v210.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v2.10: Tile-Based BG Colorization ===")
    print("  Each BG tile gets palette based on tile ID:")
    print("    Floor (0x00-0x1F) -> Palette 0 (blue)")
    print("    Walls (0x20-0x7F) -> Palette 2 (purple)")
    print("    Items (0x80-0xDF) -> Palette 1 (gold)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Memory layout in bank 13:
    palette_data_addr = 0x6800      # 64 bytes BG + 48 bytes OBJ
    gargoyle_addr = 0x6880          # 8 bytes
    spider_addr = 0x6888            # 8 bytes
    colorizer_addr = 0x6900         # ~100 bytes (OBJ colorizer)
    shadow_main_addr = 0x6980       # ~50 bytes
    palette_loader_addr = 0x69E0    # ~80 bytes
    bg_colorizer_addr = 0x6A40      # ~50 bytes (NEW)
    lookup_table_addr = 0x6B00      # 256 bytes (NEW)
    combined_addr = 0x6C00          # ~15 bytes

    colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    bg_colorizer = create_bg_colorizer(lookup_table_addr)
    lookup_table = create_tile_palette_lookup()
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"BG colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")
    print(f"Lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X}")
    print(f"Combined: {len(combined)} bytes at 0x{combined_addr:04X}")

    bank13_offset = 13 * 0x4000

    def bank_offset(addr):
        return bank13_offset + (addr - 0x4000)

    rom[bank_offset(palette_data_addr):bank_offset(palette_data_addr) + len(bg_data)] = bg_data
    rom[bank_offset(palette_data_addr) + 64:bank_offset(palette_data_addr) + 64 + len(obj_data)] = obj_data
    rom[bank_offset(gargoyle_addr):bank_offset(gargoyle_addr) + len(gargoyle)] = gargoyle
    rom[bank_offset(spider_addr):bank_offset(spider_addr) + len(spider)] = spider
    rom[bank_offset(colorizer_addr):bank_offset(colorizer_addr) + len(colorizer)] = colorizer
    rom[bank_offset(shadow_main_addr):bank_offset(shadow_main_addr) + len(shadow_main)] = shadow_main
    rom[bank_offset(palette_loader_addr):bank_offset(palette_loader_addr) + len(palette_loader)] = palette_loader
    rom[bank_offset(bg_colorizer_addr):bank_offset(bg_colorizer_addr) + len(bg_colorizer)] = bg_colorizer
    rom[bank_offset(lookup_table_addr):bank_offset(lookup_table_addr) + len(lookup_table)] = lookup_table
    rom[bank_offset(combined_addr):bank_offset(combined_addr) + len(combined)] = combined

    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook
    rom[0x143] = 0x80

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v2.10 Build Complete ===")


if __name__ == "__main__":
    main()
