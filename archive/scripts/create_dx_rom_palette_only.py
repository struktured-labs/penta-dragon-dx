#!/usr/bin/env python3
"""
Create ROM with ONLY palette loading - no OAM setter

This is a diagnostic step to see if we can get past white screen freeze
without the OAM palette setter code.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches

try:
    import yaml
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pyyaml"], check=True)
    import yaml


def parse_color(c):
    if isinstance(c, int):
        return c & 0x7FFF
    s = str(c).strip()
    if len(s) == 4:
        return int(s, 16) & 0x7FFF
    raise ValueError(f"Invalid color: {c}")


def create_palette(colors):
    c = [parse_color(x) for x in colors]
    return bytes([c[0]&0xFF, c[0]>>8, c[1]&0xFF, c[1]>>8, c[2]&0xFF, c[2]>>8, c[3]&0xFF, c[3]>>8])


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_PALETTE_ONLY.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")

    print("Loading ROM...")
    rom = bytearray(input_rom.read_bytes())

    print("Applying display patches...")
    rom, patches = apply_all_display_patches(rom)
    print(f"  Applied {len(patches)} patches")

    print("Loading palettes...")
    with open(palette_yaml) as f:
        config = yaml.safe_load(f)

    bg_data = bytearray()
    obj_data = bytearray()

    for name, data in list(config['bg_palettes'].items())[:8]:
        bg_data.extend(create_palette(data['colors']))
    while len(bg_data) < 64:
        bg_data.extend(create_palette(['0000', '7FFF', '5294', '2108']))

    for name, data in list(config['obj_palettes'].items())[:8]:
        obj_data.extend(create_palette(data['colors']))
    while len(obj_data) < 64:
        obj_data.extend(create_palette(['0000', '7FFF', '5294', '2108']))

    print("Writing palette data to Bank 13...")
    BANK_13 = 0x034000
    pal_offset = BANK_13 + 0x2C80
    rom[pal_offset:pal_offset+64] = bg_data
    rom[pal_offset+64:pal_offset+128] = obj_data

    print("Creating minimal combined function (NO OAM SETTER)...")
    original_input = bytes(rom[0x0824:0x0824+46])

    # Combined function: input + palette load ONLY (no OAM setter)
    combined = original_input + bytes([
        0xFA, 0xA0, 0xC0,      # LD A,[C0A0]
        0xFE, 0x01,            # CP 1
        0x28, 0x2E,            # JR Z, ret (skip if already loaded)
        0xFA, 0xA1, 0xC0,      # LD A,[C0A1]
        0x3C,                  # INC A
        0xEA, 0xA1, 0xC0,      # LD [C0A1],A
        0xFE, 0x3C,            # CP 60 (1 second delay)
        0x38, 0x26,            # JR C, ret
        0x3E, 0x01,            # LD A, 1
        0xEA, 0xA0, 0xC0,      # LD [C0A0], A
        # Load BG palettes
        0x21, 0x80, 0x6C,      # LD HL, 0x6C80
        0x3E, 0x80,            # LD A, 0x80
        0xE0, 0x68,            # LDH [FF68], A
        0x0E, 0x40,            # LD C, 64
        0x2A, 0xE0, 0x69,      # LD A,[HL+]; LDH [FF69], A
        0x0D, 0x20, 0xFA,      # DEC C; JR NZ, -6
        # Load OBJ palettes
        0x3E, 0x80,            # LD A, 0x80
        0xE0, 0x6A,            # LDH [FF6A], A
        0x0E, 0x40,            # LD C, 64
        0x2A, 0xE0, 0x6B,      # LD A,[HL+]; LDH [FF6B], A
        0x0D, 0x20, 0xFA,      # DEC C; JR NZ, -6
        # NO OAM SETTER CALL HERE
        0xC9,                  # RET
        0xC9, 0xC9,            # Early returns
    ])

    combined_offset = BANK_13 + 0x2D00
    rom[combined_offset:combined_offset+len(combined)] = combined

    print("Installing trampoline...")
    trampoline = bytes([
        0xF5,                  # PUSH AF
        0x3E, 0x0D,            # LD A, 13
        0xEA, 0x00, 0x20,      # LD [2000], A
        0xF1,                  # POP AF
        0xCD, 0x00, 0x6D,      # CALL 0x6D00
        0xF5,                  # PUSH AF
        0x3E, 0x01,            # LD A, 1
        0xEA, 0x00, 0x20,      # LD [2000], A
        0xF1,                  # POP AF
        0xC9,                  # RET
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline

    print("Setting CGB flag...")
    rom[0x143] = 0x80

    print("Fixing checksum...")
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk

    with open(output_rom, 'wb') as f:
        f.write(rom)

    print(f"\n✅ Created: {output_rom}")
    print("   This ROM only loads palettes - NO OAM palette setter")
    print("   Expected: Colors appear but all monsters same color")
    print("   Goal: Verify no white screen freeze")


if __name__ == "__main__":
    main()
