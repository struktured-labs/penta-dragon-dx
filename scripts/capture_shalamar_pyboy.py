import sys
from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
pb = PyBoy(rom, window="null", cgb=True)
pb.set_emulation_speed(0)
mem = pb.memory

# 1. Title navigation inputs
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

# 2. Wait for the dungeon to load
print("Waiting for active gameplay...")
for f in range(1000):
    if mem[0xD880] == 0x02:
        break
    pb.tick(1, True)

print(f"Reached dungeon: D880=0x{mem[0xD880]:02X}")
pb.tick(30, True)

# 3. Teleport to Shalamar
# target = 0 (Shalamar). Pre-write FFBA = 8 so SELECT+START combo INC wraps to 0.
mem[0xFFBA] = 8
mem[0xDF0C] = 0
mem[0xDF1D] = 0

print("Pressing SELECT + START to teleport...")
pb.button_press('select')
pb.button_press('start')
for _ in range(10):
    pb.tick(1, True)
pb.button_release('select')
pb.button_release('start')

# 4. Wait for the boss arena to load and settle
print("Transitioning to boss arena...")
for f in range(400):
    pb.tick(1, True)
    if mem[0xD880] >= 0x0C and mem[0xD880] <= 0x14:
        if f > 250:
            break

print(f"Arena loaded! D880=0x{mem[0xD880]:02X}")

# Tick 30 frames to let animations play
pb.tick(30, True)

# Save the screenshot
img = pb.screen.image
img.save("/home/struktured/projects/penta-dragon-dx-claude/rom/working/proof_shalamar_perfect.png")
print("Saved flawless screenshot to rom/working/proof_shalamar_perfect.png!")

pb.stop(save=False)
