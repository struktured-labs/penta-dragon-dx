from pyboy import PyBoy
from pathlib import Path
import sys

rom_path = "rom/working/penta_dragon_dx_teleport.gb"
out_dir = Path("tmp/gameplay_dx_cgb")
out_dir.mkdir(parents=True, exist_ok=True)

# Navigation sequence:
# frame ranges and the key mask to press
# PyBoy keys: "down" is bit 7, "start" is bit 3, "a" is bit 0, "b" is bit 1, "right" is bit 4, etc.
# In PyBoy, we can press keys using send_input or by setting Button values.
# Let's map Game Boy keys to PyBoy input buttons:
# A = "a", B = "b", select = "select", start = "start", up = "up", down = "down", left = "left", right = "right"
TITLE_INPUTS = {
    (180, 185): "down",
    (193, 198): "a",
    (241, 246): "a",
    (291, 296): "a",
    (341, 346): "start",
    (391, 396): "a",
}

pyboy = PyBoy(rom_path, window="null", cgb=True)
print("Initialized PyBoy")

active_buttons = set()

for frame in range(1, 1000):
    # Press buttons starting on their start frames
    for (start, end), key in TITLE_INPUTS.items():
        if frame == start:
            pyboy.button_press(key)
            active_buttons.add(key)
            
    # Release buttons after their end frames
    for (start, end), key in TITLE_INPUTS.items():
        if frame == end + 1:
            if key in active_buttons:
                pyboy.button_release(key)
                active_buttons.remove(key)
                
    # After frame 429, press "right" continuously
    if frame == 430:
        pyboy.button_press("right")
        
    pyboy.tick()
        
    if frame in [100, 200, 300, 320, 350, 400, 450, 500, 600, 700, 800, 900]:
        pyboy.screen.image.save(out_dir / f"frame_{frame}.png")
        print(f"Captured frame {frame}")

pyboy.stop()
print("Done!")
