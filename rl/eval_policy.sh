#!/bin/bash
# Evaluate latest Shalamar policy with deterministic argmax — see if it kills.
cd /home/struktured/projects/penta-dragon-dx-claude/rl
source .venv/bin/activate

LABEL="${1:-shalamar_v6}"
N_EPS="${2:-10}"
CKPT="ppo_${LABEL}_latest.pt"

if [ ! -f "$CKPT" ]; then
    echo "No ckpt at $CKPT"
    exit 1
fi

python3 << EOF
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
torch.set_num_threads(1)
import numpy as np
from train_shalamar_np import ShalamarArenaEnv, boss_kill_reward_cfg, NumpyPolicy
from penta_rl.env import N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PPOAgent, PPOConfig

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

device = "cpu"
env = ShalamarArenaEnv(ROM, max_steps=3000, savestate_path=SHALAMAR,
                        reward_cfg=boss_kill_reward_cfg(), init_level=1)
obs_dim = vector_dim()
cfg = PPOConfig()
agent = PPOAgent(obs_dim, N_ACTIONS, cfg, device=device)
state = torch.load("$CKPT", map_location=device, weights_only=False)
agent.net.load_state_dict(state["model"])
np_policy = NumpyPolicy(agent)

n_kills = 0
returns = []
min_dcbbs = []
for ep in range($N_EPS):
    obs, info = env.reset()
    init_dcbb = info["state"].boss_hp
    min_dcbb = init_dcbb
    init_ffba = info["state"].level
    ep_reward = 0.0
    for t in range(3000):
        logits, v = np_policy.forward(obs)
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        a = int(np.argmax(probs))
        obs, rew, term, trunc, info = env.step(a)
        ep_reward += rew
        if info["state"].boss_hp < min_dcbb:
            min_dcbb = info["state"].boss_hp
        if info["state"].level > init_ffba:
            n_kills += 1
            break
        if term or trunc:
            break
    returns.append(ep_reward)
    min_dcbbs.append(min_dcbb)
print(f"\\n$LABEL: {n_kills}/$N_EPS kills, mean ret={np.mean(returns):.1f}, mean min_DCBB={np.mean(min_dcbbs):.1f}")
env.close()
EOF
