#!/usr/bin/env python3
"""
v1.36: Edge-based BG colorization (O(edge) not O(screen))

Key insight: Only NEW tiles need coloring when scrolling.
Instead of updating entire screen, update EDGES where new tiles appear:
- Top row (20 tiles) - catches downward scroll
- Bottom row (20 tiles) - catches upward scroll
- Left column (18 tiles) - catches rightward scroll
- Right column (18 tiles) - catches leftward scroll

Total: ~76 tiles/frame vs 360, with BATCHED bank switching for speed.

Tile ranges:
- 0x00-0x3F: Floor/basic tiles → palette 0
- 0x40-0x7F: Wall tiles → palette 2 (purple/blue)
- 0x80-0x9F: Hazard/spike tiles → palette 3 (green)
- 0xA0-0xDF: Item tiles → palette 1 (gold)
- 0xE0-0xFF: Special/decorative → palette 0
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
    """Create 256-byte lookup table: tile_id → palette number."""
    lookup = bytearray(256)
    for i in range(256):
        if 0x40 <= i < 0x80:
            lookup[i] = 2  # Walls → purple
        elif 0x80 <= i < 0xA0:
            lookup[i] = 3  # Hazards → green
        elif 0xA0 <= i < 0xE0:
            lookup[i] = 1  # Items → gold
        else:
            lookup[i] = 0  # Floor/default
    return bytes(lookup)


def create_tile_based_colorizer() -> bytes:
    """Sprite colorizer - MUST BE AT 0x6C00."""
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


def create_bg_colorizer(lookup_table_addr: int, temp_buffer_addr: int) -> bytes:
    """
    Edge-based BG colorizer with BATCHED bank switching.

    Updates visible screen edges (top row + bottom row = 40 tiles).
    Uses temp buffer to batch reads before writes, minimizing bank switches.

    Algorithm:
    1. Read SCY/SCX to get visible area
    2. BATCH: Read top row tile IDs, lookup palettes, store in buffer
    3. BATCH: Read bottom row tile IDs, lookup palettes, store in buffer
    4. Switch to bank 1 ONCE
    5. BATCH: Write all attributes from buffer
    6. Switch back to bank 0

    This reduces bank switches from 80 to 2!
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # ===== PHASE 1: Read tile IDs and lookup palettes (bank 0) =====
    code.extend([0x3E, 0x00])  # LD A, 0
    code.extend([0xE0, 0x4F])  # LDH [VBK], A - stay in bank 0

    # Calculate top visible row: SCY / 8
    code.extend([0xF0, 0x42])  # LDH A, [SCY]
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A - A = top row (0-31)
    code.extend([0xE6, 0x1F])  # AND 0x1F (wrap)

    # Calculate tilemap address for top row: 0x9800 + row * 32
    code.append(0x87)  # ADD A, A (x2)
    code.append(0x87)  # ADD A, A (x4)
    code.append(0x87)  # ADD A, A (x8)
    code.append(0x87)  # ADD A, A (x16)
    code.append(0x87)  # ADD A, A (x32) - A = row * 32 (low byte)
    code.append(0x6F)  # LD L, A
    code.extend([0x26, 0x98])  # LD H, 0x98
    # Add SCX / 8 for horizontal offset
    code.extend([0xF0, 0x43])  # LDH A, [SCX]
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A - A = left col (0-31)
    code.extend([0xE6, 0x1F])  # AND 0x1F
    code.append(0x85)  # ADD A, L
    code.append(0x6F)  # LD L, A
    # Now HL = tilemap addr of top-left visible tile

    # DE = temp buffer
    code.extend([0x11, temp_buffer_addr & 0xFF, (temp_buffer_addr >> 8) & 0xFF])

    # B = lookup table high byte
    code.extend([0x06, (lookup_table_addr >> 8) & 0xFF])

    # Read 20 tiles from top row, lookup palettes, store in buffer
    code.extend([0x0E, 0x14])  # LD C, 20
    top_loop = len(code)
    code.append(0x7E)          # LD A, [HL] - tile ID
    code.append(0xE5)          # PUSH HL
    code.append(0x6F)          # LD L, A
    code.append(0x60)          # LD H, B - HL = lookup + tile
    code.append(0x7E)          # LD A, [HL] - palette
    code.append(0xE1)          # POP HL
    code.append(0x12)          # LD [DE], A - store palette in buffer
    code.append(0x13)          # INC DE
    code.append(0x2C)          # INC L (next tile, wraps within row)
    code.append(0x0D)          # DEC C
    code.extend([0x20, (top_loop - len(code) - 2) & 0xFF])

    # Calculate bottom row address (top + 17 rows = +544 bytes)
    # Recalculate from SCY + 17*8 = SCY + 136
    code.extend([0xF0, 0x42])  # LDH A, [SCY]
    code.extend([0xC6, 0x88])  # ADD A, 136 (17 rows * 8 pixels)
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xCB, 0x3F])  # SRL A
    code.extend([0xE6, 0x1F])  # AND 0x1F
    code.append(0x87)  # x32
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x6F)  # LD L, A
    code.extend([0x26, 0x98])  # LD H, 0x98
    code.extend([0xF0, 0x43])  # LDH A, [SCX]
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xE6, 0x1F])
    code.append(0x85)
    code.append(0x6F)

    # Read 20 tiles from bottom row
    code.extend([0x0E, 0x14])  # LD C, 20
    bottom_loop = len(code)
    code.append(0x7E)
    code.append(0xE5)
    code.append(0x6F)
    code.append(0x60)
    code.append(0x7E)
    code.append(0xE1)
    code.append(0x12)
    code.append(0x13)
    code.append(0x2C)
    code.append(0x0D)
    code.extend([0x20, (bottom_loop - len(code) - 2) & 0xFF])

    # ===== PHASE 2: Write attributes (bank 1) =====
    code.extend([0x3E, 0x01])  # LD A, 1
    code.extend([0xE0, 0x4F])  # LDH [VBK], A - switch to bank 1 ONCE

    # Reset to top row address
    code.extend([0xF0, 0x42])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xE6, 0x1F])
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x6F)
    code.extend([0x26, 0x98])
    code.extend([0xF0, 0x43])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xE6, 0x1F])
    code.append(0x85)
    code.append(0x6F)

    # DE = buffer start
    code.extend([0x11, temp_buffer_addr & 0xFF, (temp_buffer_addr >> 8) & 0xFF])

    # Write 20 attributes to top row
    code.extend([0x0E, 0x14])
    write_top = len(code)
    code.append(0x1A)          # LD A, [DE]
    code.append(0x77)          # LD [HL], A
    code.append(0x13)          # INC DE
    code.append(0x2C)          # INC L
    code.append(0x0D)
    code.extend([0x20, (write_top - len(code) - 2) & 0xFF])

    # Calculate bottom row address again
    code.extend([0xF0, 0x42])
    code.extend([0xC6, 0x88])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xE6, 0x1F])
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x87)
    code.append(0x6F)
    code.extend([0x26, 0x98])
    code.extend([0xF0, 0x43])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xCB, 0x3F])
    code.extend([0xE6, 0x1F])
    code.append(0x85)
    code.append(0x6F)

    # Write 20 attributes to bottom row
    code.extend([0x0E, 0x14])
    write_bottom = len(code)
    code.append(0x1A)
    code.append(0x77)
    code.append(0x13)
    code.append(0x2C)
    code.append(0x0D)
    code.extend([0x20, (write_bottom - len(code) - 2) & 0xFF])

    # Switch back to bank 0
    code.extend([0x3E, 0x00])
    code.extend([0xE0, 0x4F])

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)

    return bytes(code)


def create_onetime_init(init_done_flag: int) -> bytes:
    """
    Hybrid palette initialization:
    - Hardcode ONE full palette to prime the hardware
    - Use loops for the remaining palettes
    This is compact but still initializes the hardware properly.
    """
    code = bytearray()

    # === BG palettes ===
    code.extend([0x3E, 0x80])  # LD A, 0x80 (auto-increment)
    code.extend([0xE0, 0x68])  # LDH [BCPS], A

    # Hardcode first palette (8 bytes) to prime hardware
    for _ in range(8):
        code.extend([0x3E, 0x00])
        code.extend([0xE0, 0x69])

    # Loop for remaining 56 bytes (7 palettes)
    code.extend([0x06, 0x38])  # LD B, 56
    code.append(0xAF)          # XOR A
    bg_loop = len(code)
    code.extend([0xE0, 0x69])  # LDH [BCPD], A
    code.append(0x05)          # DEC B
    code.extend([0x20, (bg_loop - len(code) - 2) & 0xFF])

    # === OBJ palettes ===
    code.extend([0x3E, 0x80])  # LD A, 0x80 (auto-increment)
    code.extend([0xE0, 0x6A])  # LDH [OCPS], A

    # Hardcode first palette (8 bytes) to prime hardware
    code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])  # trans lo
    code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])  # trans hi
    code.extend([0x3E, 0xFF]); code.extend([0xE0, 0x6B])  # white lo
    code.extend([0x3E, 0x7F]); code.extend([0xE0, 0x6B])  # white hi
    code.extend([0x3E, 0x94]); code.extend([0xE0, 0x6B])  # gray lo
    code.extend([0x3E, 0x52]); code.extend([0xE0, 0x6B])  # gray hi
    code.extend([0x3E, 0x08]); code.extend([0xE0, 0x6B])  # dark lo
    code.extend([0x3E, 0x21]); code.extend([0xE0, 0x6B])  # dark hi

    # Loop grayscale pattern for remaining 7 palettes
    code.extend([0x06, 0x07])  # LD B, 7
    obj_loop = len(code)
    code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x00]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0xFF]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x7F]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x94]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x52]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x08]); code.extend([0xE0, 0x6B])
    code.extend([0x3E, 0x21]); code.extend([0xE0, 0x6B])
    code.append(0x05)          # DEC B
    code.extend([0x20, (obj_loop - len(code) - 2) & 0xFF])

    # Set init done flag
    code.extend([0x3E, 0x01])
    code.extend([0xE0, init_done_flag & 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_fast_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int,
                                init_routine_addr: int, init_done_flag: int) -> bytes:
    """Fast palette loader with one-time init check."""
    code = bytearray()

    code.extend([0xF0, init_done_flag & 0xFF])
    code.append(0xB7)
    code.extend([0x20, 0x03])
    code.extend([0xCD, init_routine_addr & 0xFF, init_routine_addr >> 8])

    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x0E, 0x40])
    loop1_start = len(code)
    code.append(0x2A)
    code.extend([0xE0, 0x69])
    code.append(0x0D)
    code.extend([0x20, (loop1_start - len(code) - 2) & 0xFF])

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

    pal6_normal_addr = obj_data_addr + 48
    code.extend([0x21, pal6_normal_addr & 0xFF, (pal6_normal_addr >> 8) & 0xFF])
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


def create_combined_with_bg(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """Combined function with BG colorization."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])
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
    output_rom = Path("rom/working/penta_dragon_dx_v136.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.36: Edge-Based BG Colorization ===")
    print("  Updates top+bottom rows (40 tiles) with batched bank switching")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Address layout (all code before 0x6C00 except colorizer)
    # Lookup table at 0x6B00 (ends at 0x6C00, just before colorizer)
    palette_data_addr = 0x6800     # 128 bytes (64 BG + 64 OBJ), ends at 0x6880
    gargoyle_addr = 0x6880         # 8 bytes, ends at 0x6888
    spider_addr = 0x6888           # 8 bytes, ends at 0x6890
    init_routine_addr = 0x6890     # ~122 bytes (hybrid), ends at ~0x690A
    palette_loader_addr = 0x6910   # 79 bytes, ends at 0x695F
    bg_colorizer_addr = 0x6960     # ~200 bytes (edge-based), ends at ~0x6A28
    shadow_main_addr = 0x6A30      # 52 bytes, ends at 0x6A64
    combined_addr = 0x6A70         # 13 bytes, ends at 0x6A7D
    lookup_table_addr = 0x6B00     # 256 bytes (ALIGNED!), ends at 0x6C00
    colorizer_addr = 0x6C00        # 90 bytes, MUST BE HERE
    temp_buffer_addr = 0xCF00      # 64 bytes in WRAM for edge palettes

    init_done_flag = 0xC0   # HRAM 0xFFC0

    lookup_table = create_tile_palette_lookup()
    onetime_init = create_onetime_init(init_done_flag)
    palette_loader = create_fast_palette_loader(palette_data_addr, gargoyle_addr, spider_addr,
                                                 init_routine_addr, init_done_flag)
    colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    bg_colorizer = create_bg_colorizer(lookup_table_addr, temp_buffer_addr)
    combined = create_combined_with_bg(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X}")
    print(f"One-time init: {len(onetime_init)} bytes at 0x{init_routine_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Sprite colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"BG colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")
    print(f"Temp buffer: 64 bytes at 0x{temp_buffer_addr:04X}")
    print(f"Combined: {len(combined)} bytes at 0x{combined_addr:04X}")

    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr: int, data: bytes):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    write_to_bank13(palette_data_addr, bg_data)
    write_to_bank13(palette_data_addr + 64, obj_data)
    write_to_bank13(gargoyle_addr, gargoyle)
    write_to_bank13(spider_addr, spider)
    write_to_bank13(lookup_table_addr, lookup_table)
    write_to_bank13(init_routine_addr, onetime_init)
    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(colorizer_addr, colorizer)
    write_to_bank13(shadow_main_addr, shadow_main)
    write_to_bank13(bg_colorizer_addr, bg_colorizer)
    write_to_bank13(combined_addr, combined)

    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook
    rom[0x143] = 0x80

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")


if __name__ == "__main__":
    main()
