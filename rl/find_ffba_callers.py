"""Find who calls the FFBA increment site at 0x73EB and related locations."""
ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
with open(ROM_PATH, "rb") as f: rom = f.read()

# CD EB 73 = CALL $73EB
target = bytes([0xCD, 0xEB, 0x73])
positions = []
pos = 0
while True:
    pos = rom.find(target, pos)
    if pos < 0: break
    positions.append(pos)
    pos += 1
print(f"CALL $73EB sites: {len(positions)}")
for p in positions:
    print(f"  0x{p:04X}: {' '.join(f'{b:02X}' for b in rom[p-8:p+5])}")

# Same for 0x74XX (the function code at 0x7394 zeros FFBA)
# Search "CD 94 73"
target2 = bytes([0xCD, 0x94, 0x73])
positions2 = []
pos = 0
while True:
    pos = rom.find(target2, pos)
    if pos < 0: break
    positions2.append(pos)
    pos += 1
print(f"\nCALL $7394 (FFBA reset) sites: {len(positions2)}")
for p in positions2:
    print(f"  0x{p:04X}: {' '.join(f'{b:02X}' for b in rom[p-8:p+5])}")

# Also find references to address 0x73EB, 0x7394, 0x73FF, 0x740F as 16-bit immediates
# (LD HL, addr or JP addr): 21 EB 73 or C3 EB 73
for addr_label, addr in [("0x73EB", 0x73EB), ("0x7394", 0x7394), ("0x73FF", 0x73FF), ("0x740F", 0x740F), ("0x1A92", 0x1A92)]:
    lo = addr & 0xFF
    hi = (addr >> 8) & 0xFF
    refs = 0
    for prefix in [0x21, 0xC3, 0xCD, 0xC2, 0xCA, 0xC4, 0xCC, 0xD2, 0xDA, 0xD4, 0xDC]:
        pat = bytes([prefix, lo, hi])
        p = 0
        while True:
            p = rom.find(pat, p)
            if p < 0: break
            refs += 1
            p += 1
    print(f"References to {addr_label}: {refs}")
