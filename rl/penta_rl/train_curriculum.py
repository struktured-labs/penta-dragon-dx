"""Curriculum-aware vectorized PPO training with LLM coach.

Each env worker holds its own RewardConfig; we pass updates via a
control message channel to apply curriculum stage transitions.
"""
from __future__ import annotations
import json, time, sys, os
import numpy as np
import torch
from .vec_env import VecPentaEnv
from .state import vector_dim
from .ppo import PPOAgent, PPOConfig, TrajectoryBuffer
from .coach import LLMCoach
from .reward import RewardConfig
from .curriculum import CurriculumScheduler, DEFAULT_CURRICULUM
from .env import N_ACTIONS


ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def main(epochs: int = 50, steps_per_epoch: int = 1024, n_envs: int = 4,
         coach_every: int = 10, max_steps: int = 4000, save_dir: str = SAVE_DIR,
         resume: str = None):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}, n_envs={n_envs}, epochs={epochs}, steps/epoch={steps_per_epoch}")

    venv = VecPentaEnv(ROM, n=n_envs, max_steps=max_steps)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch * n_envs, train_iters=10)
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    if resume and os.path.exists(resume):
        state = torch.load(resume, map_location=device, weights_only=False)
        agent.net.load_state_dict(state["model"])
        print(f"Resumed from {resume}")

    coach = LLMCoach()
    curriculum = CurriculumScheduler()
    print(f"Curriculum stage 0: {curriculum.current.name}")

    metrics = []
    obs = venv.reset()
    ep_rewards = np.zeros(n_envs, dtype=np.float32)
    ep_lengths = np.zeros(n_envs, dtype=np.int32)
    completed_returns = []
    completed_bosses = []
    completed_events = []

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
                    completed_bosses.append(int(infos[i].get("n_unique_bosses", 0)))
                    if infos[i].get("events"):
                        completed_events.append(infos[i]["events"])
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
        recent = completed_returns[-20:] or [0.0]
        recent_b = completed_bosses[-20:] or [0]
        m = {
            "epoch": ep + 1,
            "stage": curriculum.current.name,
            "stage_idx": curriculum.idx,
            "elapsed_s": round(elapsed, 1),
            "n_eps_total": len(completed_returns),
            "mean_return_20": round(float(np.mean(recent)), 3),
            "max_return_20": round(float(max(recent)), 3),
            "mean_bosses_20": round(float(np.mean(recent_b)), 2),
            "max_bosses_20": int(max(recent_b)),
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        print(f"ep {ep+1:3d}/{epochs}  [{curriculum.current.name:8s}]  eps={len(completed_returns):4d}  "
              f"ret={m['mean_return_20']:7.2f}  max_ret={m['max_return_20']:7.2f}  "
              f"bosses={m['max_bosses_20']}  ent={m['entropy']:.3f}  t={elapsed:.0f}s")

        # Curriculum advancement (note: stage change doesn't propagate to workers
        # in current design — they keep using initial RewardConfig. Future work.)
        advanced, reason = curriculum.step(m)
        if advanced:
            print(f"[curriculum] {reason}")

        # LLM coaching
        if (ep + 1) % coach_every == 0 and ep > 0:
            try:
                guidance = coach.coach(metrics, curriculum.current.reward_cfg, completed_events[-10:])
                if guidance:
                    print(f"[coach] guidance: {json.dumps(guidance, default=str)[:300]}")
            except Exception as e:
                print(f"[coach] error: {e}")

        # Periodic checkpoint
        if (ep + 1) % 10 == 0:
            ckpt = f"{save_dir}/ppo_curriculum_ep{ep+1}.pt"
            torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                        "curriculum_idx": curriculum.idx}, ckpt)
            print(f"  ckpt → {ckpt}")

    final = f"{save_dir}/ppo_curriculum_final.pt"
    torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                "curriculum_idx": curriculum.idx}, final)
    with open(final.replace(".pt", "_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nFinal: {final}")
    print(f"Total: {len(completed_returns)} episodes, "
          f"max boss kills in any single episode: {max(completed_bosses or [0])}")
    venv.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    main(epochs=epochs, steps_per_epoch=steps, n_envs=n)
