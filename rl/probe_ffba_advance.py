"""Test: write FFBA=1 to advance Sara to level 1 where arena event 0x29 exists.
Then check if arena becomes triggerable by walking through doors.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from pyboy import PyBoy
from penta_rl.state import read_state
from penta_rl.env import N_ACTIONS, ACTION_BUTTONS
from penta_rl.godmode_env import godmode_step

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh:
    pb.load_state(fh)
for _ in range(8): pb.tick()
s = read_state(pb)
print(f"Start: scene={hex(s.scene)} sect={s.section} room={s.room} mb={s.miniboss} ffba={s.level}")

# Force FFBA=1
print("\nForcing FFBA=1...")
pb.memory[0xFFBA] = 1

# Verify
for _ in range(2): pb.tick()
s = read_state(pb)
print(f"After write: scene={hex(s.scene)} sect={s.section} room={s.room} mb={s.miniboss} ffba={s.level}")

# Tick for 60 seconds, see if game adapts to FFBA=1
import numpy as np
rng = np.random.default_rng(0)
last_d880 = -1
seen_arenas = set()
for t in range(3000):
    a = int(rng.integers(0, N_ACTIONS))
    held = ACTION_BUTTONS[a]
    for b in held: pb.button_press(b)
    for _ in range(4):
        godmode_step(pb)
        # Re-clamp FFBA every tick (game might overwrite)
        pb.memory[0xFFBA] = 1
        pb.tick()
    for b in held: pb.button_release(b)
    s = read_state(pb)
    if 0x0C <= s.scene <= 0x14 and s.scene not in seen_arenas:
        seen_arenas.add(s.scene)
        print(f"  *** ARENA {hex(s.scene)} at t={t}, room={s.room} ffba={s.level} ***")
    if t % 3000 == 0:
        print(f"t={t} scene={hex(s.scene)} sect={s.section} room={s.room} mb={s.miniboss} ffba={s.level} arenas={len(seen_arenas)}")
print(f"\nDone: arenas={seen_arenas}")
pb.stop()
