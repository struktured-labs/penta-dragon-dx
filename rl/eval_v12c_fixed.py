"""Eval v12c policy with FIXED reward kill detection on real ROM."""
import sys, os, json
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet, PPOConfig

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v12c_cheat_2env_final.pt"
N_EPS = 20
MAX_STEPS = 15000  # 4+ min per ep — give time for multi-kill

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
cfg = PPOConfig(hidden=256, n_layers=3)
net = PolicyValueNet(vector_dim(), N_ACTIONS, cfg.hidden, cfg.n_layers).to(device)
net.load_state_dict(state["model"])
net.eval()
print(f"loaded {CKPT}")

for mode in ["sample", "det", "random"]:
    env = PentaEnv(REAL, max_steps=MAX_STEPS, savestate_path=SAVE)
    kills = 0
    total_kills = 0
    multi_kill_eps = 0
    total_ret = 0.0
    for ep in range(N_EPS):
        obs, _ = env.reset()
        ep_ret = 0.0; ep_kills = 0
        for t in range(MAX_STEPS):
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, _ = net(o)
                if mode == "det":
                    a = int(logits.argmax(-1).item())
                elif mode == "random":
                    a = int(np.random.randint(0, N_ACTIONS))
                else:
                    a = int(torch.distributions.Categorical(logits=logits).sample().item())
            obs, r, term, trunc, info = env.step(a)
            ep_ret += r
            for ev in info.get("events", []):
                if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                    ep_kills += 1
            if term or trunc: break
        if ep_kills > 0:
            kills += 1
            total_kills += ep_kills
        if ep_kills >= 2:
            multi_kill_eps += 1
        total_ret += ep_ret
        if ep < 3 or ep_kills >= 2:
            print(f"  [{mode}] ep {ep+1:2d} ret={ep_ret:7.2f} steps={t+1} kills={ep_kills}")
    env.close()
    print(f"=== {mode} {N_EPS} eps: kill_eps={kills}/{N_EPS} multi_kill_eps={multi_kill_eps}/{N_EPS} total_kills={total_kills} mean_ret={total_ret/N_EPS:.2f} ===\n")
