"""Random policy on Shalamar arena — see if random play can ever beat the boss."""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sys
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar_np import ShalamarArenaEnv, boss_kill_reward_cfg
from penta_rl.env import N_ACTIONS
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"


def main():
    env = ShalamarArenaEnv(ROM, max_steps=5000, savestate_path=SHALAMAR,
                            reward_cfg=boss_kill_reward_cfg(), init_level=1)
    rng = np.random.default_rng(0)

    # Try 5 episodes of pure random
    for ep in range(5):
        obs, info = env.reset()
        ep_reward = 0.0
        max_dcbb_drop = 0
        init_dcbb = info["state"].boss_hp
        for t in range(5000):
            a = int(rng.integers(0, N_ACTIONS))
            obs, rew, term, trunc, info = env.step(a)
            ep_reward += rew
            if info["state"].boss_hp < init_dcbb:
                drop = init_dcbb - info["state"].boss_hp
                max_dcbb_drop = max(max_dcbb_drop, drop)
            if term:
                print(f"  ep {ep+1}: SUCCESS at t={t} reward={ep_reward:.1f}", flush=True)
                break
            if trunc:
                print(f"  ep {ep+1}: timeout, reward={ep_reward:.1f} max_DCBB_drop={max_dcbb_drop}", flush=True)
                break
    env.close()


if __name__ == "__main__":
    main()
