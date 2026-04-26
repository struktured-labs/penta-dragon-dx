"""Run a BC-pretrained net against PentaEnv and compare with random baseline."""
from __future__ import annotations
import json, sys, time
import numpy as np
import torch
from .env import PentaEnv, N_ACTIONS
from .state import vector_dim
from .ppo import PolicyValueNet, PPOConfig


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def run_policy(net, env, n_episodes: int, deterministic: bool, device: str):
    results = []
    for ep in range(n_episodes):
        obs, info = env.reset()
        ep_r = 0.0; n_step = 0
        while True:
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, _ = net(o)
                if deterministic:
                    a = int(logits.argmax(-1).item())
                else:
                    dist = torch.distributions.Categorical(logits=logits)
                    a = int(dist.sample().item())
            obs, r, term, trunc, info = env.step(a)
            ep_r += r; n_step += 1
            if term or trunc: break
        s = env.get_state()
        results.append({"ep": ep, "steps": n_step, "reward": round(ep_r, 2),
                        "n_unique_bosses": info.get("n_unique_bosses", 0),
                        "scene": hex(s.scene), "room": s.room, "level": s.level,
                        "player_hp": s.player_hp, "boss_hp": s.boss_hp})
    return results


def run_random(env, n_episodes: int, rng: np.random.Generator):
    results = []
    for ep in range(n_episodes):
        obs, info = env.reset()
        ep_r = 0.0; n_step = 0
        while True:
            a = int(rng.integers(0, N_ACTIONS))
            obs, r, term, trunc, info = env.step(a)
            ep_r += r; n_step += 1
            if term or trunc: break
        s = env.get_state()
        results.append({"ep": ep, "steps": n_step, "reward": round(ep_r, 2),
                        "n_unique_bosses": info.get("n_unique_bosses", 0),
                        "scene": hex(s.scene), "room": s.room, "level": s.level,
                        "player_hp": s.player_hp, "boss_hp": s.boss_hp})
    return results


def main(bc_ckpt: str, n_episodes: int = 5, max_steps: int = 1500,
         savestate: str = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    obs_dim = vector_dim()
    cfg = PPOConfig()
    net = PolicyValueNet(obs_dim, N_ACTIONS, cfg.hidden).to(device)
    state = torch.load(bc_ckpt, map_location=device, weights_only=False)
    net.load_state_dict(state["model"], strict=False)
    net.eval()

    env = PentaEnv(ROM, max_steps=max_steps, savestate_path=savestate)

    print("=== RANDOM BASELINE ===")
    rng = np.random.default_rng(42)
    rand_results = run_random(env, n_episodes, rng)
    for r in rand_results:
        print(f"  ep {r['ep']}: steps={r['steps']} ret={r['reward']} bosses={r['n_unique_bosses']} hp={r['player_hp']}")

    print("\n=== BC POLICY (sample) ===")
    bc_sample = run_policy(net, env, n_episodes, deterministic=False, device=device)
    for r in bc_sample:
        print(f"  ep {r['ep']}: steps={r['steps']} ret={r['reward']} bosses={r['n_unique_bosses']} hp={r['player_hp']}")

    print("\n=== BC POLICY (deterministic) ===")
    bc_det = run_policy(net, env, n_episodes, deterministic=True, device=device)
    for r in bc_det:
        print(f"  ep {r['ep']}: steps={r['steps']} ret={r['reward']} bosses={r['n_unique_bosses']} hp={r['player_hp']}")

    summary = {
        "random": {"mean_return": float(np.mean([r["reward"] for r in rand_results])),
                   "mean_bosses": float(np.mean([r["n_unique_bosses"] for r in rand_results])),
                   "mean_steps": float(np.mean([r["steps"] for r in rand_results]))},
        "bc_sample": {"mean_return": float(np.mean([r["reward"] for r in bc_sample])),
                      "mean_bosses": float(np.mean([r["n_unique_bosses"] for r in bc_sample])),
                      "mean_steps": float(np.mean([r["steps"] for r in bc_sample]))},
        "bc_det": {"mean_return": float(np.mean([r["reward"] for r in bc_det])),
                   "mean_bosses": float(np.mean([r["n_unique_bosses"] for r in bc_det])),
                   "mean_steps": float(np.mean([r["steps"] for r in bc_det]))},
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    out = bc_ckpt.replace(".pt", "_eval.json")
    with open(out, "w") as f:
        json.dump({"random": rand_results, "bc_sample": bc_sample, "bc_det": bc_det,
                   "summary": summary}, f, indent=2, default=str)
    print(f"Saved {out}")
    env.close()


if __name__ == "__main__":
    bc = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    main(bc, n_episodes=n)
