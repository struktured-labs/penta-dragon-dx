"""Replicate the FULL arena setup routine in Python for FFBA 2, 5, 6.

Each ROM arena routine does:
1. LD [D880], arena_value     — scene flag
2. LDH [FFB7], arena_value    — boss flag
3. LD [DD85/86], boss_x       — boss x position
4. LD [DD87/88], boss_y       — boss y position
5. CALL 0x063E                 — common arena init (palette, sprites, etc.)

We can't easily CALL 0x063E from Python, but we can replicate the result by writing
all the state, then triggering the game's natural state-handling code.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"
GAMEPLAY = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

# Per-arena boss positions (from ROM arena setup routines)
ARENA_DATA = {
    2: {"d880": 0x0E, "boss_x": 0x60, "boss_y": 0x60},
    5: {"d880": 0x11, "boss_x": 0xA0, "boss_y": 0xC0},
    6: {"d880": 0x12, "boss_x": 0x90, "boss_y": 0xC0},
}


def setup_arena(pb, ffba, d880, boss_x, boss_y):
    """Replicate ROM arena setup routine state."""
    pb.memory[0xFFBA] = ffba
    pb.memory[0xD880] = d880
    pb.memory[0xFFB7] = d880   # boss flag = arena value
    pb.memory[0xDD85] = boss_x  # boss x_lo
    pb.memory[0xDD86] = 0       # boss x_hi
    pb.memory[0xDD87] = boss_y  # boss y_lo
    pb.memory[0xDD88] = 0       # boss y_hi


def godmode(pb):
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFE6] = 0xFF
    pb.memory[0xDD06] = 0


print(f"{'FFBA':<5} {'arena':<8} {'d880_after_120':<14} {'OAM_n':<7} {'FFB7':<6} verdict")
for ffba, data in ARENA_DATA.items():
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(GAMEPLAY, "rb") as fh: pb.load_state(fh)
    for _ in range(8): pb.tick()  # settle

    # Apply arena setup
    setup_arena(pb, ffba, data["d880"], data["boss_x"], data["boss_y"])

    # Tick frames re-applying setup so init code can pick up state
    for t in range(120):
        setup_arena(pb, ffba, data["d880"], data["boss_x"], data["boss_y"])
        godmode(pb)
        pb.tick()

    final_d880 = pb.memory[0xD880]
    final_ffb7 = pb.memory[0xFFB7]
    oam_active = sum(1 for slot in range(40)
                     if pb.memory[0xFE00 + slot * 4] not in (0, 0xFF))

    if final_d880 == data["d880"]:
        path = f"{SAVE_DIR}/arena_FFBA{ffba}_D880_{hex(final_d880)}_full_init.state"
        with open(path, "wb") as fh: pb.save_state(fh)
        verdict = f"saved: {path.split('/')[-1]}"
    else:
        verdict = f"reverted to {hex(final_d880)}"

    print(f"  {ffba:<5} {hex(data['d880']):<8} {hex(final_d880):<14} {oam_active:<7} {hex(final_ffb7):<6} {verdict}")
    pb.stop()
