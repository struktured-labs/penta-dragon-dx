#!/usr/bin/env python3
"""
v0.97: Tile-based colorization with Sara W/D distinction and boss-specific palettes.

Features:
- Sara W (tiles 0x20-0x27): Palette 2 (skin/pink)
- Sara D (tiles 0x28-0x2F): Palette 1 (green)
- Gargoyle miniboss (boss_flag=1): Palette 6
- Spider miniboss (boss_flag=2): Palette 7
- Normal enemies: Tile-based palette lookup
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def create_tile_palette_table() -> bytes:
    """
    Create 256-byte tile-to-palette lookup table for normal mode.

    Tile ranges and palettes:
    0x00-0x1F: Palette 0 (effects)
    0x20-0x27: Palette 2 (Sara W) - but handled in code
    0x28-0x2F: Palette 1 (Sara D) - but handled in code
    0x30-0x3F: Palette 3 (crow/flying dark)
    0x40-0x4F: Palette 4 (hornets/flying)
    0x50-0x5F: Palette 4 (ground/orc)
    0x60-0x6F: Palette 5 (humanoid/soldier/moth)
    0x70-0x7F: Palette 3 (catfish/special)
    0x80-0xFF: Palette 4 (default)
    """
    table = bytearray(256)

    for tile in range(256):
        if tile < 0x20:
            table[tile] = 0  # Effects
        elif tile < 0x28:
            table[tile] = 2  # Sara W
        elif tile < 0x30:
            table[tile] = 1  # Sara D
        elif tile < 0x40:
            table[tile] = 3  # Crow/flying dark
        elif tile < 0x50:
            table[tile] = 4  # Hornets/flying
        elif tile < 0x60:
            table[tile] = 4  # Ground/orc
        elif tile < 0x70:
            table[tile] = 5  # Humanoid
        elif tile < 0x80:
            table[tile] = 3  # Catfish/special
        else:
            table[tile] = 4  # Default

    return bytes(table)


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

    # BG palettes
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    # OBJ palettes - new v0.97 layout
    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'CrowCatfish',
                'RegularBlue', 'HumanoidPurple', 'GargoyleBoss', 'SpiderBoss']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    return bytes(bg_data), bytes(obj_data)


def create_v097_oam_loop(tile_table_addr: int) -> bytes:
    """
    v0.97: Tile-based OAM colorization with Sara W/D detection.

    Logic:
    1. Read Sara's tile from slot 0 to determine Sara W (0x20-0x27) vs D (0x28-0x2F)
    2. Check boss_flag:
       - boss_flag=1: Gargoyle -> all enemies palette 6
       - boss_flag=2: Spider -> all enemies palette 7
       - boss_flag=0: Tile-based palette lookup for enemies
    3. For each sprite:
       - Slots 0-3: Sara palette (1 or 2)
       - Slots 4+: Enemy palette (based on boss_flag or tile lookup)

    Register usage:
    - HL: Current sprite address (preserved across tile lookup via PUSH/POP)
    - B: Sprite counter (40 down to 0)
    - C: Slot number (0 to 39)
    - D: Sara palette (stored once, reused)
    - E: Boss palette (0 = use tile lookup, 6 = Gargoyle, 7 = Spider)
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # === Determine Sara palette (store in D) ===
    # Read form flag at 0xFFBE: 0 = Sara W, 1 = Sara D
    code.extend([0xF0, 0xBE])        # LDH A, [0xFFBE] - Sara form flag
    code.append(0xB7)                # OR A (test if zero)
    code.extend([0x20, 0x04])        # JR NZ, +4 (form != 0 = Sara D)
    code.extend([0x16, 0x02])        # LD D, 2 (Sara W palette - skin/pink)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Sara D palette - green)

    # === Determine enemy palette (store in E) ===
    # Check boss_flag at 0xFFBF
    # E: 0 = tile lookup, 6 = gargoyle, 7 = spider
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.append(0xB7)                # OR A
    code.extend([0x28, 0x0C])        # JR Z, +12 (no boss, E=0)

    # Boss mode: Check boss_flag value
    code.extend([0xFE, 0x02])        # CP 2
    code.extend([0x38, 0x04])        # JR C, +4 (boss_flag < 2 = Gargoyle)
    code.extend([0x1E, 0x07])        # LD E, 7 (Spider palette)
    code.extend([0x18, 0x06])        # JR +6 (skip gargoyle and no-boss code)
    code.extend([0x1E, 0x06])        # LD E, 6 (Gargoyle palette)
    code.extend([0x18, 0x02])        # JR +2 (skip no-boss code)
    # No boss: E = 0 means use tile lookup
    code.extend([0x1E, 0x00])        # LD E, 0

    # === Process all three OAM locations ===
    # Hardware OAM (0xFE00) for immediate effect
    # Shadow buffers (0xC000, 0xC100) for persistence across frames
    table_low = tile_table_addr & 0xFF   # 0x80
    table_high = (tile_table_addr >> 8) & 0xFF  # 0x68

    for base_hi in [0xFE, 0xC0, 0xC1]:  # All three OAM locations
        # HL = base address (sprite 0)
        code.extend([0x21, 0x00, base_hi])  # LD HL, base
        code.extend([0x06, 0x28])           # LD B, 40 (sprite count)
        # C is free - use as palette temp

        loop_start = len(code)

        # Calculate slot number: slot = 40 - B
        code.extend([0x3E, 0x28])    # LD A, 40
        code.append(0x90)            # SUB B (A = 40 - B = slot)
        code.extend([0xFE, 0x04])    # CP 4
        code.extend([0x30, 0x03])    # JR NC, +3 (slot >= 4, enemy) - skip 3 bytes

        # Sara: Use palette D
        code.append(0x7A)            # LD A, D (Sara palette)
        code.extend([0x18, 0x12])    # JR +18 (skip to apply palette)

        # Enemy slot (4+): Check E for boss palette or tile lookup
        code.append(0x7B)            # LD A, E
        code.append(0xB7)            # OR A
        code.extend([0x20, 0x0E])    # JR NZ, +14 (use boss palette in A=E)

        # Tile lookup: Read tile at HL+2, lookup in table
        code.append(0xE5)            # PUSH HL (save sprite pointer)
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL (HL = tile address)
        code.append(0x7E)            # LD A, [HL] - tile ID
        # Calculate table address: HL = 0x6880 + A
        code.extend([0xC6, table_low])  # ADD A, 0x80
        code.append(0x6F)            # LD L, A
        code.extend([0x3E, table_high])  # LD A, 0x68
        code.extend([0xCE, 0x00])    # ADC A, 0 (add carry)
        code.append(0x67)            # LD H, A
        code.append(0x7E)            # LD A, [HL] - palette from table
        code.append(0xE1)            # POP HL (restore sprite pointer)

        # A now contains the palette (from tile lookup or boss palette)

        # === Apply palette ===
        # A = palette to apply
        code.append(0x4F)            # LD C, A (save palette)
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL
        code.append(0x23)            # INC HL (HL = flags byte)
        code.append(0x7E)            # LD A, [HL]
        code.extend([0xE6, 0xF8])    # AND 0xF8 (clear palette bits 0-2)
        code.append(0xB1)            # OR C (set new palette)
        code.append(0x77)            # LD [HL], A

        # Next sprite: HL++, B--
        code.append(0x23)            # INC HL (move to next sprite)
        code.append(0x05)            # DEC B

        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_palette_loader() -> bytes:
    """Load CGB palettes from bank 13 data at 0x6800."""
    code = bytearray()

    # BG palettes (at 0x6800)
    code.extend([
        0x21, 0x00, 0x68,  # LD HL, 0x6800
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
    output_rom = Path("rom/working/penta_dragon_dx_v097.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        return

    if not palette_yaml.exists():
        print(f"ERROR: Palette file not found: {palette_yaml}")
        return

    rom = bytearray(input_rom.read_bytes())

    # Save original input handler BEFORE any patches
    original_input = bytes(rom[0x0824:0x0824+46])

    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80  # CGB flag

    # Load palettes
    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    print("\n=== v0.97: Tile-based colorization ===")
    print("  Sara W (0x20-0x27): Palette 2 (skin/pink)")
    print("  Sara D (0x28-0x2F): Palette 1 (green)")
    print("  Gargoyle (boss_flag=1): Palette 6")
    print("  Spider (boss_flag=2): Palette 7")
    print("  Normal enemies: Tile-based lookup")
    print()

    BANK13_BASE = 0x034000  # Bank 13 file offset

    # === BANK 13 LAYOUT ===
    PALETTE_DATA = 0x6800      # 128 bytes
    TILE_TABLE = 0x6880        # 256 bytes
    OAM_LOOP = 0x6980          # ~200 bytes
    PALETTE_LOADER = 0x6A60    # ~40 bytes
    COMBINED_FUNC = 0x6A90     # ~60 bytes

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes
    print(f"Palette data: 128 bytes at 0x{PALETTE_DATA:04X}")

    # Write tile lookup table
    tile_table = create_tile_palette_table()
    offset = BANK13_BASE + (TILE_TABLE - 0x4000)
    rom[offset:offset+256] = tile_table
    print(f"Tile lookup table: 256 bytes at 0x{TILE_TABLE:04X}")

    # Write OAM loop
    oam_loop = create_v097_oam_loop(TILE_TABLE)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM loop: {len(oam_loop)} bytes at 0x{OAM_LOOP:04X}")

    # Write palette loader
    palette_loader = create_palette_loader()
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    rom[offset:offset+len(palette_loader)] = palette_loader
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{PALETTE_LOADER:04X}")

    # Write combined function: original input + OAM loop + palette loader
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

    # === TRAMPOLINE ===
    trampoline = bytearray()
    trampoline.extend([0xF5])  # PUSH AF
    trampoline.extend([0x3E, 0x0D])  # LD A, 13
    trampoline.extend([0xEA, 0x00, 0x20])  # LD [0x2000], A
    trampoline.extend([0xCD, COMBINED_FUNC & 0xFF, COMBINED_FUNC >> 8])
    trampoline.extend([0x3E, 0x01])  # LD A, 1
    trampoline.extend([0xEA, 0x00, 0x20])  # LD [0x2000], A
    trampoline.extend([0xF1])  # POP AF
    trampoline.append(0xC9)  # RET

    rom[0x0824:0x0824+len(trampoline)] = trampoline
    remaining = 46 - len(trampoline)
    if remaining > 0:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * remaining)
    print(f"Trampoline: {len(trampoline)} bytes at 0x0824")

    # Fix header checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)

    print(f"\nCreated: {output_rom}")
    print("  v0.97: Tile-based with Sara W/D distinction")


if __name__ == "__main__":
    main()
