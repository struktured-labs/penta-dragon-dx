"""From gameplay_start, see what FF9F / entity_coord values are produced by play.

Gatekeeper formula: FFD3 = entity_coord - FF9F.
Need FFD3=4 for Shalamar (FFBA=1) arena entry via event 0x29.
So entity_coord - FF9F should equal 4.

Probe: random play, log every (FFCF, room, entity_coord, FF9F, FFD3) tuple.
Find combinations that hit FFD3=4 naturally.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np
from collections import Counter

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"


def light_godmode(pb):
    """Just keep player alive — DON'T touch FFBA, FFD3, FF9F (we want natural values)."""
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFE6] = 0xFF
    pb.memory[0xDD06] = 0
    if pb.memory[0xFFBF] == 0:
        pb.memory[0xDCBB] = 0xFF


pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh: pb.load_state(fh)
for _ in range(8): pb.tick()

print(f"Initial: FFBA={pb.memory[0xFFBA]} FFD3={pb.memory[0xFFD3]} FF9F={pb.memory[0xFF9F]} FFBD={pb.memory[0xFFBD]}")

rng = np.random.default_rng(42)
btns = ["right", "left", "up", "down", "a", "b"]
ffd3_seen = Counter()
ff9f_seen = Counter()
entity_coord_seen = Counter()
arena_hit = False
for t in range(60000):  # 60k frames = ~16 min gameplay
    btn = btns[rng.integers(0, len(btns))]
    pb.button_press(btn); light_godmode(pb); pb.tick()
    pb.button_release(btn); light_godmode(pb); pb.tick()
    ffd3 = pb.memory[0xFFD3]
    ff9f = pb.memory[0xFF9F]
    ffd3_seen[ffd3] += 1
    ff9f_seen[ff9f] += 1
    # Read entity coord
    entity_addr_lo = pb.memory[0xDC10]
    entity_addr_hi = pb.memory[0xDC11]
    entity_addr = entity_addr_lo | (entity_addr_hi << 8)
    if 0xC000 <= entity_addr < 0xE000:
        ec = pb.memory[entity_addr]
        entity_coord_seen[ec] += 1
    d880 = pb.memory[0xD880]
    if 0x0C <= d880 <= 0x14:
        arena_hit = True
        print(f"  *** ARENA REACHED *** t={t} D880={hex(d880)} FFBA={pb.memory[0xFFBA]} FFD3={ffd3}")
        break
    if t % 10000 == 0:
        print(f"t={t} FFBA={pb.memory[0xFFBA]} FFD3={hex(ffd3)} FF9F={hex(ff9f)} FFBD={pb.memory[0xFFBD]} D880={hex(d880)}")

print(f"\nFFD3 distribution:")
for v, c in sorted(ffd3_seen.items()):
    print(f"  FFD3={hex(v)}: {c}")
print(f"\nFF9F distribution (top 10):")
for v, c in ff9f_seen.most_common(10):
    print(f"  FF9F={hex(v)}: {c}")
print(f"\nentity_coord distribution (top 10):")
for v, c in entity_coord_seen.most_common(10):
    print(f"  ec={hex(v)}: {c}")
print(f"\narena_hit={arena_hit}")
print(f"FFD3=4 ever?: {ffd3_seen.get(4, 0)} times")
print(f"FFD3=5 ever?: {ffd3_seen.get(5, 0)} times")
pb.stop()
