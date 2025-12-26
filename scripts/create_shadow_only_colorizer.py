#!/usr/bin/env python3
"""
Shadow-only colorizer - modifies BOTH shadow buffers but NOT actual OAM.
This avoids racing with DMA since we only touch the source buffers.
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
    """Create 256-byte tile-to-palette lookup table."""
    table = bytearray([0xFF] * 256)

    # SARA D (tiles 0-7): Palette 0
    for tile in range(0, 8):
        table[tile] = 0

    # SARA W (tiles 8-15): Palette 1
    for tile in range(8, 16):
        table[tile] = 1

    # DRAGONFLY (tiles 32-47): Palette 2
    for tile in range(32, 48):
        table[tile] = 2

    # Additional ranges
    for tile in range(16, 32):
        table[tile] = 3
    for tile in range(48, 64):
        table[tile] = 4
    for tile in range(64, 96):
        table[tile] = 5
    for tile in range(96, 128):
        table[tile] = 6
    for tile in range(128, 256):
        table[tile] = 7

    return bytes(table)

def create_shadow_only_loop(lookup_table_addr: int) -> bytes:
    """
    Modify BOTH shadow buffers (0xC000 and 0xC100) but NOT actual OAM.
    This ensures whichever buffer DMA uses will have correct palettes.
    """
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Process both shadow buffers: 0xC000 and 0xC100
    for base_hi in [0xC0, 0xC1]:
        code.extend([0x21, 0x00, base_hi])  # LD HL, 0xC000 or 0xC100
        code.extend([0x06, 0x28])  # LD B, 40

        loop_start = len(code)
        code.append(0x7E)  # LD A, [HL]
        code.append(0xA7)  # AND A
        skip_jrz = len(code)
        code.extend([0x28, 0x00])
        code.extend([0xFE, 0xA0])  # CP 160
        skip_jrnc = len(code)
        code.extend([0x30, 0x00])

        code.extend([0x23, 0x23])  # INC HL x2 (to tile)
        code.append(0x5E)  # LD E, [HL]
        code.append(0x23)  # INC HL (to flags)
        code.append(0xE5)  # PUSH HL
        code.extend([0x16, 0x00, 0x21, lo, hi, 0x19, 0x7E])  # lookup
        code.append(0xE1)  # POP HL
        code.extend([0xFE, 0xFF])  # CP 0xFF
        skip_mod = len(code)
        code.extend([0x28, 0x00])
        code.extend([0x57, 0x7E, 0xE6, 0xF8, 0xB2, 0x77])  # apply palette

        skip_mod_tgt = len(code)
        code[skip_mod + 1] = (skip_mod_tgt - skip_mod - 2) & 0xFF
        code.append(0x23)  # INC HL to next Y
        jr_dec = len(code)
        code.extend([0x18, 0x00])

        next_spr = len(code)
        code[skip_jrz + 1] = (next_spr - skip_jrz - 2) & 0xFF
        code[skip_jrnc + 1] = (next_spr - skip_jrnc - 2) & 0xFF
        code.extend([0x23, 0x23, 0x23, 0x23])  # skip 4 bytes

        dec_b = len(code)
        code[jr_dec + 1] = (dec_b - jr_dec - 2) & 0xFF
        code.append(0x05)  # DEC B
        code.extend([0x20, (loop_start - len(code) - 2) & 0xFF])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1, 0xC9])
    return bytes(code)

def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")

    rom = bytearray(input_rom.read_bytes())
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80

    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    PALETTE_DATA_OFFSET = 0x036C80
    rom[PALETTE_DATA_OFFSET:PALETTE_DATA_OFFSET+64] = bg_palettes
    rom[PALETTE_DATA_OFFSET+64:PALETTE_DATA_OFFSET+128] = obj_palettes

    lookup_table = create_lookup_table()
    LOOKUP_TABLE_OFFSET = 0x036E00
    rom[LOOKUP_TABLE_OFFSET:LOOKUP_TABLE_OFFSET+256] = lookup_table

    sprite_loop = create_shadow_only_loop(0x6E00)
    print(f"Sprite loop size: {len(sprite_loop)} bytes")

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

    print(f"✓ Created: {output_rom}")
    print(f"  Shadow-only approach (no actual OAM modification)")

if __name__ == "__main__":
    main()
