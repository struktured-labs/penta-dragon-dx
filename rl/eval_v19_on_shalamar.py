"""Eval v19 ep200 (golden ckpt) on Shalamar arena.

v19 was trained on mini-bosses but reached 100% det multi-kill. Maybe it can
also handle Shalamar (a stage boss) via the same combat patterns.
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
torch.set_num_threads(1)
import numpy as np
from train_shalamar_np import ShalamarArenaEnv, boss_kill_reward_cfg, NumpyPolicy
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"


def main():
    device = "cpu"
    env = ShalamarArenaEnv(ROM, max_steps=2000, savestate_path=SHALAMAR,
                            reward_cfg=boss_kill_reward_cfg(), init_level=1)
    obs_dim = vector_dim()
    cfg = PPOConfig()
    agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
    if os.path.exists(CKPT):
        state = torch.load(CKPT, map_location=device, weights_only=False)
        try:
            agent.net.load_state_dict(state["model"])
            print(f"Loaded {CKPT}", flush=True)
        except Exception as e:
            print(f"Load failed: {e}", flush=True)
            return

    np_policy = NumpyPolicy(agent)

    n_kills = 0
    n_eps = 10
    rng = np.random.default_rng(0)
    for ep in range(n_eps):
        obs, info = env.reset()
        init_ffba = info["state"].level
        n_steps = 0
        ep_reward = 0.0
        max_ent_t = 0
        for t in range(2000):
            logits, v = np_policy.forward(obs)
            probs = np.exp(logits - logits.max())
            probs /= probs.sum()
            # Deterministic argmax
            a = int(np.argmax(probs))
            obs2, rew, term, trunc, info2 = env.step(a)
            ep_reward += rew
            n_steps += 1
            if info2["state"].level > init_ffba:
                n_kills += 1
                print(f"  ep {ep+1}: KILL at t={t} reward={ep_reward:.2f}", flush=True)
                break
            if term or trunc:
                break
            obs = obs2
        else:
            print(f"  ep {ep+1}: no kill, max_steps reached, reward={ep_reward:.2f}", flush=True)
    print(f"\nTotal kills: {n_kills}/{n_eps}", flush=True)
    env.close()


if __name__ == "__main__":
    main()
