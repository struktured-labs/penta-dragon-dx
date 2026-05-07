"""Dump the per-level event sequence subtable for level 0."""
ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
with open(ROM_PATH, "rb") as f:
    rom = f.read()

# Level pointer at 0x1BCA + 0 (level 0) = 2 bytes little-endian
def read_word_le(addr):
    return rom[addr] | (rom[addr+1] << 8)

# Per-level event sequence pointers (9 levels × 2 bytes)
print("Per-level event sequence pointers (FFBA → ROM addr):")
for ffba in range(9):
    ptr = read_word_le(0x1BCA + ffba * 2)
    print(f"  FFBA={ffba}: ptr=0x{ptr:04X}")

# Dump level 0's event sequence
ptr0 = read_word_le(0x1BCA + 0)
print(f"\nLevel 0 event sequence at 0x{ptr0:04X} (40 bytes):")
for i in range(40):
    val = rom[ptr0 + i]
    print(f"  +{i:02X} = 0x{val:02X}", end="")
    # Note: 0x29 = arena event!
    if val == 0x29: print(" *** ARENA EVENT 0x29 ***", end="")
    if (i+1) % 4 == 0: print()
print()

# Also dump level 1's event sequence
ptr1 = read_word_le(0x1BCA + 2)
print(f"\nLevel 1 (FFBA=1) at 0x{ptr1:04X} (40 bytes):")
for i in range(40):
    val = rom[ptr1 + i]
    print(f"  +{i:02X} = 0x{val:02X}", end="")
    if val == 0x29: print(" *** ARENA EVENT ***", end="")
    if (i+1) % 4 == 0: print()
