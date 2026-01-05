#!/usr/bin/env python3
"""
v1.11: Same as v1.10 (BG item colorization WIP)

BG item colorization attempted but disabled due to:
  - Game resets BG tile attributes, overwriting our changes
  - Scanning 1024 tiles per frame exceeds VBlank timing
  - Need O(1) solution: hook game's tile write routine instead

Item tiles identified for future work:
  - 0x88-0x9F: Potions, turbo powerup
  - 0xA8-0xBF: Health, extra life, flash
  - 0xC8-0xDF: Rock, dragon powerup

OBJ Tile-based coloring (same as v1.10):
  - 0x00-0x0F: Effects/projectiles (palette 0)
  - 0x20-0x27: Sara W (palette 2)
  - 0x28-0x2F: Sara D (palette 1)
  - 0x30-0x3F: Crow (palette 3)
  - 0x40-0x4F: Hornets (palette 4)
  - 0x50-0x5F: Orcs (palette 5)
  - 0x60-0x6F: Humanoids (palette 6)
  - 0x70-0x7F: Miniboss (palette 7)

Boss detection via 0xFFBF with DYNAMIC palette swapping:
  - 0xFFBF = 1 → Load Gargoyle colors into palette 6, all enemies use it
  - 0xFFBF = 2 → Load Spider colors into palette 7, all enemies use it
  - 0xFFBF = 0 → Normal tile-based coloring with standard palettes
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
    (Same as v1.10 - handles OBJ sprites)
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])  # LD B, 40
    labels['loop_start'] = len(code)

    # Check if Sara slot (0-3)
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B
    code.extend([0xFE, 0x04])        # CP 4
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])        # JR C, sara_palette

    # Read tile (at HL-1)
    code.append(0x2B)                # DEC HL
    code.append(0x7E)                # LD A, [HL]
    code.append(0x23)                # INC HL
    code.append(0x4F)                # LD C, A

    # Check projectile (tile < 0x10)
    code.extend([0xFE, 0x10])        # CP 0x10
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])        # JR C, projectile_palette

    # Check boss/miniboss mode
    code.append(0x7B)                # LD A, E
    code.append(0xB7)                # OR A
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])        # JR NZ, boss_palette

    # Normal mode: tile-based
    code.append(0x79)                # LD A, C

    code.extend([0xFE, 0x50])        # CP 0x50
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])        # JR C, check_hornet

    code.extend([0xFE, 0x60])        # CP 0x60
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])        # JR C, orc_palette

    code.extend([0xFE, 0x70])        # CP 0x70
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])        # JR C, humanoid_palette

    code.extend([0xFE, 0x80])        # CP 0x80
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])        # JR C, miniboss_palette

    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['check_hornet'] = len(code)
    code.append(0x79)                # LD A, C
    code.extend([0xFE, 0x40])        # CP 0x40
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])        # JR NC, hornet_palette

    code.extend([0xFE, 0x30])        # CP 0x30
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x30, 0x00])        # JR NC, crow_palette

    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])        # LD A, 3
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['sara_palette'] = len(code)
    code.append(0x7A)                # LD A, D
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])        # LD A, 0
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['boss_palette'] = len(code)
    code.extend([0x3E, 0x07])        # LD A, 7
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])        # LD A, 5
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])        # LD A, 6
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])        # LD A, 7

    labels['apply_palette'] = len(code)
    code.append(0x4F)                # LD C, A
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB1)                # OR C
    code.append(0x77)                # LD [HL], A

    code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4
    code.append(0x05)                # DEC B
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop_start
    code.append(0xC9)                # RET

    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_bg_item_colorizer() -> bytes:
    """
    Scan BG tilemap and set palette 1 for item tiles (0x88-0xDF).

    OPTIMIZED: Only scans 256 tiles (16x16 area) to fit in VBlank.
    For tiles >= 0x88 and < 0xE0, set BG attribute to palette 1.

    VRAM bank 0: tile IDs
    VRAM bank 1: attributes (bits 0-2 = palette)
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Scan a fixed 16x16 region (256 tiles) - much faster than 1024
    # Start at row 4 (0x9800 + 4*32 = 0x9880) to cover typical play area
    # LD HL, 0x9880 (start at row 4)
    code.extend([0x21, 0x80, 0x98])

    # LD B, 16 (16 rows)
    code.extend([0x06, 0x10])

    # row_loop:
    labels['row_loop'] = len(code)

    # LD C, 20 (20 columns - visible width)
    code.extend([0x0E, 0x14])

    # col_loop:
    labels['col_loop'] = len(code)

    # Switch to VRAM bank 0 to read tile ID
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK)

    # LD A, [HL] - read tile ID
    code.append(0x7E)

    # Check if tile >= 0x88 (item range start)
    code.extend([0xFE, 0x88])        # CP 0x88
    jumps_to_fix.append((len(code), 'next_col'))
    code.extend([0x38, 0x00])        # JR C, next_col

    # Check if tile < 0xE0 (item range end)
    code.extend([0xFE, 0xE0])        # CP 0xE0
    jumps_to_fix.append((len(code), 'next_col'))
    code.extend([0x30, 0x00])        # JR NC, next_col

    # It's an item tile! Switch to VRAM bank 1 and set palette
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK = 1)

    # Read current attribute, set palette bits to 1
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8 (clear palette bits)
    code.extend([0xF6, 0x01])        # OR 0x01 (set palette 1)
    code.append(0x77)                # LD [HL], A

    # next_col:
    labels['next_col'] = len(code)
    code.append(0x23)                # INC HL
    code.append(0x0D)                # DEC C
    jumps_to_fix.append((len(code), 'col_loop'))
    code.extend([0x20, 0x00])        # JR NZ, col_loop

    # End of row - skip remaining 12 tiles to next row (32-20=12)
    code.extend([0x11, 0x0C, 0x00])  # LD DE, 12
    code.append(0x19)                # ADD HL, DE

    code.append(0x05)                # DEC B
    jumps_to_fix.append((len(code), 'row_loop'))
    code.extend([0x20, 0x00])        # JR NZ, row_loop

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    code.append(0xC9)                # RET

    # Fix all jump offsets
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Colorizes BOTH shadow buffers (0xC000 and 0xC100)."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Determine Sara palette (D)
    code.extend([0xF0, 0xBE])        # LDH A, [FFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Dragon)
    code.extend([0x16, 0x02])        # LD D, 2 (Witch)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Dragon)

    # Check boss flag
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.extend([0xFE, 0x01])        # CP 1
    code.extend([0x28, 0x08])        # JR Z, +8 (Gargoyle)
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x28, 0x06])        # JR Z, +6 (Spider)
    code.extend([0x1E, 0x00])        # LD E, 0 (normal)
    code.extend([0x18, 0x06])        # JR +6
    code.extend([0x1E, 0x06])        # LD E, 6 (Gargoyle)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x1E, 0x07])        # LD E, 7 (Spider)

    # Colorize shadow buffer 1
    code.extend([0x21, 0x03, 0xC0])  # LD HL, 0xC003
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Colorize shadow buffer 2
    code.extend([0x21, 0x03, 0xC1])  # LD HL, 0xC103
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)                # RET
    return bytes(code)


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Load CGB palettes with dynamic boss palette swapping."""
    code = bytearray()

    # Load BG palettes (64 bytes)
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])        # LD A, 0x80
    code.extend([0xE0, 0x68])        # LDH [FF68], A
    code.extend([0x0E, 0x40])        # LD C, 64
    code.extend([0x2A])              # LD A, [HL+]
    code.extend([0xE0, 0x69])        # LDH [FF69], A
    code.extend([0x0D])              # DEC C
    code.extend([0x20, 0xFA])        # JR NZ, bg_loop

    # Load OBJ palettes 0-5 (48 bytes)
    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])        # LD A, 0x80
    code.extend([0xE0, 0x6A])        # LDH [FF6A], A
    code.extend([0x0E, 0x30])        # LD C, 48
    code.extend([0x2A])              # LD A, [HL+]
    code.extend([0xE0, 0x6B])        # LDH [FF6B], A
    code.extend([0x0D])              # DEC C
    code.extend([0x20, 0xFA])        # JR NZ, obj_loop1

    # Palette 6: Check for Gargoyle
    code.extend([0xF0, 0xBF])        # LDH A, [FFBF]
    code.extend([0xFE, 0x01])        # CP 1
    code.extend([0x20, 0x03])        # JR NZ, +3
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])        # LD C, 8
    code.extend([0x2A])              # LD A, [HL+]
    code.extend([0xE0, 0x6B])        # LDH [FF6B], A
    code.extend([0x0D])              # DEC C
    code.extend([0x20, 0xFA])        # JR NZ, pal6_loop

    # Palette 7: Check for Spider
    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])        # LDH A, [FFBF]
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x20, 0x03])        # JR NZ, +3
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])        # LD C, 8
    code.extend([0x2A])              # LD A, [HL+]
    code.extend([0xE0, 0x6B])        # LDH [FF6B], A
    code.extend([0x0D])              # DEC C
    code.extend([0x20, 0xFA])        # JR NZ, pal7_loop

    code.append(0xC9)                # RET
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """
    Combined function: load palettes, colorize shadows, run DMA.

    NOTE: BG item colorization disabled for now - game resets BG attributes
    and scanning every frame causes performance issues. Need to hook game's
    tile write routine for O(1) item colorization.
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    # BG colorizer disabled: code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # CALL DMA
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook at 0x0824 with input handler."""
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
    output_rom = Path("rom/working/penta_dragon_dx_v111.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.11: Background Item Colorization ===")
    print("  NEW: BG tiles 0x88-0xDF (items) -> BG palette 1 (gold)")
    print("  Item tiles: potions, powerups, extra lives, etc.")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    colorizer_addr = 0x6900
    bg_colorizer_addr = 0x6990  # NEW: BG item colorizer
    shadow_main_addr = 0x69D0
    palette_loader_addr = 0x6A30
    combined_addr = 0x6AB0

    colorizer = create_tile_based_colorizer()
    bg_colorizer = create_bg_item_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"OBJ Colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"BG Colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (colorizer_addr - 0x4000):bank13_offset + (colorizer_addr - 0x4000) + len(colorizer)] = colorizer
    rom[bank13_offset + (bg_colorizer_addr - 0x4000):bank13_offset + (bg_colorizer_addr - 0x4000) + len(bg_colorizer)] = bg_colorizer
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    print(f"\nOriginal at 0x06D5: {rom[0x06D5:0x06D8].hex()}")
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    print("Patched 0x06D5: 00 00 00 (NOP)")

    print(f"\nVBlank hook: {len(vblank_hook)} bytes")
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.11 Build Complete ===")


if __name__ == "__main__":
    main()
