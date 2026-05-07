"""Probe what FFD3 values Sara can reach in level 0 by walking around with godmode.
This tells us which events ARE reachable in level 0.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.state import read_state
from penta_rl.godmode_env import godmode_step
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh: pb.load_state(fh)
for _ in range(8): pb.tick()

# Walk in random directions for 30k frames, log all (FFD3, FFCF, room) tuples seen
seen_ffd3 = set()
seen_ffcf = set()
seen_rooms = set()
seen_combos = set()
rng = np.random.default_rng(0)
btns = ["left", "right", "up", "down", "a", "b"]

print("Probing FFD3 range with godmode + random movement (30k frames)...")
for t in range(30000):
    btn = btns[rng.integers(0, len(btns))]
    pb.button_press(btn)
    godmode_step(pb)
    pb.tick()
    pb.button_release(btn)
    godmode_step(pb)
    pb.tick()
    seen_ffd3.add(pb.memory[0xFFD3])
    seen_ffcf.add(pb.memory[0xFFCF])
    seen_rooms.add(pb.memory[0xFFBD])
    seen_combos.add((pb.memory[0xFFBA], pb.memory[0xFFBD], pb.memory[0xFFD3]))

print(f"\nFFBA values seen: {sorted(set(c[0] for c in seen_combos))}")
print(f"Rooms seen: {sorted(seen_rooms)}")
print(f"FFCF values seen: {sorted([hex(x) for x in seen_ffcf])}")
print(f"FFD3 values seen: {sorted([hex(x) for x in seen_ffd3])}")
print(f"\nCombos (FFBA, room, FFD3):")
for c in sorted(seen_combos): print(f"  ffba={c[0]} room={c[1]} ffd3={hex(c[2])}")
pb.stop()
