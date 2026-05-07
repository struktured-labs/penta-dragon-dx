"""Probe FFD3 values reachable per DCB8 section, also track FF9F."""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.godmode_env import godmode_step
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh: pb.load_state(fh)
for _ in range(8): pb.tick()

# Probe per DCB8 section
combos = set()  # (DCB8, FF9F, FFCF, FFD3)
rng = np.random.default_rng(0)
btns = ["left", "right", "up", "down", "a", "b", "left", "up"]

print("Probing FFD3/FF9F per DCB8 (60k frames godmode + random)...")
for t in range(60000):
    btn = btns[rng.integers(0, len(btns))]
    pb.button_press(btn)
    godmode_step(pb)
    pb.tick()
    pb.button_release(btn)
    godmode_step(pb)
    pb.tick()
    combos.add((
        pb.memory[0xDCB8],
        pb.memory[0xFF9F],
        pb.memory[0xFFCF],
        pb.memory[0xFFD3],
        pb.memory[0xFFBD],
    ))

print(f"\n{'DCB8':<6} {'FF9F':<6} {'FFCF':<6} {'FFD3':<6} {'room':<6}")
for c in sorted(combos):
    print(f"  {c[0]:<6} 0x{c[1]:02X}    0x{c[2]:02X}    0x{c[3]:02X}    {c[4]:<6}")
pb.stop()
