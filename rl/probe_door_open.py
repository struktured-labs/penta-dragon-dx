"""Detect tilemap changes when a mini-boss is killed.
Strategy: run v19 ep200 from gameplay_start, snapshot tilemap before mini-boss kill,
then snapshot again right after. Diff the tilemaps — changed tiles are newly-opened doors.
"""
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet
from penta_rl.godmode_env import godmode_step

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"

device = "cuda" if torch.cuda.is_available() else "cpu"
state = torch.load(CKPT, map_location=device, weights_only=False)
net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
net.load_state_dict(state["model"]); net.eval()

env = PentaEnv(REAL, max_steps=50000, savestate_path=SAVE)
obs, _ = env.reset()
pb = env.pb

def read_tilemap(base):
    return [pb.memory[base + i] for i in range(0x400)]

def compare(t1, t2, label):
    diffs = [(i, t1[i], t2[i]) for i in range(0x400) if t1[i] != t2[i]]
    print(f"{label}: {len(diffs)} tile changes")
    for i, before, after in diffs[:30]:
        col = i % 32; row = i // 32
        print(f"  ({col:2d}, {row:2d}): 0x{before:02X} → 0x{after:02X}")

# Run v19 ep200 with godmode until first kill
n_kills = 0
last_tilemap = None
print("Running until mini-boss kill...")
for t in range(50000):
    held = ACTION_BUTTONS[int(net(torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0))[0].argmax(-1).item())]
    for b in env._held: pb.button_release(b)
    env._held = held
    for b in held: pb.button_press(b)
    for _ in range(env.frame_skip):
        godmode_step(pb)
        pb.tick()
    env.steps += 1
    s = read_state(pb)
    obs, r, term, trunc, info = state, 0, False, False, {"state": s}
    from penta_rl.state import state_to_vector
    obs = state_to_vector(s)
    # Detect kill (mb→0)
    mb_now = pb.memory[0xFFBF]
    if last_tilemap is None and mb_now != 0:
        # Snapshot pre-kill
        last_tilemap = read_tilemap(0x9800)
        print(f"  t={t}: pre-kill snapshot taken (mb={mb_now}, room={s.room}, sect={s.section})")
    if last_tilemap is not None and mb_now == 0 and t > 100:
        # Wait 30 frames for tilemap to update
        for _ in range(30 * env.frame_skip):
            godmode_step(pb); pb.tick()
        post_tilemap = read_tilemap(0x9800)
        s2 = read_state(pb)
        print(f"  t={t+30}: post-kill, mb={pb.memory[0xFFBF]}, room={s2.room}, sect={s2.section}")
        compare(last_tilemap, post_tilemap, "Tilemap diff (post-kill)")
        n_kills += 1
        if n_kills >= 2: break
        # Reset for next kill
        last_tilemap = None
    if term or trunc:
        print(f"  Episode ended at t={t}")
        break
env.close()
