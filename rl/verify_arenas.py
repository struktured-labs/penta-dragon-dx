"""Verify each captured arena: load state, attack with godmode, see if FFBA advances."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"

# One canonical arena state per FFBA
arenas = [
    (1, "arena_FFBA1_D880_0xd_FFD3_4.state"),
    (2, "arena_FFBA2_D880_0xe_from_gameplay.state"),
    (3, "arena_FFBA3_D880_0xf_FFD3_1.state"),
    (4, "arena_FFBA4_D880_0x10_FFD3_6.state"),
    (5, "arena_FFBA5_D880_0x11_direct.state"),
    (6, "arena_FFBA6_D880_0x12_direct.state"),
    (7, "arena_FFBA7_D880_0x13_FFD3_7.state"),
    (8, "arena_FFBA8_D880_0x14_FFD3_7.state"),
]


def godmode(pb):
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xDD06] = 0
    pb.memory[0xFFE6] = 0xFF


print(f"{'FFBA':<5} {'D880':<8} {'init_FFBA':<10} {'final_FFBA':<11} {'final_D880':<11} {'OAM_n':<7} {'verdict'}")
for ffba, state_file in arenas:
    state_path = f"{SAVE_DIR}/{state_file}"
    if not os.path.exists(state_path):
        print(f"  {ffba} MISSING")
        continue
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(state_path, "rb") as fh: pb.load_state(fh)
    init_ffba = pb.memory[0xFFBA]
    init_d880 = pb.memory[0xD880]

    # Attack for 1500 frames
    rng = np.random.default_rng(ffba)
    btns = ["a", "right", "a", "left", "a", "up", "a", "down"]
    saw_advance = False
    saw_d880_change = False
    for t in range(1500):
        btn = btns[rng.integers(0, len(btns))]
        pb.button_press(btn); godmode(pb); pb.tick()
        pb.button_release(btn); godmode(pb); pb.tick()
        cur_ffba = pb.memory[0xFFBA]
        cur_d880 = pb.memory[0xD880]
        if cur_ffba > init_ffba:
            saw_advance = True
        if cur_d880 != init_d880 and not (0x0C <= cur_d880 <= 0x14):
            saw_d880_change = True
            break
    final_ffba = pb.memory[0xFFBA]
    final_d880 = pb.memory[0xD880]

    # Count active OAM entities (Y != 0)
    oam_active = 0
    for slot in range(40):
        y = pb.memory[0xFE00 + slot * 4]
        if y != 0 and y != 0xFF:
            oam_active += 1

    verdict = ""
    if saw_advance:
        verdict = "FFBA ADVANCED — boss killed!"
    elif saw_d880_change:
        verdict = f"D880 left arena → {hex(final_d880)}"
    elif 0x0C <= final_d880 <= 0x14:
        verdict = "stable in arena"
    else:
        verdict = "exited arena"

    print(f"  {ffba:<5} {hex(init_d880):<8} {init_ffba:<10} {final_ffba:<11} {hex(final_d880):<11} {oam_active:<7} {verdict}")
    pb.stop()
