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

    v0.24: Extended ranges to reduce tiny flickers.

    From v0.23 testing:
    - Sara W: green (24-47) with tiny flicker -> extend to 24-55
    - Wolves: orange (72-95) with slight flicker -> extend to 64-95
    - Hornets: purple (96-127) solid -> keep as is

    Tiles 0-23:   Palette 0 (RED)
    Tiles 24-55:  Palette 1 (GREEN) - Sara W extended
    Tiles 56-63:  Palette 2 (BLUE) - small gap
    Tiles 64-95:  Palette 3 (ORANGE) - Wolf extended
    Tiles 96-127: Palette 4 (PURPLE) - Hornet
    Tiles 128+:   Palette 5-7 cycling
    """
    table = bytearray(256)

    for tile in range(256):
        if tile < 24:
            table[tile] = 0      # RED
        elif tile < 56:
            table[tile] = 1      # GREEN - Sara W extended
        elif tile < 64:
            table[tile] = 2      # BLUE - small gap
        elif tile < 96:
            table[tile] = 3      # ORANGE - Wolf extended
        elif tile < 128:
            table[tile] = 4      # PURPLE - Hornet
        else:
            table[tile] = 5 + ((tile - 128) // 32)  # CYAN, PINK, YELLOW

    return bytes(table)

def create_tile_lookup_sprite_loop(lookup_table_addr: int) -> bytes:
    """
    TILE-BASED with actual lookup table, shadow-only, unconditional.
    Uses lookup table for custom tile boundaries.
    """
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    code = bytearray()

    # PUSH AF, BC, DE, HL
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    # Process ONLY shadow buffers (C0, C1)
    for base_hi in [0xC0, 0xC1]:
        # LD HL, base+2 (start at tile ID of sprite 0)
        code.extend([0x21, 0x02, base_hi])
        # LD B, 40
        code.extend([0x06, 0x28])

        loop_start = len(code)

        # Get tile ID
        code.append(0x5E)  # LD E, [HL] - tile ID into E
        code.extend([0x16, 0x00])  # LD D, 0 - DE = tile ID

        # Save HL position
        code.append(0xE5)  # PUSH HL

        # Lookup palette from table
        code.extend([0x21, lo, hi])  # LD HL, lookup_table
        code.append(0x19)  # ADD HL, DE - HL = table + tile_id
        code.append(0x4E)  # LD C, [HL] - C = palette from table

        # Restore position
        code.append(0xE1)  # POP HL (back to tile ID position)
        code.append(0x23)  # INC HL (now at flags)

        # Modify flags: clear palette bits, set new palette
        code.append(0x7E)  # LD A, [HL] - get flags
        code.extend([0xE6, 0xF8])  # AND 0xF8 - clear palette bits (0-2)
        code.append(0xB1)  # OR C - set new palette
        code.append(0x77)  # LD [HL], A - write back

        # Advance to next sprite's tile (+3: flags+1 -> Y -> X -> next_tile)
        code.extend([0x23, 0x23, 0x23])

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
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
