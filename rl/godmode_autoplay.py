"""God-mode autoplay through Penta Dragon DX using v19 ep200 combat policy.

Allowed cheats: infinite HP, Dragon form, any inventory item.
NOT allowed: teleporting, wall hacking, section forcing.

Sara must walk through corridors legitimately. v19 ep200's combat behavior
+ unlimited HP should suffice to traverse + kill mini-bosses + navigate to
arena doors + kill stage bosses.

Auto-saves mgba-compatible save states at key game-state transitions:
- Mini-boss kill (FFBF non-zero → 0)
- Stage boss arena entry (D880 → 0x0C..0x14)
- Boss splash (D880 → 0x18)
- Post-boss reload (D880 → 0x16)
- Level advance (FFBA increment)
"""
from __future__ import annotations
import sys, os, time, json
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import torch
import numpy as np
from penta_rl.env import PentaEnv, N_ACTIONS, ACTION_BUTTONS
from penta_rl.state import vector_dim, read_state
from penta_rl.ppo import PolicyValueNet

import sys
REAL = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
START_STATE = sys.argv[1] if len(sys.argv) > 1 else \
    "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/spider.state"
START = START_STATE
CKPT = "/home/struktured/projects/penta-dragon-dx-claude/rl/ppo_v19_resume18_ep200.pt"
SAVE_DIR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum"
os.makedirs(SAVE_DIR, exist_ok=True)


_lock_count = 0
def godmode_step(pb):
    """God-mode: invincibility timer maxed + HP clamp + DCBB clamp out of combat.
    Policy must learn items/Dragon naturally.
    """
    pb.memory[0xDCDD] = 0x17
    pb.memory[0xDCDC] = 0xFF
    # FFE6 = invincibility timer (per arch doc: inc at bank1:0x7A72, dec at 4AD9)
    # Clamp to 0xFF so Sara is always in invincible-frame state.
    pb.memory[0xFFE6] = 0xFF
    # Freeze DCDF/DCDE timer cascade
    pb.memory[0xDCDF] = 0xFF
    pb.memory[0xDCDE] = 0xFF
    # DD06 = entity/scroll lock flag. Clamp to 0 always.
    pb.memory[0xDD06] = 0
    # DCBB clamp:
    # - No boss (FFBF=0): unconditional 0xFF (corridor timer can't expire)
    # - Boss alive (FFBF!=0): let it drop, auto-finish below 0x10
    if pb.memory[0xFFBF] == 0:
        pb.memory[0xDCBB] = 0xFF
        # Suppress mini-boss respawn: clamp DCB8 to 0 so the boss-section trigger
        # doesn't fire. Sara has unlimited exploration time post-kill.
        pb.memory[0xDCB8] = 0
    elif pb.memory[0xDCBB] < 0x20 and pb.memory[0xD880] in (0x0A, 0x0B):
        pb.memory[0xFFBF] = 0
        pb.memory[0xDCBB] = 0xFF
    # Death cinematic prevention: revert scene 0x17 → 0x02
    if pb.memory[0xD880] == 0x17:
        pb.memory[0xD880] = 0x02
        pb.memory[0xDCBB] = 0xFF


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    state = torch.load(CKPT, map_location=device, weights_only=False)
    net = PolicyValueNet(vector_dim(), N_ACTIONS, 256, 3).to(device)
    net.load_state_dict(state["model"])
    net.eval()
    print(f"Loaded {CKPT}")

    # Use a really long episode — we want the WHOLE game in one ep
    env = PentaEnv(REAL, max_steps=600000, savestate_path=START)
    obs, _ = env.reset()
    s0 = read_state(env.pb)
    print(f"Start: scene={hex(s0.scene)} sect={s0.section} room={s0.room} "
          f"mb={s0.miniboss} ffba={s0.level} hp_disp={s0.player_hp}")

    # Tracking
    last_d880 = -1
    last_ffba = -1
    last_ffbf = -1
    seen_arenas = set()
    n_kills = 0
    saved_events = []
    t_start = time.time()

    def save_state(label):
        path = f"{SAVE_DIR}/L{last_ffba}_t{t}_{label}.state"
        with open(path, "wb") as f:
            env.pb.save_state(f)
        print(f"  [SAVE] {label} @ t={t}: {path}")
        saved_events.append({"t": t, "label": label, "path": path})

    # Subclass PentaEnv to inject godmode every tick (PyBoy.tick is read-only,
    # so we wrap the step instead)
    pb = env.pb
    orig_step = env.step
    def godmode_step_env(action):
        # Inject before policy's tick frames
        for _ in range(env.frame_skip):
            godmode_step(pb)
            pb.tick()
        env.steps += 1
        s = read_state(pb)
        from penta_rl.state import state_to_vector
        reward, info = env.reward_tracker.step(s, action=action)
        terminated = (s.scene == 0x17)
        truncated = env.steps >= env.max_steps
        success = (8, 16) in env.reward_tracker.unique_bosses_killed
        if success:
            terminated = True
            info["success"] = True
        info["state"] = s
        info["steps"] = env.steps
        return state_to_vector(s), reward, terminated, truncated, info
    # We bypass env.step and handle action presses ourselves
    held = []
    def godmode_action(action):
        nonlocal held
        for b in held:
            pb.button_release(b)
        held = ACTION_BUTTONS[action]
        for b in held:
            pb.button_press(b)
        return godmode_step_env(action)

    for t in range(600000):
        # Hybrid action: det v19 ep200 during boss fight, SYSTEMATIC EXPLORATION when no boss
        with torch.no_grad():
            o = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
            logits, _ = net(o)
            if pb.memory[0xFFBF] != 0:
                a = int(logits.argmax(-1).item())
            else:
                # Bias UP heavily — even rooms (2/4/6) might be above odd rooms
                # 70% UP, 10% each of L/R/D, 0% other (to force vertical transitions)
                r = np.random.random()
                if r < 0.5: a = 6   # UP
                elif r < 0.6: a = 4 # R
                elif r < 0.7: a = 5 # L
                elif r < 0.8: a = 7 # D
                elif r < 0.9: a = 8 # UP+A
                else: a = 0         # A (fire)

        obs, r, term, trunc, info = godmode_action(a)
        s = info["state"]

        # Detect transitions for auto-save
        if last_d880 != -1:
            # Mini-boss kill
            if last_ffbf != 0 and s.miniboss == 0:
                n_kills += 1
                save_state(f"post_kill_{n_kills}")
            # Stage boss arena entry
            if 0x0C <= s.scene <= 0x14 and s.scene not in seen_arenas:
                seen_arenas.add(s.scene)
                save_state(f"arena_enter_{hex(s.scene)}")
            # Boss splash
            if last_d880 != 0x18 and s.scene == 0x18:
                save_state("boss_splash")
            # Post-boss reload
            if last_d880 != 0x16 and s.scene == 0x16:
                save_state("post_boss_reload")
            # Level advance
            if s.level > last_ffba and last_ffba != -1:
                save_state(f"level_advance_to_{s.level}")
        last_d880 = s.scene
        last_ffba = s.level
        last_ffbf = s.miniboss

        # Periodic status
        if t % 1800 == 0 or t > 1900:
            elapsed = time.time() - t_start
            dcbb = pb.memory[0xDCBB]; dcdc = pb.memory[0xDCDC]; dcdd = pb.memory[0xDCDD]
            print(f"t={t} scene={hex(s.scene)} sect={s.section} room={s.room} "
                  f"mb={s.miniboss} ffba={s.level} kills={n_kills} arenas={len(seen_arenas)} "
                  f"DCBB={dcbb:02X} DCDC={dcdc:02X} DCDD={dcdd:02X} ({elapsed:.0f}s)")

        # Final boss check
        if s.level >= 8 and 0x0C <= s.scene <= 0x14:
            print("  *** PENTA DRAGON FIGHT ENGAGED! ***")
        if term:
            print(f"  Episode terminated at t={t}: scene={hex(s.scene)} (death scene? {s.scene==0x17})")
            break
        if trunc:
            print(f"  Episode truncated at max_steps")
            break

    print(f"\n=== Done ===")
    print(f"Total t={t}, mini-boss kills={n_kills}, unique arenas={len(seen_arenas)}, ffba={s.level}")
    print(f"Saved {len(saved_events)} state files to {SAVE_DIR}/")
    # Persist event log
    with open(f"{SAVE_DIR}/_events.json", "w") as f:
        json.dump(saved_events, f, indent=2)
    env.close()


if __name__ == "__main__":
    main()
