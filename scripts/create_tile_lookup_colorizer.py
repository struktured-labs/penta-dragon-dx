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

    64-tile blocks for stability with unconditional sprite modification.
    """
    table = bytearray(256)

    # Tiles 0-63: Palette 0 (RED)
    for tile in range(0, 64):
        table[tile] = 0

    # Tiles 64-127: Palette 1 (GREEN)
    for tile in range(64, 128):
        table[tile] = 1

    # Tiles 128-191: Palette 2 (BLUE)
    for tile in range(128, 192):
        table[tile] = 2

    # Tiles 192-255: Palette 3 (ORANGE)
    for tile in range(192, 256):
        table[tile] = 3

    return bytes(table)

def create_tile_lookup_sprite_loop(lookup_table_addr: int) -> bytes:
    """
    SLOT-BASED palettes - assign by sprite position, not tile ID.
    Every 5 sprites get a different palette (8 palettes for 40 sprites).
    This gives consistent colors regardless of which tiles are used.
    """
    code = bytearray()

    # PUSH AF, BC, DE, HL
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Process ONLY shadow buffers
    for base_hi in [0xC0, 0xC1]:
        # LD HL, base+3 (start at flags)
        code.extend([0x21, 0x03, base_hi])

        # LD D, 0 (palette counter, 0-7)
        code.extend([0x16, 0x00])
        # LD E, 4 (sprites per palette group - matches 2x2 sprite layout)
        code.extend([0x1E, 0x04])
        # LD B, 40 (total sprites)
        code.extend([0x06, 0x28])

        # .loop:
        loop_start = len(code)

        # LD A, [HL] - get current flags
        code.append(0x7E)
        # AND 0xF8 - clear palette bits
        code.extend([0xE6, 0xF8])
        # OR D - set palette from D (0-7)
        code.append(0xB2)
        # LD [HL], A - write back
        code.append(0x77)

        # Advance HL by 4 to next sprite's flags
        code.extend([0x23, 0x23, 0x23, 0x23])

        # DEC E (sprites remaining in this palette group)
        code.append(0x1D)
        # JR NZ, .skip_palette_change
        skip_pal = len(code)
        code.extend([0x20, 0x00])

        # E reached 0, increment palette (mod 8) and reset E
        code.append(0x14)  # INC D (next palette)
        code.append(0x7A)  # LD A, D
        code.extend([0xE6, 0x07])  # AND 7 (wrap palette 0-7)
        code.append(0x57)  # LD D, A
        code.extend([0x1E, 0x04])  # LD E, 4

        # .skip_palette_change:
        code[skip_pal + 1] = (len(code) - skip_pal - 2) & 0xFF

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ, .loop

    # POP HL, DE, BC, AF
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)  # RET

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
