#!/usr/bin/env python3
"""
v0.52: 5 colors with 8 slots each (fewer split monsters).

v0.51 had too many boundary crossings with 5 slots each.
Larger ranges = fewer monsters spanning multiple colors:
- Slots 0-7:   Palette 1 (GREEN - Sara W)
- Slots 8-15:  Palette 2 (BLUE)
- Slots 16-23: Palette 3 (ORANGE)
- Slots 24-31: Palette 4 (PURPLE)
- Slots 32-39: Palette 5 (CYAN)
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

    obj_keys = ['Default', 'Sara', 'Hornet', 'Wolf',
                'OtherEnemies', 'Unused5', 'Hazard', 'Miniboss']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    return bytes(bg_data), bytes(obj_data)


def create_tile_lookup_loop(lookup_table_addr: int) -> bytes:
    """
    v0.66: Tile-based palette lookup.

    For each sprite:
    1. Read tile ID
    2. Look up palette from 256-byte table
    3. Set palette bits in flags

    Modifies all three OAM locations for redundancy.
    """
    code = bytearray()
    lo = lookup_table_addr & 0xFF
    hi = (lookup_table_addr >> 8) & 0xFF

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Process all three OAM locations: 0xFE00, 0xC000, 0xC100
    for base_hi in [0xFE, 0xC0, 0xC1]:
        # HL = base + 2 (tile ID byte)
        code.extend([0x21, 0x02, base_hi])  # LD HL, base+2
        code.extend([0x06, 0x28])  # LD B, 40 sprites

        loop_start = len(code)

        # Read tile ID into E
        code.append(0x5E)  # LD E, [HL]
        code.extend([0x16, 0x00])  # LD D, 0

        # Save HL
        code.append(0xE5)  # PUSH HL

        # Look up palette: HL = lookup_table + tile_id
        code.extend([0x21, lo, hi])  # LD HL, lookup_table
        code.append(0x19)  # ADD HL, DE
        code.append(0x4E)  # LD C, [HL] - palette into C

        # Restore HL (at tile ID)
        code.append(0xE1)  # POP HL
        code.append(0x23)  # INC HL (now at flags)

        # Modify flags: clear bits 0-2, set palette from C
        code.append(0x7E)  # LD A, [HL]
        code.extend([0xE6, 0xF8])  # AND 0xF8
        code.append(0xB1)  # OR C
        code.append(0x77)  # LD [HL], A

        # Next sprite (flags+1 -> Y -> X -> tile = +3)
        code.extend([0x23, 0x23, 0x23])  # INC HL x3

        code.append(0x05)  # DEC B
        loop_offset = loop_start - len(code) - 2
        code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_bg_attribute_modifier_visible(row_counter_addr: int = 0x6A80) -> bytes:
    """
    Scroll-aware BG attribute modifier - processes visible rows only.
    Each frame processes 2 rows of the visible 18-row area.
    Only targets specific hazard tile IDs (0x74).

    Uses SCY to determine which tilemap rows are visible.
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Get current row counter (0-17, wraps)
    code.extend([0x21, row_counter_addr & 0xFF, row_counter_addr >> 8])  # LD HL, counter
    code.append(0x7E)  # LD A, [HL]
    code.append(0x47)  # LD B, A (save row offset in B)

    # Increment and wrap counter at 18
    code.append(0x3C)  # INC A
    code.extend([0xFE, 0x12])  # CP 18
    code.extend([0x38, 0x01])  # JR C, +1 (skip reset if < 18)
    code.append(0xAF)  # XOR A (reset to 0)
    code.append(0x77)  # LD [HL], A (save new counter)

    # Get SCY (vertical scroll)
    code.extend([0xF0, 0x42])  # LDH A, [SCY]
    code.extend([0xE6, 0xF8])  # AND 0xF8 (round to tile: /8 * 8)
    code.append(0x0F)  # RRCA (divide by 2)
    code.append(0x0F)  # RRCA (divide by 4)
    code.append(0x0F)  # RRCA (divide by 8) - now A = tile row from scroll
    # Add row offset
    code.append(0x80)  # ADD B
    code.extend([0xE6, 0x1F])  # AND 0x1F (wrap at 32 rows)

    # Calculate tilemap row address: HL = 0x9800 + (row * 32)
    # row * 32 = row << 5
    code.append(0x6F)  # LD L, A
    code.extend([0x26, 0x00])  # LD H, 0
    code.append(0x29)  # ADD HL, HL (x2)
    code.append(0x29)  # ADD HL, HL (x4)
    code.append(0x29)  # ADD HL, HL (x8)
    code.append(0x29)  # ADD HL, HL (x16)
    code.append(0x29)  # ADD HL, HL (x32)
    code.extend([0x01, 0x00, 0x98])  # LD BC, 0x9800
    code.append(0x09)  # ADD HL, BC

    # Process 32 tiles in this row (full row width)
    code.extend([0x0E, 0x20])  # LD C, 32

    # --- Tile loop ---
    loop_start = len(code)

    # Switch to VRAM bank 0, read tile
    code.append(0xAF)  # XOR A
    code.extend([0xE0, 0x4F])  # LDH [VBK], A
    code.append(0x7E)  # LD A, [HL]

    # Check if hazard tile (0x6A-0x6F only - avoids shared ceiling tiles)
    code.extend([0xFE, 0x6A])  # CP 0x6A
    code.extend([0x38, 0x06])  # JR C, .not_hazard (A < 0x6A)
    code.extend([0xFE, 0x70])  # CP 0x70
    code.extend([0x30, 0x02])  # JR NC, .not_hazard (A >= 0x70)
    code.extend([0x06, 0x01])  # LD B, 1 (palette 1 = hazard)
    code.extend([0x18, 0x02])  # JR .write
    # .not_hazard
    code.extend([0x06, 0x00])  # LD B, 0 (palette 0)

    # .write - switch to VRAM bank 1, write attribute
    code.extend([0x3E, 0x01])  # LD A, 1
    code.extend([0xE0, 0x4F])  # LDH [VBK], A
    code.append(0x70)  # LD [HL], B

    # Next tile
    code.append(0x23)  # INC HL
    code.append(0x0D)  # DEC C
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

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
    # v0.71: Added incremental BG attribute modifier for hazards
    # 0x6800: Palette data (128 bytes) -> ends 0x6880
    # 0x6880: Tile lookup table (256 bytes) -> ends 0x6980
    # 0x6980: OAM palette loop (~100 bytes) -> ends ~0x69E4
    # 0x69F0: Palette loader (~40 bytes) -> ends ~0x6A18
    # 0x6A20: BG attribute modifier (~70 bytes) -> ends ~0x6A70
    # 0x6A80: BG counter (2 bytes)
    # 0x6A90: Combined function (~70 bytes)

    BANK13_BASE = 0x034000  # Bank 13 file offset

    # Memory layout for v0.71 with BG modifier
    PALETTE_DATA = 0x6800      # 128 bytes -> ends 0x6880
    TILE_LOOKUP = 0x6880       # 256 bytes -> ends 0x6980
    OAM_LOOP = 0x6980          # ~100 bytes -> ends ~0x69E4
    PALETTE_LOADER = 0x69F0    # ~40 bytes -> ends ~0x6A18
    BG_MODIFIER = 0x6A20       # ~70 bytes -> ends ~0x6A70
    BG_COUNTER = 0x6A80        # 2 bytes for position counter
    COMBINED_FUNC = 0x6A90     # ~70 bytes

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes

    # Load and write tile lookup table
    tile_lookup = load_tile_mappings_from_yaml(palette_yaml)
    offset = BANK13_BASE + (TILE_LOOKUP - 0x4000)
    rom[offset:offset+256] = tile_lookup
    print(f"Tile lookup table: 256 bytes at 0x{TILE_LOOKUP:04X}")

    # Write OAM palette loop (tile-based)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    oam_loop = create_tile_lookup_loop(TILE_LOOKUP)
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM palette loop (tile-based): {len(oam_loop)} bytes")

    # Write palette loader
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    palette_loader = create_palette_loader()
    rom[offset:offset+len(palette_loader)] = palette_loader

    # Write BG attribute modifier (scroll-aware version)
    offset = BANK13_BASE + (BG_MODIFIER - 0x4000)
    bg_modifier = create_bg_attribute_modifier_visible(BG_COUNTER)
    rom[offset:offset+len(bg_modifier)] = bg_modifier
    print(f"BG attribute modifier (scroll-aware): {len(bg_modifier)} bytes")

    # Initialize BG counter to 0
    offset = BANK13_BASE + (BG_COUNTER - 0x4000)
    rom[offset:offset+2] = bytes([0x00, 0x00])

    # Write combined function: original input + OAM loop + BG modifier + palette load
    combined = bytearray()
    combined.extend(original_input)  # Original input handler
    # Remove trailing RET if present, we'll add our own
    if combined[-1] == 0xC9:
        combined = combined[:-1]
    combined.extend([0xCD, OAM_LOOP & 0xFF, OAM_LOOP >> 8])  # CALL OAM loop
    combined.extend([0xCD, BG_MODIFIER & 0xFF, BG_MODIFIER >> 8])  # BG modifier for hazards (0x69-0x7F)
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
    print(f"  v0.75: BG hazard colorization (tiles 0x69-0x7F)")
    print(f"  Sprites: Sara=green, Hornet=yellow, Wolf=gray, Miniboss=red")
    print(f"  BG: Spike log tiles (0x69-0x7F) -> palette 1 (brown/wood)")


if __name__ == "__main__":
    main()
