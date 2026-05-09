"""Test that an injected state runs cleanly in PentaEnv.
Run a random walk for N steps, log scene/HP/section transitions, ensure no crashes."""
from __future__ import annotations
import os, sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
import numpy as np

from penta_rl.env import PentaEnv, N_ACTIONS

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"


def test_state(state_path: str, n_steps: int = 500, seed: int = 42):
    env = PentaEnv(ROM, max_steps=n_steps, savestate_path=state_path)
    obs, info = env.reset()
    s = info["state"]
    pb = env.pb
    print(f"=== {state_path} ===")
    print(f"  init D880=0x{s.scene:02x} FFBA={s.level} FFBD={s.room} FFBF={s.miniboss} "
          f"DCB8={pb.memory[0xDCB8]} HP={pb.memory[0xDCDC]:02x}/{pb.memory[0xDCDD]:02x}")
    rng = np.random.default_rng(seed)
    scene_log = [s.scene]
    mb_log = [s.miniboss]
    hp_log = [pb.memory[0xDCDC]]
    deaths = 0
    actions_taken = 0
    try:
        for t in range(n_steps):
            a = int(rng.integers(N_ACTIONS))
            obs, rew, term, trunc, info = env.step(a)
            s = info["state"]
            actions_taken += 1
            if scene_log[-1] != s.scene:
                scene_log.append(s.scene)
            if s.scene == 0x17 and mb_log[-1] != s.scene:  # death
                deaths += 1
            if term or trunc:
                break
        print(f"  ran {actions_taken} actions, NO CRASH")
        print(f"  final D880=0x{s.scene:02x} FFBA={s.level} FFBD={s.room} FFBF={s.miniboss}")
        print(f"  scene path: {[hex(x) for x in scene_log[:10]]}")
        print(f"  deaths: {deaths}")
    except Exception as e:
        print(f"  CRASH after {actions_taken} actions: {e}")
    env.close()


if __name__ == "__main__":
    for sp in sys.argv[1:]:
        test_state(sp, n_steps=500)
        print()
