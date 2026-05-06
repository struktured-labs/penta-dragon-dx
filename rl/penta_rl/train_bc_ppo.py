"""PPO fine-tune from a BC pre-trained checkpoint.

Loads the BC weights into PolicyValueNet, then runs combat-focused PPO on
the gargoyle save state.
"""
from __future__ import annotations
import json, time, sys, os
import numpy as np
import torch
from .vec_env import VecPentaEnv
from .state import vector_dim
from .ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from .env import N_ACTIONS


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def main(bc_ckpt: str, epochs: int = 100, steps_per_epoch: int = 512, n_envs: int = 4,
         max_steps: int = 3000, label: str = "bc_ppo",
         savestate: str = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state",
         pi_lr: float = 1e-4):  # lower lr to preserve BC features
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}, BC checkpoint: {bc_ckpt}")

    venv = VecPentaEnv(ROM, n=n_envs, max_steps=max_steps, savestate_path=savestate)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs,
                    train_iters=8, entropy_coef=0.02, pi_lr=pi_lr)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    # Load BC weights
    state = torch.load(bc_ckpt, map_location=device, weights_only=False)
    agent.net.load_state_dict(state["model"], strict=False)
    print(f"Loaded BC weights from {bc_ckpt}")

    metrics, completed_returns, completed_bosses, boss_kill_eps = [], [], [], []
    obs = venv.reset()
    ep_rewards = np.zeros(n_envs, dtype=np.float32)
    last_print = time.time()
    t_start = time.time()
    for ep in range(epochs):
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch * n_envs)
        for t in range(steps_per_epoch):
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device)
                logits, vals = agent.net(o)
                dist = torch.distributions.Categorical(logits=logits)
                acts = dist.sample(); logps = dist.log_prob(acts)
            acts_np = acts.cpu().numpy(); vals_np = vals.cpu().numpy(); logps_np = logps.cpu().numpy()
            obs2, rews, dones, infos = venv.step(acts_np)
            for i in range(n_envs):
                buf.store(obs[i], int(acts_np[i]), float(rews[i]), float(vals_np[i]),
                          float(logps_np[i]), bool(dones[i]))
                ep_rewards[i] += rews[i]
                if dones[i]:
                    completed_returns.append(float(ep_rewards[i]))
                    nb = int(infos[i].get("n_unique_bosses", 0))
                    completed_bosses.append(nb)
                    if nb > 0:
                        boss_kill_eps.append({"ep_global": len(completed_returns),
                            "epoch": ep+1, "n_bosses": nb, "reward": float(ep_rewards[i])})
                        print(f"  *** KILL *** ep={len(completed_returns)} reward={ep_rewards[i]:.2f}")
                    ep_rewards[i] = 0
            obs = obs2

        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device)
            _, last_v = agent.net(o); last_val = float(last_v.mean().item())
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        elapsed = time.time() - t_start
        recent = completed_returns[-30:] or [0.0]; recent_b = completed_bosses[-30:] or [0]
        m = {"epoch": ep+1, "elapsed_s": round(elapsed, 1),
             "n_eps_total": len(completed_returns),
             "mean_return": round(float(np.mean(recent)), 3),
             "max_return": round(float(max(recent)), 3),
             "max_bosses": int(max(recent_b)),
             "total_kills": int(np.sum(completed_bosses)),
             "loss_pi": round(losses["pi"], 4), "entropy": round(losses["ent"], 4)}
        metrics.append(m)
        if time.time() - last_print >= 5 or ep == 0 or ep == epochs - 1:
            print(f"ep {ep+1:4d}/{epochs}  eps={len(completed_returns):5d}  "
                  f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
                  f"bosses={m['max_bosses']} (cum {m['total_kills']})  "
                  f"ent={m['entropy']:.3f}  t={elapsed:.0f}s")
            last_print = time.time()

        if (ep + 1) % 25 == 0:
            ckpt = f"{SAVE_DIR}/ppo_{label}_ep{ep+1}.pt"
            torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                        "boss_kill_episodes": boss_kill_eps}, ckpt)

    final = f"{SAVE_DIR}/ppo_{label}_final.pt"
    torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                "boss_kill_episodes": boss_kill_eps}, final)
    with open(final.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nFinal: {final}")
    print(f"Total: {len(completed_returns)} eps, {sum(completed_bosses)} cum kills, "
          f"{len(boss_kill_eps)} kill-episodes")
    venv.close()


if __name__ == "__main__":
    bc = sys.argv[1] if len(sys.argv) > 1 else \
        "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_pretrained.pt"
    epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 512
    n = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    main(bc, epochs=epochs, steps_per_epoch=steps, n_envs=n)
