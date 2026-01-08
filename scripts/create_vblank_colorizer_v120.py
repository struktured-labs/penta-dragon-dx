#!/usr/bin/env python3
"""
v1.20: Direct VRAM Scan with 256-Byte Lookup Table - WORKING BG COLORIZATION

This version implements TRUE direct VRAM scanning for BG tile colorization.
Reads tile IDs from VRAM bank 0, looks up palette from 256-byte table,
writes attributes to VRAM bank 1 at the SAME address.

Key Features:
  - DC0B-based tilemap selection (0x9800 or 0x9C00)
  - 512 tiles processed per frame (16 rows x 32 cols)
  - Fast O(1) palette lookup via 256-byte table
  - Guaranteed alignment - read/write at same VRAM address

BG Tile → Palette mapping:
  0x00-0x0F: Floor/effects → Palette 0 (base)
  0x10-0x5F: Walls/borders → Palette 2 (blue/purple)
  0x60-0x7F: Structure → Palette 0 (base)
  0x80-0xBF: Hazards → Palette 3 (red)
  0xC0-0xDF: Items → Palette 1 (gold) [dragon powerup, flash, etc]
  0xE0-0xFF: Borders → Palette 2 (blue/purple)

OBJ Colorization (unchanged from v1.11):
  - Tile-based palette assignment for sprites
  - Boss detection via 0xFFBF flag
  - Dynamic palette loading for bosses
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


def create_tile_palette_lookup_table() -> bytes:
    """
    Create 256-byte lookup table: tile_id -> palette_number

    Based on VRAM analysis:
      0x00-0x0F: Floor/empty → Palette 0
      0x10-0x3F: Walls, borders, decorations → Palette 2 (blue/walls)
      0x40-0x5F: More decorations → Palette 2
      0x60-0x7F: Structure → Palette 0
      0x80-0xBF: Special/hazards → Palette 3 (red/hazards)
      0xC0-0xDF: Items! → Palette 1 (gold)
      0xE0-0xFF: Borders/special → Palette 2
    """
    table = [0] * 256  # Default palette 0

    # Walls and borders (blue)
    for t in range(0x10, 0x40):
        table[t] = 2
    for t in range(0x40, 0x60):
        table[t] = 2

    # Hazards (red) - 0x80-0xBF excluding items
    for t in range(0x80, 0xC0):
        table[t] = 3

    # Items (gold) - 0xC0-0xDF
    for t in range(0xC0, 0xE0):
        table[t] = 1

    # High borders (blue)
    for t in range(0xE0, 0x100):
        table[t] = 2

    return bytes(table)


def create_direct_vram_colorizer(lookup_table_addr: int) -> bytes:
    """
    Direct VRAM scan: Read from bank 0, write to bank 1.

    Final version with DC0B tilemap selection and 16 rows coverage.
    """
    code = bytearray()
    labels = {}
    jumps = []

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Ensure ROM bank 13 is selected (for lookup table)
    code.extend([0x3E, 0x0D])        # LD A, 13
    code.extend([0xEA, 0x00, 0x20])  # LD [0x2000], A

    # Get tilemap base from DC0B (in WRAM bank 1)
    code.extend([0xF0, 0x70])        # LDH A, [FF70] (save WRAM bank)
    code.append(0xF5)                # PUSH AF
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [DC0B]
    code.append(0x4F)                # LD C, A (save DC0B in C!)
    code.append(0xF1)                # POP AF (restore WRAM bank)
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Check DC0B (saved in C) and set tilemap base
    code.append(0x79)                # LD A, C (get DC0B back)
    code.extend([0xE6, 0x01])        # AND 1
    jumps.append((len(code), 'use_9800'))
    code.extend([0x28, 0x00])        # JR Z, use_9800
    code.extend([0x11, 0x00, 0x9C])  # LD DE, 0x9C00
    jumps.append((len(code), 'have_base'))
    code.extend([0x18, 0x00])        # JR have_base

    labels['use_9800'] = len(code)
    code.extend([0x11, 0x00, 0x98])  # LD DE, 0x9800

    labels['have_base'] = len(code)

    # Do 2 passes of 256 tiles each (16 rows total)
    code.extend([0x06, 0x02])        # LD B, 2 (outer loop: 2 passes)

    labels['outer_loop'] = len(code)
    code.append(0xC5)                # PUSH BC (save outer counter)
    code.extend([0x06, 0x00])        # LD B, 0 (inner loop: 256 tiles)

    labels['inner_loop'] = len(code)

    # VBK = 0 (tile bank)
    code.extend([0xAF])              # XOR A
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    # Read tile ID
    code.append(0x1A)                # LD A, [DE]

    # Lookup palette: HL = 0x6900 + A
    table_high = (lookup_table_addr >> 8) & 0xFF
    code.extend([0x26, table_high])  # LD H, table_high
    code.append(0x6F)                # LD L, A
    code.append(0x7E)                # LD A, [HL] (palette from table)
    code.append(0x4F)                # LD C, A (save palette)

    # VBK = 1 (attr bank)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    # Write palette
    code.append(0x79)                # LD A, C
    code.append(0x12)                # LD [DE], A

    # Next tile
    code.append(0x13)                # INC DE

    # Inner loop
    code.append(0x05)                # DEC B
    jumps.append((len(code), 'inner_loop'))
    code.extend([0x20, 0x00])        # JR NZ, inner_loop

    # Outer loop
    code.append(0xC1)                # POP BC
    code.append(0x05)                # DEC B
    jumps.append((len(code), 'outer_loop'))
    code.extend([0x20, 0x00])        # JR NZ, outer_loop

    # Restore VBK = 0
    code.extend([0xAF])              # XOR A
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)                # RET

    # Fix jumps
    for pos, label in jumps:
        target = labels[label]
        offset = target - (pos + 2)
        code[pos + 1] = offset & 0xFF

    return bytes(code)



def create_tile_based_colorizer() -> bytes:
    """OBJ tile-based colorizer (same as v1.11+)."""
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


def create_combined_vblank(palette_loader_addr: int, shadow_main_addr: int,
                           vram_colorizer_addr: int) -> bytes:
    """
    Combined VBlank: palettes, OBJ colorization, BG VRAM colorization, OAM DMA.
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, vram_colorizer_addr & 0xFF, vram_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # OAM DMA
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
    output_rom = Path("rom/working/penta_dragon_dx_v120.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.20: TRUE Direct VRAM Scan ===")
    print("  FIXES v1.19: Now reads from VRAM bank 0, not C1A0!")
    print("  256-byte lookup table for fast palette assignment")
    print("  Guaranteed alignment - same address for read/write")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800      # 128 bytes
    gargoyle_addr = 0x6880          # 8 bytes
    spider_addr = 0x6888            # 8 bytes
    lookup_table_addr = 0x6900      # 256 bytes (NEW!)
    obj_colorizer_addr = 0x6A00     # ~100 bytes
    vram_colorizer_addr = 0x6A80    # ~80 bytes
    shadow_main_addr = 0x6B00       # ~60 bytes
    palette_loader_addr = 0x6B40    # ~70 bytes
    combined_addr = 0x6BA0          # ~16 bytes

    # Generate code
    lookup_table = create_tile_palette_lookup_table()
    obj_colorizer = create_tile_based_colorizer()
    vram_colorizer = create_direct_vram_colorizer(lookup_table_addr)
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_vblank(palette_loader_addr, shadow_main_addr, vram_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X}")
    print(f"OBJ Colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"VRAM Colorizer: {len(vram_colorizer)} bytes at 0x{vram_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr, data):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    write_to_bank13(palette_data_addr, bg_data)
    write_to_bank13(palette_data_addr + 64, obj_data)
    write_to_bank13(gargoyle_addr, gargoyle)
    write_to_bank13(spider_addr, spider)
    write_to_bank13(lookup_table_addr, lookup_table)
    write_to_bank13(obj_colorizer_addr, obj_colorizer)
    write_to_bank13(vram_colorizer_addr, vram_colorizer)
    write_to_bank13(shadow_main_addr, shadow_main)
    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(combined_addr, combined)

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
    print("\n=== v1.20 Build Complete ===")
    print("\nLookup table palette assignments:")
    print("  0x00-0x0F: Palette 0 (floor)")
    print("  0x10-0x5F: Palette 2 (walls/blue)")
    print("  0x60-0x7F: Palette 0 (floor)")
    print("  0x80-0xBF: Palette 3 (hazards/red)")
    print("  0xC0-0xDF: Palette 1 (items/gold)")
    print("  0xE0-0xFF: Palette 2 (borders)")


if __name__ == "__main__":
    main()
