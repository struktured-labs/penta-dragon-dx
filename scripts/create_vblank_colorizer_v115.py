#!/usr/bin/env python3
"""
v1.15: O(1) BG Colorization via CALL Hook

TRUE O(1) solution! Hooks the game's tile copy CALL sites.

Architecture:
1. Patch CALL 42A7 at 0x43BA → CALL FFDE
2. Patch CALL 42A7 at 0x43D5 → CALL FFDE
3. HRAM Hook (FFDE, 15 bytes) - calls original, then colorizes
4. BG Colorizer (WRAM Bank 2, D000) - processes the 192 tiles just copied

This is SAFE because:
- We're patching CALL targets, not modifying any vectors
- The original tile copy routine is untouched
- RST vectors are left alone

Memory Layout:
  FFDE-FFEC: HRAM hook (15 bytes)
  D000-D0FF: WRAM bank 2 colorizer (~80 bytes)
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


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

    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_hram_trampoline() -> bytes:
    """
    HRAM hook at FFDE (exactly 15 bytes to fit FFDE-FFEC).

    Called INSTEAD of the original tile copy (42A7).
    Uses CFF0 (in WRAM bank 0, always accessible) as marker byte:
      - CFF0 = 0x00 (before init): skip colorizer, return immediately (still in bank 1!)
      - CFF0 = 0xFF (after init): switch to bank 2 and run colorizer

    CRITICAL: Check marker BEFORE switching banks so RET Z returns in bank 1!
    """
    code = bytearray([
        0xCD, 0xA7, 0x42, # CALL 42A7 - original tile copy FIRST (3 bytes)
        0xFA, 0xF0, 0xCF, # LD A, [CFF0] - marker in bank 0 (always accessible) (3 bytes)
        0xB7,             # OR A - check if zero (1 byte)
        0xC8,             # RET Z - return if not initialized (still in bank 1 - SAFE!) (1 byte)
        0x3E, 0x02,       # LD A, 0x02 (2 bytes)
        0xE0, 0x70,       # LDH [FF70], A - NOW switch to WRAM bank 2 (2 bytes)
        0xC3, 0x01, 0xD0, # JP D001 - colorizer (restores bank 1 before RET) (3 bytes)
    ])
    # Total: 15 bytes exactly - fits FFDE-FFEC!
    print(f"HRAM hook size: {len(code)} bytes")
    if len(code) != 15:
        raise ValueError(f"HRAM hook must be exactly 15 bytes, got {len(code)}")
    return bytes(code)


def create_wram_bg_colorizer() -> bytes:
    """
    BG colorizer for WRAM bank 2 at D000.

    Called after game copies tiles to VRAM. Sets BG attributes based on
    tile IDs in the C1A0 buffer.

    For item tiles (0x88-0xDF): palette 1 (gold)
    For other tiles: don't modify (keep existing palette 0)
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Save registers
    code.extend([0xF5])              # PUSH AF
    code.extend([0xC5])              # PUSH BC
    code.extend([0xD5])              # PUSH DE
    code.extend([0xE5])              # PUSH HL

    # Determine tilemap address from DC0B (game's toggle)
    # If DC0B & 1 == 0: tilemap = 0x9800
    # If DC0B & 1 == 1: tilemap = 0x9C00
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [DC0B]
    code.extend([0xE6, 0x01])        # AND 1
    code.extend([0x28, 0x04])        # JR Z, +4 (use 9800)
    code.extend([0x26, 0x9C])        # LD H, 0x9C
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x26, 0x98])        # LD H, 0x98
    code.extend([0x2E, 0x00])        # LD L, 0x00
    # Now HL = tilemap address (0x9800 or 0x9C00)

    # DE = C1A0 (source buffer with tile IDs)
    code.extend([0x11, 0xA0, 0xC1])  # LD DE, C1A0

    # B = 8 rows, C = 24 tiles per row
    code.extend([0x06, 0x08])        # LD B, 8

    labels['row_loop'] = len(code)
    code.extend([0x0E, 0x18])        # LD C, 24

    labels['tile_loop'] = len(code)

    # Read tile ID from buffer
    code.extend([0x1A])              # LD A, [DE]
    code.extend([0x13])              # INC DE

    # Check if item tile (0x88 <= tile < 0xE0)
    code.extend([0xFE, 0x88])        # CP 0x88
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x38, 0x00])        # JR C, not_item

    code.extend([0xFE, 0xE0])        # CP 0xE0
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x30, 0x00])        # JR NC, not_item

    # It's an item tile! Set palette 1 in VRAM bank 1
    # Switch to VRAM bank 1
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK)

    # Read current attribute, set palette to 1
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8 (clear palette bits)
    code.extend([0xF6, 0x01])        # OR 0x01 (set palette 1)
    code.append(0x77)                # LD [HL], A

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    jumps_to_fix.append((len(code), 'next_tile'))
    code.extend([0x18, 0x00])        # JR next_tile

    labels['not_item'] = len(code)
    # Not an item - set palette to 0 (to clear any previous item color)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK = 1)
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8 (clear palette bits, palette = 0)
    code.append(0x77)                # LD [HL], A
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK = 0)

    labels['next_tile'] = len(code)
    code.append(0x23)                # INC HL
    code.append(0x0D)                # DEC C
    jumps_to_fix.append((len(code), 'tile_loop'))
    code.extend([0x20, 0x00])        # JR NZ, tile_loop

    # End of row - skip 8 tiles to next row (tilemap is 32 wide, we did 24)
    code.extend([0x11, 0x08, 0x00])  # LD DE, 8
    code.append(0x19)                # ADD HL, DE

    # Reload DE with next row of buffer (we're at C1A0 + 24*row)
    # Actually DE was already incremented, so it's correct
    # But we clobbered DE with the ADD offset. Need to recalculate.
    # Let me restructure this...

    # Actually, let's save/restore DE around the ADD HL, DE
    # Or use a different approach for the row skip

    # Restructure: use stack to save buffer pointer
    # This is getting complicated. Let me simplify.

    code.append(0x05)                # DEC B
    jumps_to_fix.append((len(code), 'row_loop'))
    code.extend([0x20, 0x00])        # JR NZ, row_loop

    # Restore registers
    code.extend([0xE1])              # POP HL
    code.extend([0xD1])              # POP DE
    code.extend([0xC1])              # POP BC
    code.extend([0xF1])              # POP AF
    code.append(0xC9)                # RET

    # Fix jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        if offset < -128 or offset > 127:
            raise ValueError(f"Jump offset {offset} out of range for {target_label}")
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_wram_bg_colorizer_v2() -> bytes:
    """
    BG colorizer for WRAM bank 2.

    Layout:
      D000: Marker byte (0xFF = initialized)
      D001: Actual colorizer code starts here

    Called via JP D001 from HRAM trampoline.
    Must restore WRAM bank 1 before RET (since we're in bank 2).

    Colorizes the 192 tiles (8 rows x 24 cols) in the tilemap.
    Item tiles (0x88-0xDF) get palette 1 (gold), others get palette 0.
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # D000: Marker byte (0xFF = initialized, 0x00 = not initialized)
    code.append(0xFF)  # Marker - DO NOT REMOVE, trampoline checks this!

    # D001: Actual colorizer code starts here
    # NOTE: We're called from HRAM in WRAM bank 2.
    # DC0B is in bank 1's address space, so we need to temporarily switch.

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Temporarily switch to bank 1 to read DC0B (tilemap toggle)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A - switch to bank 1
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [DC0B] - read tilemap toggle
    code.append(0x47)                # LD B, A - save toggle in B
    code.extend([0x3E, 0x02])        # LD A, 2
    code.extend([0xE0, 0x70])        # LDH [FF70], A - switch back to bank 2

    # Now B contains DC0B. Check bit 0 to select tilemap.
    code.append(0x78)                # LD A, B
    code.extend([0xE6, 0x01])        # AND 1
    code.extend([0x20, 0x04])        # JR NZ, +4 (use 9C00)
    code.extend([0x21, 0x00, 0x98])  # LD HL, 0x9800
    code.extend([0x18, 0x03])        # JR +3
    code.extend([0x21, 0x00, 0x9C])  # LD HL, 0x9C00

    # DE = C1A0 (source buffer)
    code.extend([0x11, 0xA0, 0xC1])  # LD DE, C1A0

    # B = 8 rows
    code.extend([0x06, 0x08])        # LD B, 8

    labels['row_loop'] = len(code)
    # Save row counter
    code.append(0xC5)                # PUSH BC

    # C = 24 tiles per row
    code.extend([0x0E, 0x18])        # LD C, 24

    labels['tile_loop'] = len(code)
    # Read tile ID from buffer
    code.append(0x1A)                # LD A, [DE]
    code.append(0x13)                # INC DE

    # Check if item tile (0x88-0xDF)
    code.extend([0xFE, 0x88])        # CP 0x88
    jumps_to_fix.append((len(code), 'set_pal0'))
    code.extend([0x38, 0x00])        # JR C, set_pal0

    code.extend([0xFE, 0xE0])        # CP 0xE0
    jumps_to_fix.append((len(code), 'set_pal0'))
    code.extend([0x30, 0x00])        # JR NC, set_pal0

    # Item tile - set palette 1
    code.extend([0x3E, 0x01])        # LD A, 1 (palette 1)
    jumps_to_fix.append((len(code), 'write_attr'))
    code.extend([0x18, 0x00])        # JR write_attr

    labels['set_pal0'] = len(code)
    code.extend([0x3E, 0x00])        # LD A, 0 (palette 0)

    labels['write_attr'] = len(code)
    # Save palette value
    code.append(0x47)                # LD B, A

    # Switch to VRAM bank 1
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [VBK], A

    # Write palette (just the palette bits, preserve other flags)
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB0)                # OR B
    code.append(0x77)                # LD [HL], A

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [VBK], A

    # Next tile
    code.append(0x23)                # INC HL
    code.append(0x0D)                # DEC C
    jumps_to_fix.append((len(code), 'tile_loop'))
    code.extend([0x20, 0x00])        # JR NZ, tile_loop

    # End of row - skip 8 positions in tilemap (32-24=8)
    # HL += 8
    code.extend([0x3E, 0x08])        # LD A, 8
    code.append(0x85)                # ADD L
    code.append(0x6F)                # LD L, A
    code.extend([0x30, 0x01])        # JR NC, +1
    code.append(0x24)                # INC H

    # Restore row counter and decrement
    code.append(0xC1)                # POP BC
    code.append(0x05)                # DEC B
    jumps_to_fix.append((len(code), 'row_loop'))
    code.extend([0x20, 0x00])        # JR NZ, row_loop

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF

    # CRITICAL: Restore WRAM bank 1 before returning
    # (We're in bank 2, need to switch back to bank 1 for the game)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A - switch to WRAM bank 1

    code.append(0xC9)                # RET

    # Fix jumps (account for marker byte at position 0)
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    print(f"WRAM colorizer size: {len(code)} bytes (includes marker at D000)")
    return bytes(code)


def create_init_code(trampoline_data_addr: int, colorizer_data_addr: int) -> bytes:
    """
    Initialization code to copy trampoline to HRAM and colorizer to WRAM.
    Called once during palette loading.

    Also sets marker at CFF0 (in WRAM bank 0) to signal initialization complete.
    """
    code = bytearray()

    # Copy 15-byte trampoline from ROM to HRAM (FFDE)
    code.extend([0x21, trampoline_data_addr & 0xFF, (trampoline_data_addr >> 8) & 0xFF])  # LD HL, src
    code.extend([0x11, 0xDE, 0xFF])  # LD DE, FFDE
    code.extend([0x06, 0x0F])        # LD B, 15
    # copy_loop1:
    code.append(0x2A)                # LD A, [HL+]
    code.append(0x12)                # LD [DE], A
    code.append(0x13)                # INC DE
    code.append(0x05)                # DEC B
    code.extend([0x20, 0xFA])        # JR NZ, copy_loop1

    # Switch to WRAM bank 2
    code.extend([0x3E, 0x02])        # LD A, 2
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Copy colorizer from ROM to WRAM D000 (assume ~100 bytes)
    code.extend([0x21, colorizer_data_addr & 0xFF, (colorizer_data_addr >> 8) & 0xFF])  # LD HL, src
    code.extend([0x11, 0x00, 0xD0])  # LD DE, D000
    code.extend([0x06, 0x70])        # LD B, 112 (enough for colorizer ~92 bytes + margin)
    # copy_loop2:
    code.append(0x2A)                # LD A, [HL+]
    code.append(0x12)                # LD [DE], A
    code.append(0x13)                # INC DE
    code.append(0x05)                # DEC B
    code.extend([0x20, 0xFA])        # JR NZ, copy_loop2

    # Switch back to WRAM bank 1 (default)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # SET MARKER at CFF0 (WRAM bank 0 - always accessible)
    # This signals that initialization is complete
    code.extend([0x3E, 0xFF])        # LD A, 0xFF
    code.extend([0xEA, 0xF0, 0xCF])  # LD [CFF0], A - marker = initialized

    code.append(0xC9)                # RET

    return bytes(code)


def create_tile_based_colorizer() -> bytes:
    """OBJ tile-based colorizer (same as v1.11)."""
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])  # LD B, 40
    labels['loop_start'] = len(code)

    code.extend([0x3E, 0x28])
    code.append(0x90)
    code.extend([0xFE, 0x04])
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])

    code.append(0x2B)
    code.append(0x7E)
    code.append(0x23)
    code.append(0x4F)

    code.extend([0xFE, 0x10])
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])

    code.append(0x7B)
    code.append(0xB7)
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])

    code.append(0x79)

    code.extend([0xFE, 0x50])
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])

    code.extend([0xFE, 0x60])
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])

    code.extend([0xFE, 0x70])
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])

    code.extend([0xFE, 0x80])
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])

    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['check_hornet'] = len(code)
    code.append(0x79)
    code.extend([0xFE, 0x40])
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])

    code.extend([0xFE, 0x30])
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x30, 0x00])

    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['sara_palette'] = len(code)
    code.append(0x7A)
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['boss_palette'] = len(code)
    code.extend([0x3E, 0x07])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])

    labels['apply_palette'] = len(code)
    code.append(0x4F)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.append(0xB1)
    code.append(0x77)

    code.extend([0x23, 0x23, 0x23, 0x23])
    code.append(0x05)
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)

    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Colorizes BOTH shadow buffers."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    code.extend([0xF0, 0xBE])
    code.append(0xB7)
    code.extend([0x20, 0x04])
    code.extend([0x16, 0x02])
    code.extend([0x18, 0x02])
    code.extend([0x16, 0x01])

    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x28, 0x08])
    code.extend([0xFE, 0x02])
    code.extend([0x28, 0x06])
    code.extend([0x1E, 0x00])
    code.extend([0x18, 0x06])
    code.extend([0x1E, 0x06])
    code.extend([0x18, 0x02])
    code.extend([0x1E, 0x07])

    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)
    return bytes(code)


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Load CGB palettes with dynamic boss palette swapping."""
    code = bytearray()

    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x0E, 0x40])
    code.extend([0x2A])
    code.extend([0xE0, 0x69])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x30])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x03])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x03])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    code.append(0xC9)
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, init_addr: int) -> bytes:
    """Combined function with initialization."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, init_addr & 0xFF, init_addr >> 8])  # Init trampoline/colorizer
    code.extend([0xCD, 0x80, 0xFF])  # CALL DMA
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook at 0x0824 with input handler."""
    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    return bytes(simplified_input + hook_code)


def create_early_init_bootstrap(init_addr: int) -> bytes:
    """
    Early init bootstrap to run at game startup (before any tile copies).

    Placed in title area (0x0134-0x0142, 15 bytes).
    NOTE: 0x0143 is the CGB flag, must NOT be overwritten by bootstrap!

    Called from patched entry point JP at 0x0101.
    """
    code = bytearray([
        0x21, 0x00, 0x20, # LD HL, 2000 (bank register) - 3 bytes
        0x3E, 0x0D,       # LD A, 13 - 2 bytes
        0x77,             # LD (HL), A - switch to bank 13 - 1 byte
        0xCD, init_addr & 0xFF, (init_addr >> 8) & 0xFF,  # CALL init - 3 bytes
        0x3E, 0x01,       # LD A, 1 - 2 bytes
        0x77,             # LD (HL), A - switch to bank 1 - 1 byte
        0xC3, 0x50, 0x01, # JP 0150 - original entry - 3 bytes
    ])
    # Total: 15 bytes - fits in 0x0134-0x0142, leaves 0x0143 for CGB flag!
    print(f"Early init bootstrap: {len(code)} bytes")
    if len(code) != 15:
        raise ValueError(f"Bootstrap must be exactly 15 bytes, got {len(code)}")
    return bytes(code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v115.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.15: O(1) BG Colorization via HRAM/WRAM Hook ===")
    print("  Early init at startup (0x0134 bootstrap)")
    print("  HRAM trampoline at FFDE (15 bytes)")
    print("  BG colorizer in WRAM bank 2 (D000)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    trampoline_data_addr = 0x6890  # Store trampoline bytes in ROM
    colorizer_data_addr = 0x68A0   # Store WRAM colorizer in ROM
    obj_colorizer_addr = 0x6900
    shadow_main_addr = 0x6980
    palette_loader_addr = 0x69E0
    init_addr = 0x6A60
    combined_addr = 0x6AC0

    # Generate code
    hram_trampoline = create_hram_trampoline()
    wram_colorizer = create_wram_bg_colorizer_v2()
    obj_colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    init_code = create_init_code(trampoline_data_addr, colorizer_data_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, init_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)
    early_bootstrap = create_early_init_bootstrap(init_addr)

    print(f"Early bootstrap: {len(early_bootstrap)} bytes at 0x0134 (title area)")
    print(f"HRAM trampoline: {len(hram_trampoline)} bytes (stored at ROM 0x{trampoline_data_addr:04X})")
    print(f"WRAM colorizer: {len(wram_colorizer)} bytes (stored at ROM 0x{colorizer_data_addr:04X})")
    print(f"OBJ colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Init code: {len(init_code)} bytes at 0x{init_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (trampoline_data_addr - 0x4000):bank13_offset + (trampoline_data_addr - 0x4000) + len(hram_trampoline)] = hram_trampoline
    rom[bank13_offset + (colorizer_data_addr - 0x4000):bank13_offset + (colorizer_data_addr - 0x4000) + len(wram_colorizer)] = wram_colorizer
    rom[bank13_offset + (obj_colorizer_addr - 0x4000):bank13_offset + (obj_colorizer_addr - 0x4000) + len(obj_colorizer)] = obj_colorizer
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (init_addr - 0x4000):bank13_offset + (init_addr - 0x4000) + len(init_code)] = init_code
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    # CRITICAL: Early init bootstrap at startup
    # Write bootstrap to title area (0x0134-0x0142, 15 bytes)
    # NOTE: 0x0143 is CGB flag, set separately below!
    print(f"\nOriginal title at 0x0134: {rom[0x0134:0x0143].hex()}")
    rom[0x0134:0x0143] = early_bootstrap
    print(f"Wrote early bootstrap to 0x0134-0x0142 (15 bytes)")

    # Patch entry point to jump to bootstrap instead of 0x0150
    # Original: 00 C3 50 01 (NOP, JP 0150)
    # New:      00 C3 34 01 (NOP, JP 0134 -> bootstrap)
    print(f"Original entry at 0x0100: {rom[0x0100:0x0104].hex()}")
    rom[0x0101:0x0104] = bytes([0xC3, 0x34, 0x01])  # JP 0134
    print("Patched entry: JP 0134 (bootstrap)")

    # Patch the original code
    print(f"\nOriginal at 0x06D5: {rom[0x06D5:0x06D8].hex()}")
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    print("Patched 0x06D5: 00 00 00 (NOP)")

    # CRITICAL: Patch the CALL sites that invoke tile copy
    # Change CALL 42A7 to CALL FFDE at both locations

    # Patch 0x43BA: CD A7 42 → CD DE FF
    print(f"\nOriginal CALL at 0x43BA: {rom[0x43BA:0x43BD].hex()}")
    rom[0x43BA:0x43BD] = bytes([0xCD, 0xDE, 0xFF])  # CALL FFDE
    print("Patched 0x43BA: CD DE FF (CALL FFDE)")

    # Patch 0x43D5: CD A7 42 → CD DE FF
    print(f"Original CALL at 0x43D5: {rom[0x43D5:0x43D8].hex()}")
    rom[0x43D5:0x43D8] = bytes([0xCD, 0xDE, 0xFF])  # CALL FFDE
    print("Patched 0x43D5: CD DE FF (CALL FFDE)")

    print(f"\nVBlank hook: {len(vblank_hook)} bytes")
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    # Recalculate header checksum (required after modifying 0x0134-0x014C)
    # Checksum = complement of sum of bytes 0x0134-0x014C
    checksum = 0
    for addr in range(0x0134, 0x014D):
        checksum = (checksum - rom[addr] - 1) & 0xFF
    rom[0x014D] = checksum
    print(f"Recalculated header checksum: 0x{checksum:02X}")

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.15 Build Complete ===")
    print("\nKey features:")
    print("  - RST 08 hook (single byte at 0x436D)")
    print("  - Guard code handles uninitialized HRAM gracefully")
    print("  - TRUE O(1) BG colorization when tiles are copied!")


if __name__ == "__main__":
    main()
