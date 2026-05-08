"""Force FFBA=1 every tick, run godmode + random play, watch for arena.
If FFBA=1 makes level 1's event 0x29 reachable at FFD3=5, Sara should
trigger arena via random walking eventually.
"""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
import numpy as np

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

def godmode(pb):
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    pb.memory[0xFFBA] = 1  # FORCE level 1
    pb.memory[0xDD06] = 0
    if pb.memory[0xFFBF] == 0:
        pb.memory[0xDCBB] = 0xFF
    # Hijack FF9F so that current entity coord - FF9F = 5 (arena trigger in level 1)
    # Read entity coord at DC10 (per gatekeeper code: HL=DC10, then iterates)
    # Force FF9F = entity_coord - 5 so FFD3 evaluates to 5
    entity_addr_lo = pb.memory[0xDC10]
    entity_addr_hi = pb.memory[0xDC11]
    entity_addr = entity_addr_lo | (entity_addr_hi << 8)
    if entity_addr >= 0xC000 and entity_addr < 0xE000:
        entity_coord = pb.memory[entity_addr]
        if entity_coord > 5:
            pb.memory[0xFF9F] = entity_coord - 5
        # Also write FFD3 directly
        pb.memory[0xFFD3] = 5

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh: pb.load_state(fh)
for _ in range(8): pb.tick()

print(f"Initial: FFBA={pb.memory[0xFFBA]} FFBD={pb.memory[0xFFBD]} D880={hex(pb.memory[0xD880])}")
pb.memory[0xFFBA] = 1
print(f"After FFBA=1 write: FFBA={pb.memory[0xFFBA]}")

rng = np.random.default_rng(0)
btns = ["right", "left", "up", "down", "a", "b", "right", "up"]

print("Running 30000 frames with FFBA=1 clamped...")
t_start = time.time()
seen_arenas = set()
seen_ffd3 = set()
seen_d880 = set()
ffba_actual_history = []
for t in range(30000):
    btn = btns[rng.integers(0, len(btns))]
    pb.button_press(btn)
    godmode(pb)
    pb.tick()
    pb.button_release(btn)
    godmode(pb)
    pb.tick()
    d880 = pb.memory[0xD880]
    seen_d880.add(d880)
    seen_ffd3.add(pb.memory[0xFFD3])
    if 0x0C <= d880 <= 0x14:
        if d880 not in seen_arenas:
            seen_arenas.add(d880)
            print(f"  *** ARENA {hex(d880)} FIRST at t={t} room={pb.memory[0xFFBD]} ***")
            path = f"/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_{hex(d880)}_first.state"
            import os; os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh: pb.save_state(fh)
            print(f"    Saved: {path}")
    if t % 1000 == 0:
        ffba = pb.memory[0xFFBA]
        ffba_actual_history.append(ffba)
        elapsed = time.time() - t_start
        print(f"t={t} FFBA={ffba} FFBD={pb.memory[0xFFBD]} D880={hex(d880)} "
              f"FFD3={hex(pb.memory[0xFFD3])} ({elapsed:.1f}s)")

print(f"\nDone. arenas={[hex(x) for x in seen_arenas]} d880_seen={sorted([hex(x) for x in seen_d880])}")
print(f"FFD3 values seen: {sorted([hex(x) for x in seen_ffd3])}")
print(f"FFBA history sample: {ffba_actual_history}")
pb.stop()
