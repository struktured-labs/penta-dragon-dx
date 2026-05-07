"""Hold each direction for 600 frames, log FFD3 progression.
Find which direction takes FFD3 toward higher values (0x17 needed for level 0 end).
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.godmode_env import godmode_step

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

for direction in ["right", "left", "up", "down"]:
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(SAVE, "rb") as fh: pb.load_state(fh)
    for _ in range(8): pb.tick()
    print(f"\n=== Hold {direction.upper()} for 1500 frames ===")
    last_ffd3 = -1
    last_room = -1
    for t in range(1500):
        pb.button_press(direction)
        godmode_step(pb)
        pb.tick()
        if pb.memory[0xFFD3] != last_ffd3 or pb.memory[0xFFBD] != last_room:
            last_ffd3 = pb.memory[0xFFD3]
            last_room = pb.memory[0xFFBD]
            print(f"  t={t}: FFD3={hex(last_ffd3)} FF9F={hex(pb.memory[0xFF9F])} "
                  f"DCB8={pb.memory[0xDCB8]} FFCF={hex(pb.memory[0xFFCF])} room={last_room}")
            if last_ffd3 >= 0x17 and pb.memory[0xFFBA] == 0:
                print(f"  *** FFD3 in level-end range! ***")
    pb.stop()
