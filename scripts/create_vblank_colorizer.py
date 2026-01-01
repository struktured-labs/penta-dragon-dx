#!/usr/bin/env python3
"""
v0.93 STABLE: Simple slot-based palette assignment.

- Slots 0-3: Sara (palette 1)
- Slots 4+: palette 7 (all enemies same color)
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_tile_mappings_from_yaml(yaml_path: Path) -> bytes:
    """Create 256-byte lookup table: tile_id -> palette."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    # Default all tiles to default_palette
    mappings = data.get('sprite_tile_mappings', {})
    default_pal = mappings.get('default_palette', 0)
    lookup = bytearray([default_pal] * 256)

    # Map each monster's tiles to its palette
    for name, info in mappings.items():
        if name == 'default_palette':
            continue
        if not isinstance(info, dict):
            continue

        palette = info.get('palette', 0)

        # Handle tile_ranges format: [[start, end], [start, end], ...]
        tile_ranges = info.get('tile_ranges', [])
        for range_pair in tile_ranges:
            if len(range_pair) == 2:
                start, end = range_pair
                if isinstance(start, str):
                    start = int(start, 16)
                if isinstance(end, str):
                    end = int(end, 16)
                for tile in range(start, end + 1):
                    if 0 <= tile < 256:
                        lookup[tile] = palette

        # Also handle old tiles format for backwards compatibility
        tiles = info.get('tiles', [])
        for tile in tiles:
            if isinstance(tile, str):
                tile = int(tile, 16)
            if 0 <= tile < 256:
                lookup[tile] = palette

    return bytes(lookup)


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

    bg_keys = ['Dungeon', 'Hazard', 'Default2', 'Default3',
               'Default4', 'Default5', 'Default6', 'Default7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_keys = ['Default', 'Sara', 'Reserved2', 'Reserved3',
                'OtherEnemies', 'SpiderBoss', 'BeeBoss', 'ButterflyBoss']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    return bytes(bg_data), bytes(obj_data)


def create_tile_lookup_loop(lookup_table_addr: int) -> bytes:
    """
    v0.96 STABLE: Simple slot-based assignment with boss detection.
    - Slots 0-3: Sara (palette 1)
    - Slots 4+: E (7 for boss, 4 for regular)
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Check boss flag ONCE, store enemy palette in E
    # If 0xFFBF != 0: E = 7 (boss)
    # If 0xFFBF == 0: E = 4 (regular enemy)
    code.extend([0xF0, 0xBF])  # LDH A, [0xFFBF]
    code.extend([0x1E, 0x07])  # LD E, 7 (assume boss)
    code.append(0xB7)          # OR A (set flags)
    code.extend([0x20, 0x02])  # JR NZ, +2 (skip if boss)
    code.extend([0x1E, 0x04])  # LD E, 4 (no boss)

    # Process all three OAM locations: 0xFE00, 0xC000, 0xC100
    for base_hi in [0xFE, 0xC0, 0xC1]:
        # HL = base + 3 (flags byte of sprite 0)
        code.extend([0x21, 0x03, base_hi])  # LD HL, base+3
        code.extend([0x06, 0x28])  # LD B, 40 (sprite counter)
        code.extend([0x0E, 0x00])  # LD C, 0 (slot counter)

        loop_start = len(code)

        # STABLE v0.96: Simple slot-based with E for enemy palette
        # Slots 0-3: Sara (palette 1)
        # Slots 4+: E (7 for boss, 4 for regular)
        code.append(0x79)           # LD A, C (slot number)
        code.extend([0xFE, 0x04])   # CP 4
        code.extend([0x30, 0x04])   # JR NC, +4 (slot >= 4, enemy)
        code.extend([0x3E, 0x01])   # LD A, 1 (Sara palette)
        code.extend([0x18, 0x01])   # JR +1 (skip LD A, E)
        code.append(0x7B)           # LD A, E (enemy palette)
        code.append(0x57)           # LD D, A (save palette)

        # Modify flags byte at [HL]: clear bits 0-2, set palette
        code.append(0x7E)  # LD A, [HL]
        code.extend([0xE6, 0xF8])  # AND 0xF8
        code.append(0xB2)  # OR D
        code.append(0x77)  # LD [HL], A

        # Next sprite (flags -> Y -> X -> tile -> flags = +4)
        code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4
        code.append(0x0C)  # INC C (slot counter)

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_entity_scanner(entity_palette_table: int) -> bytes:
    """
    v0.97: Entity-based palette assignment with HRAM intermediary.

    Scans entity data at 0xC200+ to determine monster types:
    - Entity structure: 24 bytes per entity
    - Entity type at offset 3 (0xC203, 0xC21B, etc.)
    - Lookup palette from table at entity_palette_table

    HRAM layout (0xFF80-0xFFA7):
    - Slots 0-3: Sara (palette 1)
    - Slots 4-7: Entity 1 palette (4 sprites)
    - Slots 8-11: Entity 2 palette (4 sprites)
    - etc.

    Uses unrolled writes to avoid loop timing issues.
    """
    code = bytearray()

    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Check boss flag first - if set, all enemies get palette 7
    code.extend([0xF0, 0xBF])  # LDH A, [0xFFBF]
    code.append(0xB7)          # OR A (set flags)
    boss_skip = len(code)
    code.extend([0x28, 0x00])  # JR Z, skip_boss (patch later)

    # BOSS MODE: All enemies get palette 7 (only slots 0-15 in HRAM)
    code.extend([0x3E, 0x01])  # LD A, 1 (Sara)
    code.extend([0xE0, 0x80])  # LDH [0xFF80], A
    code.extend([0xE0, 0x81])
    code.extend([0xE0, 0x82])
    code.extend([0xE0, 0x83])
    code.extend([0x3E, 0x07])  # LD A, 7 (boss palette)
    for hram_offset in range(0x84, 0x90):  # Only slots 4-15 (0xFF84-0xFF8F)
        code.extend([0xE0, hram_offset])
    # Use JP (absolute) instead of JR - entity detection is >127 bytes
    jp_skip_entity = len(code)
    code.extend([0xC3, 0x00, 0x00])  # JP skip_entity_scan (patch later)

    # Patch boss skip jump
    skip_boss_target = len(code)
    code[boss_skip + 1] = (skip_boss_target - boss_skip - 2) & 0xFF

    # NO BOSS: Entity-based detection
    # Sara slots 0-3 = palette 1
    code.extend([0x3E, 0x01])  # LD A, 1
    code.extend([0xE0, 0x80])  # LDH [0xFF80], A
    code.extend([0xE0, 0x81])
    code.extend([0xE0, 0x82])
    code.extend([0xE0, 0x83])

    # For each enemy entity (9 entities = slots 4-39)
    # Read entity type from 0xC200 + (entity_index * 24) + 3
    # Lookup palette from table
    # Write to 4 consecutive HRAM slots

    # Entity 1: 0xC218 + 3 = 0xC21B -> slots 4-7 (HRAM 0x84-0x87)
    # Entity 2: 0xC230 + 3 = 0xC233 -> slots 8-11 (HRAM 0x88-0x8B)
    # etc.

    # Entity data layout: 24 bytes per entity, type at offset 3
    # Only handle first 3 entities (slots 4-15) to avoid HRAM conflict at 0xFF90+
    # Entity 0: 0xC200 (type at 0xC203) -> OAM slots 4-7 (HRAM 0x84-0x87)
    # Entity 1: 0xC218 (type at 0xC21B) -> OAM slots 8-11 (HRAM 0x88-0x8B)
    # Entity 2: 0xC230 (type at 0xC233) -> OAM slots 12-15 (HRAM 0x8C-0x8F)
    entity_addrs = [
        (0xC203, 0x84),  # Entity 0 -> slots 4-7
        (0xC21B, 0x88),  # Entity 1 -> slots 8-11
        (0xC233, 0x8C),  # Entity 2 -> slots 12-15
    ]

    # DE = entity_palette_table base
    code.extend([0x11, entity_palette_table & 0xFF, (entity_palette_table >> 8) & 0xFF])

    for entity_addr, hram_base in entity_addrs:
        # HL = entity type address
        code.extend([0x21, entity_addr & 0xFF, (entity_addr >> 8) & 0xFF])
        # A = entity type
        code.append(0x7E)  # LD A, [HL]
        # Check if valid entity (type != 0 and type != 0xFF)
        code.append(0xB7)  # OR A
        code.extend([0x28, 0x0A])  # JR Z, use_default (10 bytes ahead)
        code.extend([0xFE, 0xFF])  # CP 0xFF
        code.extend([0x28, 0x06])  # JR Z, use_default (6 bytes ahead)
        # HL = table + type
        code.extend([0x6F])  # LD L, A
        code.extend([0x26, 0x00])  # LD H, 0
        code.append(0x19)  # ADD HL, DE (HL = table + type)
        code.append(0x7E)  # LD A, [HL]
        code.extend([0x18, 0x02])  # JR skip_default (+2)
        # use_default:
        code.extend([0x3E, 0x04])  # LD A, 4 (default enemy palette)
        # skip_default:
        # Write to 4 consecutive HRAM slots
        code.extend([0xE0, hram_base])
        code.extend([0xE0, hram_base + 1])
        code.extend([0xE0, hram_base + 2])
        code.extend([0xE0, hram_base + 3])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    # Patch the JP skip_entity_scan with absolute address
    # The code will be placed at ENTITY_SCANNER = 0x6980
    ENTITY_SCANNER_BASE = 0x6980
    end_offset = len(code) - 5  # Position of POP HL (where we want to jump)
    end_addr = ENTITY_SCANNER_BASE + end_offset
    code[jp_skip_entity + 1] = end_addr & 0xFF
    code[jp_skip_entity + 2] = (end_addr >> 8) & 0xFF

    return bytes(code)


def create_batch_oam_loop() -> bytes:
    """
    v0.97: Hybrid OAM processing loop.

    - Slots 0-15: Read palette from HRAM (0xFF80-0xFF8F)
    - Slots 16+: Use boss flag to determine palette (4 or 7)

    This avoids HRAM region 0xFF90+ which the game uses.
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Check boss flag once, store in E for slots 16+
    code.extend([0xF0, 0xBF])  # LDH A, [0xFFBF]
    code.extend([0x1E, 0x07])  # LD E, 7 (assume boss)
    code.append(0xB7)          # OR A
    code.extend([0x20, 0x02])  # JR NZ, +2
    code.extend([0x1E, 0x04])  # LD E, 4 (no boss)

    # Process all three OAM locations
    for base_hi in [0xFE, 0xC0, 0xC1]:
        code.extend([0x21, 0x03, base_hi])  # LD HL, base+3 (flags of sprite 0)
        code.extend([0x06, 0x28])  # LD B, 40 (sprite counter)
        code.extend([0x0E, 0x00])  # LD C, 0 (slot counter)

        loop_start = len(code)

        # D will hold the palette for this slot
        # Check if slot < 16 (can use HRAM)
        code.append(0x79)          # LD A, C (slot number)
        code.extend([0xFE, 0x10])  # CP 16
        code.extend([0x30, 0x09])  # JR NC, +9 (slot >= 16, use E)

        # Slots 0-15: Read palette from HRAM
        code.append(0xC5)          # PUSH BC (save B=counter, C=slot)
        code.extend([0xC6, 0x80])  # ADD A, 0x80 (A = 0x80 + slot)
        code.append(0x4F)          # LD C, A (HRAM offset)
        code.extend([0xF2])        # LDH A, [C] (read palette)
        code.append(0x57)          # LD D, A (palette in D)
        code.append(0xC1)          # POP BC (restore B and C)
        code.extend([0x18, 0x01])  # JR +1 (skip LD D, E)

        # Slots 16+: Use boss palette from E
        code.append(0x53)          # LD D, E

        # Apply palette
        code.append(0x7E)          # LD A, [HL]
        code.extend([0xE6, 0xF8])  # AND 0xF8
        code.append(0xB2)          # OR D
        code.append(0x77)          # LD [HL], A

        # Next sprite
        code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4
        code.append(0x0C)          # INC C

        code.append(0x05)          # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_bg_attribute_modifier_scy_based() -> bytes:
    """
    v0.85: Simplified - scan entire 32x32 tilemap over 8 frames.

    Process 4 rows per frame starting from row (frame_counter * 4) % 32.
    Uses a byte in WRAM at 0xDFFC (very end of WRAM, unlikely to be used).
    Each frame processes 128 tiles = ~3000 cycles, fits in VBlank.
    Full tilemap covered every 8 frames.
    """
    code = bytearray()

    # Counter address at very end of WRAM (less likely to conflict)
    counter_addr = 0xDFFC

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Get BG tilemap base from LCDC bit 3
    code.extend([0xF0, 0x40])  # LDH A, [LCDC]
    code.extend([0xE6, 0x08])  # AND 0x08
    code.extend([0x28, 0x04])  # JR Z, +4 (use 0x9800)
    code.extend([0x01, 0x00, 0x9C])  # LD BC, 0x9C00
    code.extend([0x18, 0x03])  # JR +3
    code.extend([0x01, 0x00, 0x98])  # LD BC, 0x9800
    # BC now has tilemap base

    # Read counter from WRAM, use as starting row
    code.extend([0xFA, counter_addr & 0xFF, (counter_addr >> 8) & 0xFF])  # LD A, [counter]
    code.extend([0xE6, 0x1F])  # AND 0x1F (ensure 0-31)
    code.append(0x57)  # LD D, A (D = starting row)

    # Increment counter by 4 for next frame
    code.extend([0xC6, 0x04])  # ADD A, 4
    code.extend([0xE6, 0x1F])  # AND 0x1F (wrap at 32)
    code.extend([0xEA, counter_addr & 0xFF, (counter_addr >> 8) & 0xFF])  # LD [counter], A

    # Process 4 rows
    code.extend([0x1E, 0x04])  # LD E, 4 (row count)

    # --- Row loop ---
    row_loop = len(code)

    # Calculate address: HL = BC + (D * 32)
    code.append(0x7A)  # LD A, D
    code.append(0x6F)  # LD L, A
    code.extend([0x26, 0x00])  # LD H, 0
    code.append(0x29)  # ADD HL, HL (x2)
    code.append(0x29)  # ADD HL, HL (x4)
    code.append(0x29)  # ADD HL, HL (x8)
    code.append(0x29)  # ADD HL, HL (x16)
    code.append(0x29)  # ADD HL, HL (x32)
    code.append(0x09)  # ADD HL, BC (add tilemap base)

    # Inner loop: all 32 tiles in row
    code.append(0xC5)  # PUSH BC (save tilemap base)
    code.extend([0x06, 0x20])  # LD B, 32 (tile count)

    tile_loop = len(code)

    # Read tile from VRAM bank 0
    code.append(0xAF)  # XOR A
    code.extend([0xE0, 0x4F])  # LDH [VBK], A
    code.append(0x7E)  # LD A, [HL]

    # Check if hazard tile (0x60-0x7F)
    code.extend([0xFE, 0x60])  # CP 0x60
    code.extend([0x38, 0x0A])  # JR C, .skip (tile < 0x60)
    code.extend([0xFE, 0x80])  # CP 0x80
    code.extend([0x30, 0x06])  # JR NC, .skip (tile >= 0x80)

    # Write palette 1 to VRAM bank 1
    code.extend([0x3E, 0x01])  # LD A, 1
    code.extend([0xE0, 0x4F])  # LDH [VBK], A
    code.extend([0x36, 0x01])  # LD [HL], 1 (palette 1)

    # .skip: Next tile
    code.append(0x23)  # INC HL
    code.append(0x05)  # DEC B
    tile_offset = tile_loop - len(code) - 2
    code.extend([0x20, tile_offset & 0xFF])  # JR NZ, tile_loop

    code.append(0xC1)  # POP BC (restore tilemap base)

    # Next row (with wrap at 32)
    code.append(0x14)  # INC D
    code.append(0x7A)  # LD A, D
    code.extend([0xE6, 0x1F])  # AND 0x1F (wrap at 32)
    code.append(0x57)  # LD D, A
    code.append(0x1D)  # DEC E
    row_offset = row_loop - len(code) - 2
    code.extend([0x20, row_offset & 0xFF])  # JR NZ, row_loop

    # Switch back to VRAM bank 0
    code.append(0xAF)  # XOR A
    code.extend([0xE0, 0x4F])  # LDH [VBK], A

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
    import argparse
    parser = argparse.ArgumentParser(description='Create Penta Dragon DX colorized ROM')
    parser.add_argument('--experimental', '-e', action='store_true',
                        help='Use experimental v0.97 entity-based colorization')
    args = parser.parse_args()

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

    BANK13_BASE = 0x034000  # Bank 13 file offset

    if args.experimental:
        print("\n=== EXPERIMENTAL v0.97: Entity-based colorization ===\n")

        # === BANK 13 LAYOUT for v0.97 ===
        # 0x6800: Palette data (128 bytes)
        # 0x6880: Entity-type-to-palette table (256 bytes)
        # 0x6980: Entity scanner (~200 bytes)
        # 0x6A50: Batch OAM loop (~150 bytes)
        # 0x6AF0: Palette loader (~40 bytes)
        # 0x6B20: Combined function (~80 bytes)

        PALETTE_DATA = 0x6800
        ENTITY_PALETTE_TABLE = 0x6880
        ENTITY_SCANNER = 0x6980
        BATCH_OAM_LOOP = 0x6A50
        PALETTE_LOADER = 0x6AF0
        COMBINED_FUNC = 0x6B20

        # Write palette data
        offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
        rom[offset:offset+64] = bg_palettes
        rom[offset+64:offset+128] = obj_palettes

        # Write entity-type-to-palette table
        # For now, simple mapping:
        # 0x17 -> palette 4 (regular enemy)
        # 0x1D -> palette 5 (miniboss type 1)
        # 0x1E -> palette 6 (miniboss type 2)
        # 0x1F -> palette 7 (boss)
        # Others -> palette 4
        entity_table = bytearray([4] * 256)  # Default to palette 4
        entity_table[0x17] = 4  # Regular enemy
        entity_table[0x1D] = 5  # Miniboss?
        entity_table[0x1E] = 6  # Another type?
        entity_table[0x1F] = 7  # Boss type?

        offset = BANK13_BASE + (ENTITY_PALETTE_TABLE - 0x4000)
        rom[offset:offset+256] = entity_table
        print(f"Entity palette table: 256 bytes at 0x{ENTITY_PALETTE_TABLE:04X}")

        # Write entity scanner
        offset = BANK13_BASE + (ENTITY_SCANNER - 0x4000)
        entity_scanner = create_entity_scanner(ENTITY_PALETTE_TABLE)
        rom[offset:offset+len(entity_scanner)] = entity_scanner
        print(f"Entity scanner: {len(entity_scanner)} bytes at 0x{ENTITY_SCANNER:04X}")

        # Write batch OAM loop
        offset = BANK13_BASE + (BATCH_OAM_LOOP - 0x4000)
        batch_loop = create_batch_oam_loop()
        rom[offset:offset+len(batch_loop)] = batch_loop
        print(f"Batch OAM loop: {len(batch_loop)} bytes at 0x{BATCH_OAM_LOOP:04X}")

        # Write palette loader
        offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
        palette_loader = create_palette_loader()
        rom[offset:offset+len(palette_loader)] = palette_loader
        print(f"Palette loader: {len(palette_loader)} bytes at 0x{PALETTE_LOADER:04X}")

        # Write combined function: original input + entity scanner + batch OAM + palette loader
        combined = bytearray()
        combined.extend(original_input)
        if combined[-1] == 0xC9:
            combined = combined[:-1]
        combined.extend([0xCD, ENTITY_SCANNER & 0xFF, ENTITY_SCANNER >> 8])
        combined.extend([0xCD, BATCH_OAM_LOOP & 0xFF, BATCH_OAM_LOOP >> 8])
        combined.extend([0xCD, PALETTE_LOADER & 0xFF, PALETTE_LOADER >> 8])
        combined.append(0xC9)

        offset = BANK13_BASE + (COMBINED_FUNC - 0x4000)
        rom[offset:offset+len(combined)] = combined
        print(f"Combined function: {len(combined)} bytes at 0x{COMBINED_FUNC:04X}")

        version_str = "v0.97 EXPERIMENTAL: Entity-based colorization"

    else:
        print("\n=== STABLE v0.96: Slot-based colorization ===\n")

        # === BANK 13 LAYOUT for v0.96 ===
        PALETTE_DATA = 0x6800
        TILE_LOOKUP = 0x6880
        OAM_LOOP = 0x6980
        PALETTE_LOADER = 0x69F0
        BG_MODIFIER = 0x6A20
        COMBINED_FUNC = 0x6AA0

        # Write palette data
        offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
        rom[offset:offset+64] = bg_palettes
        rom[offset+64:offset+128] = obj_palettes

        # Load and write tile lookup table
        tile_lookup = load_tile_mappings_from_yaml(palette_yaml)
        offset = BANK13_BASE + (TILE_LOOKUP - 0x4000)
        rom[offset:offset+256] = tile_lookup
        print(f"Tile lookup table: 256 bytes at 0x{TILE_LOOKUP:04X}")

        # Write OAM palette loop
        offset = BANK13_BASE + (OAM_LOOP - 0x4000)
        oam_loop = create_tile_lookup_loop(TILE_LOOKUP)
        rom[offset:offset+len(oam_loop)] = oam_loop
        print(f"OAM palette loop: {len(oam_loop)} bytes at 0x{OAM_LOOP:04X}")

        # Write palette loader
        offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
        palette_loader = create_palette_loader()
        rom[offset:offset+len(palette_loader)] = palette_loader
        print(f"Palette loader: {len(palette_loader)} bytes at 0x{PALETTE_LOADER:04X}")

        # Write BG attribute modifier (disabled but kept for reference)
        offset = BANK13_BASE + (BG_MODIFIER - 0x4000)
        bg_modifier = create_bg_attribute_modifier_scy_based()
        rom[offset:offset+len(bg_modifier)] = bg_modifier

        # Write combined function
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

        version_str = "v0.96 STABLE: Slot-based with boss detection"

    # === TRAMPOLINE (same for both versions) ===
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
    print(f"  {version_str}")


if __name__ == "__main__":
    main()
