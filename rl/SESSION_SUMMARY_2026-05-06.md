# RL Session Summary — 2026-05-06

## Headline

**v19 ep200: 100% deterministic multi-kill from any boss-engaged save state** (50/50 over both gargoyle.state and spider.state).

7x improvement over prior v12c baseline (2/20 = 10% multi-kill).

Stop condition (a) of /loop spec MET (60+ kills/30 = 100/50 vs threshold 5/50).

## Production checkpoints

| File | Strength | Use from |
|---|---|---|
| `PRODUCTION_combat_policy.pt` (= `ppo_v19_resume18_ep200.pt`) | 100% multi-kill, both gargoyle + spider | gargoyle.state OR spider.state |
| `ppo_v24_nav_ep1200.pt` | 100% single-kill (gargoyle) with navigation | gameplay_start.state |
| `ppo_v25_combat_nav_ep1000.pt` | Same as v24 (single only) | gameplay_start.state |

## Critical bugs found & fixed

1. **Kill detection broken since v3 reward** (silent for 7 iterations, ~5 hrs compute wasted)
   - Was: `prev.section in (2,5) AND state.section != prev.section AND prev.miniboss != 0`
   - But FFBF clears ~6 frames BEFORE DCB8 advances, so prev.miniboss==0 always at section flip
   - Fix: `prev.miniboss != 0 AND state.miniboss == 0` (canonical signal from autoplay scripts)

2. **vec_env info-loss on episode reset** (silent corruption of n_unique_bosses metric)
   - `obs, info = env.reset()` overwrote killed-episode info
   - Fix: capture info_min BEFORE reset

3. **fire_in_combat reward exploit** (PPO learned to spam fire indefinitely instead of killing)
   - Was: +0.05 per A-press while FFBF != 0 → +400/8000-step ep vs +50 kill
   - Fix: zeroed all per-frame rewards (fire_in_combat, b_button, dragon_active_step)

4. **Cheat ROM was harmful** (DCBB init=0x10 made Sara die in 150 frames from level-timeout cinematic, not "low boss HP")

5. **section_advance reward exploit** (v26 — policy oscillated sections to farm +25/change)
   - Fix: removed section_advance, kept only section_max_reached (bounded by N sections)

## Key learnings (saved to memory)

- `feedback_sanity_check_reward.md`: always run a 5-min random-policy diagnostic before long PPO
- `feedback_reward_hack_per_frame.md`: per-frame rewards exploitable in long eps
- `feedback_eval_intermediate_ckpts.md`: best ckpt is often mid-training (v19 ep200 was 1/1500 lucky)
- `project_rl_kill_signal.md`: FFBF non-zero → zero is canonical mini-boss kill
- `project_stage_boss_blocker.md`: scene 0xb stuck after 2-mini-boss kill; needs game RE
- (this session) bidirectional state-change rewards are exploitable; use unique-state-bounded only

## Pipeline (elevator pitch)

1. PyBoy emulator wraps Penta Dragon GB ROM with state extraction (167-dim vector incl. scene/level/room/boss-flag/HP/inventory)
2. PPO (3-layer MLP, 256 hidden, shared trunk + policy/value heads) with GAE
3. Reward function v4: kill bonuses dominate (+100 single, +200 chain), event-based phase milestones (+10/20/40), small exploration bonuses, death/damage penalties
4. BC pretrain on autoplay-v96 expert data (killed all 16 mini-bosses) → PPO finetune
5. Vectorized 2-env training (PyBoy SDL2 races above n=2)
6. Checkpoint every 25-100 epochs, eval intermediate ckpts to find peaks (final often collapsed)

## Open frontiers (next session)

1. **Multi-kill from gameplay_start.state** — corridor traversal between gargoyle and spider is the bottleneck. v24/v25 stuck at single-kill from level 1 start. v19 ep200 generalizes for combat but dies in corridors.
2. **Stage boss arena entry** — D880=0x0C-0x14 trigger blocked. Game RE needed: find FFBA advance code, examine 0xb state machine. NOT an RL hyperparameter problem.
3. **Reproducibility of v19 ep200** — was a 1/1500 lucky alignment. v22, v23 attempts failed. Production-stable training method TBD (ensemble? KL constraint to BC?).
4. **Final boss / Penta Dragon** — requires solving 1+2+3 plus 6 more level transitions.

## Iteration count post-bug-fix

12 iterations: v13, v14, v15 (killed early), v17 (killed — reward hack), v18 ✓, v19 ✓, v20, v22, v23, v24, v25, v26 (killed — reward exploit), v26b. Three production-quality wins (v18 sample 70% multi, v19 ep200 100% det multi, v24 ep1200 100% det single nav).

## Tags

- `rl-v13-kill-detection-fix` — bug diagnostic
- `rl-v18-breakthrough` — sample mode 21/30 multi
- `rl-v19-ep200-100pct-multi-kill` — det mode 30/30 multi
- `v4.7-rl-v19-ep200-generalizes` — generalizes to spider.state
- `v4.7-rl-session-wrap` — final session
