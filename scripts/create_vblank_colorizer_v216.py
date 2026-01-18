#!/usr/bin/env python3
"""
v2.16: Fixed Sara corruption + reduced BG flicker

FIXES from v2.15:
1. Sara sprite corruption - Use TILE-BASED detection for ALL sprites,
   not slot-based. Sara's tiles are 0x20-0x2F regardless of OAM slot.
2. BG flicker reduction - Process 3 rows per frame instead of 1,
   reducing full-screen colorization time from 18 frames to 6 frames.

OBJ tile ranges (purely tile-based):
- 0x00-0x1F: Effects/projectiles -> Palette 0 (white/gray)
- 0x20-0x27: Sara Witch -> Palette 2 (skin/pink)
- 0x28-0x2F: Sara Dragon -> Palette 1 (green)
- 0x30-0x3F: Crow -> Palette 3 (dark blue)
- 0x40-0x4F: Hornets -> Palette 4 (yellow/orange)
- 0x50-0x5F: Orcs -> Palette 5 (green/brown)
- 0x60-0x6F: Humanoid -> Palette 6 (purple)
- 0x70-0x7F: Special -> Palette 3 (cyan)
- 0x80+: Use palette 7

BG tile ranges:
- 0x00-0x1F: Floor -> Palette 0 (blue)
- 0x20-0x7F: Walls -> Palette 2 (purple)
- 0x80-0xDF: Items -> Palette 1 (gold)
- 0xE0-0xFF: Borders -> Palette 2 (purple)
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
            obj_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    gargoyle = pal_to_bytes(data['obj_palettes'].get('Gargoyle', {}).get('colors', ["7FFF", "5294", "2108", "0000"]))
    spider = pal_to_bytes(data['obj_palettes'].get('Spider', {}).get('colors', ["7FFF", "5294", "2108", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_tile_palette_lookup() -> bytes:
    """256-byte lookup table: tile_id -> BG palette"""
    lookup = bytearray(256)

    for i in range(256):
        if i < 0x20:
            lookup[i] = 0  # Floor -> Palette 0 (blue)
        elif i < 0x80:
            lookup[i] = 2  # Walls -> Palette 2 (purple)
        elif i < 0xE0:
            lookup[i] = 1  # Items -> Palette 1 (gold)
        elif i == 0xFF:
            lookup[i] = 0  # Void -> Palette 0
        else:
            lookup[i] = 2  # Borders -> Palette 2

    return bytes(lookup)


def create_tile_based_colorizer_v216() -> bytes:
    """
    Tile-based OBJ colorizer with boss support.

    Uses D register (Sara palette from main) and E register (boss override).
    Tile-based Sara detection instead of slot-based (fixes corruption).

    Tile ranges:
    - 0x00-0x1F: Effects -> palette 0
    - 0x20-0x2F: Sara -> palette from D register (1=dragon, 2=witch)
    - 0x30-0x3F: Crow -> palette 3
    - 0x40-0x4F: Hornets -> palette 4
    - 0x50-0x5F: Orcs -> palette 5
    - 0x60-0x6F: Humanoid -> palette 6
    - 0x70-0x7F: Special -> palette 3
    - 0x80+: Default -> palette 4
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Loop counter: 40 sprites
    code.extend([0x06, 0x28])              # LD B, 40

    labels['loop_start'] = len(code)

    # Read tile ID: HL-1 points to tile, HL points to flags
    code.append(0x2B)                      # DEC HL
    code.append(0x7E)                      # LD A, [HL] (tile ID)
    code.append(0x23)                      # INC HL (back to flags)
    code.append(0x4F)                      # LD C, A (save tile in C)

    # Check for effects (0x00-0x1F)
    code.extend([0xFE, 0x20])              # CP 0x20
    jumps_to_fix.append((len(code), 'effects_palette'))
    code.extend([0x38, 0x00])              # JR C, effects_palette

    # Check for Sara (0x20-0x2F) - USE D REGISTER for palette!
    code.extend([0xFE, 0x30])              # CP 0x30
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])              # JR C, sara_palette

    # Check boss override (E != 0 means all enemies use boss palette)
    code.append(0x7B)                      # LD A, E
    code.append(0xB7)                      # OR A
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])              # JR NZ, boss_palette

    # Normal enemy path - check tile ranges
    code.append(0x79)                      # LD A, C (restore tile)

    # Check for crow (0x30-0x3F)
    code.extend([0xFE, 0x40])              # CP 0x40
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x38, 0x00])              # JR C, crow_palette

    # Check for hornets (0x40-0x4F)
    code.extend([0xFE, 0x50])              # CP 0x50
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x38, 0x00])              # JR C, hornet_palette

    # Check for orcs (0x50-0x5F)
    code.extend([0xFE, 0x60])              # CP 0x60
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])              # JR C, orc_palette

    # Check for humanoid (0x60-0x6F)
    code.extend([0xFE, 0x70])              # CP 0x70
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])              # JR C, humanoid_palette

    # Check for special (0x70-0x7F)
    code.extend([0xFE, 0x80])              # CP 0x80
    jumps_to_fix.append((len(code), 'special_palette'))
    code.extend([0x38, 0x00])              # JR C, special_palette

    # Default: palette 4
    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])              # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Effects: palette 0
    labels['effects_palette'] = len(code)
    code.extend([0x3E, 0x00])              # LD A, 0
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Sara: use D register (1=dragon, 2=witch)
    labels['sara_palette'] = len(code)
    code.append(0x7A)                      # LD A, D
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Boss override: use E register (6=gargoyle, 7=spider)
    labels['boss_palette'] = len(code)
    code.append(0x7B)                      # LD A, E
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Crow: palette 3
    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])              # LD A, 3
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Hornets: palette 4
    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])              # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Orcs: palette 5
    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])              # LD A, 5
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Humanoid: palette 6
    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])              # LD A, 6
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])              # JR apply_palette

    # Special: palette 3
    labels['special_palette'] = len(code)
    code.extend([0x3E, 0x03])              # LD A, 3

    # Apply palette
    labels['apply_palette'] = len(code)
    code.append(0x4F)                      # LD C, A (save palette)
    code.append(0x7E)                      # LD A, [HL] (read flags)
    code.extend([0xE6, 0xF8])              # AND 0xF8 (clear palette bits)
    code.append(0xB1)                      # OR C (set new palette)
    code.append(0x77)                      # LD [HL], A (write back)

    # Next sprite: HL += 4
    code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4

    # Loop
    code.append(0x05)                      # DEC B
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    code.append(0xC9)                      # RET

    # Fix up jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """
    Main routine from v2.15 that sets up D/E registers and calls colorizer.

    D = Sara palette (1 for dragon, 2 for witch) based on 0xFFBE
    E = Boss override palette (0=none, 6=gargoyle, 7=spider) based on 0xFFBF
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Read Sara form from 0xFFBE
    code.extend([0xF0, 0xBE])              # LDH A, [0xBE]
    code.append(0xB7)                      # OR A
    code.extend([0x20, 0x04])              # JR NZ, +4 (skip witch)
    code.extend([0x16, 0x02])              # LD D, 2 (witch palette)
    code.extend([0x18, 0x02])              # JR +2 (skip dragon)
    code.extend([0x16, 0x01])              # LD D, 1 (dragon palette)

    # Read boss flag from 0xFFBF
    code.extend([0xF0, 0xBF])              # LDH A, [0xBF]
    code.extend([0xFE, 0x01])              # CP 1 (gargoyle?)
    code.extend([0x28, 0x08])              # JR Z, +8 (gargoyle)
    code.extend([0xFE, 0x02])              # CP 2 (spider?)
    code.extend([0x28, 0x06])              # JR Z, +6 (spider)
    code.extend([0x1E, 0x00])              # LD E, 0 (no boss)
    code.extend([0x18, 0x06])              # JR +6 (skip boss setup)
    code.extend([0x1E, 0x06])              # LD E, 6 (gargoyle palette)
    code.extend([0x18, 0x02])              # JR +2
    code.extend([0x1E, 0x07])              # LD E, 7 (spider palette)

    # Colorize shadow OAM 1: C000-C09F (start at C003 for flags)
    code.extend([0x21, 0x03, 0xC0])        # LD HL, 0xC003
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Colorize shadow OAM 2: C100-C19F (start at C103 for flags)
    code.extend([0x21, 0x03, 0xC1])        # LD HL, 0xC103
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF

    code.append(0xC9)                      # RET

    return bytes(code)


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Load BG and OBJ palettes, with boss palette swapping."""
    code = bytearray()

    # Load BG palettes (64 bytes)
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])              # LD A, 0x80 (auto-increment, palette 0)
    code.extend([0xE0, 0x68])              # LDH [BCPS], A
    code.extend([0x0E, 0x40])              # LD C, 64
    code.extend([0x2A])                    # LD A, [HL+]
    code.extend([0xE0, 0x69])              # LDH [BCPD], A
    code.extend([0x0D])                    # DEC C
    code.extend([0x20, 0xFA])              # JR NZ, -6

    # Load OBJ palettes (48 bytes = 6 palettes, leaving 6 and 7 for bosses)
    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])              # LD A, 0x80
    code.extend([0xE0, 0x6A])              # LDH [OCPS], A
    code.extend([0x0E, 0x30])              # LD C, 48 (6 palettes)
    code.extend([0x2A])                    # LD A, [HL+]
    code.extend([0xE0, 0x6B])              # LDH [OCPD], A
    code.extend([0x0D])                    # DEC C
    code.extend([0x20, 0xFA])              # JR NZ, -6

    # Load palette 6 (default)
    pal6_addr = obj_data_addr + 48
    code.extend([0x21, pal6_addr & 0xFF, (pal6_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])              # LD C, 8
    code.extend([0x2A])                    # LD A, [HL+]
    code.extend([0xE0, 0x6B])              # LDH [OCPD], A
    code.extend([0x0D])                    # DEC C
    code.extend([0x20, 0xFA])              # JR NZ, -6

    # Check boss flag for palette 6 override
    code.extend([0xF0, 0xBF])              # LDH A, [0xBF]
    code.extend([0xFE, 0x01])              # CP 1 (Gargoyle?)
    code.extend([0x20, 0x0A])              # JR NZ, +10 (skip gargoyle load)
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x3E, 0xB0])              # LD A, 0xB0 (palette 6, auto-inc)
    code.extend([0xE0, 0x6A])              # LDH [OCPS], A
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    # Load palette 7 (default)
    pal7_addr = obj_data_addr + 56
    code.extend([0x21, pal7_addr & 0xFF, (pal7_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    # Check boss flag for palette 7 override
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])              # CP 2 (Spider?)
    code.extend([0x20, 0x0A])              # JR NZ, +10
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x3E, 0xB8])              # LD A, 0xB8 (palette 7)
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    code.append(0xC9)

    return bytes(code)


def create_bg_colorizer_3rows(lookup_table_addr: int, row_counter_addr: int = 0xD0) -> bytes:
    """
    BG colorizer that processes 3 ROWS per VBlank (96 tiles).

    Full screen in 6 frames (~0.1 seconds) vs 18 frames for 1 row.
    ~96 tiles × 35 cycles = 3,360 cycles (still fits in VBlank)
    """
    code = bytearray()

    # Check 0xFFC1 - if 0, skip (menu)
    code.extend([0xF0, 0xC1])              # LDH A, [0xC1]
    code.append(0xB7)                      # OR A
    code.extend([0xC8])                    # RET Z

    # Check 0xFFC2 - if non-zero, skip (stage title)
    code.extend([0xF0, 0xC2])              # LDH A, [0xC2]
    code.append(0xB7)                      # OR A
    code.extend([0xC0])                    # RET NZ

    # Get current row batch (0-5, each batch = 3 rows)
    code.extend([0xF0, row_counter_addr])  # LDH A, [row_counter]
    code.append(0x57)                      # LD D, A (save batch in D)

    # Calculate starting row: batch * 3
    code.append(0x87)                      # ADD A, A (A*2)
    code.append(0x82)                      # ADD A, D (A*3)
    code.append(0x47)                      # LD B, A (starting row in B)

    # Process 3 rows
    code.extend([0x0E, 0x03])              # LD C, 3 (row counter)

    row_loop_start = len(code)

    # Calculate HL = 0x9800 + row * 32
    code.append(0x78)                      # LD A, B
    code.append(0x5F)                      # LD E, A
    code.extend([0x16, 0x00])              # LD D, 0
    # DE = row, shift left 5 times
    for _ in range(5):
        code.append(0xCB)                  # SLA E
        code.append(0x23)
        code.append(0xCB)                  # RL D
        code.append(0x12)
    # HL = 0x9800 + DE
    code.extend([0x21, 0x00, 0x98])        # LD HL, 0x9800
    code.append(0x19)                      # ADD HL, DE

    # Process 32 tiles in this row
    code.append(0xE5)                      # PUSH HL (save row start)
    code.append(0xC5)                      # PUSH BC (save counters)

    code.extend([0x06, 0x20])              # LD B, 32 (tile counter)

    tile_loop_start = len(code)

    # Read tile ID from VBK 0
    code.extend([0xAF])                    # XOR A
    code.extend([0xE0, 0x4F])              # LDH [VBK], A
    code.append(0x56)                      # LD D, [HL]

    # Look up palette
    code.append(0xE5)                      # PUSH HL
    code.extend([0x26, (lookup_table_addr >> 8) & 0xFF])
    code.append(0x7A)                      # LD A, D
    code.append(0x6F)                      # LD L, A
    code.append(0x5E)                      # LD E, [HL]
    code.append(0xE1)                      # POP HL

    # Write palette to VBK 1
    code.extend([0x3E, 0x01])              # LD A, 1
    code.extend([0xE0, 0x4F])              # LDH [VBK], A
    code.append(0x73)                      # LD [HL], E

    # Next tile
    code.append(0x23)                      # INC HL
    code.append(0x05)                      # DEC B
    tile_offset = tile_loop_start - len(code) - 2
    code.extend([0x20, tile_offset & 0xFF])  # JR NZ, tile_loop

    # Restore counters, move to next row
    code.append(0xC1)                      # POP BC
    code.append(0xE1)                      # POP HL
    code.append(0x04)                      # INC B (next row)
    code.append(0x0D)                      # DEC C
    row_offset = row_loop_start - len(code) - 2
    code.extend([0x20, row_offset & 0xFF])  # JR NZ, row_loop

    # Update row counter (wrap at 6)
    code.extend([0xF0, row_counter_addr])  # LDH A, [row_counter]
    code.append(0x3C)                      # INC A
    code.extend([0xFE, 0x06])              # CP 6
    code.extend([0x38, 0x01])              # JR C, +1
    code.extend([0xAF])                    # XOR A (wrap to 0)
    code.extend([0xE0, row_counter_addr])  # LDH [row_counter], A

    # Reset VBK to 0
    code.extend([0xAF])                    # XOR A
    code.extend([0xE0, 0x4F])              # LDH [VBK], A

    code.append(0xC9)                      # RET

    return bytes(code)


def create_combined_with_dma(
    palette_loader_addr: int,
    obj_colorizer_addr: int,
    bg_colorizer_addr: int
) -> bytes:
    """Combined handler that calls palette loader, OBJ colorizer, BG colorizer, then DMA."""
    code = bytearray()

    # Call palette loader
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])

    # Call OBJ colorizer
    code.extend([0xCD, obj_colorizer_addr & 0xFF, obj_colorizer_addr >> 8])

    # Call BG colorizer
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])

    # Call DMA routine at 0xFF80
    code.extend([0xCD, 0x80, 0xFF])

    code.append(0xC9)  # RET

    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook that reads input and calls our combined function."""
    # Simplified input reader (from v2.15)
    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    # Bank switch and call
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,  # LD A, 13; LD [0x2000], A
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,  # CALL combined
        0x3E, 0x01, 0xEA, 0x00, 0x20,  # LD A, 1; LD [0x2000], A
        0xC9,  # RET
    ])
    return bytes(simplified_input + hook_code)


def main():
    project_root = Path(__file__).parent.parent
    rom_path = project_root / 'rom' / 'Penta Dragon (J).gb'
    output_path = project_root / 'rom' / 'working' / 'penta_dragon_dx_v216.gb'
    fixed_output = project_root / 'rom' / 'working' / 'penta_dragon_dx_FIXED.gb'
    yaml_path = project_root / 'palettes' / 'penta_palettes_v097.yaml'

    rom_data = bytearray(rom_path.read_bytes())

    # Apply CGB patches
    apply_all_display_patches(rom_data)

    # Load palettes
    bg_palettes, obj_palettes, gargoyle_pal, spider_pal = load_palettes_from_yaml(yaml_path)
    print(f"Loading palettes from: {yaml_path}")

    print("\n=== v2.16: Fixed Sara + Reduced BG Flicker ===")
    print("  OBJ: Tile-based Sara detection (fixes corruption)")
    print("  BG: 3 rows/frame (full screen in 6 frames)")
    print()

    # Create components
    lookup_table = create_tile_palette_lookup()

    # Layout in Bank 13 (0x34000-0x37FFF, mapped to 0x4000-0x7FFF)
    bank13_offset = 13 * 0x4000

    def bank_offset(addr):
        return bank13_offset + (addr - 0x4000)

    # Addresses (same layout as v2.15)
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    obj_colorizer_addr = 0x6900  # Tile-based colorizer
    obj_main_addr = 0x6980       # Shadow colorizer main
    palette_loader_addr = 0x69E0
    bg_colorizer_addr = 0x6A40
    lookup_table_addr = 0x6B00
    combined_addr = 0x6C00

    # Create all the code
    obj_colorizer = create_tile_based_colorizer_v216()
    obj_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    bg_colorizer = create_bg_colorizer_3rows(lookup_table_addr)
    combined = create_combined_with_dma(palette_loader_addr, obj_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"OBJ colorizer (tile-based): {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"OBJ colorizer main: {len(obj_main)} bytes at 0x{obj_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"BG colorizer (3 rows): {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")
    print(f"Lookup table: 256 bytes at 0x{lookup_table_addr:04X}")
    print(f"Combined handler: {len(combined)} bytes at 0x{combined_addr:04X}")
    print(f"VBlank hook: {len(vblank_hook)} bytes at 0x0824")

    # Write palette data
    rom_data[bank_offset(palette_data_addr):bank_offset(palette_data_addr) + len(bg_palettes)] = bg_palettes
    rom_data[bank_offset(palette_data_addr) + 64:bank_offset(palette_data_addr) + 64 + len(obj_palettes)] = obj_palettes
    rom_data[bank_offset(gargoyle_addr):bank_offset(gargoyle_addr) + len(gargoyle_pal)] = gargoyle_pal
    rom_data[bank_offset(spider_addr):bank_offset(spider_addr) + len(spider_pal)] = spider_pal

    # Write code
    rom_data[bank_offset(obj_colorizer_addr):bank_offset(obj_colorizer_addr) + len(obj_colorizer)] = obj_colorizer
    rom_data[bank_offset(obj_main_addr):bank_offset(obj_main_addr) + len(obj_main)] = obj_main
    rom_data[bank_offset(palette_loader_addr):bank_offset(palette_loader_addr) + len(palette_loader)] = palette_loader
    rom_data[bank_offset(bg_colorizer_addr):bank_offset(bg_colorizer_addr) + len(bg_colorizer)] = bg_colorizer
    rom_data[bank_offset(lookup_table_addr):bank_offset(lookup_table_addr) + len(lookup_table)] = lookup_table
    rom_data[bank_offset(combined_addr):bank_offset(combined_addr) + len(combined)] = combined

    # Patch entry points (same as v2.15)
    rom_data[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])  # NOP out old code
    rom_data[0x0824:0x0824 + len(vblank_hook)] = vblank_hook
    rom_data[0x143] = 0x80  # Set CGB flag

    # Write output
    output_path.write_bytes(rom_data)
    fixed_output.write_bytes(rom_data)
    print(f"\nWrote: {output_path}")
    print(f"Wrote: {fixed_output}")

    print("\n=== v2.16 Build Complete ===")
    print("Fixes:")
    print("  1. Sara corruption: Now uses tile-based detection (0x20-0x2F)")
    print("  2. BG flicker: Processes 3 rows/frame (full screen in 6 frames)")


if __name__ == '__main__':
    main()
