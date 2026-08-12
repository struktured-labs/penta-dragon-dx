import sys
from pyboy import PyBoy

rom = "rom/working/penta_dragon_dx_teleport.gb"
pb = PyBoy(rom, window="null", cgb=True)
pb.set_emulation_speed(0)
mem = pb.memory
rf = pb.register_file

# Navigation to Shalamar
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

for f in range(1000):
    if mem[0xD880] == 0x02:
        break
    pb.tick(1, True)

pb.tick(30, True)
mem[0xFFBA] = 8
mem[0xDF0C] = 0
mem[0xDF1D] = 0

pb.button_press('select')
pb.button_press('start')
for _ in range(10):
    pb.tick(1, True)
pb.button_release('select')
pb.button_release('start')

for f in range(400):
    pb.tick(1, True)
    if mem[0xD880] >= 0x0C and mem[0xD880] <= 0x14:
        if f > 250:
            break

print(f"D880 = 0x{mem[0xD880]:02X}")

# To read VRAM Bank 1, we must set VBK = 1 (FF4F = 1)
# PyBoy memory access: mem[0x9C00] reads the active VRAM bank.
# Wait! In PyBoy, can we select VRAM bank 1?
# Yes! Let's check how PyBoy handles VRAM bank 1.
# Usually, pb.memory[0x9800] reads Bank 0 or Bank 1 depending on FF4F.
# Let's set FF4F to 1 and read!
mem[0xFF4F] = 1
print("VBK set to 1")

print("Dumping VRAM Attrs (Bank 1) from 0x9C00:")
for r in range(18):
    row_attrs = []
    for c in range(20):
        addr = 0x9C00 + r * 32 + c
        row_attrs.append(f"{mem[addr] & 7}")
    print(f"Row {r:02d}: " + " ".join(row_attrs))

pb.stop(save=False)
