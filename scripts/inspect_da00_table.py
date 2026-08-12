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

# Dump 256 bytes from WRAM 0xDA00 (which is always in bank 0 or 1, and in GBC is bank-independent / accessible)
print("Dumping WRAM 0xDA00 table:")
table = [mem[0xDA00 + i] for i in range(256)]

# Let's print non-zero entries
non_zeros = []
for i, v in enumerate(table):
    if v != 0:
        non_zeros.append(f"0x{i:02X}:{v}")
print(", ".join(non_zeros))

pb.stop(save=False)
