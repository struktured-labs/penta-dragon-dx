from pyboy import PyBoy
import sys

rom_path = "rom/working/penta_dragon_dx_teleport.gb"
pyboy = PyBoy(rom_path, window="null", cgb=True)

TITLE_INPUTS = {
    (180, 185): "down",
    (193, 198): "a",
    (241, 246): "a",
    (291, 296): "a",
    (341, 346): "start",
    # Hold A down continuously from frame 450 onwards to force skipping the splash screen!
    (450, 950): "a",
}

active_buttons = set()

for frame in range(1, 1000):
    for (start, end), key in TITLE_INPUTS.items():
        if frame == start:
            pyboy.button_press(key)
            active_buttons.add(key)
        if frame == end + 1:
            if key in active_buttons:
                pyboy.button_release(key)
                active_buttons.remove(key)
                
    pyboy.tick()
    
    if 300 <= frame <= 950:
        if frame % 10 == 0 or frame >= 750:
            d880 = pyboy.memory[0xD880]
            ffc1 = pyboy.memory[0xFFC1]
            ffbd = pyboy.memory[0xFFBD]
            print(f"Frame {frame:03d}: D880={d880:#04X}, FFC1={ffc1:#04X}, FFBD={ffbd:#04X}")

pyboy.stop()
