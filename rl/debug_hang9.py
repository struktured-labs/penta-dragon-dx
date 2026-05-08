"""Debug 9: full train loop with PPO update."""
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
print(f"Start init_ffba={init_ffba}", flush=True)
t0 = time.time()
rng = np.random.default_rng(42)

for ep in range(3):
    print(f"  EP {ep+1} start at t={time.time()-t0:.1f}s", flush=True)
    buf = TrajectoryBuffer(obs_dim, 256)
    for t in range(256):
        if t == 0:
            print(f"    [t=0 before no_grad]", flush=True)
        with torch.no_grad():
            o = torch.from_numpy(obs).float().unsqueeze(0)
            logits, vals = agent.net(o)
            probs = torch.softmax(logits, dim=-1).numpy().squeeze()
            a = int(rng.choice(N_ACTIONS, p=probs))
            lp = float(np.log(probs[a] + 1e-10))
        v = float(vals.item())
        if t == 0:
            print(f"    [t=0 before env.step]", flush=True)
        obs2, rew, term, trunc, info2 = env.step(a)
        if t == 0:
            print(f"    [t=0 after env.step]", flush=True)
        done = term or trunc
        buf.store(obs, a, float(rew), v, lp, done)
        if info2["state"].level > init_ffba:
            done = True
        if done:
            obs, info = env.reset()
        else:
            obs = obs2
    print(f"  EP {ep+1} loop done at t={time.time()-t0:.1f}s, calling update...", flush=True)
    with torch.no_grad():
        o = torch.from_numpy(obs).float().unsqueeze(0)
        _, last_v = agent.net(o)
        last_val = float(last_v.item())
    data = buf.finish(cfg.gamma, cfg.lam, last_val=last_val)
    losses = agent.update(data)
    print(f"  EP {ep+1} update done at t={time.time()-t0:.1f}s, loss_pi={losses['pi']:.4f}", flush=True)
print(f"DONE {time.time()-t0:.2f}s", flush=True)
env.close()
