#!/usr/bin/env python3
"""
v0.99: Dynamic boss palette swapping - 5 enemy palettes!

Features:
- Palettes 3-7 all available for regular enemies
- When boss_flag=1: Palette 6 becomes Gargoyle, all enemies use it
- When boss_flag=2: Palette 7 becomes Spider, all enemies use it
- No duplicate colors - each enemy type has unique palette

Enemy tile mapping:
- 0x30-0x3F: Crow -> Palette 3 (dark blue)
- 0x40-0x4F: Hornets -> Palette 4 (yellow/orange)
- 0x50-0x5F: Orc/Ground -> Palette 5 (green)
- 0x60-0x6F: Humanoid -> Palette 6 (purple)
- 0x70-0x7F: Catfish -> Palette 7 (cyan)
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
            table[tile] = 2  # Sara (both forms use 0x20-0x2F, differentiated by form flag)
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
    """Load BG, OBJ, and boss palettes from YAML file.

    Returns: (bg_palettes, obj_palettes, gargoyle_palette, spider_palette)
    """
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

    # Boss palettes (for dynamic swap)
    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_v099_oam_loop(tile_table_addr: int) -> bytes:
    """
    v0.99: OAM colorization with 5 enemy palettes.

    When boss_flag=0: Use tile-based palette lookup (palettes 3-7)
    When boss_flag=1: Force all enemies to palette 6 (Gargoyle)
    When boss_flag=2: Force all enemies to palette 7 (Spider)
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # === Determine Sara palette (store in D) ===
    # Read form flag at 0xFFBE: 0 = Sara W, 1 = Sara D
    code.extend([0xF0, 0xBE])        # LDH A, [0xFFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Sara D)
    code.extend([0x16, 0x02])        # LD D, 2 (Sara W)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Sara D)

    # === Determine boss mode (store in E) ===
    # E: 0 = tile lookup, 6 = Gargoyle, 7 = Spider
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.append(0xB7)                # OR A
    code.extend([0x28, 0x0C])        # JR Z, +12 (no boss, E=0)

    # Boss mode: check value
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x38, 0x04])        # JR C, +4 (boss_flag=1 -> Gargoyle)
    code.extend([0x1E, 0x07])        # LD E, 7 (Spider)
    code.extend([0x18, 0x06])        # JR +6
    code.extend([0x1E, 0x06])        # LD E, 6 (Gargoyle)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x1E, 0x00])        # LD E, 0 (no boss)

    table_low = tile_table_addr & 0xFF
    table_high = (tile_table_addr >> 8) & 0xFF

    for base_hi in [0xFE, 0xC0, 0xC1]:  # All three OAM locations
        code.extend([0x21, 0x00, base_hi])  # LD HL, base
        code.extend([0x06, 0x28])           # LD B, 40

        loop_start = len(code)

        # Calculate slot number: slot = 40 - B
        code.extend([0x3E, 0x28])    # LD A, 40
        code.append(0x90)            # SUB B (A = slot)
        code.extend([0xFE, 0x04])    # CP 4
        code.extend([0x30, 0x03])    # JR NC, +3 (slot >= 4, enemy)

        # Sara: Use palette D
        code.append(0x7A)            # LD A, D
        code.extend([0x18, 0x12])    # JR +18 (apply palette)

        # Enemy slot: Check E for boss mode
        code.append(0x7B)            # LD A, E
        code.append(0xB7)            # OR A
        code.extend([0x20, 0x0E])    # JR NZ, +14 (boss mode, use A=E)

        # Normal mode: Tile lookup
        code.append(0xE5)            # PUSH HL
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL (tile address)
        code.append(0x7E)            # LD A, [HL]
        code.extend([0xC6, table_low])  # ADD A, table_low
        code.append(0x6F)            # LD L, A
        code.extend([0x3E, table_high])  # LD A, table_high
        code.extend([0xCE, 0x00])    # ADC A, 0
        code.append(0x67)            # LD H, A
        code.append(0x7E)            # LD A, [HL] (palette from table)
        code.append(0xE1)            # POP HL

        # Apply palette (A = palette number)
        code.append(0x4F)            # LD C, A
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL (flags address)
        code.append(0x7E)            # LD A, [HL]
        code.extend([0xE6, 0xF8])    # AND 0xF8
        code.append(0xB1)            # OR C
        code.append(0x77)            # LD [HL], A

        # Next sprite
        code.append(0x23)            # INC HL
        code.append(0x05)            # DEC B

        loop_offset = loop_start - len(code) - 2
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
    """
    Load CGB palettes with dynamic boss palette swapping.

    When boss_flag=0: Load normal palettes 6 and 7
    When boss_flag=1: Load Gargoyle into palette 6
    When boss_flag=2: Load Spider into palette 7
    """
    code = bytearray()

    # BG palettes (always same)
    code.extend([
        0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF,  # LD HL, palette_data
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

    # OBJ palettes 0-5 (always same) - 48 bytes
    code.extend([
        0x3E, 0x80,        # LD A, 0x80
        0xE0, 0x6A,        # LDH [0x6A], A (OBPI)
        0x0E, 0x30,        # LD C, 48 (palettes 0-5)
    ])
    code.extend([
        0x2A,              # LD A, [HL+]
        0xE0, 0x6B,        # LDH [0x6B], A (OBPD)
        0x0D,              # DEC C
        0x20, 0xFA,        # JR NZ, -6
    ])
    # HL now points to normal palette 6 data

    # Check boss_flag for palette 6
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.extend([0xFE, 0x01])        # CP 1
    code.extend([0x20, 0x05])        # JR NZ, +5 (not Gargoyle)
    # Load Gargoyle palette into palette 6
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])  # LD HL, gargoyle
    code.extend([0x18, 0x00])        # JR +0 (continue to load)

    # Load 8 bytes (palette 6)
    load_pal6_start = len(code)
    code.extend([0x0E, 0x08])        # LD C, 8
    code.extend([
        0x2A,              # LD A, [HL+]
        0xE0, 0x6B,        # LDH [0x6B], A (OBPD)
        0x0D,              # DEC C
        0x20, 0xFA,        # JR NZ, -6
    ])

    # For palette 7, need to set HL correctly
    # After loading palette 6, HL points past it
    # For normal mode, HL points to normal palette 7
    # For boss mode, we already loaded from gargoyle_addr, need to reset to normal palette 7

    # Save current palette 7 source based on boss_flag
    obj_pal7_normal = palette_data_addr + 64 + 56  # offset 56 = palette 7 in OBJ data (after BG 64 + OBJ 0-6*8)

    # Actually simpler: just recalculate HL for palette 7
    code.extend([0x21, (palette_data_addr + 64 + 56) & 0xFF, ((palette_data_addr + 64 + 56) >> 8) & 0xFF])  # LD HL, normal_pal7

    # Check boss_flag for palette 7
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x20, 0x05])        # JR NZ, +5 (not Spider)
    # Load Spider palette into palette 7
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])  # LD HL, spider
    code.extend([0x18, 0x00])        # JR +0 (continue)

    # Load 8 bytes (palette 7)
    code.extend([0x0E, 0x08])        # LD C, 8
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
    output_rom = Path("rom/working/penta_dragon_dx_v099.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        return

    if not palette_yaml.exists():
        print(f"ERROR: Palette file not found: {palette_yaml}")
        return

    rom = bytearray(input_rom.read_bytes())
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80  # CGB flag

    # Load palettes
    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes, gargoyle_pal, spider_pal = load_palettes_from_yaml(palette_yaml)

    print("\n=== v0.99: Dynamic Boss Palette Swap ===")
    print("  5 enemy palettes in normal mode:")
    print("    Palette 3: Crow (dark blue)")
    print("    Palette 4: Hornets (yellow)")
    print("    Palette 5: Orc (green)")
    print("    Palette 6: Humanoid (purple)")
    print("    Palette 7: Catfish (cyan)")
    print("  Boss mode swaps palette 6 or 7:")
    print("    boss_flag=1: Palette 6 -> Gargoyle")
    print("    boss_flag=2: Palette 7 -> Spider")
    print()

    BANK13_BASE = 0x034000

    # Layout
    PALETTE_DATA = 0x6800      # 128 bytes (BG 64 + OBJ 64)
    GARGOYLE_PAL = 0x6880      # 8 bytes
    SPIDER_PAL = 0x6888        # 8 bytes
    TILE_TABLE = 0x6890        # 256 bytes
    OAM_LOOP = 0x6990          # ~180 bytes
    PALETTE_LOADER = 0x6A50    # ~80 bytes
    COMBINED_FUNC = 0x6AB0     # ~60 bytes

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes
    print(f"Palette data: 128 bytes at 0x{PALETTE_DATA:04X}")

    # Write boss palettes
    offset = BANK13_BASE + (GARGOYLE_PAL - 0x4000)
    rom[offset:offset+8] = gargoyle_pal
    offset = BANK13_BASE + (SPIDER_PAL - 0x4000)
    rom[offset:offset+8] = spider_pal
    print(f"Boss palettes: 16 bytes at 0x{GARGOYLE_PAL:04X}")

    # Write tile table
    tile_table = create_tile_palette_table()
    offset = BANK13_BASE + (TILE_TABLE - 0x4000)
    rom[offset:offset+256] = tile_table
    print(f"Tile table: 256 bytes at 0x{TILE_TABLE:04X}")

    # Write OAM loop
    oam_loop = create_v099_oam_loop(TILE_TABLE)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM loop: {len(oam_loop)} bytes at 0x{OAM_LOOP:04X}")

    # Write palette loader
    palette_loader = create_dynamic_palette_loader(PALETTE_DATA, GARGOYLE_PAL, SPIDER_PAL)
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    rom[offset:offset+len(palette_loader)] = palette_loader
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{PALETTE_LOADER:04X}")

    # Combined function
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

    # Trampoline
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

    # Fix checksum
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
