"""Probe: from post_multi_kill state (no mini-bosses), force Sara to each room
and see which room transitions D880 to arena (0x0C-0x14).

Strategy: load v19 ep200 + gargoyle.state, run until both mini-bosses dead.
Then write FFBD = 1, 2, 3, ... 7 and watch what scene becomes.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/spider.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"])
net.eval()

env = PentaEnv(REAL, max_steps=15000, savestate_path=SAVE)
obs, _ = env.reset()

# Run v19 ep200 deterministically until both kills
n_kills = 0
print("Running v19 ep200 to clear both mini-bosses...")
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
    if n_kills >= 2:
        break
    if term or trunc:
        print(f"  Episode ended early at t={t} with {n_kills} kills")
        break

# Save state at this point (just after 2nd kill)
saved = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/probe_post_2kills.state"
with open(saved, "wb") as f:
    env.pb.save_state(f)
s = read_state(env.pb)
print(f"\nPost-2-kill state saved: section={s.section} scene={hex(s.scene)} room={s.room} mb={s.miniboss}")

# Now probe: for each FFBD value 1-7, write it + tick, see what scene becomes
print("\nProbing FFBD → scene transitions:")
for room in [1, 2, 3, 4, 5, 6, 7]:
    # Reload the save
    with open(saved, "rb") as f:
        env.pb.load_state(f)
    for _ in range(2): env.pb.tick()
    # Force room transition: write FFCE (next room) and wait for game to consume
    env.pb.memory[0xFFCE] = room
    # Tick for several frames to let scroll handler consume FFCE
    last_scenes = []
    for tick in range(300):
        env.pb.tick()
        s = read_state(env.pb)
        if s.scene not in last_scenes[-3:]:
            last_scenes.append(s.scene)
    s = read_state(env.pb)
    arena = "ARENA!" if 0x0C <= s.scene <= 0x14 else ""
    print(f"  FFBD={room}: end scene={hex(s.scene)} room={s.room} mb={s.miniboss} player_hp={s.player_hp} {arena}")
    print(f"    scenes seen: {[hex(x) for x in last_scenes][:8]}")
env.close()
