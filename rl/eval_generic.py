"""Generic eval: load a PPO checkpoint, run sample/det/random on real ROM."""
from __future__ import annotations
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet, PPOConfig

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"


def eval_ckpt(ckpt_path: str, n_eps: int = 20, max_steps: int = 15000, hidden: int = 256, n_layers: int = 3):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    state = torch.load(ckpt_path, map_location=device, weights_only=False)
    net = PolicyValueNet(vector_dim(), N_ACTIONS, hidden, n_layers).to(device)
    net.load_state_dict(state["model"])
    net.eval()
    print(f"loaded {ckpt_path}  n_eps={n_eps}  max_steps={max_steps}")
    out = {}
    for mode in ["sample", "det", "random"]:
        env = PentaEnv(REAL, max_steps=max_steps, savestate_path=SAVE)
        kills, total_kills, multi_eps, total_ret = 0, 0, 0, 0.0
        for ep in range(n_eps):
            obs, _ = env.reset()
            ep_ret, ep_kills = 0.0, 0
            for t in range(max_steps):
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
                kills += 1; total_kills += ep_kills
            if ep_kills >= 2: multi_eps += 1
            total_ret += ep_ret
        env.close()
        result = {
            "kill_eps": kills, "n_eps": n_eps, "multi_kill_eps": multi_eps,
            "total_kills": total_kills, "mean_ret": total_ret / n_eps,
        }
        out[mode] = result
        print(f"  [{mode}] kill_eps={kills}/{n_eps} multi_kill_eps={multi_eps}/{n_eps} "
              f"total={total_kills} mean_ret={total_ret/n_eps:.2f}")
    return out


if __name__ == "__main__":
    ckpt = sys.argv[1] if len(sys.argv) > 1 else "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v13_fixed_reward_final.pt"
    n_eps = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    max_steps = int(sys.argv[3]) if len(sys.argv) > 3 else 15000
    eval_ckpt(ckpt, n_eps, max_steps)
