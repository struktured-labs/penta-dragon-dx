"""Dump byte sequences around the event dispatch and arena handler addrs."""
ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
with open(ROM_PATH, "rb") as f:
    rom = f.read()

def hex_dump(addr, n=32, label=""):
    print(f"\n{label} @ 0x{addr:04X}:")
    for i in range(0, n, 8):
        bytes_ = rom[addr+i:addr+i+8]
        hex_str = ' '.join(f'{b:02X}' for b in bytes_)
        print(f"  {addr+i:04X}: {hex_str}")

hex_dump(0x13E5, 64, "Event dispatch master handler")
hex_dump(0x797B, 64, "Entity zone gatekeeper")
hex_dump(0x1A2B, 64, "Boss arena entry handler (event 0x29)")
hex_dump(0x4466, 32, "Room guard")

# Find code that calls 0x1A2B (CD 2B 1A in any of the various pages)
target = bytes([0xCD, 0x2B, 0x1A])  # CALL $1A2B
positions = []
pos = 0
while True:
    pos = rom.find(target, pos)
    if pos < 0: break
    positions.append(pos)
    pos += 1
print(f"\nCallers of 0x1A2B (CALL $1A2B): {[hex(p) for p in positions]}")

# Look at byte 0x29 in event sequences (what writes/reads it)
# Search for "FE 29" (CP $29) — checking if event = 0x29
target2 = bytes([0xFE, 0x29])
positions2 = []
pos = 0
while True:
    pos = rom.find(target2, pos)
    if pos < 0: break
    positions2.append(pos)
    pos += 1
print(f"CP 0x29 sites (compare event to 0x29): {len(positions2)} hits")
for p in positions2[:10]: print(f"  0x{p:04X}: {' '.join(f'{b:02X}' for b in rom[p:p+8])}")
