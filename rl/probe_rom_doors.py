"""Search ROM for arena/teleporter trigger code patterns.

The game's arena entry is at code 0x1A2B (per RE notes).
Search for:
1. Sequences of bytes that compare Sara's position against thresholds
2. Bytes that write D880 = 0x0C..0x14 (LD A, 0x0C-0x14; LDH (D880), A)
3. The FFBA-indexed subtable at 0x1BCA
"""
import sys

ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"

with open(ROM_PATH, "rb") as f:
    rom = f.read()
print(f"ROM size: {len(rom)} bytes ({len(rom)/1024:.0f} KB)")

# Search 1: pattern "LD A, 0x0C; LDH (D880), A" — writes arena scene
# 3E 0C  EA 80 D8 (LD A, $0C; LD [$D880], A) for ROM bank 0
# Or LDH variant: F0/E0
for arena in range(0x0C, 0x15):
    # 3E XX EA 80 D8
    pat = bytes([0x3E, arena, 0xEA, 0x80, 0xD8])
    pos = 0
    found = []
    while True:
        pos = rom.find(pat, pos)
        if pos < 0: break
        found.append(pos)
        pos += 1
    if found:
        print(f"Arena 0x{arena:02X} write site (LD A,XX; LD [D880],A): {len(found)} hits at {[hex(p) for p in found[:5]]}")

# Search 2: FFBA-indexed subtable at 0x1BCA
print(f"\nFFBA subtable at 0x1BCA:")
for i in range(0, 32):
    print(f"  +{i:02X}: 0x{rom[0x1BCA+i]:02X}", end="")
    if (i+1) % 8 == 0: print()

# Search 3: arena entry handler at 0x1A2B
print(f"\nArena handler at 0x1A2B (first 32 bytes):")
for i in range(0, 32):
    print(f"  +{i:02X}: 0x{rom[0x1A2B+i]:02X}", end="")
    if (i+1) % 8 == 0: print()

# Search 4: look for the room transition table at 0x0BBF
print(f"\nRoom transition table at 0x0BBF (16 bytes):")
print("  ", end="")
for i in range(16):
    print(f"0x{rom[0x0BBF+i]:02X}", end=" ")
print()
