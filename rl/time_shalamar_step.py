"""Measure per-step time of ShalamarArenaEnv to find perf bottleneck."""
import sys, time
sys.path.insert(0, "/home/struktured/projects/penta-dragon-dx-claude/rl")
from train_shalamar import ShalamarArenaEnv, boss_kill_reward_cfg

ROM = "/home/struktured/projects/penta-dragon-dx-claude/rom/Penta Dragon (J) [A-fix].gb"
SHALAMAR = "/home/struktured/projects/penta-dragon-dx-claude/rl/saves/curriculum/arena_FFBA1_D880_0xd_FFD3_4.state"

env = ShalamarArenaEnv(ROM, max_steps=600, savestate_path=SHALAMAR,
                       reward_cfg=boss_kill_reward_cfg(), init_level=1)
t0 = time.time()
obs, info = env.reset()
print(f"First reset: {time.time()-t0:.2f}s")

# Time 100 steps
t0 = time.time()
for i in range(100):
    obs, rew, term, trunc, info = env.step(0)  # action 0 = A button
    if term or trunc:
        env.reset()
elapsed = time.time() - t0
print(f"100 steps: {elapsed:.2f}s ({elapsed*10:.1f}ms/step, {100/elapsed:.0f} steps/s)")

# Time 5 resets
t0 = time.time()
for i in range(5):
    env.reset()
elapsed = time.time() - t0
print(f"5 resets: {elapsed:.2f}s ({elapsed/5*1000:.0f}ms/reset)")

env.close()
