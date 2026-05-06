"""Test if corridor save → spider kill is achievable with random play."""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import read_state

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/post_gargoyle_corridor.state"

env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE)
obs, _ = env.reset()
s0 = read_state(env.pb)
print(f"Start: section={s0.section} scene={hex(s0.scene)} room={s0.room} mb={s0.miniboss} player_hp={s0.player_hp}")

rng = np.random.default_rng(0)
n_eps = 5
spider_reaches = 0
spider_kills = 0
for ep in range(n_eps):
    obs, _ = env.reset()
    saw_spider_section = False
    saw_spider_engaged = False
    saw_kill = False
    last_section = -1
    sections_seen = set()
    for t in range(15000):
        a = int(rng.integers(0, N_ACTIONS))
        obs, r, term, trunc, info = env.step(a)
        s = info["state"]
        sections_seen.add(s.section)
        if s.section == 5:
            saw_spider_section = True
        if s.miniboss == 2:
            saw_spider_engaged = True
        for ev in info.get("events", []):
            if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                saw_kill = True
        if term or trunc: break
    if saw_spider_section: spider_reaches += 1
    if saw_kill: spider_kills += 1
    print(f"  ep{ep+1}: t={t} sections={sorted(sections_seen)} spider_engaged={saw_spider_engaged} kill={saw_kill}")
print(f"\nSpider section reach: {spider_reaches}/{n_eps}, kills: {spider_kills}/{n_eps}")
env.close()
