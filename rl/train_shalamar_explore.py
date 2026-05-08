"""High-entropy variant of train_shalamar_np for exploring Shalamar damage windows.

User hint: stage bosses have specific damage spots/moments. Need exploration.
entropy_coef=0.10 (vs 0.03 default) keeps policy stochastic longer.
"""
from __future__ import annotations
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import json, sys, time
import numpy as np
import torch
torch.set_num_threads(1)

sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar_np import ShalamarArenaEnv, boss_kill_reward_cfg, NumpyPolicy
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"
OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl"


def run_chunk(epochs, steps_per_epoch, label, resume_path=None):
    device = "cpu"
    env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                            reward_cfg=boss_kill_reward_cfg(), init_level=1)
    obs_dim = vector_dim()
    cfg = PPOConfig(epochs=epochs, steps_per_epoch=steps_per_epoch,
                    train_iters=10, entropy_coef=0.10)  # higher entropy!
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    if resume_path and os.path.exists(resume_path):
        state = torch.load(resume_path, map_location=device, weights_only=False)
        agent.net.load_state_dict(state["model"])
        prior_metrics = state.get("metrics", [])
        prior_advances = state.get("ffba_advances", 0)
        print(f"Resumed from {resume_path}, {len(prior_metrics)} prior epochs", flush=True)
    else:
        prior_metrics = []
        prior_advances = 0

    np_policy = NumpyPolicy(agent)
    obs, info = env.reset()
    init_ffba = info["state"].level
    print(f"Initial: FFBA={init_ffba} D880={hex(info['state'].scene)}", flush=True)

    completed_returns = []
    ffba_advances = prior_advances
    metrics = list(prior_metrics)
    t_start = time.time()
    rng = np.random.default_rng(int(time.time()) & 0xFFFF)

    def save_ckpt():
        save_path = f"{OUT_DIR}/ppo_{label}_chunk{len(metrics)}.pt"
        torch.save({"model": agent.net.state_dict(), "metrics": metrics,
                    "ffba_advances": ffba_advances}, save_path)
        latest = f"{OUT_DIR}/ppo_{label}_latest.pt"
        if os.path.lexists(latest):
            os.unlink(latest)
        os.symlink(save_path, latest)

    for ep in range(epochs):
        buf = TrajectoryBuffer(obs_dim, steps_per_epoch)
        n_done = 0
        ep_reward = 0.0
        np_policy.refresh()
        for t in range(steps_per_epoch):
            logits, v = np_policy.forward(obs)
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            a = int(rng.choice(N_ACTIONS, p=probs))
            lp = float(np.log(probs[a] + 1e-10))
            obs2, rew, term, trunc, info2 = env.step(a)
            done = term or trunc
            buf.store(obs, a, float(rew), v, lp, done)
            ep_reward += float(rew)
            if info2["state"].level > init_ffba:
                ffba_advances += 1
                print(f"  *** FFBA ADVANCE *** ep={n_done+1} reward={ep_reward:.2f}", flush=True)
                done = True
            if done:
                n_done += 1
                completed_returns.append(ep_reward)
                ep_reward = 0.0
                obs, info = env.reset()
            else:
                obs = obs2

        _, last_val = np_policy.forward(obs)
        data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
        losses = agent.update(data)

        recent = completed_returns[-20:] or [0.0]
        elapsed = time.time() - t_start
        m = {
            "epoch": len(metrics) + 1, "elapsed_s": round(elapsed, 1),
            "n_eps_chunk": len(completed_returns),
            "mean_return": round(float(np.mean(recent)), 2),
            "max_return": round(float(max(recent)), 2),
            "ffba_advances": ffba_advances,
            "loss_pi": round(losses["pi"], 4),
            "loss_v": round(losses["v"], 4),
            "entropy": round(losses["ent"], 4),
        }
        metrics.append(m)
        print(f"ep {len(metrics):4d}  eps={len(completed_returns):3d}  "
              f"ret={m['mean_return']:7.2f}  max={m['max_return']:7.2f}  "
              f"adv={ffba_advances}  ent={m['entropy']:.3f}  t={elapsed:.0f}s", flush=True)
        save_ckpt()

    print(f"\nChunk done: {len(metrics)} total epochs, {ffba_advances} advances", flush=True)
    env.close()


if __name__ == "__main__":
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1024
    label = sys.argv[3] if len(sys.argv) > 3 else "shalamar_explore"
    resume = sys.argv[4] if len(sys.argv) > 4 else f"{OUT_DIR}/ppo_{label}_latest.pt"
    run_chunk(epochs, steps, label, resume_path=resume)
