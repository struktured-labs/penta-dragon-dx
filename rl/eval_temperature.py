"""Eval existing policies with TEMPERATURE-SCALED det inference.

Hypothesis: det collapse happens because argmax picks "mode" action that's not the multi-kill action.
Sample succeeds because stochasticity covers the right behaviors. Temperature 0.3-0.7 might give
near-deterministic behavior but covers the right mode.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"

CKPTS = [
    ("v18 final", "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v18_bc_v4r_final.pt", 256, 3),
    ("v19 ep200", "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt", 256, 3),
    ("v31 final", "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v31_bignet_final.pt", 512, 4),
]
TEMPERATURES = [1.0, 0.5, 0.3, 0.1]
N_EPS = 10
device = "cuda" if torch.cuda.is_available() else "cpu"

for name, path, h, l in CKPTS:
    state = torch.load(path, map_location=device, weights_only=False)
    net = PolicyValueNet(vector_dim(), N_ACTIONS, h, l).to(device)
    net.load_state_dict(state["model"])
    net.eval()
    print(f"\n=== {name} ===")
    env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE)
    for temp in TEMPERATURES:
        kills, multi = 0, 0
        for ep in range(N_EPS):
            obs, _ = env.reset()
            ep_k = 0
            for t in range(15000):
                with torch.no_grad():
                    o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                    logits, _ = net(o)
                    if temp == 0:
                        a = int(logits.argmax(-1).item())
                    else:
                        a = int(torch.distributions.Categorical(logits=logits / temp).sample().item())
                obs, r, term, trunc, info = env.step(a)
                for ev in info.get("events", []):
                    if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                        ep_k += 1
                if term or trunc: break
            kills += ep_k
            if ep_k >= 2: multi += 1
        print(f"  temp={temp}: total={kills} multi={multi}/{N_EPS}")
    env.close()
