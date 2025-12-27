#!/usr/bin/env python3
"""
v0.44: Run palette code FIRST, before input handler.

v0.43 showed green with mild red flicker - confirms timing issue.
The original input handler may return early on some frames.
Fix: Run OUR code first (unconditionally), then input handler.

This ensures palette modifications happen EVERY frame.
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


def create_slot_palette_loop() -> bytes:
    """
    v0.43 DIAGNOSTIC: Set ALL sprites to palette 1 (GREEN).

    If we still see red flickering with this, our code isn't running
    consistently or something is overwriting after us.
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xE5])  # PUSH AF, BC, HL

    # Set ALL 40 sprites to palette 1 (GREEN)
    code.extend([0x21, 0x03, 0xFE])  # LD HL, 0xFE03 (first sprite's flags)
    code.extend([0x06, 0x28])  # LD B, 40

    loop_start = len(code)
    code.append(0x7E)  # LD A, [HL]
    code.extend([0xE6, 0xF8])  # AND 0xF8 (clear palette bits)
    code.extend([0xF6, 0x01])  # OR 1 (palette 1 = GREEN)
    code.append(0x77)  # LD [HL], A
    code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4 (next sprite)
    code.append(0x05)  # DEC B
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    # Restore registers
    code.extend([0xE1, 0xC1, 0xF1])  # POP HL, BC, AF
    code.append(0xC9)  # RET

    return bytes(code)


def create_palette_loader() -> bytes:
    """Load CGB palettes from bank 13 data."""
    code = bytearray()

    # BG palettes
    code.extend([
        0x21, 0x80, 0x6C,  # LD HL, 0x6C80
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
    # 0x6C80: Palette data (128 bytes)
    # 0x6E00: OAM palette loop (slot-based)
    # 0x6E80: Palette loader
    # 0x6F00: Combined function (original input + palette loop + palette load)

    BANK13_BASE = 0x034000  # Bank 13 file offset

    PALETTE_DATA = 0x6C80
    OAM_LOOP = 0x6E00
    PALETTE_LOADER = 0x6E80
    COMBINED_FUNC = 0x6F00

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes

    # Write OAM palette loop (slot-based, modifies actual OAM at 0xFE00)
    offset = BANK13_BASE + (OAM_LOOP - 0x4000)
    oam_loop = create_slot_palette_loop()
    rom[offset:offset+len(oam_loop)] = oam_loop
    print(f"OAM palette loop (slot-based): {len(oam_loop)} bytes")

    # Write palette loader
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    palette_loader = create_palette_loader()
    rom[offset:offset+len(palette_loader)] = palette_loader

    # Write combined function: palette code FIRST, then input handler
    # v0.44: Run our code first to ensure it runs every frame
    # Original input handler might return early on some frames
    combined = bytearray()
    # OUR CODE FIRST - runs unconditionally
    combined.extend([0xCD, PALETTE_LOADER & 0xFF, PALETTE_LOADER >> 8])  # CALL palette loader
    combined.extend([0xCD, OAM_LOOP & 0xFF, OAM_LOOP >> 8])  # CALL OAM loop
    # Original input handler LAST (includes its own RET)
    combined.extend(original_input)

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
    print(f"  v0.44: Palette code runs FIRST (before input handler)")
    print(f"  All sprites = palette 1 (GREEN) - should be stable now")
    print(f"  If still flickering, something overwrites AFTER our code")


if __name__ == "__main__":
    main()
