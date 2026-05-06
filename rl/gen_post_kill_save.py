"""Generate save state right after v19 ep200 kills both mini-bosses.

Strategy: run v19 ep200 deterministically, monitor n_unique_bosses == 2,
save state at that frame for v21 to start from.
"""
import sys, os
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE_IN = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gargoyle.state"
SAVE_OUT = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/post_multi_kill.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE_IN)
obs, _ = env.reset()
n_kills = 0
saved_at = -1
for t in range(15000):
    with torch.no_grad():
        o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        logits, _ = net(o)
        a = int(logits.argmax(-1).item())
    obs, r, term, trunc, info = env.step(a)
    for ev in info.get("events", []):
        if isinstance(ev, tuple) and ev and "BOSS_KILL" in str(ev[0]):
            n_kills += 1
            print(f"  t={t}: KILL #{n_kills}")
    if n_kills == 2 and saved_at < 0:
        # Wait until scene returns to 0x02 (gameplay) — bounded settle
        for settle_t in range(600):  # up to 10 sec
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, _ = net(o)
                a = int(logits.argmax(-1).item())
            obs, r, term, trunc, info = env.step(a)
            s_now = read_state(env.pb)
            if s_now.scene == 0x02:
                break
        s = read_state(env.pb)
        print(f"  Settled at t={t+settle_t}: scene={hex(s.scene)} (waited {settle_t} steps)")
        print(f"  state: section={s.section} room={s.room} mb={s.miniboss} player_hp={s.player_hp} level={s.level}")
        # Save state to file
        with open(SAVE_OUT, "wb") as f:
            env.pb.save_state(f)
        print(f"  ✓ Saved to {SAVE_OUT}")
        saved_at = t + 120
        break
    if term or trunc:
        print(f"  Episode ended at t={t} before 2 kills (n_kills={n_kills})")
        break

env.close()
print(f"\nDone. saved_at={saved_at}, total_kills={n_kills}")
