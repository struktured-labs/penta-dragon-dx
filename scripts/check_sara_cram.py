#!/usr/bin/env python3
"""Read CRAM via PyBoy tick-based approach and check actual rendering."""
from pyboy import PyBoy
import os
import time

ROM_PATH = os.path.expanduser("~/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_FIXED.gb")

pb = PyBoy(ROM_PATH, window="null", cgb=True)
pb.set_emulation_speed(0)

# Navigate to gameplay
print("Navigating menus...")
sched = [(180, 186, 'down'), (201, 207, 'a'), (261, 267, 'a'), (321, 327, 'a'), (381, 387, 'start'), (431, 437, 'a')]
held = None

for f in range(1, 1800):
    want = None
    for s, e, b in sched:
        if s <= f < e:
            want = b
            break
    if want != held:
        if held: pb.button_release(held)
        if want: pb.button_press(want)
        held = want
    pb.tick(1, True)

if held: pb.button_release(held)

for _ in range(100):
    pb.tick(1, True)

mem = pb.memory
print(f"\nState: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]} FFBE=0x{mem[0xFFBE]:02X}")

# Check a specific frame position with visible OAM
for _ in range(90):  # mid-frame
    pb.tick(1, True)

mem = pb.memory
print(f"State: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]}")

# Read OAM (hardware sprite table)
print("\n=== Hardware OAM (sprite attributes) ===")
for slot in range(8):
    base = 0xFE00 + slot * 4
    y = mem[base]
    x = mem[base+1]
    tile = mem[base+2]
    attr = mem[base+3]
    pal = attr & 0x07
    if y > 0 and y < 160:  # visible sprite
        print(f"  Slot {slot}: Y={y} X={x} Tile=0x{tile:02X} Attr=0x{attr:02X} pal={pal}")

# Check which tiles are OBJ colorizer targets
# The colorizer writes to shadow OAM (C000 area) and modifies attr bytes
print("\n=== Shadow OAM C000 (after colorizer) ===")
visible_count = 0
for slot in range(40):
    base = 0xC000 + slot * 4
    y = mem[base]
    x = mem[base+1]
    tile = mem[base+2]
    attr = mem[base+3]
    pal = attr & 0x07
    if y > 0 and y < 160 and tile != 0:
        visible_count += 1
        if visible_count <= 10:
            print(f"  Slot {slot}: Y={y} X={x} Tile=0x{tile:02X} Attr=0x{attr:02X} pal={pal}")
print(f"  Total visible sprites: {visible_count}")

# Check the palette_loader state
print(f"\n=== Palette state ===")
print(f"  DF00 (hash): 0x{mem[0xDF00]:02X}")
print(f"  DF02 (init): 0x{mem[0xDF02]:02X}")

# Read palette data from ROM to confirm it's correct
with open(ROM_PATH, 'rb') as f:
    rom = bytearray(f.read())
bank13 = 13 * 0x4000

print("\n=== ROM OBJ palette data ===")
for pal in range(8):
    off = bank13 + (0x6840 - 0x4000) + pal * 8
    vals = []
    for i in range(0, 8, 2):
        val = rom[off+i] | (rom[off+i+1] << 8)
        vals.append(f"0x{val:04X}")
    print(f"  Pal {pal}: {' '.join(vals)}")

# Now also: read VRAM tile data to see what tiles are being drawn
# Get screen data
print("\n=== Screen content ===")
try:
    screen = pb.screen
    print(f"  Screen type: {type(screen)}")
    # screen might be ndarray
    print(f"  Screen shape: {screen.shape if hasattr(screen, 'shape') else 'N/A'}")
except Exception as e:
    print(f"  Screen error: {e}")

pb.stop(save=False)
