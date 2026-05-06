"""Test v19 ep200 generalization: does it work from gameplay_start.state (level 1 start)?"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"
GARGOYLE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"
START = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
SPIDER = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/spider.state"

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

for save_name, save_path in [("gameplay_start", START), ("spider", SPIDER), ("gargoyle (sanity)", GARGOYLE)]:
    print(f"\n=== {save_name} ===")
    env = PentaEnv(REAL, max_steps=15000, savestate_path=save_path)
    for mode in ["det", "sample"]:
        kills_total = 0; ep_kills_max = 0; multi_eps = 0
        n_eps = 10
        rng = np.random.default_rng(0)
        for ep in range(n_eps):
            obs, _ = env.reset()
            ep_kills = 0
            for t in range(15000):
                with torch.no_grad():
                    o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                    logits, _ = net(o)
                    if mode == "det":
                        a = int(logits.argmax(-1).item())
                    else:
                        a = int(torch.distributions.Categorical(logits=logits).sample().item())
                obs, r, term, trunc, info = env.step(a)
                for ev in info.get("events", []):
                    if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
                        ep_kills += 1
                if term or trunc: break
            kills_total += ep_kills
            if ep_kills >= 2: multi_eps += 1
            if ep_kills > ep_kills_max: ep_kills_max = ep_kills
        print(f"  [{mode}] {n_eps} eps: total_kills={kills_total}, max_ep_kills={ep_kills_max}, multi_eps={multi_eps}/{n_eps}")
    env.close()
