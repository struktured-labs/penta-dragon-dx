"""Generate save state in corridor between gargoyle (kill) and spider section.

Strategy: Run v19 ep200 deterministically from gameplay_start. Wait for KILL #1 (gargoyle).
After kill, wait until scene returns to 0x02 (gameplay) and section advances to 3 (post-gargoyle corridor).
Save state there.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
START = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
OUT = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/post_gargoyle_corridor.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

env = PentaEnv(REAL, max_steps=20000, savestate_path=START)
obs, _ = env.reset()
n_kills = 0
saved = False
print("Running v19 ep200 deterministically from gameplay_start...")
for t in range(20000):
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        logits, _ = net(o)
        a = int(logits.argmax(-1).item())
    obs, r, term, trunc, info = env.step(a)
    for ev in info.get("events", []):
        if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
            n_kills += 1
            print(f"  t={t}: KILL #{n_kills}")
    s = info["state"]
    # Save when we're in corridor (post-gargoyle, scene back to gameplay, section advanced)
    if n_kills == 1 and not saved and s.scene == 0x02 and s.section == 3:
        with open(OUT, "wb") as f:
            env.pb.save_state(f)
        print(f"  ✓ Saved at t={t}: section={s.section} scene={hex(s.scene)} room={s.room} mb={s.miniboss}")
        saved = True
        break
    if term or trunc: break

if not saved:
    s = read_state(env.pb)
    print(f"  No save: t={t} kills={n_kills} section={s.section} scene={hex(s.scene)} room={s.room}")
env.close()
