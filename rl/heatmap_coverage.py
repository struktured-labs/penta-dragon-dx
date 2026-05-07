"""Build coverage heatmap of Sara's screen positions across all rooms.

Run godmode + uniform random for many frames, log (room, sara_x, sara_y) every step.
Then visualize coverage to find dead zones.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from penta_rl.state import read_state
from penta_rl.godmode_env import godmode_step

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"

env = PentaEnv(REAL, max_steps=60000, savestate_path=SAVE)
obs, _ = env.reset()
pb = env.pb

# Track per-room screen coverage (Sara's avg OAM position)
coverage = {}  # {room: set of (x_bin, y_bin)}
rng = np.random.default_rng(0)

print("Running 60k frames godmode + uniform random, logging coverage...")
for t in range(60000):
    a = int(rng.integers(0, N_ACTIONS))
    for b in env._held: pb.button_release(b)
    env._held = ACTION_BUTTONS[a]
    for b in env._held: pb.button_press(b)
    for _ in range(env.frame_skip):
        godmode_step(pb)
        pb.tick()
    env.steps += 1
    s = read_state(pb)
    # Get Sara's avg OAM position
    sara_xs = [pb.memory[0xFE01 + i*4] for i in range(4)]  # OAM x
    sara_ys = [pb.memory[0xFE00 + i*4] for i in range(4)]  # OAM y
    sara_x = int(np.mean(sara_xs))
    sara_y = int(np.mean(sara_ys))
    if s.miniboss == 0:  # only count exploration when no boss
        x_bin = sara_x // 8  # 8-pixel tile bins
        y_bin = sara_y // 8
        if s.room not in coverage:
            coverage[s.room] = set()
        coverage[s.room].add((x_bin, y_bin))
    if t % 25000 == 0:
        print(f"t={t}: rooms={sorted(coverage.keys())}, "
              f"coverage_size={[len(coverage[r]) for r in sorted(coverage.keys())]}")

print("\n--- COVERAGE PER ROOM ---")
for room in sorted(coverage.keys()):
    tiles = coverage[room]
    print(f"\nRoom {room}: {len(tiles)} unique tiles")
    if not tiles: continue
    xs = sorted(set(x for x,y in tiles))
    ys = sorted(set(y for x,y in tiles))
    print(f"  X range: {min(xs)} to {max(xs)}, Y range: {min(ys)} to {max(ys)}")
    # Show grid (small)
    minx, miny = min(xs), min(ys)
    maxx, maxy = max(xs), max(ys)
    if maxx - minx < 30 and maxy - miny < 30:
        grid = [[' ']*(maxx-minx+1) for _ in range(maxy-miny+1)]
        for x, y in tiles:
            grid[y-miny][x-minx] = '#'
        for row in grid[:25]:
            print('  ' + ''.join(row))
env.close()
