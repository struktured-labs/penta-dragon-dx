"""Systematic grid sweep: when Sara is in gameplay (mb=0), drive her in a snake
pattern (right N steps, down N steps, left N steps, down N steps) to cover every
tile in the current room. If a teleporter exists, stepping on it triggers transition.
"""
from __future__ import annotations
import sys, os, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
from penta_rl.env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet
from penta_rl.godmode_env import godmode_step

REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SAVE = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/gameplay_start.state"
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"
os.makedirs(SAVE_DIR, exist_ok=True)


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    state = torch.load(CKPT, map_location=device, weights_only=False)
    net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
    net.load_state_dict(state["model"]); net.eval()

    env = PentaEnv(REAL, max_steps=600000, savestate_path=SAVE)
    obs, _ = env.reset()
    pb = env.pb

    # Snake-pattern: for non-boss state, do RIGHT 30, DOWN 4, LEFT 30, DOWN 4, ...
    # Plus periodic A press to interact with potential teleporters
    SWEEP_RIGHT = [4]*40   # 40 frames right
    SWEEP_DOWN = [7]*4     # 4 frames down (1 tile)
    SWEEP_LEFT = [5]*40    # 40 frames left
    SWEEP_INTERACT = [0]*4  # 4 frames A press
    sweep_pattern = SWEEP_RIGHT + SWEEP_DOWN + SWEEP_INTERACT + SWEEP_LEFT + SWEEP_DOWN + SWEEP_INTERACT

    sweep_idx = 0
    last_d880 = -1; last_ffba = -1; last_ffbf = -1
    seen_arenas = set(); seen_rooms = set()
    n_kills = 0
    saved = []
    t_start = time.time()

    print(f"Snake-sweep length: {len(sweep_pattern)} actions")

    for t in range(600000):
        # Get action
        if pb.memory[0xFFBF] != 0:
            # Boss alive: use v19 ep200 det policy (combat mode)
            with torch.no_grad():
                o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
                logits, _ = net(o)
                a = int(logits.argmax(-1).item())
        else:
            # No boss: snake sweep
            a = sweep_pattern[sweep_idx % len(sweep_pattern)]
            sweep_idx += 1

        # Execute step with godmode
        for b in env._held: pb.button_release(b)
        env._held = ACTION_BUTTONS[a]
        for b in env._held: pb.button_press(b)
        for _ in range(env.frame_skip):
            godmode_step(pb)
            pb.tick()
        env.steps += 1

        s = read_state(pb)
        from penta_rl.state import state_to_vector
        obs = state_to_vector(s)

        # Track new rooms
        if s.room not in seen_rooms:
            seen_rooms.add(s.room)
            print(f"  NEW ROOM {s.room} at t={t}")
        # Track arena
        if 0x0C <= s.scene <= 0x14 and s.scene not in seen_arenas:
            seen_arenas.add(s.scene)
            print(f"  *** ARENA {hex(s.scene)} at t={t} *** room={s.room}")
            path = f"{SAVE_DIR}/arena_{hex(s.scene)}_t{t}.state"
            with open(path, "wb") as f:
                pb.save_state(f)
            saved.append(path)
        # Track kills
        if last_ffbf != 0 and s.miniboss == 0:
            n_kills += 1

        last_d880 = s.scene; last_ffba = s.level; last_ffbf = s.miniboss

        if t % 3600 == 0:
            elapsed = time.time() - t_start
            print(f"t={t} scene={hex(s.scene)} sect={s.section} room={s.room} "
                  f"mb={s.miniboss} kills={n_kills} arenas={len(seen_arenas)} "
                  f"rooms={sorted(seen_rooms)} ({elapsed:.0f}s)")

    print(f"\nDone. kills={n_kills} arenas={len(seen_arenas)} rooms={sorted(seen_rooms)}")
    env.close()


if __name__ == "__main__":
    main()
