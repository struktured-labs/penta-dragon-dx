"""What happens when we write FFBF=0 (the canonical 'boss dead' signal)?"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from penta_rl.state import read_state

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh:
    pb.load_state(fh)
for _ in range(4): pb.tick()
s = read_state(pb)
print(f"start: scene={hex(s.scene)} sect={s.section} mb={s.miniboss} boss_hp={hex(s.boss_hp)} ply_hp={s.player_hp}")

print("FORCE FFBF=0; ticking 240 frames...")
pb.memory[0xFFBF] = 0x00
last = None
for i in range(240):
    pb.tick()
    s = read_state(pb)
    sig = (hex(s.scene), s.section, s.miniboss, hex(s.boss_hp))
    if sig != last:
        print(f"  frame {i}: scene={sig[0]} sect={sig[1]} mb={sig[2]} boss_hp={sig[3]} ply_hp={s.player_hp}")
        last = sig
pb.stop()
