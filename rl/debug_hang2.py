"""Debug 2: env.step + torch.no_grad inference, but no PPO update.

Test if combining env.step + torch.net(o) causes hang.
"""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig
import torch
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

device = "cpu"  # try CPU to rule out CUDA issue
env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
cfg = PPOConfig()
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

obs, info = env.reset()
print(f"Start, obs shape={obs.shape}", flush=True)

# Run 3000 steps WITHOUT PPO updates, with torch.no_grad
slow_steps = []
n_resets = 0
t_start = time.time()
for t in range(3000):
    t0 = time.time()
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        logits, vals = agent.net(o)
        dist = torch.distributions.Categorical(logits=logits)
        act = dist.sample()
    a = int(act.item())
    obs2, rew, term, trunc, info2 = env.step(a)
    dt = time.time() - t0
    if dt > 0.01:
        slow_steps.append((t, a, dt))
    if term or trunc:
        n_resets += 1
        obs, info = env.reset()
    else:
        obs = obs2
    if t % 200 == 0:
        elapsed = time.time() - t_start
        print(f"  t={t} ({elapsed:.1f}s, {n_resets} resets, {len(slow_steps)} slow)", flush=True)

print(f"\nTOTAL: {len(slow_steps)} slow, top 5:", flush=True)
slow_steps.sort(key=lambda x: -x[2])
for t, a, dt in slow_steps[:5]:
    print(f"  step {t} action={a} dt={dt*1000:.1f}ms", flush=True)
env.close()
print("DONE", flush=True)
