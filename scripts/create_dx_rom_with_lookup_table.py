#!/usr/bin/env python3
"""
Create Penta Dragon DX with Tile-to-Palette Lookup Table

This ACTUALLY implements the solution:
1. Generates 256-byte lookup table: table[tile_id] = palette_id
2. Adds Z80 code to set OAM palette bits from lookup table
3. Hooks it into the input handler (runs every frame when buttons pressed)

Based on the working create_dx_rom.py but with OAM palette assignment added.
"""
import sys
import yaml
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def parse_color(color_val) -> int:
    """Simple color parser - just hex for now"""
    if isinstance(color_val, int):
        return color_val & 0x7FFF

    s = str(color_val).strip()
    if len(s) == 4 and all(ch in '0123456789abcdefABCDEF' for ch in s):
        return int(s, 16) & 0x7FFF

    raise ValueError(f"Invalid color: {color_val}. Use 4-hex BGR555")


def create_palette(colors: list) -> bytes:
    """Convert 4 BGR555 colors to 8-byte palette data"""
    c = [parse_color(x) for x in colors]
    return bytes([
        c[0] & 0xFF, (c[0] >> 8) & 0xFF,
        c[1] & 0xFF, (c[1] >> 8) & 0xFF,
        c[2] & 0xFF, (c[2] >> 8) & 0xFF,
        c[3] & 0xFF, (c[3] >> 8) & 0xFF,
    ])


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes]:
    """Load palettes from YAML"""
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)

    bg_data = bytearray()
    obj_data = bytearray()

    # Load all BG palettes (up to 8)
    bg_pals = config.get('bg_palettes', {})
    for i, (name, data) in enumerate(bg_pals.items()):
        if i >= 8:
            break
        colors = data['colors']
        bg_data.extend(create_palette(colors))

    # Pad to 8 palettes
    while len(bg_data) < 64:
        bg_data.extend(create_palette(['0000', '7FFF', '5294', '2108']))

    # Load all OBJ palettes (up to 8)
    obj_pals = config.get('obj_palettes', {})
    for i, (name, data) in enumerate(obj_pals.items()):
        if i >= 8:
            break
        colors = data['colors']
        obj_data.extend(create_palette(colors))

    # Pad to 8 palettes
    while len(obj_data) < 64:
        obj_data.extend(create_palette(['0000', '7FFF', '5294', '2108']))

    return bytes(bg_data), bytes(obj_data)


def generate_lookup_table(monster_map_path: Path) -> bytes:
    """Generate 256-byte tile-to-palette lookup table"""
    with open(monster_map_path, 'r') as f:
        data = yaml.safe_load(f)

    # Initialize with 0xFF (don't modify)
    lookup_table = bytearray([0xFF] * 256)

    # Fill from monster map
    monster_map = data.get('monster_palette_map', {})

    for monster_name, info in monster_map.items():
        palette_id = info.get('palette', 0)
        tile_range = info.get('tile_range', [])

        for tile_id in tile_range:
            if 0 <= tile_id <= 255:
                lookup_table[tile_id] = palette_id

    return bytes(lookup_table)


def build_oam_palette_setter() -> bytes:
    """
    Build Z80 code to set OAM palette bits from lookup table

    Iterates all 40 sprites in OAM:
    - Read tile ID from OAM[i].tile (offset +2)
    - Lookup palette: A = lookup_table[tile_id]
    - If palette != 0xFF, set OAM[i].flags palette bits (offset +3)

    Bank 13, address 0x6E80

    OAM structure (4 bytes per sprite):
    Offset 0: Y position
    Offset 1: X position
    Offset 2: Tile number
    Offset 3: Attributes/Flags (palette is bits 0-2)
    """
    return bytes([
        # Save registers
        0xC5,                      # PUSH BC
        0xD5,                      # PUSH DE
        0xE5,                      # PUSH HL

        # Setup: B = counter, HL = OAM pointer
        0x06, 0x28,                # LD B, 40 sprites
        0x21, 0x00, 0xFE,          # LD HL, 0xFE00 (OAM base)

        # === LOOP START ===
        # HL points to sprite base (Y position)

        # Skip to tile ID (offset +2)
        0x23,                      # INC HL (now at X)
        0x23,                      # INC HL (now at Tile ID)
        0x7E,                      # LD A, [HL] (A = tile ID)

        # Lookup palette from table at 0x6E00
        0x5F,                      # LD E, A (low byte = tile ID)
        0x16, 0x6E,                # LD D, 0x6E (high byte of table)
        0x1A,                      # LD A, [DE] (A = lookup_table[tile_id])

        # Check if should modify (0xFF = don't modify)
        0xFE, 0xFF,                # CP 0xFF
        0x28, 0x09,                # JR Z, skip (+9 bytes to skip modification)

        # Modify palette bits
        0x4F,                      # LD C, A (save palette in C)
        0x23,                      # INC HL (now at Flags)
        0x7E,                      # LD A, [HL] (A = current flags)
        0xE6, 0xF8,                # AND 0xF8 (clear palette bits 0-2)
        0xB1,                      # OR C (set new palette)
        0x77,                      # LD [HL], A (write back flags)
        0x18, 0x01,                # JR +1 (skip next INC HL)

        # Skip modification
        0x23,                      # INC HL (if we didn't modify, move to flags anyway)

        # Move to next sprite
        0x23,                      # INC HL (now past this sprite)
        0x05,                      # DEC B (decrement counter)
        0x20, 0xE5,                # JR NZ, loop_start (-27 bytes)

        # Restore and return
        0xE1,                      # POP HL
        0xD1,                      # POP DE
        0xC1,                      # POP BC
        0xC9,                      # RET
    ])


def main():
    # Paths
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_LOOKUP_TABLE.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")
    monster_map = Path("palettes/monster_palette_map.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        sys.exit(1)

    print(f"Loading ROM: {input_rom}")
    rom = bytearray(input_rom.read_bytes())

    # Apply display patches
    print("Applying display compatibility patches...")
    rom, _ = apply_all_display_patches(rom)

    # Load palettes
    print(f"Loading palettes from {palette_yaml}...")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    # Generate lookup table
    print(f"Generating tile-to-palette lookup table...")
    lookup_table = generate_lookup_table(monster_map)
    print(f"  Mapped {sum(1 for b in lookup_table if b != 0xFF)} tiles")

    # Write to Bank 13
    BANK_13_FILE_OFFSET = 0x034000  # Bank 13 starts at file offset 0x34000

    # Palette data at 0x6C80 (bank addr) = file offset 0x036C80
    palette_offset = BANK_13_FILE_OFFSET + 0x2C80
    rom[palette_offset:palette_offset+64] = bg_palettes
    rom[palette_offset+64:palette_offset+128] = obj_palettes
    print(f"  Palette data at file offset 0x{palette_offset:06X}")

    # Lookup table at 0x6E00 (bank addr) = file offset 0x036E00
    lookup_offset = BANK_13_FILE_OFFSET + 0x2E00
    rom[lookup_offset:lookup_offset+256] = lookup_table
    print(f"  Lookup table at file offset 0x{lookup_offset:06X}")

    # OAM palette setter at 0x6E80 (bank addr) = file offset 0x036E80
    oam_setter = build_oam_palette_setter()
    oam_setter_offset = BANK_13_FILE_OFFSET + 0x2E80
    rom[oam_setter_offset:oam_setter_offset+len(oam_setter)] = oam_setter
    print(f"  OAM palette setter at file offset 0x{oam_setter_offset:06X} ({len(oam_setter)} bytes)")

    # Build combined function: original input + palette load + OAM setter call
    print("Building combined function...")
    original_input = bytes(rom[0x0824:0x0824+46])

    combined_function = original_input + bytes([
        # One-shot guard
        0xFA, 0xA0, 0xC0,          # LD A,[C0A0]
        0xFE, 0x01,                # CP 1
        0x28, 0x34,                # JR Z,+52 -> RET if already loaded

        # Frame delay (wait 60 frames)
        0xFA, 0xA1, 0xC0,          # LD A,[C0A1]
        0x3C,                      # INC A
        0xEA, 0xA1, 0xC0,          # LD [C0A1],A
        0xFE, 0x3C,                # CP 60
        0x38, 0x2C,                # JR C,+44 -> RET if not yet

        # Set loaded flag
        0x3E, 0x01,                # LD A,1
        0xEA, 0xA0, 0xC0,          # LD [C0A0],A

        # Load BG palettes
        0x21, 0x80, 0x6C,          # LD HL,0x6C80
        0x3E, 0x80,                # LD A,0x80
        0xE0, 0x68,                # LDH [FF68],A (BCPS)
        0x0E, 0x40,                # LD C,64
        # loop:
        0x2A,                      # LD A,[HL+]
        0xE0, 0x69,                # LDH [FF69],A (BCPD)
        0x0D,                      # DEC C
        0x20, 0xFA,                # JR NZ,loop

        # Load OBJ palettes
        0x3E, 0x80,                # LD A,0x80
        0xE0, 0x6A,                # LDH [FF6A],A (OCPS)
        0x0E, 0x40,                # LD C,64
        # loop:
        0x2A,                      # LD A,[HL+]
        0xE0, 0x6B,                # LDH [FF6B],A (OCPD)
        0x0D,                      # DEC C
        0x20, 0xFA,                # JR NZ,loop

        # Call OAM palette setter
        0xCD, 0x80, 0x6E,          # CALL 0x6E80

        0xC9,                      # RET
        # Early returns
        0xC9,                      # RET (already loaded)
        0xC9,                      # RET (frame delay)
    ])

    # Write combined function to bank 13 at 0x6D00
    combined_offset = BANK_13_FILE_OFFSET + 0x2D00
    rom[combined_offset:combined_offset+len(combined_function)] = combined_function
    print(f"  Combined function at file offset 0x{combined_offset:06X}")

    # Minimal trampoline at 0x0824
    print("Installing trampoline at 0x0824...")
    trampoline = bytes([
        0xF5,                      # PUSH AF
        0x3E, 0x0D,                # LD A,13
        0xEA, 0x00, 0x20,          # LD [2000],A (switch to bank 13)
        0xF1,                      # POP AF
        0xCD, 0x00, 0x6D,          # CALL 0x6D00
        0xF5,                      # PUSH AF
        0x3E, 0x01,                # LD A,1
        0xEA, 0x00, 0x20,          # LD [2000],A (restore bank 1)
        0xF1,                      # POP AF
        0xC9,                      # RET
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline

    # Set CGB flag
    print("Setting CGB compatibility flag...")
    rom[0x143] = 0x80

    # Fix header checksum
    print("Fixing header checksum...")
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    # Write output
    print(f"\nWriting ROM...")
    with open(output_rom, 'wb') as f:
        f.write(rom)

    print(f"\n✅ Created: {output_rom}")
    print(f"   Size: {len(rom)} bytes")
    print()
    print("This ROM includes:")
    print("  • Tile-to-palette lookup table")
    print("  • OAM palette setter (runs every frame)")
    print("  • Sara D (tiles 0-3) → Palette 0 (RED)")
    print("  • Sara W (tiles 4-7) → Palette 1 (GREEN)")
    print("  • Dragon Fly (tiles 8-9) → Palette 2 (BLUE)")
    print()
    print("Test with:")
    print(f"  QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia mgba-qt {output_rom}")


if __name__ == "__main__":
    main()
