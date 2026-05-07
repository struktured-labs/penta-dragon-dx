"""Read FF9F (gatekeeper base) and entity_coord during gameplay.
FFD3 = entity_coord - FF9F. If we know FF9F and which entity_coord triggers
arena (0x29 in level 1), we can target Sara's exact required position.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.state import read_state

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh: pb.load_state(fh)
for _ in range(8): pb.tick()

# Probe the gatekeeper-related bytes in HRAM
print("Initial state:")
print(f"  FF9F={pb.memory[0xFF9F]:02X}  FFA0={pb.memory[0xFFA0]:02X}  "
      f"FFA1={pb.memory[0xFFA1]:02X}  FFA2={pb.memory[0xFFA2]:02X}")
print(f"  FFD3={pb.memory[0xFFD3]:02X} (event seq idx)")
print(f"  FFBA={pb.memory[0xFFBA]:02X} (level)")
print(f"  FFBD={pb.memory[0xFFBD]:02X} (room)")
print(f"  FFCF={pb.memory[0xFFCF]:02X} (scroll pos)")

# Sara's OAM-derived position (sprite slots 0-3)
sara_x = sum(pb.memory[0xFE01 + i*4] for i in range(4)) // 4
sara_y = sum(pb.memory[0xFE00 + i*4] for i in range(4)) // 4
print(f"  Sara avg OAM: x={sara_x} y={sara_y}")

# Tick for a few frames in different directions to see how FF9F and FFD3 change
print("\nWalking down 60 frames...")
last_ffd3 = -1
for t in range(60):
    pb.button_press("down")
    pb.tick()
    pb.button_release("down")
    pb.tick()
    if pb.memory[0xFFD3] != last_ffd3:
        last_ffd3 = pb.memory[0xFFD3]
        sx = sum(pb.memory[0xFE01 + i*4] for i in range(4)) // 4
        sy = sum(pb.memory[0xFE00 + i*4] for i in range(4)) // 4
        print(f"  t={t}: FFD3={last_ffd3:02X} FF9F={pb.memory[0xFF9F]:02X} "
              f"FFCF={pb.memory[0xFFCF]:02X} room={pb.memory[0xFFBD]} sara=({sx},{sy})")

print("\nWalking up 60 frames...")
last_ffd3 = -1
for t in range(60):
    pb.button_press("up")
    pb.tick()
    pb.button_release("up")
    pb.tick()
    if pb.memory[0xFFD3] != last_ffd3:
        last_ffd3 = pb.memory[0xFFD3]
        sx = sum(pb.memory[0xFE01 + i*4] for i in range(4)) // 4
        sy = sum(pb.memory[0xFE00 + i*4] for i in range(4)) // 4
        print(f"  t={t}: FFD3={last_ffd3:02X} FF9F={pb.memory[0xFF9F]:02X} "
              f"FFCF={pb.memory[0xFFCF]:02X} room={pb.memory[0xFFBD]} sara=({sx},{sy})")

pb.stop()
