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
        palette = info.get('palette', 0)
        tiles = info.get('tiles', [])
        for tile in tiles:
            # Handle hex strings like "0x20" or integers
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
                'Soldier', 'Slime', 'Hazard', 'Projectiles']
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


def create_bg_attribute_modifier() -> bytes:
    """
    Modify BG tile attributes based on tile ID.
    Hazard tiles (0x3E-0x7F) get palette 1, others get palette 0.

    Scans the visible BG area and sets CGB tile attributes in VRAM bank 1.
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # We need to scan the BG tile map and set attributes
    # BG map is at 0x9800 (32x32 tiles)
    # For each tile, check if it's a hazard tile and set attribute accordingly

    # Process all 1024 tiles (32x32) - this is slow but thorough
    # HL = tile map address (VRAM bank 0)
    # DE = attribute map address (VRAM bank 1, same address)

    code.extend([0x21, 0x00, 0x98])  # LD HL, 0x9800 (BG map)
    code.extend([0x01, 0x00, 0x04])  # LD BC, 0x0400 (1024 tiles)

    # Main loop
    loop_start = len(code)

    # Switch to VRAM bank 0 to read tile ID
    code.extend([0x3E, 0x00])  # LD A, 0
    code.extend([0xE0, 0x4F])  # LDH [0x4F], A (VBK = 0)

    # Read tile ID
    code.append(0x56)  # LD D, [HL] - tile ID into D

    # Check if tile ID is in hazard range (0x3E-0x7F)
    # D >= 0x3E AND D <= 0x7F
    code.append(0x7A)  # LD A, D
    code.extend([0xFE, 0x3E])  # CP 0x3E
    code.extend([0x38, 0x08])  # JR C, +8 (if A < 0x3E, skip to palette 0)
    code.extend([0xFE, 0x80])  # CP 0x80
    code.extend([0x30, 0x04])  # JR NC, +4 (if A >= 0x80, skip to palette 0)
    # In range - use palette 1
    code.extend([0x1E, 0x01])  # LD E, 1 (palette 1)
    code.extend([0x18, 0x02])  # JR +2 (skip palette 0)
    # Not in range - use palette 0
    code.extend([0x1E, 0x00])  # LD E, 0 (palette 0)

    # Switch to VRAM bank 1 to write attribute
    code.extend([0x3E, 0x01])  # LD A, 1
    code.extend([0xE0, 0x4F])  # LDH [0x4F], A (VBK = 1)

    # Write attribute (E contains palette number)
    code.append(0x73)  # LD [HL], E

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])  # LD A, 0
    code.extend([0xE0, 0x4F])  # LDH [0x4F], A (VBK = 0)

    # Next tile
    code.append(0x23)  # INC HL
    code.append(0x0B)  # DEC BC

    # Check if BC == 0
    code.append(0x78)  # LD A, B
    code.append(0xB1)  # OR C
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
    # v0.51: OAM loop is now 378 bytes, need more space!
    # 0x6800: Palette data (128 bytes) -> ends 0x6880
    # 0x6880: OAM palette loop (~400 bytes) -> ends ~0x6A10
    # 0x6A20: Palette loader (32 bytes) -> ends ~0x6A40
    # 0x6A50: Combined function (60 bytes)

    BANK13_BASE = 0x034000  # Bank 13 file offset

    # Memory layout for v0.66 tile-based system
    PALETTE_DATA = 0x6800      # 128 bytes -> ends 0x6880
    TILE_LOOKUP = 0x6880       # 256 bytes -> ends 0x6980
    OAM_LOOP = 0x6980          # ~100 bytes -> ends ~0x69E4
    PALETTE_LOADER = 0x69F0    # ~40 bytes -> ends ~0x6A18
    COMBINED_FUNC = 0x6A20     # ~60 bytes

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

    # Write combined function: original input + OAM loop + palette load
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
    print(f"  v0.66: Tile-based per-monster colorization")
    print(f"  Sara=green, Hornet=yellow, Wolf=gray, Soldier=blue")
    print(f"  Slime=purple, Hazard=brown, Miniboss=red")


if __name__ == "__main__":
    main()
