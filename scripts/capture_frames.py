import sys
from pyboy import PyBoy
from pathlib import Path

rom_path = sys.argv[1]
out_dir = Path(sys.argv[2])
out_dir.mkdir(parents=True, exist_ok=True)

pyboy = PyBoy(rom_path, window="null", cgb=True)
print(f"Loaded {rom_path}")

for frame in range(1, 1000):
    pyboy.tick()
    if frame in [100, 200, 300, 400, 500, 600, 800, 900]:
        screen_image = pyboy.screen.image
        screen_image.save(out_dir / f"frame_{frame}.png")
        print(f"Saved frame {frame} to {out_dir}")

pyboy.stop()
