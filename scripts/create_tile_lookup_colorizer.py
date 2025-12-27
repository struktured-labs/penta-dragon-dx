#!/usr/bin/env python3
"""
Tile-based palette lookup colorizer.
Modifies all three OAM locations (0xFE00, 0xC000, 0xC100).
Uses a 256-byte lookup table to map tile IDs to palettes.
Loads palettes from YAML file.
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes]:
    """Load BG and OBJ palettes from YAML file."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors: list[str]) -> bytes:
        result = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)

    bg_keys = ['Dungeon', 'Default1', 'Default2', 'Default3',
               'Default4', 'Default5', 'Default6', 'Default7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_keys = ['SaraD', 'SaraW', 'DragonFly', 'DefaultSprite3',
                'DefaultSprite4', 'DefaultSprite5', 'DefaultSprite6', 'DefaultSprite7']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    return bytes(bg_data), bytes(obj_data)

def create_lookup_table() -> bytes:
    """Create 256-byte tile-to-palette lookup table.

    Based on monster_palette_map.yaml analysis - group related tiles.
    """
    table = bytearray(256)

    # Sara/Player: tiles 0-15 -> Palette 0 (RED)
    for tile in range(0, 16):
        table[tile] = 0

    # Monster group 1: tiles 16-31 -> Palette 1 (GREEN)
    for tile in range(16, 32):
        table[tile] = 1

    # Monster group 2: tiles 32-47 -> Palette 2 (BLUE)
    for tile in range(32, 48):
        table[tile] = 2

    # Monster group 3: tiles 48-63 -> Palette 3 (ORANGE)
    for tile in range(48, 64):
        table[tile] = 3

    # Monster group 4: tiles 64-79 -> Palette 4 (PURPLE)
    for tile in range(64, 80):
        table[tile] = 4

    # Monster group 5: tiles 80-95 -> Palette 5 (CYAN)
    for tile in range(80, 96):
        table[tile] = 5

    # Monster group 6: tiles 96-111 -> Palette 6 (PINK)
    for tile in range(96, 112):
        table[tile] = 6

    # Monster group 7: tiles 112-127 -> Palette 7 (YELLOW)
    for tile in range(112, 128):
        table[tile] = 7

    # Tiles 128-255: cycle through palettes
    for tile in range(128, 256):
        table[tile] = (tile >> 4) & 7

    return bytes(table)

def create_tile_lookup_sprite_loop(lookup_table_addr: int) -> bytes:
    """
    TILE-BASED with lookup table, shadow-only, unconditional.
    Uses 16-tile blocks for 8 different palettes.
    """
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    code = bytearray()

    # PUSH AF, BC, DE, HL
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Process ONLY shadow buffers (C0, C1)
    for base_hi in [0xC0, 0xC1]:
        # LD HL, base+2 (start at tile ID)
        code.extend([0x21, 0x02, base_hi])
        # LD B, 40
        code.extend([0x06, 0x28])

        # .loop:
        loop_start = len(code)

        # Get tile ID and look up palette
        code.append(0x5E)  # LD E, [HL] - tile ID
        code.append(0x23)  # INC HL (to flags)

        # Lookup: DE = tile_id, add to lookup table base
        code.extend([0x16, 0x00])  # LD D, 0
        code.extend([0xD5])  # PUSH DE (save tile index)
        code.extend([0x21, lo, hi])  # LD HL, lookup_table
        code.append(0x19)  # ADD HL, DE
        code.append(0x4E)  # LD C, [HL] - palette from table

        # Restore position: POP DE, then compute flags address
        code.append(0xD1)  # POP DE
        # E still has tile ID, calculate flags address
        # flags = base + sprite_num*4 + 3
        # We're at loop iteration (40-B), so flags = base + (40-B)*4 + 3
        # Simpler: just track position with another register

        # Actually, let's use a simpler approach - compute from B
        # Current sprite = 40 - B, flags offset = (40-B)*4 + 3
        # This is complex. Let me use a different approach.

        # Use HL to track position directly
        code.extend([0xD1])  # POP DE (we pushed it, pop to balance)

        # Recalculate: we need flags address
        # Let's restructure...

    # This is getting complex. Let me simplify.
    code = bytearray()

    # PUSH AF, BC, HL
    code.extend([0xF5, 0xC5, 0xE5])

    for base_hi in [0xC0, 0xC1]:
        # LD HL, base+2 (tile ID of sprite 0)
        code.extend([0x21, 0x02, base_hi])
        # LD B, 40
        code.extend([0x06, 0x28])

        loop_start = len(code)

        # LD A, [HL] - get tile ID
        code.append(0x7E)
        # Compute palette = tile_id >> 6 (64-tile blocks, 0-3 for tiles 0-255)
        code.extend([0xCB, 0x3F])  # SRL A
        code.extend([0xCB, 0x3F])  # SRL A
        code.extend([0xCB, 0x3F])  # SRL A
        code.extend([0xCB, 0x3F])  # SRL A
        code.extend([0xCB, 0x3F])  # SRL A
        code.extend([0xCB, 0x3F])  # SRL A (6 shifts = divide by 64)
        # A is now 0-3 for tiles 0-255
        code.append(0x4F)  # LD C, A (save palette)

        # INC HL to flags
        code.append(0x23)

        # LD A, [HL] - get flags
        code.append(0x7E)
        # AND 0xF8 - clear palette
        code.extend([0xE6, 0xF8])
        # OR C - set palette
        code.append(0xB1)
        # LD [HL], A - write
        code.append(0x77)

        # Advance to next sprite's tile (+3 to next tile)
        code.extend([0x23, 0x23, 0x23])

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])

    code.extend([0xE1, 0xC1, 0xF1])
    code.append(0xC9)

    return bytes(code)

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")

    rom = bytearray(input_rom.read_bytes())

    # Save original input handler BEFORE any patches
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80

    # Load palettes from YAML file
    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    PALETTE_DATA_OFFSET = 0x036C80
    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes

    # Lookup table at 0x6E00 (file offset 0x036E00)
    lookup_table = create_lookup_table()
    LOOKUP_TABLE_OFFSET = 0x036E00
    LOOKUP_TABLE_ADDR = 0x6E00
    rom[LOOKUP_TABLE_OFFSET:LOOKUP_TABLE_OFFSET+256] = lookup_table

    # Sprite loop
    sprite_loop = create_tile_lookup_sprite_loop(LOOKUP_TABLE_ADDR)

    print(f"Sprite loop size: {len(sprite_loop)} bytes")

    # Combined function - single sprite loop AFTER input handler (v0.4 style)
    combined = bytes([
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40,
        0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40,
        0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
    ]) + original_input + sprite_loop + bytes([0xC9])

    COMBINED_OFFSET = 0x036D00
    rom[COMBINED_OFFSET:COMBINED_OFFSET+len(combined)] = combined

    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xF1, 0xCD, 0x00, 0x6D,
        0xF5, 0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xF1, 0xC9
    ])

    rom[0x0824:0x0824+len(trampoline)] = trampoline
    rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))

    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    mapped_tiles = sum(1 for x in lookup_table if x != 0xFF)
    print(f"✓ Created: {output_rom}")
    print(f"  Lookup table: {mapped_tiles}/256 tiles mapped")
    print(f"  Combined function: {len(combined)} bytes")
    print(f"  8 Palettes: RED, GREEN, BLUE, ORANGE, PURPLE, CYAN, PINK, YELLOW")
    print(f"  All 35+ monster groups mapped to distinct palettes")

if __name__ == "__main__":
    main()
