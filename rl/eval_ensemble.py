"""Ensemble eval: 3 policies vote on action each step.

Hypothesis: individual policies have det collapse (wrong mode). Ensemble vote might
hit the correct multi-kill mode if any one policy has it.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
import numpy as np
from collections import Counter
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"

CKPTS = [
    ("/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v18_bc_v4r_final.pt", 256, 3),
    ("/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt", 256, 3),
    ("/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v31_bignet_final.pt", 512, 4),
]
device = "cuda" if torch.cuda.is_available() else "cpu"

nets = []
for path, h, l in CKPTS:
    net = PolicyValueNet(vector_dim(), N_ACTIONS, h, l).to(device)
    state = torch.load(path, map_location=device, weights_only=False)
    net.load_state_dict(state["model"])
    net.eval()
    nets.append(net)
print(f"Loaded {len(nets)} policies")

def ensemble_action(obs, mode):
    """Return action via majority vote (det) or stochastic mix (sample)."""
    actions = []
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        for net in nets:
            logits, _ = net(o)
            if mode == "det":
                a = int(logits.argmax(-1).item())
            else:
                a = int(torch.distributions.Categorical(logits=logits).sample().item())
            actions.append(a)
    if mode == "det":
        # Majority vote
        c = Counter(actions)
        return c.most_common(1)[0][0]
    else:
        # Random pick from samples
        return actions[np.random.randint(len(actions))]

env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE)
for mode in ["det", "sample"]:
    kills, multi, total_ret = 0, 0, 0.0
    for ep in range(20):
        obs, _ = env.reset()
        ep_k = 0; ep_r = 0.0
        for t in range(15000):
            a = ensemble_action(obs, mode)
            obs, r, term, trunc, info = env.step(a)
            ep_r += r
            for ev in info.get("events", []):
                if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                    ep_k += 1
            if term or trunc: break
        kills += ep_k
        if ep_k >= 2: multi += 1
        total_ret += ep_r
    print(f"  ENSEMBLE [{mode}] 20 eps: total={kills} multi={multi}/20 mean_ret={total_ret/20:.2f}")
env.close()
