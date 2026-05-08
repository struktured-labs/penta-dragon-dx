"""Debug 3: just torch inference, no env."""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig
import torch
import numpy as np

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Device: {device}", flush=True)
obs_dim = vector_dim()
cfg = PPOConfig()
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
print(f"Agent created", flush=True)

obs = np.random.randn(obs_dim).astype(np.float32)
t0 = time.time()
for t in range(3000):
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        logits, vals = agent.net(o)
        dist = torch.distributions.Categorical(logits=logits)
        act = dist.sample()
    if t % 500 == 0:
        elapsed = time.time() - t0
        print(f"  t={t} ({elapsed:.1f}s)", flush=True)
print(f"DONE {time.time()-t0:.1f}s", flush=True)
