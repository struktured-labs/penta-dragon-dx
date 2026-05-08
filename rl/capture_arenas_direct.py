"""Direct D880 write to capture remaining arenas FFBA 2, 5, 6.
For each missing FFBA, write D880=arena_value directly (with level setup) and see if the
scene initializes or stays. Also try combining with all FFD3 0-127 (broader scan).
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"

# Each FFBA → expected arena D880 value (from earlier capture: 1→0xD, 3→0xF, 4→0x10, 7→0x13, 8→0x14)
# Pattern: arena = 0x0C + FFBA, so FFBA=2→0x0E, FFBA=5→0x11, FFBA=6→0x12
TARGETS = {2: 0x0E, 5: 0x11, 6: 0x12}


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


# Strategy 1: Try ALL FFD3 0-127 (broader scan)
print("=== STRATEGY 1: broader FFD3 scan 0-127 ===")
for force_ffba, target_d880 in TARGETS.items():
    found = False
    for force_ffd3 in range(128):
        pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
        with open(SAVE, "rb") as fh: pb.load_state(fh)
        for _ in range(8): pb.tick()
        rng = np.random.default_rng(force_ffba * 1000 + force_ffd3)
        btns = ["right", "left", "up", "down", "a"]
        triggered = None
        for t in range(300):
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
        print(f"FFBA={force_ffba}: STILL no arena with FFD3 0-127")

# Strategy 2: Direct D880 write — start from FFBA=1 arena state, change FFBA + D880
print("\n=== STRATEGY 2: direct D880 write from FFBA=1 arena state ===")
SOURCE_STATE = f"{SAVE_DIR}/arena_FFBA1_D880_0xd_FFD3_4.state"
for force_ffba, target_d880 in TARGETS.items():
    if not os.path.exists(SOURCE_STATE):
        print(f"  no source state, skipping FFBA={force_ffba}")
        continue
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(SOURCE_STATE, "rb") as fh: pb.load_state(fh)
    pb.memory[0xFFBA] = force_ffba
    pb.memory[0xD880] = target_d880
    # Tick a few frames and see if it stays
    stable = []
    for t in range(120):
        pb.memory[0xFFBA] = force_ffba
        pb.memory[0xD880] = target_d880
        pb.memory[0xDCDD] = 0x17  # full HP
        pb.tick()
        stable.append(pb.memory[0xD880])
    # Check what D880 settled to
    final = pb.memory[0xD880]
    print(f"  FFBA={force_ffba} target={hex(target_d880)} final={hex(final)} ", end="")
    if 0x0C <= final <= 0x14:
        path = f"{SAVE_DIR}/arena_FFBA{force_ffba}_D880_{hex(final)}_direct.state"
        with open(path, "wb") as fh: pb.save_state(fh)
        print(f"saved direct: {path.split('/')[-1]}")
    else:
        print("(rejected — game reverted scene)")
    pb.stop()
