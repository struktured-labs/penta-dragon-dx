"""Debug train_shalamar — print every PPO update step to find hang."""
import sys, time, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
import torch
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig, TrajectoryBuffer

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

device = "cuda" if torch.cuda.is_available() else "cpu"
env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
cfg = PPOConfig(epochs=30, steps_per_epoch=1024, train_iters=10, entropy_coef=0.03)
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

obs, info = env.reset()
print(f"Reset done. obs shape={obs.shape}", flush=True)

for ep in range(30):
    t_ep = time.time()
    print(f"\n=== EPOCH {ep+1} starting ===", flush=True)
    buf = TrajectoryBuffer(obs_dim, 1024)
    n_done = 0
    for t in range(1024):
        if t == 0 or t % 200 == 0:
            print(f"  step {t} ({time.time()-t_ep:.1f}s elapsed, {n_done} eps done)", flush=True)
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            logits, vals = agent.net(o)
            dist = torch.distributions.Categorical(logits=logits)
            act = dist.sample()
            logp = dist.log_prob(act)
        a = int(act.item())
        v = float(vals.item())
        lp = float(logp.item())
        obs2, rew, term, trunc, info2 = env.step(a)
        done = term or trunc
        buf.store(obs, a, float(rew), v, lp, done)
        if done:
            n_done += 1
            obs, info = env.reset()
        else:
            obs = obs2
    print(f"  Epoch {ep+1}: {n_done} eps done, {time.time()-t_ep:.1f}s", flush=True)
    t_upd = time.time()
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        _, last_v = agent.net(o)
        last_val = float(last_v.item())
    data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
    losses = agent.update(data)
    print(f"  PPO update: {time.time()-t_upd:.2f}s, losses={losses}", flush=True)

env.close()
print("DONE", flush=True)
