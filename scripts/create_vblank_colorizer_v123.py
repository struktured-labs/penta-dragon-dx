#!/usr/bin/env python3
"""
v1.23: Tile Copy Routine Replacement with Inline Attribute Writes

DRASTIC APPROACH: Replace the game's tile copy routine (0x4295-0x436D) with
a new version that writes BOTH tiles AND attributes.

How it works:
1. Small trampoline at 0x4295 switches to bank 13 and calls new routine
2. New routine in bank 13 copies tiles from C1A0 to VRAM bank 0
3. IMMEDIATELY after each tile write, switches to bank 1 and writes attribute
4. Uses 256-byte lookup table for tile_id -> palette mapping
5. Returns through trampoline which restores bank 1

Key insight: The original routine runs during FRAME TIME (not VBlank), using
PPU mode polling for safe VRAM access. We maintain this approach but add
attribute writes at the same time.

This is synchronized with the game's own timing - no race conditions!
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
    Create 256-byte lookup table: tile_id -> BG palette number.

    Based on observed tile usage:
    - 0x00-0x0F: Effects/empty -> palette 0
    - 0x10-0x3F: Floor tiles -> palette 0 (main dungeon)
    - 0x40-0x7F: Wall decorations -> palette 2 (purple/blue)
    - 0x80-0x9F: Hazards -> palette 3 (green for nature/danger)
    - 0xA0-0xBF: Items type A -> palette 1 (gold)
    - 0xC0-0xDF: Items type B -> palette 4 (cyan)
    - 0xE0-0xFF: Special/borders -> palette 2
    """
    table = [0] * 256  # Default: palette 0

    # Floor/base tiles - palette 0 (main dungeon colors)
    for t in range(0x00, 0x40):
        table[t] = 0

    # Wall decorations - palette 2 (purple/blue accents)
    for t in range(0x40, 0x80):
        table[t] = 2

    # Hazards - palette 3 (green/nature)
    for t in range(0x80, 0xA0):
        table[t] = 3

    # Items type A - palette 1 (gold/yellow)
    for t in range(0xA0, 0xC0):
        table[t] = 1

    # Items type B - palette 4 (cyan)
    for t in range(0xC0, 0xE0):
        table[t] = 4

    # Special/borders - palette 2
    for t in range(0xE0, 0x100):
        table[t] = 2

    return bytes(table)


def create_tile_copy_with_attributes(lookup_table_addr: int, base_addr: int = 0x4800) -> bytes:
    """
    New tile copy routine that writes both tiles AND attributes.

    This replaces the original routine at 0x4295-0x436D.
    Called from bank 14 via trampoline (to avoid VBlank conflict).

    Original routine logic:
    - Toggle DC0B to select tilemap (0x9800 or 0x9C00)
    - HL = tilemap base, DE = 0xC1A0 (source)
    - Copy 24 tiles per row, 8 rows
    - Wait for PPU mode 3 before each 4-tile burst

    New routine adds:
    - After writing tile to VRAM bank 0, switch to bank 1
    - Look up palette from table, write attribute
    - Switch back to bank 0
    """
    code = bytearray()

    # === Setup (same as original) ===
    # Toggle DC0B to select tilemap
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [0xDC0B]
    code.append(0x3C)                 # INC A
    code.extend([0xE6, 0x01])         # AND 0x01
    code.extend([0xEA, 0x0B, 0xDC])   # LD [0xDC0B], A
    code.extend([0x28, 0x05])         # JR Z, use_9800
    code.extend([0x26, 0x9C])         # LD H, 0x9C
    code.extend([0xC3])               # JP skip_9800
    skip_addr = len(code)
    code.extend([0x00, 0x00])         # placeholder for JP address
    # use_9800:
    use_9800_addr = len(code)
    code.extend([0x26, 0x98])         # LD H, 0x98
    # skip_9800:
    skip_9800_addr = len(code)

    # Fix JP address (relative to base_addr)
    code[skip_addr] = (base_addr + skip_9800_addr) & 0xFF
    code[skip_addr + 1] = ((base_addr + skip_9800_addr) >> 8) & 0xFF

    code.extend([0x2E, 0x00])         # LD L, 0x00
    code.extend([0x11, 0xA0, 0xC1])   # LD DE, 0xC1A0
    code.extend([0x0E, 0x08])         # LD C, 0x08 (row offset)
    code.extend([0x06, 0x18])         # LD B, 0x18 (24 rows)

    # === Main row loop ===
    row_loop_start = len(code)

    # Save B (row counter) in a safe place
    code.append(0xF5)                 # PUSH AF (we'll use A for tile)
    code.append(0xC5)                 # PUSH BC

    # Process 24 tiles per row (6 groups of 4)
    for group in range(6):
        # Wait for PPU mode 3 (same as original)
        code.append(0xF3)             # DI
        ppu_wait1 = len(code)
        code.extend([0xF0, 0x41])     # LDH A, [STAT]
        code.extend([0xE6, 0x03])     # AND 0x03
        code.extend([0xFE, 0x03])     # CP 0x03
        # JP NZ back to ppu_wait1
        code.append(0xC2)
        code.append((base_addr + ppu_wait1) & 0xFF)
        code.append(((base_addr + ppu_wait1) >> 8) & 0xFF)

        ppu_wait2 = len(code)
        code.extend([0xF0, 0x41])     # LDH A, [STAT]
        code.extend([0xE6, 0x03])     # AND 0x03
        # JP NZ back to ppu_wait2
        code.append(0xC2)
        code.append((base_addr + ppu_wait2) & 0xFF)
        code.append(((base_addr + ppu_wait2) >> 8) & 0xFF)

        # Copy 4 tiles with attribute writes
        for tile in range(4):
            # Read tile from C1A0
            code.append(0x1A)         # LD A, [DE]
            code.append(0x13)         # INC DE

            # Save tile ID for attribute lookup
            code.append(0xF5)         # PUSH AF

            # Write tile to VRAM bank 0
            code.append(0x22)         # LD [HL+], A

            # Now write attribute to VRAM bank 1
            # First, save HL and go back one position
            code.append(0x2B)         # DEC HL (point to tile we just wrote)

            # Switch to VRAM bank 1
            code.extend([0x3E, 0x01]) # LD A, 0x01
            code.extend([0xE0, 0x4F]) # LDH [VBK], A

            # Lookup palette from table
            # A = tile ID (on stack), need to compute table[tile_id]
            code.append(0xF1)         # POP AF (tile ID)
            code.append(0xE5)         # PUSH HL (save VRAM addr)

            # HL = lookup_table + A
            code.extend([0x26, (lookup_table_addr >> 8) & 0xFF])  # LD H, high(table)
            code.append(0x6F)         # LD L, A (tile ID)
            code.append(0x7E)         # LD A, [HL] (palette)

            code.append(0xE1)         # POP HL (restore VRAM addr)

            # Write attribute (palette) to VRAM bank 1
            code.append(0x77)         # LD [HL], A

            # Switch back to VRAM bank 0
            code.append(0xAF)         # XOR A
            code.extend([0xE0, 0x4F]) # LDH [VBK], A

            # Advance HL to next position
            code.append(0x23)         # INC HL

        code.append(0xFB)             # EI

    # Restore BC (contains B=row counter, C=8)
    code.append(0xC1)                 # POP BC
    code.append(0xF1)                 # POP AF

    # Advance HL by C (8) to skip to next row position
    code.append(0x78)                 # LD A, B (save row counter)
    code.extend([0x06, 0x00])         # LD B, 0x00
    code.append(0x09)                 # ADD HL, BC
    code.append(0x47)                 # LD B, A (restore row counter)

    # Decrement row counter and loop
    code.append(0x05)                 # DEC B
    # JP NZ to row_loop_start
    code.append(0xC2)
    code.append((base_addr + row_loop_start) & 0xFF)
    code.append(((base_addr + row_loop_start) >> 8) & 0xFF)

    code.append(0xC9)                 # RET

    return bytes(code)


def create_tile_copy_trampoline(bank_num: int = 14, bank_var_addr: int = 0xFFBA) -> bytes:
    """
    Small trampoline at 0x4295 that calls the new routine in specified bank.

    Uses bank 14 by default to avoid conflict with VBlank handler (bank 13).
    Saves current bank to HRAM variable so VBlank can restore it.
    Must be <= 214 bytes (size of original routine).
    """
    code = bytearray()
    bank_var_low = bank_var_addr & 0xFF

    # Save current bank (1) to HRAM, then switch to tile copy bank
    code.extend([0x3E, bank_num])       # LD A, bank_num
    code.extend([0xE0, bank_var_low])   # LDH [bank_var], A  (save new bank)
    code.extend([0xEA, 0x00, 0x20])     # LD [0x2000], A     (switch bank)

    # Call new routine at 0x4800 (in bank 14)
    code.extend([0xCD, 0x00, 0x48])     # CALL 0x4800

    # Switch back to bank 1 and update variable
    code.extend([0x3E, 0x01])           # LD A, 0x01
    code.extend([0xE0, bank_var_low])   # LDH [bank_var], A  (save bank 1)
    code.extend([0xEA, 0x00, 0x20])     # LD [0x2000], A     (switch bank)

    # Return
    code.append(0xC9)                   # RET

    # Pad with NOPs
    while len(code) < 24:
        code.append(0x00)

    return bytes(code)


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


def create_combined_obj_only(palette_loader_addr: int, shadow_main_addr: int) -> bytes:
    """Combined: load palettes, colorize OBJ shadows, run DMA."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int, bank_var_addr: int = 0xFFBA) -> bytes:
    """VBlank hook at 0x0824 with proper bank save/restore."""
    bank_var_low = bank_var_addr & 0xFF

    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])

    # Hook code with bank save/restore
    hook_code = bytearray([
        # Save current bank from HRAM variable
        # If 0 (uninitialized), default to bank 1
        0xF0, bank_var_low,             # LDH A, [bank_var]
        0xB7,                           # OR A (test if zero)
        0x20, 0x02,                     # JR NZ, +2 (skip if not zero)
        0x3E, 0x01,                     # LD A, 0x01 (default to bank 1)
        0xF5,                           # PUSH AF (save bank on stack)

        # Switch to bank 13 for VBlank work
        0x3E, 0x0D,                     # LD A, 0x0D
        0xEA, 0x00, 0x20,               # LD [0x2000], A

        # Call combined function
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,

        # Restore original bank from stack
        0xF1,                           # POP AF (restore saved bank)
        0xEA, 0x00, 0x20,               # LD [0x2000], A

        0xC9,                           # RET
    ])
    return bytes(simplified_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v123.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.23: Tile Copy Routine Replacement ===")
    print("  Replaces game's tile copy routine (0x4295) with new version")
    print("  Writes BOTH tiles AND attributes during normal frame time")
    print("  Uses PPU mode polling for safe VRAM access")
    print("  256-byte lookup table for tile->palette mapping")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout (VBlank code - palettes, OBJ colorization)
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    obj_colorizer_addr = 0x6A00
    shadow_main_addr = 0x6A80
    palette_loader_addr = 0x6AE0
    combined_addr = 0x6B40

    # Bank 14 layout (tile copy - separate from VBlank to avoid conflicts)
    tile_copy_addr = 0x4800  # New tile copy routine with attributes
    lookup_table_addr = 0x4C00  # 256 bytes for BG tile->palette (in bank 14)

    lookup_table = create_tile_palette_lookup_table()
    tile_copy_routine = create_tile_copy_with_attributes(lookup_table_addr, tile_copy_addr)
    tile_copy_trampoline = create_tile_copy_trampoline(bank_num=14)
    obj_colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_obj_only(palette_loader_addr, shadow_main_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X}")
    print(f"OBJ colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")
    print(f"Tile copy routine: {len(tile_copy_routine)} bytes at 0x{tile_copy_addr:04X}")
    print(f"Tile copy trampoline: {len(tile_copy_trampoline)} bytes at 0x4295")

    # Write to bank 13 (VBlank code)
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (obj_colorizer_addr - 0x4000):bank13_offset + (obj_colorizer_addr - 0x4000) + len(obj_colorizer)] = obj_colorizer
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    # Write to bank 14 (tile copy - separate from VBlank)
    bank14_offset = 14 * 0x4000
    rom[bank14_offset + (tile_copy_addr - 0x4000):bank14_offset + (tile_copy_addr - 0x4000) + len(tile_copy_routine)] = tile_copy_routine
    rom[bank14_offset + (lookup_table_addr - 0x4000):bank14_offset + (lookup_table_addr - 0x4000) + len(lookup_table)] = lookup_table

    # Replace tile copy routine at 0x4295 with trampoline
    # CRITICAL: Must write trampoline to BOTH bank 1 AND bank 14 at same address
    # Otherwise, when we switch banks mid-execution, we jump to wrong code
    print(f"\nOriginal tile copy at 0x4295 (bank 1): {rom[0x4295:0x429F].hex()}")
    rom[0x4295:0x4295 + len(tile_copy_trampoline)] = tile_copy_trampoline
    print(f"Patched bank 1 with trampoline: {rom[0x4295:0x4295 + len(tile_copy_trampoline)].hex()}")

    # Also write trampoline to bank 14 at same CPU address (0x4295)
    # Bank 14 file offset = 14 * 0x4000 + (0x4295 - 0x4000) = 0x38295
    bank14_trampoline_offset = bank14_offset + (0x4295 - 0x4000)
    print(f"Original at bank 14 offset 0x{bank14_trampoline_offset:X}: {rom[bank14_trampoline_offset:bank14_trampoline_offset+10].hex()}")
    rom[bank14_trampoline_offset:bank14_trampoline_offset + len(tile_copy_trampoline)] = tile_copy_trampoline
    print(f"Patched bank 14 with same trampoline")

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
    print("\n=== v1.23 Build Complete ===")


if __name__ == "__main__":
    main()
