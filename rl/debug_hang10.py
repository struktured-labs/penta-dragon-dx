"""Debug 10: minimal change from debug_hang8 — add custom PPOConfig."""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
torch.set_num_threads(1)
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

device = "cpu"
env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
cfg = PPOConfig(epochs=3, steps_per_epoch=256, train_iters=10, entropy_coef=0.03)
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

obs, info = env.reset()
init_ffba = info["state"].level
print(f"Start", flush=True)
buf = TrajectoryBuffer(obs_dim, 256)
t0 = time.time()
rng = np.random.default_rng(42)

for t in range(2000):
    with torch.no_grad():
        o = torch.from_numpy(obs).float().unsqueeze(0)
        logits, vals = agent.net(o)
        probs = torch.softmax(logits, dim=-1).numpy().squeeze()
        a = int(rng.choice(N_ACTIONS, p=probs))
        lp = float(np.log(probs[a] + 1e-10))
    v = float(vals.item())
    obs2, rew, term, trunc, info2 = env.step(a)
    done = term or trunc
    if t < 256:
        buf.store(obs, a, float(rew), v, lp, done)
    if info2["state"].level > init_ffba:
        done = True
    if done:
        obs, info = env.reset()
    else:
        obs = obs2
    if t % 200 == 0:
        print(f"  t={t} ({time.time()-t0:.2f}s)", flush=True)
print(f"DONE {time.time()-t0:.2f}s", flush=True)
env.close()
