"""Analyze what rooms (FFBD) and sections (DCB8) Sara visited per post_kill state."""
import sys, os, glob
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"
files = sorted(glob.glob(f"{DIR}/L0_*post_kill*.state"))[:50]
print(f"Sampling {len(files)} of post_kill states")

room_dist = {}
sect_dist = {}
mb_dist = {}
scene_dist = {}
ffce_dist = {}
ffcf_dist = {}

for f in files:
    pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
    with open(f, "rb") as fh:
        pb.load_state(fh)
    for _ in range(2): pb.tick()
    room = pb.memory[0xFFBD]
    sect = pb.memory[0xDCB8]
    mb = pb.memory[0xFFBF]
    scene = pb.memory[0xD880]
    ffce = pb.memory[0xFFCE]
    ffcf = pb.memory[0xFFCF]
    room_dist[room] = room_dist.get(room, 0) + 1
    sect_dist[sect] = sect_dist.get(sect, 0) + 1
    mb_dist[mb] = mb_dist.get(mb, 0) + 1
    scene_dist[scene] = scene_dist.get(scene, 0) + 1
    ffce_dist[ffce] = ffce_dist.get(ffce, 0) + 1
    ffcf_dist[ffcf] = ffcf_dist.get(ffcf, 0) + 1
    pb.stop()

print(f"Room (FFBD) distribution: {sorted(room_dist.items())}")
print(f"Section (DCB8) distribution: {sorted(sect_dist.items())}")
print(f"Miniboss (FFBF) distribution: {sorted(mb_dist.items())}")
print(f"Scene (D880) distribution: {sorted([(hex(k),v) for k,v in scene_dist.items()])}")
print(f"FFCE (next room) distribution: {sorted(ffce_dist.items())}")
print(f"FFCF (scroll pos) distribution: {sorted([(hex(k),v) for k,v in ffcf_dist.items()])}")
