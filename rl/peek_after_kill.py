"""Peek: what does v19 ep200 do AFTER killing both mini-bosses? (chase stage boss)"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"
device = "cuda" if torch.cuda.is_available() else "cpu"

state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

env = PentaEnv(REAL, max_steps=30000, savestate_path=SAVE)
obs, _ = env.reset()
ep_ret = 0.0
post_kill_frame = -1
n_kills = 0
last_section = -1
last_scene = -1
last_room = -1
state_changes = []
for t in range(30000):
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        logits, _ = net(o)
        a = int(logits.argmax(-1).item())  # det
    obs, r, term, trunc, info = env.step(a)
    ep_ret += r
    s = info["state"]
    sig = (s.section, hex(s.scene), s.room, s.miniboss, hex(s.boss_hp))
    if sig != (last_section, last_scene if last_scene != -1 else "?", last_room, None, None) and len(state_changes) < 60:
        state_changes.append((t, sig))
        last_section = s.section
    for ev in info.get("events", []):
        if isinstance(ev, tuple) and ev:
            if "BOSS_KILL" in str(ev[0]):
                n_kills += 1
                print(f"  t={t}: KILL #{n_kills} state={sig}")
                if n_kills == 2:
                    post_kill_frame = t
    if term or trunc:
        break
print(f"\nFinal: t={t} ret={ep_ret:.2f} kills={n_kills}")
print(f"Last state: section={s.section} scene={hex(s.scene)} room={s.room} mb={s.miniboss}")
if post_kill_frame > 0:
    print(f"Post-2nd-kill frame: {post_kill_frame}, time after: {t - post_kill_frame} steps")
print(f"\nFirst 50 state changes:")
for tt, sig in state_changes[:50]:
    print(f"  t={tt:5d}: section={sig[0]} scene={sig[1]} room={sig[2]} mb={sig[3]} boss_hp={sig[4]}")
env.close()
