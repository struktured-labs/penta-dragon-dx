#!/usr/bin/env python3
import sys
from pathlib import Path

ROM_IN = Path("rom/Penta Dragon (J).gb")
ROM_OUT = Path("rom/working/penta_dragon_dx_FORCE_ORANGE.gb")

# Bank 13 file offsets for BG/OBJ palette blocks
BG_FILE_OFF = 0x036C80
OBJ_FILE_OFF = 0x036CC0

# Simple helper: pack BGR555 into little-endian bytes
def bgr555(val):
    return bytes([val & 0xFF, (val >> 8) & 0xFF])

# Build BG palettes (leave as previously saturated but not critical here)
BG_PALETTES = [
    [0x7FFF, 0x03E0, 0x0280, 0x0000],
    [0x7FFF, 0x7C00, 0x5000, 0x2000],
    [0x7FFF, 0x001F, 0x0014, 0x0008],
    [0x7FFF, 0x7FE0, 0x5CC0, 0x2980],
    [0x7FFF, 0x03FF, 0x02BF, 0x015F],
    [0x7FFF, 0x7C1F, 0x5010, 0x2808],
    [0x7FFF, 0x5EF7, 0x3DEF, 0x1CE7],
    [0x7FFF, 0x6F7B, 0x4E73, 0x2D6B],
]

# FORCE-ORANGE: set indices 1,2,3 to orange for ALL 8 OBJ palettes
# Orange ~= 0x7E00 (R=31,G=31,B~0 with G bias) or 0x7F00; we'll use 0x7E00
ORANGE = 0x7E00
OBJ_PALETTES = [[0x0000, ORANGE, ORANGE, ORANGE] for _ in range(8)]

# Boot-time palette loader in bank 13 at 0x6D00
# Loads 64 bytes BG then 64 bytes OBJ via auto-increment registers
LOADER = bytes([
    0xF5, 0xC5, 0xE5,              # PUSH AF, BC, HL
    0x3E, 0x0D,                    # LD A,13
    0xEA, 0x00, 0x20,              # LD [2000],A
    0x21, 0x80, 0x6C,              # LD HL,6C80 (BG)
    0x3E, 0x80,                    # LD A,80h
    0xE0, 0x68,                    # LDH [FF68],A (BCPS)
    0x0E, 0x40,                    # LD C,64
    0x2A, 0xE0, 0x69,              # loop: LD A,[HL+]; LDH [FF69],A
    0x0D,                          # DEC C
    0x20, 0xFA,                    # JR NZ,loop
    0x3E, 0x80,                    # LD A,80h
    0xE0, 0x6A,                    # LDH [FF6A],A (OCPS)
    0x0E, 0x40,                    # LD C,64
    0x2A, 0xE0, 0x6B,              # loop: LD A,[HL+]; LDH [FF6B],A
    0x0D,                          # DEC C
    0x20, 0xFA,                    # JR NZ,loop
    0x3E, 0x01,                    # LD A,1
    0xEA, 0x00, 0x20,              # LD [2000],A (restore bank 1)
    0xE1, 0xC1, 0xF1,              # POP HL, BC, AF
    0xC3, 0x53, 0x01,              # JP 0x0153 (continue boot)
])

"""
Entry stub at 0x0150: switch to bank 13, CALL 0x6D00,
then jump back to the game's next boot byte at 0x0153.
RET here is unsafe because the original code path at 0x0150
is not a CALL; we JP from 0x0101 to 0x0150, so we must JP onward.
"""
ENTRY = bytes([
    0x3E, 0x0D,                    # LD A,13
    0xEA, 0x00, 0x20,              # LD [2000],A
    0xCD, 0x00, 0x6D,              # CALL 0x6D00
    0xC3, 0x53, 0x01,              # JP 0x0153 (continue original boot)
])


def write_force_orange():
    rom = bytearray(ROM_IN.read_bytes())

    # Compose palette blocks
    bg_bytes = b"".join(bgr555(c) for pal in BG_PALETTES for c in pal)
    obj_bytes = b"".join(bgr555(c) for pal in OBJ_PALETTES for c in pal)

    # Write BG and OBJ into bank 13
    rom[BG_FILE_OFF:BG_FILE_OFF+len(bg_bytes)] = bg_bytes
    rom[OBJ_FILE_OFF:OBJ_FILE_OFF+len(obj_bytes)] = obj_bytes

    # Place loader in bank 13 at 0x6D00 (file 0x036D00)
    rom[0x036D00:0x036D00+len(LOADER)] = LOADER

    # Boot hook: set 0x0100 JP to 0x0150, then at 0x0150 run ENTRY
    # Preserve any original bytes after 0x0153 by only overwriting our stub range
    rom[0x0100] = 0x00
    rom[0x0101:0x0104] = bytes([0xC3, 0x50, 0x01])
    rom[0x0150:0x0150+len(ENTRY)] = ENTRY

    # Set CGB flag
    rom[0x0143] = 0x80

    # Fix header checksum
    chk = 0
    for i in range(0x0134, 0x014D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x014D] = chk

    ROM_OUT.parent.mkdir(parents=True, exist_ok=True)
    ROM_OUT.write_bytes(rom)
    print(f"✓ Built {ROM_OUT}")
    print("  - OBJ indices 1–3 set to ORANGE in all 8 palettes")
    print("  - Boot-time loader writes BG+OBJ palettes once")
    print("  - Works regardless of OBP shade→index using 1/2/3")


if __name__ == "__main__":
    write_force_orange()
