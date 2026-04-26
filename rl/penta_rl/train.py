"""PPO training loop for PentaEnv."""
from __future__ import annotations
import json, time, os, sys
import numpy as np
import torch
from .env import PentaEnv, N_ACTIONS
from .state import vector_dim
from .ppo import PPOAgent, PPOConfig, TrajectoryBuffer


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def main(epochs: int = 10, steps_per_epoch: int = 4096, save_path: str | None = None):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    env = PentaEnv(ROM, max_steps=2000)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    buf = TrajectoryBuffer(obs_dim, steps_per_epoch)

    metrics = []
    obs, info = env.reset()
    ep_reward = 0.0
    ep_len = 0
    ep_returns = []
    ep_bosses = []

    t_start = time.time()
    for ep in range(epochs):
        buf.reset()
        ep_in_buf = 0
        for t in range(steps_per_epoch):
            a, v, logp = agent.act(obs)
            obs2, r, term, trunc, info = env.step(a)
            buf.store(obs, a, r, v, logp, term or trunc)
            obs = obs2
            ep_reward += r
            ep_len += 1
            if term or trunc:
                ep_returns.append(ep_reward)
                ep_bosses.append(info.get("n_unique_bosses", 0))
                obs, info = env.reset()
                ep_reward = 0.0
                ep_len = 0
                ep_in_buf += 1
        # Bootstrap last value
        last_val = 0.0
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            _, last_val_t = agent.net(o)
            last_val = float(last_val_t.item())
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        elapsed = time.time() - t_start
        recent = ep_returns[-10:] or [0.0]
        recent_b = ep_bosses[-10:] or [0]
        m = {
            "epoch": ep + 1, "elapsed_s": round(elapsed, 1),
            "n_eps": ep_in_buf,
            "mean_return_10": round(float(np.mean(recent)), 3),
            "max_return_10": round(float(max(recent)), 3),
            "mean_bosses_10": round(float(np.mean(recent_b)), 2),
            "max_bosses_10": int(max(recent_b)),
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        print(f"ep {ep+1}/{epochs}: eps={ep_in_buf} ret={m['mean_return_10']:.2f} "
              f"max_ret={m['max_return_10']:.2f} bosses={m['max_bosses_10']} "
              f"ent={m['entropy']:.3f} t={elapsed:.0f}s")

    save_path = save_path or "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_pentadragon.pt"
    torch.save({"model": agent.net.state_dict(), "cfg": cfg.__dict__, "metrics": metrics}, save_path)
    with open(save_path.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved {save_path}")
    env.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
    main(epochs=epochs, steps_per_epoch=steps)
