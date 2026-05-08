"""Find ROM code that writes D880 to arena values 0x0C-0x14.

Patterns:
- LD A, 0x0C..0x14 ; LD [D880], A  →  3E NN EA 80 D8
- LD HL, D880 ; LD [HL], NN
- D880 dispatch table: FFBA-indexed pointer that selects setup routine
"""
import sys
ROM_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
with open(ROM_PATH, "rb") as f: rom = f.read()

# Pattern: LD A, NN ; LD [D880], A  =  3E NN EA 80 D8
print("=== D880 = NN immediate writes ===")
for nn in range(0x0C, 0x15):
    pat = bytes([0x3E, nn, 0xEA, 0x80, 0xD8])
    pos = 0
    while True:
        pos = rom.find(pat, pos)
        if pos < 0: break
        print(f"  ROM 0x{pos:05X}: D880 = {hex(nn)}  ctx={' '.join(f'{b:02X}' for b in rom[max(0,pos-8):pos+8])}")
        pos += 1

# Pattern: LD HL, D880 ; LD [HL], NN  =  21 80 D8 36 NN
print("\n=== LD HL,D880; LD [HL],NN writes ===")
for nn in range(0x0C, 0x15):
    pat = bytes([0x21, 0x80, 0xD8, 0x36, nn])
    pos = 0
    while True:
        pos = rom.find(pat, pos)
        if pos < 0: break
        print(f"  ROM 0x{pos:05X}: D880 ← {hex(nn)} via HL")
        pos += 1

# Generic D880 writes (any LD [D880], A)
# Pattern: EA 80 D8
pat = bytes([0xEA, 0x80, 0xD8])
positions = []
pos = 0
while True:
    pos = rom.find(pat, pos)
    if pos < 0: break
    positions.append(pos)
    pos += 1
print(f"\n=== Total LD [D880], A sites: {len(positions)} ===")
for p in positions[:30]:
    # Look 8 bytes back for the LD A, NN that loaded the value
    back = rom[max(0,p-8):p]
    print(f"  0x{p:05X}: prev={' '.join(f'{b:02X}' for b in back)}  next={' '.join(f'{b:02X}' for b in rom[p:p+5])}")

# Look for FFBA-indexed jump tables near arena code
# Pattern: F0 BA  (LDH A,FFBA) followed by 6/8 byte arithmetic + JP HL
print("\n=== FFBA reads near arena setup (potential dispatch) ===")
pat = bytes([0xF0, 0xBA])
pos = 0
ct = 0
while True:
    pos = rom.find(pat, pos)
    if pos < 0: break
    ct += 1
    nxt = rom[pos:pos+12]
    # Look for jump table patterns: shift/add/JP HL etc
    if any(b in nxt for b in [0x87, 0x4F, 0xE9, 0xCB, 0xC5, 0x21]):
        print(f"  ROM 0x{pos:05X}: ldh a,FFBA; {' '.join(f'{b:02X}' for b in nxt[2:10])}")
    pos += 1
print(f"  Total FFBA reads: {ct}")
