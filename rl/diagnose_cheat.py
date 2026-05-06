"""Diagnostic: random and always-fire policies on cheat ROM.

Goals:
1. Does the cheat ROM with cheat_gargoyle save state actually let bosses die?
2. Does reward.py BOSS_KILL detection fire when it should?
3. What's the player HP at start? Does episode end before combat?
"""
from __future__ import annotations
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from penta_rl.state import read_state


CHEAT_ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"  # REAL rom now
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"


def run(policy_name, action_fn, n_eps=10, max_steps=10000, label=""):
    env = PentaEnv(CHEAT_ROM, max_steps=max_steps, savestate_path=SAVE)
    obs, _ = env.reset()
    s0 = read_state(env.pb)
    print(f"\n=== {policy_name} ({label}) ===")
    print(f"start state: scene={hex(s0.scene)} section={s0.section} miniboss={s0.miniboss} "
          f"boss_hp={hex(s0.boss_hp)} player_hp={s0.player_hp} level={s0.level}")
    kills = 0
    for ep in range(n_eps):
        obs, _ = env.reset()
        ep_return = 0.0
        ep_kills_seen = 0
        ep_events = []
        min_boss_hp = 0xFF
        for t in range(max_steps):
            a = action_fn(t)
            obs, r, term, trunc, info = env.step(a)
            ep_return += r
            evs = info.get("events", [])
            for ev in evs:
                if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                    ep_kills_seen += 1
                    ep_events.append((t, ev))
            cur_state = read_state(env.pb)
            if cur_state.boss_hp < min_boss_hp:
                min_boss_hp = cur_state.boss_hp
            if term or trunc:
                break
        end_state = read_state(env.pb)
        kills += ep_kills_seen
        print(f"  ep {ep+1}/{n_eps}: ret={ep_return:.2f} steps={t+1} kills={ep_kills_seen} "
              f"min_boss_hp={hex(min_boss_hp)} end:scene={hex(end_state.scene)} "
              f"section={end_state.section} mb={end_state.miniboss} player_hp={end_state.player_hp}")
        if ep_events:
            print(f"    events: {ep_events[:3]}")
    env.close()
    print(f"TOTAL {policy_name} kills: {kills}/{n_eps} eps")
    return kills


if __name__ == "__main__":
    # (always_A skipped, was deterministic 0 kills)

    # 2. Random — scale 30 to match policy eval
    rng = np.random.default_rng(42)
    run("random", lambda t: rng.integers(0, N_ACTIONS), n_eps=30, label="seed 42, scale 30")
