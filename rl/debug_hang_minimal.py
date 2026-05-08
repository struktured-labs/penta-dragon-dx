"""Minimal hang check — skip ANY torch network call, use simple numpy MLP."""
import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
torch.set_num_threads(1)
torch.set_num_interop_threads(1)
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
print(f"Start", flush=True)
obs, info = env.reset()

# Numpy MLP (3 hidden layers, 256)
np.random.seed(0)
W1 = np.random.randn(obs_dim, 256).astype(np.float32) * 0.01
b1 = np.zeros(256, np.float32)
W2 = np.random.randn(256, 256).astype(np.float32) * 0.01
b2 = np.zeros(256, np.float32)
Wpi = np.random.randn(256, N_ACTIONS).astype(np.float32) * 0.01
bpi = np.zeros(N_ACTIONS, np.float32)

def policy(obs):
    h1 = np.maximum(0, obs @ W1 + b1)
    h2 = np.maximum(0, h1 @ W2 + b2)
    logits = h2 @ Wpi + bpi
    return logits

t0 = time.time()
rng = np.random.default_rng(42)
for t in range(2000):
    logits = policy(obs)
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    a = int(rng.choice(N_ACTIONS, p=probs))
    obs, rew, term, trunc, info = env.step(a)
    if term or trunc:
        obs, info = env.reset()
    if t % 200 == 0:
        print(f"  t={t} ({time.time()-t0:.2f}s)", flush=True)
print(f"DONE {time.time()-t0:.2f}s", flush=True)
env.close()
