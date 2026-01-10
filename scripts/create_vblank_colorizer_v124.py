#!/usr/bin/env python3
"""
v1.24: Position-Based BG Colorization (One-Shot, Stable)

Based on v1.22's stable one-shot approach, but with POSITION-BASED palettes
instead of uniform coloring. Sets different palettes for different screen regions:
- Top 2 rows (HUD): palette 0
- Left/right edges (walls): palette 2
- Center area (floor): palette 0
- Bottom area: palette 3

This gives visual variety without any runtime overhead.
The attributes are set ONCE during init and never touched again.

NO tile copy routine replacement - keeps original game code intact.
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


def create_position_attribute_map() -> bytes:
    """
    Create 1024-byte attribute map based on screen POSITION.

    Tilemap is 32x32 tiles, but visible area is ~20x18.
    Each byte is palette number (0-7).

    Layout (32 columns x 32 rows):
    - Row 0-1: HUD area - palette 0 (main colors)
    - Row 2-15, Col 0-1: Left wall - palette 2 (purple accent)
    - Row 2-15, Col 18-31: Right/offscreen - palette 2
    - Row 2-15, Col 2-17: Play area - palette 0 (main)
    - Row 16-17: Bottom area - palette 3 (green accent)
    - Row 18-31: Offscreen - palette 0
    """
    attr_map = bytearray(1024)

    for row in range(32):
        for col in range(32):
            idx = row * 32 + col

            if row < 2:
                # HUD - main palette
                attr_map[idx] = 0
            elif row < 16:
                # Main play area
                if col < 2 or col >= 18:
                    # Walls/edges - purple accent
                    attr_map[idx] = 2
                else:
                    # Floor - main palette
                    attr_map[idx] = 0
            elif row < 18:
                # Bottom visible area - green accent
                attr_map[idx] = 3
            else:
                # Offscreen
                attr_map[idx] = 0

    return bytes(attr_map)


def create_tile_based_colorizer() -> bytes:
    """OBJ colorizer (same as v1.09)."""
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
    """Colorizes BOTH shadow buffers."""
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
    """Load CGB palettes."""
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


def create_bg_init_from_map(init_flag_addr: int, attr_map_addr: int) -> bytes:
    """
    One-shot BG attribute initialization from pre-computed map.

    Copies 1024 bytes from attr_map to VRAM bank 1 at 0x9800.
    Uses GDMA for fast copy (not cycle-by-cycle).

    init_flag_addr: HRAM address for flag (e.g., 0xFFBD)
    attr_map_addr: ROM address of attribute map data
    """
    code = bytearray()
    init_flag_low = init_flag_addr & 0xFF

    # Check if already initialized
    code.extend([0xF0, init_flag_low])  # LDH A, [init_flag]
    code.append(0xB7)                   # OR A
    code.extend([0xC0])                 # RET NZ (already initialized)

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Switch to VRAM bank 1 (attributes)
    code.extend([0x3E, 0x01])           # LD A, 1
    code.extend([0xE0, 0x4F])           # LDH [VBK], A

    # Copy attribute map to tilemap 0 (0x9800)
    # Source: attr_map_addr in ROM (bank 13)
    # Dest: 0x9800 in VRAM bank 1
    # Use manual loop since GDMA source must be in RAM

    code.extend([0x21, attr_map_addr & 0xFF, (attr_map_addr >> 8) & 0xFF])  # LD HL, attr_map
    code.extend([0x11, 0x00, 0x98])     # LD DE, 0x9800
    code.extend([0x01, 0x00, 0x04])     # LD BC, 0x0400 (1024)

    # Copy loop
    loop_start = len(code)
    code.append(0x2A)                   # LD A, [HL+]
    code.append(0x12)                   # LD [DE], A
    code.append(0x13)                   # INC DE
    code.append(0x0B)                   # DEC BC
    code.append(0x78)                   # LD A, B
    code.append(0xB1)                   # OR C
    offset = loop_start - len(code) - 2
    code.extend([0x20, offset & 0xFF])  # JR NZ, loop_start

    # Also copy to tilemap 1 (0x9C00) for completeness
    code.extend([0x21, attr_map_addr & 0xFF, (attr_map_addr >> 8) & 0xFF])  # LD HL, attr_map
    code.extend([0x11, 0x00, 0x9C])     # LD DE, 0x9C00
    code.extend([0x01, 0x00, 0x04])     # LD BC, 0x0400

    loop2_start = len(code)
    code.append(0x2A)                   # LD A, [HL+]
    code.append(0x12)                   # LD [DE], A
    code.append(0x13)                   # INC DE
    code.append(0x0B)                   # DEC BC
    code.append(0x78)                   # LD A, B
    code.append(0xB1)                   # OR C
    offset2 = loop2_start - len(code) - 2
    code.extend([0x20, offset2 & 0xFF]) # JR NZ, loop2_start

    # Switch back to VRAM bank 0
    code.append(0xAF)                   # XOR A
    code.extend([0xE0, 0x4F])           # LDH [VBK], A

    # Set init flag
    code.extend([0x3E, 0x01])           # LD A, 1
    code.extend([0xE0, init_flag_low])  # LDH [init_flag], A

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)                   # RET

    return bytes(code)


def create_combined_with_bg_init(palette_loader_addr: int, shadow_main_addr: int, bg_init_addr: int) -> bytes:
    """Combined: load palettes, colorize OBJ shadows, one-shot BG init, run DMA."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, bg_init_addr & 0xFF, bg_init_addr >> 8])
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
    output_rom = Path("rom/working/penta_dragon_dx_v124.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.24: Position-Based BG Colorization ===")
    print("  BG palettes based on screen POSITION (not tile content)")
    print("  One-shot init during first VBlank")
    print("  No tile copy routine modification - fully stable")
    print("  OBJ colorization continues as normal (v1.09 approach)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Create position-based attribute map
    attr_map = create_position_attribute_map()

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    attr_map_addr = 0x6900  # 1024 bytes for position-based attributes
    obj_colorizer_addr = 0x6D00
    shadow_main_addr = 0x6D80
    palette_loader_addr = 0x6DE0
    bg_init_addr = 0x6E40
    combined_addr = 0x6EC0

    init_flag_addr = 0xFFBD

    obj_colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    bg_init = create_bg_init_from_map(init_flag_addr, attr_map_addr)
    combined = create_combined_with_bg_init(palette_loader_addr, shadow_main_addr, bg_init_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Attribute map: {len(attr_map)} bytes at 0x{attr_map_addr:04X}")
    print(f"OBJ colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"BG init: {len(bg_init)} bytes at 0x{bg_init_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (attr_map_addr - 0x4000):bank13_offset + (attr_map_addr - 0x4000) + len(attr_map)] = attr_map
    rom[bank13_offset + (obj_colorizer_addr - 0x4000):bank13_offset + (obj_colorizer_addr - 0x4000) + len(obj_colorizer)] = obj_colorizer
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (bg_init_addr - 0x4000):bank13_offset + (bg_init_addr - 0x4000) + len(bg_init)] = bg_init
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    # NOP out DMA at 0x06D5
    print(f"\nOriginal at 0x06D5: {rom[0x06D5:0x06D8].hex()}")
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    print("Patched 0x06D5: 00 00 00 (NOP)")

    # VBlank hook
    print(f"\nVBlank hook: {len(vblank_hook)} bytes at 0x0824")
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    # Set CGB flag
    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.24 Build Complete ===")


if __name__ == "__main__":
    main()
