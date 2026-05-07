"""Probe the BG tilemap to identify unique tiles that might be teleporters/doors.

When Sara is in a room (e.g., room 1 with mb=0), look at:
1. VRAM 0x9800-0x9BFF (BG tilemap, 32x32 tiles)
2. Find tiles that are visually distinct from normal floor (rare tile IDs)
3. Their (col, row) positions might be teleporter tiles
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from pyboy import PyBoy
from collections import Counter
from penta_rl.state import read_state

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

# Tilemap regions: 0x9800-0x9BFF for BG, 0x9C00-0x9FFF for window/alt
TILEMAP1 = 0x9800
TILEMAP2 = 0x9C00

pb = PyBoy(REAL, window="null", sound_emulated=False, cgb=True)
with open(SAVE, "rb") as fh:
    pb.load_state(fh)
for _ in range(8): pb.tick()
s = read_state(pb)
print(f"State: scene={hex(s.scene)} sect={s.section} room={s.room} mb={s.miniboss}")

# Read both tilemaps
tilemap1 = [pb.memory[TILEMAP1 + i] for i in range(0x400)]
tilemap2 = [pb.memory[TILEMAP2 + i] for i in range(0x400)]

# Tile usage frequency
c1 = Counter(tilemap1)
c2 = Counter(tilemap2)

print(f"\nTilemap1 (0x9800): {len(c1)} unique tile IDs")
print(f"  Top 5: {c1.most_common(5)}")
# Find rare tiles (might be special)
rare = [(t, n) for t, n in c1.items() if 1 <= n <= 4]
print(f"  Rare tiles (1-4 occurrences): {rare[:30]}")
# Where are the rare tiles?
print(f"\n  Locations of tile IDs (col, row):")
for tid, _ in rare[:5]:
    locs = [(i % 32, i // 32) for i, t in enumerate(tilemap1) if t == tid]
    print(f"    tile=0x{tid:02X}: {locs}")

print(f"\nTilemap2 (0x9C00): {len(c2)} unique tile IDs")
print(f"  Top 5: {c2.most_common(5)}")
rare2 = [(t, n) for t, n in c2.items() if 1 <= n <= 4]
print(f"  Rare tiles: {rare2[:20]}")

pb.stop()
