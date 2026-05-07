"""Find ROM code that writes FFBA (level/boss counter)."""
ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
with open(ROM_PATH, "rb") as f:
    rom = f.read()

# E0 BA = LDH [FFBA], A — write FFBA
# Search for LDH [FFBA] writes in ROM
target = bytes([0xE0, 0xBA])
positions = []
pos = 0
while True:
    pos = rom.find(target, pos)
    if pos < 0: break
    positions.append(pos)
    pos += 1

print(f"E0 BA (LDH [FFBA], A) sites: {len(positions)}")
for p in positions:
    # Show context: 8 bytes before and after
    start = max(0, p - 8)
    ctx = rom[start:p+10]
    hex_str = ' '.join(f'{b:02X}' for b in ctx)
    print(f"  0x{p:04X}: ...{hex_str}")

# Also look for FA BA FF (LD A, [FFBA]) reads
target2 = bytes([0xFA, 0xBA, 0xFF])
positions2 = []
pos = 0
while True:
    pos = rom.find(target2, pos)
    if pos < 0: break
    positions2.append(pos)
    pos += 1
print(f"\nFA BA FF (LD A, [FFBA]) sites: {len(positions2)}")
for p in positions2[:5]:
    print(f"  0x{p:04X}")

# Any "INC" pattern near these write sites? Or a constant 1 near them?
# The increment pattern: LDH A, [FFBA]; INC A; LDH [FFBA], A
target3 = bytes([0xF0, 0xBA, 0x3C, 0xE0, 0xBA])  # LDH A,FFBA; INC A; LDH FFBA,A
positions3 = []
pos = 0
while True:
    pos = rom.find(target3, pos)
    if pos < 0: break
    positions3.append(pos)
    pos += 1
print(f"\n'increment FFBA' pattern (LDH A,FFBA; INC A; LDH FFBA,A): {len(positions3)} hits")
for p in positions3:
    start = max(0, p - 16)
    ctx = rom[start:p+10]
    hex_str = ' '.join(f'{b:02X}' for b in ctx)
    print(f"  0x{p:04X}: {hex_str}")
