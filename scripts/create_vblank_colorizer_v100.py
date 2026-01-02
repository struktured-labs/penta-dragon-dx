#!/usr/bin/env python3
"""
v1.00: Flicker reduction via smart shadow buffer selection.

The game double-buffers OAM using 0xC000 and 0xC100, alternating each frame.
0xFFCB contains the toggle (0 or 1) indicating which buffer will be DMA'd next.

Strategy:
- Read 0xFFCB to determine next frame's DMA source
- Modify hardware OAM (0xFE00) for immediate display
- Modify ONLY the next frame's source buffer (not the current frame's)

This ensures our palette changes are in the correct buffer for DMA.
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def create_tile_palette_table() -> bytes:
    """Create 256-byte tile-to-palette lookup table with 5 enemy palettes."""
    table = bytearray(256)

    for tile in range(256):
        if tile < 0x20:
            table[tile] = 0  # Effects
        elif tile < 0x30:
            table[tile] = 2  # Sara (both forms, differentiated by form flag)
        elif tile < 0x40:
            table[tile] = 3  # Crow (dark blue)
        elif tile < 0x50:
            table[tile] = 4  # Hornets (yellow/orange)
        elif tile < 0x60:
            table[tile] = 5  # Orc/Ground (green)
        elif tile < 0x70:
            table[tile] = 6  # Humanoid/Soldier/Moth (purple)
        elif tile < 0x80:
            table[tile] = 7  # Catfish (cyan)
        else:
            table[tile] = 4  # Default for items/misc (yellow)

    return bytes(table)


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

    # BG palettes
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    # OBJ palettes (normal mode)
    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    # Boss palettes
    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_v100_oam_loop(tile_table_addr: int) -> bytes:
    """
    v1.00: Smart shadow buffer selection for flicker reduction.

    Reads 0xFFCB to determine which shadow buffer will be DMA'd next frame,
    then modifies:
    1. Hardware OAM (0xFE00) - immediate display
    2. Next frame's shadow buffer (0xC000 or 0xC100 based on 0xFFCB)
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # === Determine Sara palette (store in D) ===
    code.extend([0xF0, 0xBE])        # LDH A, [0xFFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Sara D)
    code.extend([0x16, 0x02])        # LD D, 2 (Sara W)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Sara D)

    # === Determine boss mode (store in E) ===
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.append(0xB7)                # OR A
    code.extend([0x28, 0x0C])        # JR Z, +12 (no boss, E=0)
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x38, 0x04])        # JR C, +4 (Gargoyle)
    code.extend([0x1E, 0x07])        # LD E, 7 (Spider)
    code.extend([0x18, 0x06])        # JR +6
    code.extend([0x1E, 0x06])        # LD E, 6 (Gargoyle)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x1E, 0x00])        # LD E, 0 (no boss)

    table_low = tile_table_addr & 0xFF
    table_high = (tile_table_addr >> 8) & 0xFF

    # === Process hardware OAM first (immediate display) ===
    code.extend([0x21, 0x00, 0xFE])  # LD HL, 0xFE00
    code.extend([0x06, 0x28])        # LD B, 40

    loop_start_fe = len(code)

    # Calculate slot: A = 40 - B
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B
    code.extend([0xFE, 0x04])        # CP 4
    code.extend([0x30, 0x03])        # JR NC, +3 (enemy slot)

    # Sara palette
    code.append(0x7A)                # LD A, D
    code.extend([0x18, 0x12])        # JR +18

    # Enemy: check boss mode
    code.append(0x7B)                # LD A, E
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x0E])        # JR NZ, +14 (use boss palette)

    # Tile lookup
    code.append(0xE5)                # PUSH HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xC6, table_low])   # ADD A, table_low
    code.append(0x6F)                # LD L, A
    code.extend([0x3E, table_high])  # LD A, table_high
    code.extend([0xCE, 0x00])        # ADC A, 0
    code.append(0x67)                # LD H, A
    code.append(0x7E)                # LD A, [HL]
    code.append(0xE1)                # POP HL

    # Apply palette
    code.append(0x4F)                # LD C, A
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB1)                # OR C
    code.append(0x77)                # LD [HL], A

    code.append(0x23)                # INC HL
    code.append(0x05)                # DEC B

    loop_offset = loop_start_fe - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    # === Now process the NEXT frame's shadow buffer ===
    # Read 0xFFCB to determine which buffer: 0=0xC000, 1=0xC100
    code.extend([0xF0, 0xCB])        # LDH A, [0xFFCB]
    code.extend([0xE6, 0x01])        # AND 0x01
    code.extend([0xC6, 0xC0])        # ADD A, 0xC0  (A = 0xC0 or 0xC1)
    code.append(0x67)                # LD H, A
    code.extend([0x2E, 0x00])        # LD L, 0x00   (HL = 0xC000 or 0xC100)

    code.extend([0x06, 0x28])        # LD B, 40

    loop_start_shadow = len(code)

    # Same logic as above
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B
    code.extend([0xFE, 0x04])        # CP 4
    code.extend([0x30, 0x03])        # JR NC, +3

    code.append(0x7A)                # LD A, D (Sara)
    code.extend([0x18, 0x12])        # JR +18

    code.append(0x7B)                # LD A, E
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x0E])        # JR NZ, +14

    code.append(0xE5)                # PUSH HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xC6, table_low])   # ADD A, table_low
    code.append(0x6F)                # LD L, A
    code.extend([0x3E, table_high])  # LD A, table_high
    code.extend([0xCE, 0x00])        # ADC A, 0
    code.append(0x67)                # LD H, A
    code.append(0x7E)                # LD A, [HL]
    code.append(0xE1)                # POP HL

    code.append(0x4F)                # LD C, A
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB1)                # OR C
    code.append(0x77)                # LD [HL], A

    code.append(0x23)                # INC HL
    code.append(0x05)                # DEC B

    loop_offset = loop_start_shadow - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)  # RET

    return bytes(code)


def create_dynamic_palette_loader(
    palette_data_addr: int,
    gargoyle_addr: int,
    spider_addr: int
) -> bytes:
    """Load CGB palettes with dynamic boss palette swapping."""
    code = bytearray()

    # BG palettes
    code.extend([
        0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF,
        0x3E, 0x80,
        0xE0, 0x68,
        0x0E, 0x40,
    ])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])

    # OBJ palettes 0-5
    code.extend([0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x30])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # Palette 6: check for Gargoyle
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x05])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x18, 0x00])

    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # Palette 7: check for Spider
    obj_pal7_normal = palette_data_addr + 64 + 56
    code.extend([0x21, obj_pal7_normal & 0xFF, (obj_pal7_normal >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x05])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x18, 0x00])

    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    code.append(0xC9)
    return bytes(code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v100.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        return

    rom = bytearray(input_rom.read_bytes())
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80

    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes, gargoyle_pal, spider_pal = load_palettes_from_yaml(palette_yaml)

    print("\n=== v1.00: Flicker Reduction ===")
    print("  Smart shadow buffer selection:")
    print("    - Reads 0xFFCB to find next frame's DMA source")
    print("    - Modifies hardware OAM (immediate)")
    print("    - Modifies correct shadow buffer (next frame)")
    print()

    BANK13_BASE = 0x034000

    PALETTE_DATA = 0x6800
    GARGOYLE_PAL = 0x6880
    SPIDER_PAL = 0x6888
    TILE_TABLE = 0x6890
    OAM_LOOP = 0x6990
    PALETTE_LOADER = 0x6A80
    COMBINED_FUNC = 0x6AE0

    # Write data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes
    print(f"Palette data: 128 bytes at 0x{PALETTE_DATA:04X}")

    offset = BANK13_BASE + (GARGOYLE_PAL - 0x4000)
    rom[offset:offset+8] = gargoyle_pal
    offset = BANK13_BASE + (SPIDER_PAL - 0x4000)
    rom[offset:offset+8] = spider_pal
    print(f"Boss palettes: 16 bytes at 0x{GARGOYLE_PAL:04X}")

    tile_table = create_tile_palette_table()
    offset = BANK13_BASE + (TILE_TABLE - 0x4000)
    rom[offset:offset+256] = tile_table
    print(f"Tile table: 256 bytes at 0x{TILE_TABLE:04X}")

    oam_loop = create_v100_oam_loop(TILE_TABLE)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM loop: {len(oam_loop)} bytes at 0x{OAM_LOOP:04X}")

    palette_loader = create_dynamic_palette_loader(PALETTE_DATA, GARGOYLE_PAL, SPIDER_PAL)
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    rom[offset:offset+len(palette_loader)] = palette_loader
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{PALETTE_LOADER:04X}")

    combined = bytearray()
    combined.extend(original_input)
    if combined[-1] == 0xC9:
        combined = combined[:-1]
    combined.extend([0xCD, OAM_LOOP & 0xFF, OAM_LOOP >> 8])
    combined.extend([0xCD, PALETTE_LOADER & 0xFF, PALETTE_LOADER >> 8])
    combined.append(0xC9)

    offset = BANK13_BASE + (COMBINED_FUNC - 0x4000)
    rom[offset:offset+len(combined)] = combined
    print(f"Combined function: {len(combined)} bytes at 0x{COMBINED_FUNC:04X}")

    trampoline = bytearray()
    trampoline.extend([0xF5])
    trampoline.extend([0x3E, 0x0D])
    trampoline.extend([0xEA, 0x00, 0x20])
    trampoline.extend([0xCD, COMBINED_FUNC & 0xFF, COMBINED_FUNC >> 8])
    trampoline.extend([0x3E, 0x01])
    trampoline.extend([0xEA, 0x00, 0x20])
    trampoline.extend([0xF1])
    trampoline.append(0xC9)

    rom[0x0824:0x0824+len(trampoline)] = trampoline
    remaining = 46 - len(trampoline)
    if remaining > 0:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * remaining)
    print(f"Trampoline: {len(trampoline)} bytes at 0x0824")

    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nCreated: {output_rom}")
    print(f"Also: {fixed_rom}")


if __name__ == "__main__":
    main()
