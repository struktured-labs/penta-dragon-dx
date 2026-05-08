"""For FFBA 0, 2, 3, 5, 6 — try ALL FFD3 values 0-31 to find arena trigger."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"


def godmode_with_force(pb, force_ffba, force_ffd3):
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFBA] = force_ffba
    pb.memory[0xDD06] = 0
    if pb.memory[0xFFBF] == 0:
        pb.memory[0xDCBB] = 0xFF
    entity_lo = pb.memory[0xDC10]
    entity_hi = pb.memory[0xDC11]
    entity_addr = entity_lo | (entity_hi << 8)
    if 0xC000 <= entity_addr < 0xE000:
        ec = pb.memory[entity_addr]
        if ec > force_ffd3:
            pb.memory[0xFF9F] = ec - force_ffd3
        pb.memory[0xFFD3] = force_ffd3


for force_ffba in [0, 2, 3, 5, 6]:
    found = False
    for force_ffd3 in range(32):
        pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
        with open(SAVE, "rb") as fh: pb.load_state(fh)
        for _ in range(8): pb.tick()
        rng = np.random.default_rng(force_ffba * 100 + force_ffd3)
        btns = ["right", "left", "up", "down", "a"]
        triggered = None
        for t in range(400):
            btn = btns[rng.integers(0, len(btns))]
            pb.button_press(btn); godmode_with_force(pb, force_ffba, force_ffd3); pb.tick()
            pb.button_release(btn); godmode_with_force(pb, force_ffba, force_ffd3); pb.tick()
            d880 = pb.memory[0xD880]
            if 0x0C <= d880 <= 0x14:
                triggered = d880
                path = f"{SAVE_DIR}/arena_FFBA{force_ffba}_D880_{hex(d880)}_FFD3_{force_ffd3}.state"
                with open(path, "wb") as fh: pb.save_state(fh)
                break
        if triggered:
            print(f"FFBA={force_ffba} FFD3={force_ffd3} → D880={hex(triggered)} ✓")
            pb.stop()
            found = True
            break
        pb.stop()
    if not found:
        print(f"FFBA={force_ffba}: NO arena triggered with any FFD3 0-31")
