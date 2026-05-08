"""Debug 4: Test simpler torch ops with env."""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
import torch
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)

obs, info = env.reset()
print(f"Start", flush=True)
t0 = time.time()
for t in range(1000):
    # Simple torch op: just a tensor creation
    x = torch.tensor([1.0, 2.0, 3.0])
    obs, rew, term, trunc, info = env.step(int(x.argmax().item()))  # always action 2
    if term or trunc:
        obs, info = env.reset()
    if t % 100 == 0:
        print(f"  t={t} ({time.time()-t0:.1f}s)", flush=True)
print(f"DONE {time.time()-t0:.1f}s", flush=True)
env.close()
