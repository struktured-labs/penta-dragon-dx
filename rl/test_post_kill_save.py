"""Test if random play from post_multi_kill.state ever reaches stage boss arena."""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import read_state

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/post_multi_kill.state"

env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE)
obs, info = env.reset()
s0 = read_state(env.pb)
print(f"Start: section={s0.section} scene={hex(s0.scene)} room={s0.room} mb={s0.miniboss} player_hp={s0.player_hp} ffba={s0.level}")

rng = np.random.default_rng(0)
arena_reaches = 0
total_eps = 5
for ep in range(total_eps):
    obs, _ = env.reset()
    seen_scenes = set()
    seen_rooms = set()
    arena = False
    for t in range(15000):
        a = int(rng.integers(0, N_ACTIONS))
        obs, r, term, trunc, info = env.step(a)
        s = info["state"]
        seen_scenes.add(s.scene)
        seen_rooms.add(s.room)
        if 0x0C <= s.scene <= 0x14:
            print(f"  ep{ep+1} t={t}: ARENA! scene={hex(s.scene)}")
            arena = True
            break
        if term or trunc: break
    if arena: arena_reaches += 1
    print(f"  ep{ep+1}: t={t} arena={arena} scenes={sorted([hex(x) for x in seen_scenes])[:8]} rooms={sorted(seen_rooms)[:8]}")
print(f"\nArena reach rate: {arena_reaches}/{total_eps}")
env.close()
