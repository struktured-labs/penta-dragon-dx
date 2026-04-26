"""Simple non-curriculum training with one good reward config."""
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


def main(epochs: int = 100, steps_per_epoch: int = 1024, n_envs: int = 4,
         max_steps: int = 4000, save_dir: str = SAVE_DIR, resume: str = None,
         label: str = "simple"):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}, n_envs={n_envs}, epochs={epochs}, steps/epoch={steps_per_epoch}")

    venv = VecPentaEnv(ROM, n=n_envs, max_steps=max_steps)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs,
                    train_iters=10, entropy_coef=0.03)  # higher entropy to keep exploring
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    if resume and os.path.exists(resume):
        state = torch.load(resume, map_location=device, weights_only=False)
        agent.net.load_state_dict(state["model"])
        print(f"Resumed from {resume}")

    metrics = []
    obs = venv.reset()
    ep_rewards = np.zeros(n_envs, dtype=np.float32)
    ep_lengths = np.zeros(n_envs, dtype=np.int32)
    completed_returns = []
    completed_bosses = []
    boss_kill_episodes = []
    last_print = time.time()

    t_start = time.time()
    for ep in range(epochs):
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch * n_envs)
        for t in range(steps_per_epoch):
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device)
                logits, vals = agent.net(o)
                dist = torch.distributions.Categorical(logits=logits)
                acts = dist.sample()
                logps = dist.log_prob(acts)
            acts_np = acts.cpu().numpy()
            vals_np = vals.cpu().numpy()
            logps_np = logps.cpu().numpy()
            obs2, rews, dones, infos = venv.step(acts_np)
            for i in range(n_envs):
                buf.store(obs[i], int(acts_np[i]), float(rews[i]), float(vals_np[i]),
                          float(logps_np[i]), bool(dones[i]))
                ep_rewards[i] += rews[i]
                ep_lengths[i] += 1
                if dones[i]:
                    completed_returns.append(float(ep_rewards[i]))
                    nb = int(infos[i].get("n_unique_bosses", 0))
                    completed_bosses.append(nb)
                    if nb > 0:
                        boss_kill_episodes.append({
                            "ep_global": len(completed_returns),
                            "epoch": ep + 1,
                            "n_bosses": nb,
                            "reward": float(ep_rewards[i]),
                            "events": infos[i].get("events", [])[:30],
                        })
                        print(f"  *** BOSS KILL *** ep_global={len(completed_returns)} "
                              f"n_bosses={nb} reward={ep_rewards[i]:.2f}")
                    ep_rewards[i] = 0
                    ep_lengths[i] = 0
            obs = obs2

        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device)
            _, last_v = agent.net(o)
            last_val = float(last_v.mean().item())
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        elapsed = time.time() - t_start
        recent = completed_returns[-30:] or [0.0]
        recent_b = completed_bosses[-30:] or [0]
        m = {
            "epoch": ep + 1,
            "elapsed_s": round(elapsed, 1),
            "n_eps_total": len(completed_returns),
            "mean_return": round(float(np.mean(recent)), 3),
            "max_return": round(float(max(recent)), 3),
            "mean_bosses": round(float(np.mean(recent_b)), 2),
            "max_bosses": int(max(recent_b)),
            "total_boss_kills": int(np.sum(completed_bosses)),
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        if time.time() - last_print >= 5 or ep == 0 or ep == epochs - 1:
            print(f"ep {ep+1:4d}/{epochs}  eps={len(completed_returns):5d}  "
                  f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
                  f"bosses={m['max_bosses']} (cum {m['total_boss_kills']})  "
                  f"ent={m['entropy']:.3f}  t={elapsed:.0f}s")
            last_print = time.time()

        if (ep + 1) % 25 == 0:
            ckpt = f"{save_dir}/ppo_{label}_ep{ep+1}.pt"
            torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                        "boss_kill_episodes": boss_kill_episodes}, ckpt)

    final = f"{save_dir}/ppo_{label}_final.pt"
    torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                "boss_kill_episodes": boss_kill_episodes}, final)
    with open(final.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    with open(final.replace(".pt", "_kills.json"), "w") as f:
        json.dump(boss_kill_episodes, f, indent=2, default=str)
    print(f"\nFinal: {final}")
    print(f"Total: {len(completed_returns)} episodes, {sum(completed_bosses)} cumulative kills, "
          f"{len(boss_kill_episodes)} kill-episodes")
    venv.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    label = sys.argv[4] if len(sys.argv) > 4 else "simple"
    main(epochs=epochs, steps_per_epoch=steps, n_envs=n, label=label)
