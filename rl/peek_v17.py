"""Quick peek: run v17 mid-ckpt, log all events from 5 episodes."""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"

# Find latest checkpoint
import glob
ckpts = sorted(glob.glob("/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v17_bc_ep*.pt"),
               key=lambda p: int(p.split("ep")[-1].split(".")[0]))
ckpt_path = ckpts[-1] if ckpts else None
print(f"Using: {ckpt_path}")
device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(ckpt_path, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

env = PentaEnv(REAL, max_steps=8000, savestate_path=SAVE)
for ep in range(3):
    obs, _ = env.reset()
    ep_ret = 0.0
    all_events = []
    for t in range(8000):
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            logits, _ = net(o)
            a = int(torch.distributions.Categorical(logits=logits).sample().item())
        obs, r, term, trunc, info = env.step(a)
        ep_ret += r
        for ev in info.get("events", []):
            if ev:
                all_events.append((t, ev))
        if term or trunc: break
    print(f"\nEpisode {ep+1}: steps={t+1} ret={ep_ret:.2f} events={len(all_events)}")
    # Group + count event types
    from collections import Counter
    c = Counter()
    for t, ev in all_events:
        if isinstance(ev, tuple) and ev:
            c[ev[0]] += 1
    print(f"  Event counts: {dict(c)}")
    # First few non-trivial events
    print(f"  First 8: {[ev for _, ev in all_events[:8]]}")
env.close()
