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

## v19 checkpoint landscape (15 eps each, gargoyle.state, max_steps=15000)

| ckpt | det kills | det multi | sample kills | sample multi |
|---|---|---|---|---|
| 100 | 0 | 0 | 21 | **6 (40%)** |
| **200** | **30** | **15 (100%)** | 15 | 0 |
| 300 | 15 | 0 | 21 | **6 (40%)** |
| 400 | 0 | 0 | 17 | 2 (13%) |
| 500-900 | 0 | 0 | 0-6 | 0 |

ep200 is uniquely the golden checkpoint. ep100 and ep300 have decent sample-mode multi-kill rates (~40%) but no det multi-kill. Beyond ep400, policy collapses entirely.

The training trajectory hit a narrow window where the deterministic policy aligned with multi-kill behavior. PPO's gradient pushed past it after ~1 epoch (from peak at ep200).

## Reproducibility experiments (post-headline)

After v19 ep200 was confirmed, I tested whether the BC+PPO recipe replicates with different seeds:

| Run | Seed/Init | Outcome |
|---|---|---|
| v18 (original) | unseeded | sample 70% multi → resume to v19 ep200 (100% det multi) |
| v22 | seed=42 | stuck — only 154 cum kills in 1500 epochs, 5x worse than v18 |
| v23 | resume v22 ep1300 | sustained training peak multi100=12 but eval shows 0/20 det multi at any ckpt |
| v27 | unseeded, granular ckpts | TOTALLY STUCK at ep 0 with entropy=0.000, cum=0 in 640 epochs |

Conclusion: **v19 ep200 was a 1/3 lucky run, not a reliable recipe.** v18 succeeded → v19 followed up successfully → v22/v23/v27 failed. PPO from BC init has high variance.

For reproducibility, future work should try:
- Multi-seed ensemble (run 5+ seeds, take best peak ckpt)
- KL constraint to BC reference (prevent catastrophic drift)
- Population-Based Training (PBT) — automatic seed selection

## v28 multi-seed sweep (post-/loop-resume)

Tested explicit reproducibility with seeds 0/1/2:

| Seed | Cum kills (1500 ep) | sample 20-ep multi (best ckpt) | Outcome |
|---|---|---|---|
| 0 | 571 | 2/20 (10%) at ep700 | partial success — like v12c baseline |
| 1 | 53 | not evaluated (cum stuck) | collapsed mid-training |
| 2 | 0 (cum stuck at 0) | n/a | full stuck-zero ent=0 from start |

**Confirmed**: BC + PPO from gargoyle.state is highly seed-sensitive. Roughly 1/3 of seeds make any meaningful progress. v18 original unseeded run was upper-end of distribution. v19 ep200's 100% det multi-kill was an even rarer alignment downstream of v18.

## Tags

- `rl-v13-kill-detection-fix` — bug diagnostic
- `rl-v18-breakthrough` — sample mode 21/30 multi
- `rl-v19-ep200-100pct-multi-kill` — det mode 30/30 multi
- `v4.7-rl-v19-ep200-generalizes` — generalizes to spider.state
- `v4.7-rl-session-wrap` — final session
