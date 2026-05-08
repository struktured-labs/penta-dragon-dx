"""Probe what happens when DCBB hits 0 in stage arena.

Strategies:
1. Force DCBB=0 directly in arena, see if FFBA advances.
2. Force scene to 0x18 (boss splash), see if it transitions properly.
3. Combination: low DCBB + force scene transitions.
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.godmode_env import godmode_step
from penta_rl.env import ACTION_BUTTONS

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"


def probe(strategy):
    pb = PyBoy(ROM, window="null", sound_emulated=False, cgb=True)
    with open(SHALAMAR, "rb") as fh: pb.load_state(fh)
    init_ffba = pb.memory[0xFFBA]
    held = []

    print(f"\n=== {strategy} ===", flush=True)
    print(f"  init: FFBA={init_ffba} DCBB={hex(pb.memory[0xDCBB])} D880={hex(pb.memory[0xD880])}", flush=True)
    for t in range(2000):
        if strategy == "force_dcbb_0":
            pb.memory[0xDCBB] = 0
        elif strategy == "force_scene_18":
            if t > 100:
                pb.memory[0xD880] = 0x18
        elif strategy == "force_dcbb_then_18":
            if t < 100:
                pb.memory[0xDCBB] = 0
            else:
                pb.memory[0xD880] = 0x18
        elif strategy == "play_then_force_18":
            # Spam attack for 1000 frames
            if t < 1000:
                a = 0  # A button
                for b in held:
                    pb.button_release(b)
                held = ACTION_BUTTONS[a]
                for b in held:
                    pb.button_press(b)
            else:
                # After damage, force scene 0x18
                pb.memory[0xD880] = 0x18
        for _ in range(4):
            godmode_step(pb)
            pb.tick()
        if t % 100 == 0 or t < 5:
            d880 = pb.memory[0xD880]
            ffba = pb.memory[0xFFBA]
            dcbb = pb.memory[0xDCBB]
            print(f"  t={t} FFBA={ffba} DCBB={hex(dcbb)} D880={hex(d880)} FFBF={pb.memory[0xFFBF]} FFB7={pb.memory[0xFFB7]}", flush=True)
        if pb.memory[0xFFBA] > init_ffba:
            print(f"  ADVANCE at t={t}! FFBA={pb.memory[0xFFBA]}", flush=True)
            break
    pb.stop()


for strat in ["force_dcbb_0", "force_scene_18", "force_dcbb_then_18", "play_then_force_18"]:
    probe(strat)
