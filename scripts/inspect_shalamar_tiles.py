import sys
from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
pb = PyBoy(rom, window="null", cgb=True)
pb.set_emulation_speed(0)
mem = pb.memory
rf = pb.register_file

# Standard intro navigation
sched = [
    (180, 186, 'down'),
    (201, 207, 'a'),
    (261, 267, 'a'),
    (291, 296, 'a'),
    (341, 346, 'start'),
    (410, 415, 'a')
]
held = None
for f in range(1, 450):
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
if held:
    pb.button_release(held)

# Let the dungeon load (wait for D880 == 0x02)
for f in range(1000):
    if mem[0xD880] == 0x02:
        break
    pb.tick(1, True)

print(f"Reached dungeon: D880=0x{mem[0xD880]:02X}")
pb.tick(30, True)

# Set up target boss in FFBA and trigger SELECT+START combo
# Target = 0 (Shalamar) -> pre-write FFBA = 8 (so the combo INC wraps it to 0)
mem[0xFFBA] = 8
mem[0xDF0C] = 0
mem[0xDF1D] = 0

print("Pressing SELECT + START...")
pb.button_press('select')
pb.button_press('start')
for _ in range(10):
    pb.tick(1, True)
pb.button_release('select')
pb.button_release('start')

# Let the game transition and load the boss arena (around 200-300 frames)
for f in range(400):
    pb.tick(1, True)
    if mem[0xD880] >= 0x0C and mem[0xD880] <= 0x14:
        # Stop ticking once we've fully transitioned and settled
        if f > 250:
            break

print(f"Post-transition: D880=0x{mem[0xD880]:02X}")
print(f"LCDC FF40=0x{mem[0xFF40]:02X}")

# Let's inspect the tilemap at 0x9800 and 0x9C00
has_9800 = any(mem[0x9800 + i] != 0 for i in range(1024))
has_9c00 = any(mem[0x9C00 + i] != 0 for i in range(1024))

print(f"Non-zero tiles at 0x9800? {has_9800}")
print(f"Non-zero tiles at 0x9C00? {has_9c00}")

base = 0x9C00 if has_9c00 else 0x9800
print(f"Dumping map from 0x{base:04X}:")
for r in range(18):
    row_tiles = []
    for c in range(20):
        addr = base + r * 32 + c
        row_tiles.append(f"{mem[addr]:02X}")
    print(f"Row {r:02d}: " + " ".join(row_tiles))

pb.stop(save=False)
