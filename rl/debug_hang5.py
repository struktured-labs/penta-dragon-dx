"""Debug 5: pinpoint hang — env.step + agent.net forward."""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
torch.set_num_threads(1)  # try single thread
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

device = "cpu"
env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
cfg = PPOConfig()
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)

obs, info = env.reset()
print(f"Start, obs shape={obs.shape}", flush=True)
t0 = time.time()
for t in range(2000):
    with torch.no_grad():
        o = torch.from_numpy(obs).float().unsqueeze(0)
        logits, _ = agent.net(o)
    a = int(logits.argmax().item())
    obs, rew, term, trunc, info = env.step(a)
    if term or trunc:
        obs, info = env.reset()
    if t % 100 == 0:
        print(f"  t={t} ({time.time()-t0:.2f}s)", flush=True)
print(f"DONE {time.time()-t0:.2f}s", flush=True)
env.close()
