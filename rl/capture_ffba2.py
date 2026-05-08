"""Try multiple source states to capture FFBA=2 arena (D880=0x0E)."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"
GAMEPLAY = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

# Try multiple source states
sources = [
    ("gameplay", GAMEPLAY),
    ("FFBA3", f"{SAVE_DIR}/arena_FFBA3_D880_0xf_FFD3_1.state"),
    ("FFBA4", f"{SAVE_DIR}/arena_FFBA4_D880_0x10_FFD3_6.state"),
    ("FFBA5", f"{SAVE_DIR}/arena_FFBA5_D880_0x11_direct.state"),
]

for src_name, src_path in sources:
    if not os.path.exists(src_path):
        continue
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(src_path, "rb") as fh: pb.load_state(fh)
    # Force FFBA=2, D880=0x0E
    for t in range(240):
        pb.memory[0xFFBA] = 2
        pb.memory[0xD880] = 0x0E
        pb.memory[0xDCDD] = 0x17
        pb.memory[0xDCDC] = 0xFF
        pb.tick()
    final = pb.memory[0xD880]
    ffba = pb.memory[0xFFBA]
    print(f"  source={src_name} → D880={hex(final)} FFBA={ffba}", end=" ")
    if final == 0x0E:
        path = f"{SAVE_DIR}/arena_FFBA2_D880_0xe_from_{src_name}.state"
        with open(path, "wb") as fh: pb.save_state(fh)
        print(f"✓ saved")
    else:
        print("✗")
    pb.stop()
