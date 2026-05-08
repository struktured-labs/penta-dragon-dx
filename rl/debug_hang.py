"""Find what's causing the hang. Print every step's timing.

Hypothesis: a specific action or state causes env.step to take very long.
"""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg
import numpy as np

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)

obs, info = env.reset()
print(f"Initial: HP={info['state'].player_hp} D880={hex(info['state'].scene)}", flush=True)

# Run 3000 steps with random actions, time each step, watch for slow ones
max_step_time = 0
slow_steps = []
rng = np.random.default_rng(42)
n_resets = 0
t_global = time.time()
for t in range(3000):
    a = int(rng.integers(0, 12))
    t0 = time.time()
    obs2, rew, term, trunc, info2 = env.step(a)
    dt = time.time() - t0
    if dt > 0.01:  # slow step
        slow_steps.append((t, a, dt, info2['state'].scene, info2['state'].level))
        if len(slow_steps) <= 10:
            print(f"  SLOW step {t}: action={a} dt={dt*1000:.1f}ms scene={hex(info2['state'].scene)} ffba={info2['state'].level}", flush=True)
    max_step_time = max(max_step_time, dt)
    if term or trunc:
        n_resets += 1
        t0 = time.time()
        obs, info = env.reset()
        dt_reset = time.time() - t0
        print(f"  RESET #{n_resets} at step {t}: dt={dt_reset*1000:.1f}ms", flush=True)
        if n_resets > 10:
            break
    else:
        obs = obs2
    if t % 500 == 0:
        elapsed = time.time() - t_global
        print(f"  t={t} ({elapsed:.1f}s elapsed, {n_resets} resets, {len(slow_steps)} slow steps, max_dt={max_step_time*1000:.1f}ms)", flush=True)

print(f"\nTOTAL: {len(slow_steps)} slow steps, max={max_step_time*1000:.1f}ms", flush=True)
print(f"Top 20 slowest:", flush=True)
slow_steps.sort(key=lambda x: -x[2])
for t, a, dt, scene, ffba in slow_steps[:20]:
    print(f"  step {t} action={a} dt={dt*1000:.1f}ms scene={hex(scene)} ffba={ffba}", flush=True)

env.close()
