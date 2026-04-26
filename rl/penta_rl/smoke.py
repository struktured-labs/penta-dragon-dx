"""Smoke test: random policy for N episodes, log trajectories."""
from __future__ import annotations
import json, sys, time
import numpy as np
from .env import PentaEnv, N_ACTIONS


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def main(n_episodes: int = 5, max_steps: int = 1000, seed: int = 42):
    rng = np.random.default_rng(seed)
    env = PentaEnv(ROM, max_steps=max_steps)

    summary = []
    t0 = time.time()
    for ep in range(n_episodes):
        obs, info = env.reset()
        s0 = info["state"]
        ep_reward = 0.0
        ep_events = []
        steps = 0
        while True:
            action = int(rng.integers(0, N_ACTIONS))
            obs, r, term, trunc, info = env.step(action)
            ep_reward += r
            steps += 1
            for ev in info.get("events", []):
                ep_events.append((steps, ev))
            if term or trunc:
                break
        s1 = env.get_state()
        elapsed = time.time() - t0
        ep_summary = {
            "episode": ep,
            "steps": steps,
            "reward": round(ep_reward, 3),
            "n_unique_bosses": info.get("n_unique_bosses", 0),
            "events": ep_events[:20],  # cap
            "final_room": s1.room, "final_level": s1.level, "final_scene": hex(s1.scene),
            "final_player_hp": s1.player_hp, "final_boss_hp": s1.boss_hp,
            "elapsed_s": round(elapsed, 1),
        }
        summary.append(ep_summary)
        print(f"ep {ep}: steps={steps} reward={ep_reward:.2f} "
              f"events={len(ep_events)} bosses={info.get('n_unique_bosses', 0)} "
              f"scene=0x{s1.scene:02X} room={s1.room} hp={s1.player_hp}")
    env.close()
    with open("/home/struktured/projects/penta-dragon-dx-claude/rl/smoke_results.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nDone. {n_episodes} eps in {time.time()-t0:.1f}s. Wrote smoke_results.json")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    main(n_episodes=n)
