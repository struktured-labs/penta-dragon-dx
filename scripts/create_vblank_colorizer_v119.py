#!/usr/bin/env python3
"""
v1.19: Direct VRAM Attribute Writes with Per-Tile Scroll Correction

Fixes the fundamental HDMA bug from v1.18: HDMA copies linearly, but when
scroll offset is applied, bytes overflow into wrong rows.

Solution: Direct VRAM writes with per-tile position calculation:
  vram_col = (SCX/8 + col) % 32
  vram_addr = tilemap_base + row*32 + vram_col

This correctly handles tilemap wraparound at column 32.

Item colors (same as v1.17/v1.18):
  - Dragon powerup (0xC0-0xDF): Palette 1 (gold)
  - Flash item (0xAA-0xBF): Palette 4 (cyan)
  - Other items (0x88-0xA9): Palette 5 (red/orange)
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


def create_direct_bg_colorizer() -> bytes:
    """
    Direct VRAM attribute writes with per-tile scroll correction.

    For each tile in C1A0 buffer (8 rows x 24 cols):
      - Read tile ID
      - If item tile (0x88-0xDF), determine palette
      - Calculate VRAM position: (SCX/8 + col) % 32 + row*32 + tilemap_base
      - Write palette attribute to VRAM bank 1

    Registers:
      B = row counter (8 down to 0)
      C = column counter (24 down to 0)
      D = SCX/8 (scroll offset in tiles)
      E = current column + scroll offset (for VRAM calc)
      HL = C1A0 source pointer
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Switch to VRAM bank 1 for attribute writes
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK)

    # Get SCX/8 into D
    code.extend([0xF0, 0x43])        # LDH A, [FF43] (SCX)
    code.extend([0xCB, 0x3F])        # SRL A (/ 2)
    code.extend([0xCB, 0x3F])        # SRL A (/ 4)
    code.extend([0xCB, 0x3F])        # SRL A (/ 8)
    code.extend([0xE6, 0x1F])        # AND 0x1F (0-31)
    code.append(0x57)                # LD D, A (D = SCX tile offset)

    # HL = C1A0 (source tile buffer)
    code.extend([0x21, 0xA0, 0xC1])  # LD HL, 0xC1A0

    # B = 8 rows
    code.extend([0x06, 0x08])        # LD B, 8

    # === ROW LOOP ===
    labels['row_loop'] = len(code)
    code.extend([0x0E, 0x18])        # LD C, 24 (columns per row)
    code.extend([0x1E, 0x00])        # LD E, 0 (column counter)

    # === COLUMN LOOP ===
    labels['col_loop'] = len(code)
    code.append(0x2A)                # LD A, [HL+] (read tile, advance HL)

    # Check if item tile (0x88-0xDF)
    code.extend([0xFE, 0x88])        # CP 0x88
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x38, 0x00])        # JR C, not_item (tile < 0x88)

    code.extend([0xFE, 0xE0])        # CP 0xE0
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x30, 0x00])        # JR NC, not_item (tile >= 0xE0)

    # --- Determine palette based on tile ID ---
    # Dragon powerup (0xC0-0xDF) → Palette 1
    code.extend([0xFE, 0xC0])        # CP 0xC0
    jumps_to_fix.append((len(code), 'dragon_pal'))
    code.extend([0x30, 0x00])        # JR NC, dragon_pal

    # Flash item (0xAA-0xBF) → Palette 4
    code.extend([0xFE, 0xAA])        # CP 0xAA
    jumps_to_fix.append((len(code), 'flash_pal'))
    code.extend([0x30, 0x00])        # JR NC, flash_pal

    # Other items (0x88-0xA9) → Palette 5
    code.extend([0x3E, 0x05])        # LD A, 5 (red/orange)
    jumps_to_fix.append((len(code), 'write_vram'))
    code.extend([0x18, 0x00])        # JR write_vram

    labels['flash_pal'] = len(code)
    code.extend([0x3E, 0x04])        # LD A, 4 (cyan)
    jumps_to_fix.append((len(code), 'write_vram'))
    code.extend([0x18, 0x00])        # JR write_vram

    labels['dragon_pal'] = len(code)
    code.extend([0x3E, 0x01])        # LD A, 1 (gold)

    # --- Write to VRAM ---
    labels['write_vram'] = len(code)
    # Save all working registers
    code.append(0xC5)                # PUSH BC (save row/col counters)
    code.append(0xD5)                # PUSH DE (save SCX offset and column counter!)
    code.append(0x4F)                # LD C, A (C = palette value)

    # Calculate VRAM column: (SCX/8 + col) % 32
    # D = SCX/8, E = current column (0-23)
    code.append(0x7A)                # LD A, D (SCX/8)
    code.append(0x83)                # ADD E (+ column)
    code.extend([0xE6, 0x1F])        # AND 0x1F (% 32)
    code.append(0x5F)                # LD E, A (E = VRAM column)

    # Calculate VRAM row offset: (8 - B) * 32
    # B counts down from 8, so row = 8 - B
    # But B was just pushed, get it from stack peek? No, just recalc
    # Actually we can use the pushed value. Simpler: use A for temp
    code.extend([0x3E, 0x08])        # LD A, 8
    code.append(0x90)                # SUB B (A = 8 - B = current row 0-7)
    # Shift left 5 times (multiply by 32)
    code.extend([0xCB, 0x27])        # SLA A (*2)
    code.extend([0xCB, 0x27])        # SLA A (*4)
    code.extend([0xCB, 0x27])        # SLA A (*8)
    code.extend([0xCB, 0x27])        # SLA A (*16)
    code.extend([0xCB, 0x27])        # SLA A (*32)
    # A = row * 32

    # VRAM addr low = row*32 + vram_col
    code.append(0x83)                # ADD E (+ VRAM column)
    code.append(0x5F)                # LD E, A (E = low byte of VRAM offset)

    # Check DC0B for tilemap base (9800 or 9C00)
    code.extend([0xF0, 0x70])        # LDH A, [FF70] (current WRAM bank)
    code.append(0xF5)                # PUSH AF (save current bank)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A (switch to bank 1)
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [DC0B]
    code.extend([0xE6, 0x01])        # AND 1
    jumps_to_fix.append((len(code), 'use_9800'))
    code.extend([0x28, 0x00])        # JR Z, use_9800
    code.extend([0x16, 0x9C])        # LD D, 0x9C
    jumps_to_fix.append((len(code), 'have_base'))
    code.extend([0x18, 0x00])        # JR have_base

    labels['use_9800'] = len(code)
    code.extend([0x16, 0x98])        # LD D, 0x98

    labels['have_base'] = len(code)
    # DE = VRAM address, C = palette value
    code.append(0x79)                # LD A, C (palette)
    code.append(0x12)                # LD [DE], A

    # Restore WRAM bank
    code.append(0xF1)                # POP AF
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Restore DE (column counter E!) and BC
    code.append(0xD1)                # POP DE (restores E = column counter!)
    code.append(0xC1)                # POP BC

    # --- Next column ---
    labels['not_item'] = len(code)
    code.append(0x1C)                # INC E (next column counter)
    code.append(0x0D)                # DEC C (columns remaining)
    jumps_to_fix.append((len(code), 'col_loop'))
    code.extend([0x20, 0x00])        # JR NZ, col_loop

    # --- Next row ---
    code.append(0x05)                # DEC B (rows remaining)
    jumps_to_fix.append((len(code), 'row_loop'))
    code.extend([0x20, 0x00])        # JR NZ, row_loop

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)                # RET

    # Fix jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_tile_based_colorizer() -> bytes:
    """OBJ tile-based colorizer (same as v1.11)."""
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])  # LD B, 40
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

    code.extend([0xFE, 0x30])
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x30, 0x00])

    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])
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
    """Load CGB palettes with dynamic boss palette swapping."""
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


def create_combined_with_direct_bg(palette_loader_addr: int, shadow_main_addr: int,
                                    bg_colorizer_addr: int) -> bytes:
    """
    Combined VBlank function with direct BG colorization.

    Order:
    1. Load palettes
    2. Colorize OBJ shadows
    3. Direct VRAM attribute writes for BG
    4. Run OAM DMA
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # CALL DMA (OAM)
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
    output_rom = Path("rom/working/penta_dragon_dx_v119.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.19: Direct VRAM Attribute Writes ===")
    print("  FIXES: Per-tile scroll correction (no HDMA row overflow)")
    print("  vram_col = (SCX/8 + col) % 32")
    print("  Dragon powerup (0xC0-0xDF) -> Palette 1 (gold)")
    print("  Flash item (0xAA-0xBF) -> Palette 4 (cyan)")
    print("  Other items (0x88-0xA9) -> Palette 5 (red/orange)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    obj_colorizer_addr = 0x6900
    bg_colorizer_addr = 0x6980       # Direct BG colorizer (replaces attr_prep + hdma)
    shadow_main_addr = 0x6A80
    palette_loader_addr = 0x6AE0
    combined_addr = 0x6B40

    obj_colorizer = create_tile_based_colorizer()
    bg_colorizer = create_direct_bg_colorizer()
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_with_direct_bg(palette_loader_addr, shadow_main_addr,
                                               bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"OBJ Colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"BG Colorizer (direct): {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Check for overlaps
    if bg_colorizer_addr + len(bg_colorizer) > shadow_main_addr:
        print(f"WARNING: BG colorizer extends to 0x{bg_colorizer_addr + len(bg_colorizer):04X}, overlaps shadow_main at 0x{shadow_main_addr:04X}")
        # Adjust shadow_main_addr
        shadow_main_addr = bg_colorizer_addr + len(bg_colorizer) + 0x10
        palette_loader_addr = shadow_main_addr + len(shadow_main) + 0x10
        combined_addr = palette_loader_addr + len(palette_loader) + 0x10
        print(f"Adjusted: shadow_main=0x{shadow_main_addr:04X}, palette_loader=0x{palette_loader_addr:04X}, combined=0x{combined_addr:04X}")
        # Regenerate with new addresses
        shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
        palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
        combined = create_combined_with_direct_bg(palette_loader_addr, shadow_main_addr,
                                                   bg_colorizer_addr)
        vblank_hook = create_vblank_hook_with_input(combined_addr)

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (obj_colorizer_addr - 0x4000):bank13_offset + (obj_colorizer_addr - 0x4000) + len(obj_colorizer)] = obj_colorizer
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
    print("\n=== v1.19 Build Complete ===")
    print("\nKey changes from v1.18:")
    print("  - Replaced HDMA with direct VRAM writes")
    print("  - Per-tile scroll position calculation")
    print("  - Correct tilemap wraparound at column 32")


if __name__ == "__main__":
    main()
