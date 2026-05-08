"""Verify all 8 stage boss arena states (after full_init fix for FFBA 2/5/6)."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"

arenas = [
    (1, "arena_FFBA1_D880_0xd_FFD3_4.state", "Shalamar"),
    (2, "arena_FFBA2_D880_0xe_full_init.state", "Riff"),
    (3, "arena_FFBA3_D880_0xf_FFD3_1.state", "Crystal"),
    (4, "arena_FFBA4_D880_0x10_FFD3_6.state", "Cameo"),
    (5, "arena_FFBA5_D880_0x11_full_init.state", "Ted"),
    (6, "arena_FFBA6_D880_0x12_full_init.state", "Troop"),
    (7, "arena_FFBA7_D880_0x13_FFD3_7.state", "Faze"),
    (8, "arena_FFBA8_D880_0x14_FFD3_7.state", "Penta"),
]


def godmode(pb):
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFE6] = 0xFF
    pb.memory[0xDD06] = 0


print(f"{'FFBA':<5} {'name':<10} {'init':<6} {'final':<7} {'OAM':<5} {'DCBB':<6} verdict")
for ffba, state_file, name in arenas:
    state_path = f"{SAVE_DIR}/{state_file}"
    if not os.path.exists(state_path):
        print(f"  {ffba} {name:<10} MISSING")
        continue
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(state_path, "rb") as fh: pb.load_state(fh)
    init_d880 = pb.memory[0xD880]

    rng = np.random.default_rng(ffba * 7)
    btns = ["a", "right", "a", "left", "a", "up", "a", "down"]
    saw_advance = False
    saw_d880_change = False
    init_ffba = pb.memory[0xFFBA]
    for t in range(2000):
        btn = btns[rng.integers(0, len(btns))]
        pb.button_press(btn); godmode(pb); pb.tick()
        pb.button_release(btn); godmode(pb); pb.tick()
        cur_ffba = pb.memory[0xFFBA]
        cur_d880 = pb.memory[0xD880]
        if cur_ffba > init_ffba:
            saw_advance = True
            break
        if cur_d880 != init_d880 and not (0x0C <= cur_d880 <= 0x14):
            saw_d880_change = True
            break

    final_d880 = pb.memory[0xD880]
    final_dcbb = pb.memory[0xDCBB]
    oam_active = sum(1 for slot in range(40)
                     if pb.memory[0xFE00 + slot * 4] not in (0, 0xFF))

    if saw_advance:
        verdict = f"FFBA ADVANCED → {pb.memory[0xFFBA]}!"
    elif saw_d880_change:
        verdict = f"D880 → {hex(final_d880)} (left arena)"
    elif 0x0C <= final_d880 <= 0x14:
        verdict = "stable in arena"
    else:
        verdict = "exited"

    print(f"  {ffba:<5} {name:<10} {hex(init_d880):<6} {hex(final_d880):<7} {oam_active:<5} {hex(final_dcbb):<6} {verdict}")
    pb.stop()
