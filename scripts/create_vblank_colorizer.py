#!/usr/bin/env python3
"""
v0.48: Corrected tile-to-palette mapping from YAML notes.

Uses actual game tile assignments (scattered ranges, not contiguous):
- Palette 0 (RED/SaraD): 0-3, 32-35, 64-67, 92-95, 120-123
- Palette 1 (GREEN/SaraW): 4-7, 36-39, 68-71, 96-99, 124-127
- Palette 2 (BLUE/DragonFly): 12-13, 40-43, 72-75, 100-103
- etc.

This should give each character their correct color.
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

    Based on actual game tile assignments from YAML notes:
    - Palette 0 (RED):    Tiles 0-3, 32-35, 64-67, 92-95, 120-123
    - Palette 1 (GREEN):  Tiles 4-7, 36-39, 68-71, 96-99, 124-127
    - Palette 2 (BLUE):   Tiles 12-13, 40-43, 72-75, 100-103
    - Palette 3 (ORANGE): Tiles 14-15, 44-47, 76-79, 104-107
    - Palette 4 (PURPLE): Tiles 18-19, 48-51, 80-83, 108-111
    - Palette 5 (CYAN):   Tiles 10-11, 20-23, 52-55, 84-87
    - Palette 6 (PINK):   Tiles 24-27, 56-59, 88-91, 112-115
    - Palette 7 (YELLOW): Tiles 8-9, 28-31, 60-63, 116-119
    """
    table = bytearray(256)

    # Default all to palette 0
    for i in range(256):
        table[i] = 0

    # Palette 0 (RED/SaraD): Tiles 0-3, 32-35, 64-67, 92-95, 120-123
    for t in list(range(0, 4)) + list(range(32, 36)) + list(range(64, 68)) + \
             list(range(92, 96)) + list(range(120, 124)):
        table[t] = 0

    # Palette 1 (GREEN/SaraW): Tiles 4-7, 36-39, 68-71, 96-99, 124-127
    for t in list(range(4, 8)) + list(range(36, 40)) + list(range(68, 72)) + \
             list(range(96, 100)) + list(range(124, 128)):
        table[t] = 1

    # Palette 2 (BLUE/DragonFly): Tiles 12-13, 40-43, 72-75, 100-103
    for t in list(range(12, 14)) + list(range(40, 44)) + list(range(72, 76)) + \
             list(range(100, 104)):
        table[t] = 2

    # Palette 3 (ORANGE): Tiles 14-15, 44-47, 76-79, 104-107
    for t in list(range(14, 16)) + list(range(44, 48)) + list(range(76, 80)) + \
             list(range(104, 108)):
        table[t] = 3

    # Palette 4 (PURPLE): Tiles 18-19, 48-51, 80-83, 108-111
    for t in list(range(18, 20)) + list(range(48, 52)) + list(range(80, 84)) + \
             list(range(108, 112)):
        table[t] = 4

    # Palette 5 (CYAN): Tiles 10-11, 20-23, 52-55, 84-87
    for t in list(range(10, 12)) + list(range(20, 24)) + list(range(52, 56)) + \
             list(range(84, 88)):
        table[t] = 5

    # Palette 6 (PINK): Tiles 24-27, 56-59, 88-91, 112-115
    for t in list(range(24, 28)) + list(range(56, 60)) + list(range(88, 92)) + \
             list(range(112, 116)):
        table[t] = 6

    # Palette 7 (YELLOW): Tiles 8-9, 28-31, 60-63, 116-119
    for t in list(range(8, 10)) + list(range(28, 32)) + list(range(60, 64)) + \
             list(range(116, 120)):
        table[t] = 7

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
    print(f"  v0.48: Corrected tile-to-palette mapping")
    print(f"  Pal 0 RED:    0-3, 32-35, 64-67, 92-95, 120-123")
    print(f"  Pal 1 GREEN:  4-7, 36-39, 68-71, 96-99, 124-127")
    print(f"  Pal 2 BLUE:   12-13, 40-43, 72-75, 100-103")
    print(f"  Triple OAM for stability")


if __name__ == "__main__":
    main()
