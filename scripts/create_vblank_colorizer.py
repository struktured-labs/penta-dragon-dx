#!/usr/bin/env python3
"""
v0.47: Tile-based palette lookup for per-monster colors.

Uses a 256-byte lookup table: tile_id -> palette number.
Each monster type uses different tile ranges, so they get unique colors.

Lookup table stored in bank 13, applied to all three OAM locations.
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


def create_tile_lookup_table() -> bytes:
    """
    Create 256-byte tile-to-palette lookup table.

    Initial mapping based on typical sprite tile ranges:
    - Tiles 0x00-0x1F: Palette 1 (Sara W)
    - Tiles 0x20-0x3F: Palette 2 (Sara D)
    - Tiles 0x40-0x5F: Palette 3 (Dragon Fly)
    - Tiles 0x60-0x7F: Palette 4 (Monster type 4)
    - Tiles 0x80-0x9F: Palette 5 (Monster type 5)
    - Tiles 0xA0-0xBF: Palette 6 (Monster type 6)
    - Tiles 0xC0-0xDF: Palette 7 (Monster type 7)
    - Tiles 0xE0-0xFF: Palette 0 (Default/misc)

    Can be refined based on actual game tile usage.
    """
    table = bytearray(256)

    for tile in range(256):
        if tile < 0x20:
            table[tile] = 1  # Sara W
        elif tile < 0x40:
            table[tile] = 2  # Sara D
        elif tile < 0x60:
            table[tile] = 3  # Dragon Fly
        elif tile < 0x80:
            table[tile] = 4  # Monster 4
        elif tile < 0xA0:
            table[tile] = 5  # Monster 5
        elif tile < 0xC0:
            table[tile] = 6  # Monster 6
        elif tile < 0xE0:
            table[tile] = 7  # Monster 7
        else:
            table[tile] = 0  # Default

    return bytes(table)


def create_tile_lookup_loop(lookup_table_addr: int) -> bytes:
    """
    Tile-based palette lookup on all three OAM locations.

    For each sprite:
    1. Read tile ID from OAM
    2. Look up palette in table
    3. Set palette bits in flags

    lookup_table_addr: CPU address of the 256-byte table (in bank 13)
    """
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Process all three OAM locations: 0xFE00, 0xC000, 0xC100
    for base_hi in [0xFE, 0xC0, 0xC1]:
        # LD HL, base+2 (tile ID byte of sprite 0)
        code.extend([0x21, 0x02, base_hi])
        # LD B, 40 sprites
        code.extend([0x06, 0x28])

        loop_start = len(code)

        # Get tile ID into E
        code.append(0x5E)  # LD E, [HL]
        code.extend([0x16, 0x00])  # LD D, 0 (DE = tile ID)

        # Save HL (current OAM position)
        code.append(0xE5)  # PUSH HL

        # Look up palette: HL = table + tile_id
        code.extend([0x21, lo, hi])  # LD HL, lookup_table
        code.append(0x19)  # ADD HL, DE
        code.append(0x4E)  # LD C, [HL] (C = palette from table)

        # Restore OAM position
        code.append(0xE1)  # POP HL
        code.append(0x23)  # INC HL (now at flags byte)

        # Modify flags: clear palette bits, set new palette
        code.append(0x7E)  # LD A, [HL]
        code.extend([0xE6, 0xF8])  # AND 0xF8 (clear bits 0-2)
        code.append(0xB1)  # OR C (set palette)
        code.append(0x77)  # LD [HL], A

        # Advance to next sprite: flags+1 -> Y -> X -> tile of next sprite
        code.extend([0x23, 0x23, 0x23])  # INC HL x3

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_palette_loader() -> bytes:
    """Load CGB palettes from bank 13 data at 0x6D00."""
    code = bytearray()

    # BG palettes (at 0x6D00)
    code.extend([
        0x21, 0x00, 0x6D,  # LD HL, 0x6D00
        0x3E, 0x80,        # LD A, 0x80 (auto-increment)
        0xE0, 0x68,        # LDH [0x68], A (BGPI)
        0x0E, 0x40,        # LD C, 64
    ])
    code.extend([
        0x2A,              # LD A, [HL+]
        0xE0, 0x69,        # LDH [0x69], A (BGPD)
        0x0D,              # DEC C
        0x20, 0xFA,        # JR NZ, -6
    ])

    # OBJ palettes
    code.extend([
        0x3E, 0x80,        # LD A, 0x80
        0xE0, 0x6A,        # LDH [0x6A], A (OBPI)
        0x0E, 0x40,        # LD C, 64
    ])
    code.extend([
        0x2A,              # LD A, [HL+]
        0xE0, 0x6B,        # LDH [0x6B], A (OBPD)
        0x0D,              # DEC C
        0x20, 0xFA,        # JR NZ, -6
    ])

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
    rom[0x143] = 0x80  # CGB flag

    # Load palettes from YAML
    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    # === BANK 13 LAYOUT ===
    # 0x6C00: Tile lookup table (256 bytes)
    # 0x6D00: Palette data (128 bytes)
    # 0x6D80: OAM palette loop (tile-based)
    # 0x6E80: Palette loader
    # 0x6F00: Combined function

    BANK13_BASE = 0x034000  # Bank 13 file offset

    LOOKUP_TABLE = 0x6C00
    PALETTE_DATA = 0x6D00
    OAM_LOOP = 0x6D80
    PALETTE_LOADER = 0x6E80
    COMBINED_FUNC = 0x6F00

    # Write tile lookup table
    offset = BANK13_BASE + (LOOKUP_TABLE - 0x4000)
    lookup_table = create_tile_lookup_table()
    rom[offset:offset+256] = lookup_table
    print(f"Tile lookup table: 256 bytes at 0x{LOOKUP_TABLE:04X}")

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes

    # Write OAM palette loop (tile-based lookup)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    oam_loop = create_tile_lookup_loop(LOOKUP_TABLE)
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM palette loop (tile-based): {len(oam_loop)} bytes")

    # Write palette loader
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    palette_loader = create_palette_loader()
    rom[offset:offset+len(palette_loader)] = palette_loader

    # Write combined function: original input + OAM loop + palette load
    # v0.45: Back to v0.43 order (original handler may have self-references)
    combined = bytearray()
    combined.extend(original_input)  # Original input handler
    # Remove trailing RET if present, we'll add our own
    if combined[-1] == 0xC9:
        combined = combined[:-1]
    combined.extend([0xCD, OAM_LOOP & 0xFF, OAM_LOOP >> 8])  # CALL OAM loop
    combined.extend([0xCD, PALETTE_LOADER & 0xFF, PALETTE_LOADER >> 8])  # CALL palette loader
    combined.append(0xC9)  # RET

    offset = BANK13_BASE + (COMBINED_FUNC - 0x4000)
    rom[offset:offset+len(combined)] = combined
    print(f"Combined function: {len(combined)} bytes")

    # === SINGLE TRAMPOLINE ===
    # Only modify the input handler call, NOT the VBlank DMA call
    # This is safe because input handler runs with bank 1 active

    trampoline = bytearray()
    trampoline.extend([0xF5])  # PUSH AF
    trampoline.extend([0x3E, 0x0D])  # LD A, 13
    trampoline.extend([0xEA, 0x00, 0x20])  # LD [0x2000], A - switch to bank 13
    trampoline.extend([0xCD, COMBINED_FUNC & 0xFF, COMBINED_FUNC >> 8])  # CALL combined
    trampoline.extend([0x3E, 0x01])  # LD A, 1
    trampoline.extend([0xEA, 0x00, 0x20])  # LD [0x2000], A - restore bank 1
    trampoline.extend([0xF1])  # POP AF
    trampoline.append(0xC9)  # RET

    # Write trampoline at 0x0824 (replaces original input handler)
    rom[0x0824:0x0824+len(trampoline)] = trampoline

    # Pad remaining space with NOPs
    remaining = 46 - len(trampoline)
    if remaining > 0:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * remaining)

    print(f"Trampoline: {len(trampoline)} bytes at 0x0824")

    # DO NOT modify VBlank DMA call at 0x06D5 - that caused the crash!
    # The input handler at 0x0824 already runs after DMA during VBlank

    # Fix header checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    print(f"\nCreated: {output_rom}")
    print(f"  v0.47: Tile-based palette lookup")
    print(f"  Each tile range maps to a different palette:")
    print(f"    0x00-0x1F: Pal 1 | 0x20-0x3F: Pal 2 | 0x40-0x5F: Pal 3")
    print(f"    0x60-0x7F: Pal 4 | 0x80-0x9F: Pal 5 | 0xA0-0xBF: Pal 6")
    print(f"  Triple OAM for stability")


if __name__ == "__main__":
    main()
