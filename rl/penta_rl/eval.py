"""Eval a trained policy: run N episodes, log full traces, optional render."""
from __future__ import annotations
import json, sys
import numpy as np
import torch
from .env import PentaEnv, N_ACTIONS
from .state import vector_dim
from .ppo import PPOAgent, PPOConfig


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def main(checkpoint: str, n_episodes: int = 5, deterministic: bool = False, max_steps: int = 4000):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    env = PentaEnv(ROM, max_steps=max_steps)
    obs_dim = vector_dim()
    cfg = PPOConfig()
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    state = torch.load(checkpoint, map_location=device, weights_only=False)
    agent.net.load_state_dict(state["model"])
    agent.net.eval()

    traces = []
    for ep in range(n_episodes):
        obs, info = env.reset()
        ep_reward = 0.0
        events = []
        actions = []
        steps = 0
        while True:
            a, v, logp = agent.act(obs, deterministic=deterministic)
            actions.append(a)
            obs, r, term, trunc, info = env.step(a)
            ep_reward += r
            for ev in info.get("events", []):
                events.append((steps, ev))
            steps += 1
            if term or trunc:
                break
        s = env.get_state()
        # Action histogram
        from collections import Counter
        ah = Counter(actions)
        traces.append({
            "episode": ep,
            "steps": steps,
            "reward": round(ep_reward, 2),
            "n_unique_bosses": info.get("n_unique_bosses", 0),
            "events": events[:30],
            "final_scene": hex(s.scene),
            "final_room": s.room,
            "final_level": s.level,
            "final_player_hp": s.player_hp,
            "final_boss_hp": s.boss_hp,
            "action_hist": dict(ah.most_common()),
        })
        print(f"ep {ep}: steps={steps} reward={ep_reward:.2f} bosses={info.get('n_unique_bosses', 0)} "
              f"scene=0x{s.scene:02X} room={s.room} level={s.level} hp={s.player_hp}")

    out = checkpoint.replace(".pt", f"_eval{n_episodes}.json")
    with open(out, "w") as f:
        json.dump(traces, f, indent=2, default=str)
    print(f"Saved {out}")
    env.close()


if __name__ == "__main__":
    ckpt = sys.argv[1] if len(sys.argv) > 1 else "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_pentadragon_vec.pt"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    det = "--det" in sys.argv
    main(ckpt, n_episodes=n, deterministic=det)
