# BC + PPO Results — Day 5 Pipeline Validation

## Disclosure: Privileged-State RL (Not Pure RL)

**This is not a fair Game Boy agent.** Our PentaEnv reads WRAM/HRAM/OAM directly,
giving the policy information the human player doesn't have access to (boss HP, scene
flags, internal state machine bytes, sprite slot data). This is "asymmetric" or
"state-aware" RL — useful for:

- Verifying game mechanics hypotheses (e.g., boss 16 collision claim)
- Prototyping reward functions
- Finding ROM-patch effects
- Building intuition about state-machine transitions

It is NOT:
- A vision-based agent that could play the unmodified game from screen pixels
- A "fair" RL benchmark
- Transferable to a real human-input-only setting

A true pixel-based agent would use `pyboy.screen` (160×144 framebuffer) + a CNN
frontend. That's a different (much harder, much slower) project. For our reverse-
engineering goals, privileged-state is the right tool — we're using RL to explore
the state space the architecture doc describes.



## Summary

Built and validated a full imitation learning + reinforcement learning pipeline for Penta Dragon DX. **BC+PPO achieves 2.64× random baseline return** in mini-boss combat.

## Pipeline

1. **Recording** (`scripts/probes/autoplay_record.lua`): mgba-qt headless runs the existing `autoplay_full_game.lua` for 30 minutes. Logs `(state_vector, action_idx)` JSONL every 4 frames.
2. **Dataset** (`penta_rl/bc_data.py`): Converts JSONL → numpy arrays matching `PentaEnv.state_to_vector` schema exactly (59-dim float32 obs, 12-action int target).
3. **Behavioral cloning** (`penta_rl/bc_train.py`): Cross-entropy loss on `PolicyValueNet` policy head, class-weighted to combat action imbalance (autoplay heavily uses A button + UP+A combo).
4. **PPO fine-tune** (`penta_rl/train_bc_ppo.py`): Loads BC weights, runs combat-focused PPO at reduced learning rate (1e-4) to preserve learned features.
5. **Eval** (`penta_rl/bc_eval.py`): Random vs BC-sample vs BC-deterministic comparison on `gargoyle.state` save state.

## Empirical Results (gargoyle save state, 5 episodes each)

| Policy | Mean Return | Boss Kills | Mean Steps | vs Random |
|--------|-------------|------------|------------|-----------|
| **Random** | 31.86 | 0 | 1372.6 (dies early) | 1.0× |
| **BC only (det)** | 47.21 | 0 | 1500.0 (survives) | 1.48× |
| **BC + PPO (sample)** | 69.65 | 0 | 1348.6 | 2.19× |
| **BC + PPO (det)** | **84.25** | 0 | 1500.0 (survives) | **2.64×** |

## Key Findings

### What worked

- **End-to-end pipeline runs** in ~35 minutes total: 30 min record + 3s BC train + 38s PPO fine-tune.
- **BC initialization dramatically reduces PPO entropy** (BC+PPO starts at ent~1.4 vs fresh PPO ent~2.5) — policy is focused from epoch 1.
- **BC policy survives full episodes** while random policy dies. The learned defensive movement is real.
- **PPO improves on BC** (47 → 84 reward) — RL fine-tuning extracts more value from BC's foundation.

### What didn't crack

- **Zero boss kills** — but this isn't a pipeline failure. The autoplay expert (`autoplay_full_game.lua`) **also killed zero bosses** in our recording session (encountered Gargoyle but couldn't damage it in 30 minutes). The student can't surpass a teacher who never demonstrated the skill.

### Action distribution (autoplay, 27000 frames)

| Action | Buttons | Frequency |
|--------|---------|-----------|
| 0 | A | 38% |
| 8 | UP+A | 33% |
| 9 | DOWN+A | 23% |
| 6 | U | 6% |
| 4, 5, 7 | R, L, D | <1% each |
| 1, 2, 3, 10, 11 | B, Sel, Start, L+B, R+B | 0% |

The autoplay expert essentially never uses the B button or the menu actions. Class weighting in BC training compensates so the model still learns to use them.

## Why The Expert Couldn't Kill

Looking at autoplay log: encountered Gargoyle at f=6281 (~105s), tracked it for the remaining 28 minutes, but never landed enough projectiles. Possible reasons:

1. **Combat positioning is hard** — gargoyle moves fast; even with centroid tracking the autoplay's heuristic is too coarse
2. **Phase-reset mechanics** — DCBB rebounds at <0x80 (+0x80) and <0xC0 (+0x40) per architecture doc, requires sustained hits
3. **Random exploration not enough** — autoplay's A-every-2/3-frames may miss the boss most of the time

To get successful kill demos, we'd need either:
- A better autoplay (with smarter projectile aim)
- Use cheats: ROM-patch DCBB to start very low (0x10) so any hit kills
- Hand-record human demos via mgba

## Day 6: All-Approaches Iteration

User asked to try **all** approaches in parallel: long PPO, DAgger, cheat-ROM, combined datasets.

### Approaches tested

| Approach | Outcome |
|----------|---------|
| **Long PPO (3000 epochs)** from BC checkpoint | Best deterministic: 89.63 ret, 1/50 sample kills (2%) |
| **DAgger** (3 iters, beta 0.5→0.0) | Aggregated 39K pairs, BC acc 72.6%; det worse (21.84) but 1/10 sample kills |
| **Cheat-ROM v1** (DCBB init=0x10) | Phase resets compensated; only 11 kills in 18 min; transfer failed |
| **Cheat-ROM v2** (no phase reset + low init) | 12 kills in ~30 min; transfer to real ROM lost (24.75 ret) |
| **Combined dataset** (v9.6 + cheat2) | val acc 72%, but transfer hurt (20.5 ret) |

### Final eval (50 episodes, gargoyle save state)

```
Random:     ret=31.02  kills=0/50   dies @ step 1320
BC+PPO det: ret=89.63  kills=0/50   survives full 1500 steps
BC+PPO smp: ret=62.39  kills=1/50   (2% kill rate)
```

### Diagnosis: kill-frame rarity

In 27000-frame v9.6 expert dataset, only **35 kill events** = ~0.13% of training frames are "the moment of kill." BC and PPO learn to imitate the *survival* behavior (95%+ of frames) but the precise kill-trigger sequence is rare enough that the policy can't reliably reproduce it.

Sample policy beats deterministic on kill rate because stochasticity occasionally explores the right action sequence; deterministic locks into a single action chain that approaches but never crosses the kill threshold.

### What would work but wasn't tried

1. **Kill-frame oversampling**: weight BC loss to over-emphasize the 100 frames preceding each kill event. Would need to reprocess JSONL with kill-time annotations.
2. **Mixed expert+policy at inference time** (DAgger-at-test): use expert action when DCBB hasn't dropped in N frames.
3. **Bigger network**: current PolicyValueNet is 256-hidden 3-layer; 512×4 might capture finer patterns.
4. **RNN/LSTM**: the kill is a multi-frame pattern; recurrent state could help.

## Day 5+ Final: First Mini-Boss Kill

**🎉 BC+PPO with OAM-extended state vector killed a mini-boss.**

| Policy | Mean Return | Mean Mini-boss Kills | Notes |
|--------|-------------|----------------------|-------|
| Random | 31.86 | 0 | dies at step 1373 |
| BC+PPO (no OAM, v11.0 demos) | 84.25 (det) | 0 | survives but doesn't kill |
| BC+PPO (no OAM, v9.6 demos) | 56.98 (det) | 0 | worse — OOD action chains |
| BC+PPO (OAM, v9.6 demos) sample | 52.49 | **0.2** | **1 kill in 5 eps** |
| BC+PPO (OAM, v9.6 demos) det | 38.83 | 0 | deterministic gets stuck |

The kill: episode 2, step 1354, agent killed mini-boss then died (scene=0x17 cinematic).

### What changed

1. State vector: 59 → 71 dims, adding 12 OAM-derived features (Sara position, boss centroid, nearest enemy, projectile count, signed boss-relative offsets, has_boss flag)
2. Expert demos: 26966 frames from v9.6 autoplay (35 expert kills, Gargoyle + Spider cycle)
3. BC val accuracy: 33% → 64% → 77% across iterations
4. Sample policy gets the kill; deterministic doesn't (entropy > 0 needed for exploration)

### Why deterministic still fails

After BC overfitting to specific (state, action) pairs, det policy picks the same action in OOD states from the save state. Only sample policy (with stochasticity) explores enough to reach the kill condition. This is classic BC compounding-error.

## Day 5+ Update: v9.6 expert recording

**v11.0 autoplay (originally used) was a regression — got 0 kills in 30 min.**
**v9.6 autoplay (`tmp/autoplay_level1.lua`, 1085 lines) kills mini-bosses fluidly:**

In a 30-min recording session with v9.6:
- **35 mini-boss kills** (Gargoyle + Spider on cycle, ROM-patched entry 2)
- 26294 state-action pairs recorded
- BC val accuracy: **64%** (vs 33% on v11.0 demos)

But BC + BC+PPO eval still got **0 mini-boss kills** at inference time. Why?

**Root cause: state vector is incomplete.** The autoplay's expert decisions condition on:
- `saraX, saraY` — Sara's screen position (averaged from OAM sprite slots 0-3)
- `bossSprites` centroid — OAM-derived boss position
- `nearX, nearY, nearDist` — nearest enemy sprite

Our PentaEnv state vector has only WRAM bytes (entity slots DC85+, scene flags). The OAM-derived screen-space positions the expert actually needs aren't in the observation. The BC model is trying to learn "press UP+A in this WRAM state" from a signal that doesn't include the screen position the expert was actually reacting to.

This is also why the v9.6 BC policy got LOWER returns than random (20.51 vs 31.86) — it confidently picks suboptimal actions because its state vector hides the relevant info.

**Confirmation: spinning + spamming A "should" kill Gargoyle.** A trivial bot would work — what's blocking the RL agent is the state representation, not the combat mechanics or the demonstrations.

## Recommended Next Steps

### IMMEDIATE: Extend state vector with OAM-derived sprite positions

Add to `state.py`:
- Sara screen position (average of OAM slots 0-3 X/Y, normalized to [0,1])
- Per-enemy slot screen position (OAM 4-39, take 8 bytes from each, encode tile+Y+X)
- Distance to nearest enemy
- Boss centroid (average position of sprites with tile in 0x30-0x7F range)

This brings the state vector from 59 → ~120 dims and gives BC the same info the expert had. Then re-train BC+PPO. Expected: BC alone should approach expert kill rate (~60% of episodes within 1500 steps).

### Other improvements

1. **Cheat-based kill recording**: still useful for accelerated learning

1. **Cheat-based kill recording**: Patch ROM at 0x4101 (DCBB init) to 0x10 instead of 0xFF. Record autoplay against this — every encounter dies in 1 hit, dataset has thousands of "DCBB→0" trajectories. Then train BC on those, fine-tune PPO without the cheat. The policy learns "approach + fire" without needing to learn "fire 16 times."

2. **Self-play from BC checkpoint**: Use BC+PPO as initial policy for autoplay's combat phase. The policy decides movement, autoplay handles cheats. Self-improving loop.

3. **Action-space expansion**: Add `[A+L, A+R, B+U, B+D, NOOP]` actions. Currently many useful directional+attack combos collapse to single A button.

4. **Domain expert reward shaping**: The current reward function is generic. Adding specific bonuses like "projectile sprite within 16 pixels of boss centroid" would densify the signal.

5. **Imitation learning with successful kills**: Use the v9.5 autoplay (which memory says killed all 16 bosses) or hand-craft kill demos with state writes.

## 2026-05-06 — CRITICAL BUG: kill detection broken since v3 reward redesign

**Symptom**: 7 consecutive iterations (v6-v12c) reported 0 kills despite varied configs and even cheat-ROM training.

**Root cause** (found via diagnostic in `rl/diagnose_kill.py`, `rl/diagnose_ffbf.py`):

1. `reward.py` kill detection condition was:
   ```python
   if prev.section in (2, 5) and state.section != prev.section and prev.miniboss != 0:
   ```
   But the game flow is: **FFBF clears ~6 frames BEFORE DCB8 advances**. So at the section-advance frame, `prev.miniboss == 0` already, and the condition never fires.

2. The "cheat ROM" (`A-fix-cheat-noPhase.gb`) didn't make bosses die in 1 hit — DCBB is *primarily* a level/corridor death timer, only secondarily boss-HP-during-fight. Init=0x10 caused Sara to die from level-timeout cinematic in ~150 frames every episode. Cheat ROM was actively HARMFUL.

**Fix**: Use the canonical signal from `scripts/probes/autoplay_record.lua` — `prev.miniboss != 0 and state.miniboss == 0` (FFBF transition non-zero → zero). One-line change in `reward.py`.

**Re-eval of v12c policy with fixed reward** (real ROM, gargoyle.state, max 10000 steps, 30 eps):
- sample mode: **30/30 kill_eps (100%), mean_ret=96.67**
- det mode: **30/30 kill_eps (100%), ret=51.70 (deterministic, 746 steps to kill)**
- random baseline (seed 42): **30/30 kill_eps (100%), mean_ret=80.02**

The "100% kill rate" is CALIBRATED by random — gargoyle.state is easy enough that any policy with reasonable entropy kills the first boss. The honest signal is **multi-kill** (gargoyle THEN spider in same episode), which prior work never tracked.

**Implications**:
- v6-v12c training metrics are unreliable (kill detection broken throughout)
- Policy quality cannot be assessed from training-time kill counts
- Frontier metric: multi-kill rate (eval pending with longer episodes)

## 2026-05-06 v13 — REGRESSION (resume from v12c, max_steps=12000)

| ckpt | mode | single-kill | multi-kill | mean ret |
|---|---|---|---|---|
| v13 | sample | 20/20 | **0/20** ↓ from v12c 2/20 | 82.08 |
| v13 | det | **0/20** ↓ from v12c 30/30 | 0/20 | 1.43 |
| random | — | 20/20 | 0/20 | 81.73 |

**Diagnosis**: v13 entropy stayed at 2.3 (near-uniform random). The deterministic policy collapsed because logits were too flat — argmax picks an arbitrary single action. Sample policy's multi-kill regressed because the longer episodes (12000 vs 3000) flooded gradient with post-kill exploration noise, diluting combat signal.

**Second bug found**: `vec_env.py` worker overwrote `info` after `env.reset()` on episode end, losing the kill count from the killed-boss episode. Training metrics showed `cum_kills=0` even when reward correctly fired. Fixed (commit pending).

## v14 — fresh + short eps + entropy=0.02 → REGRESSION

| ckpt | mode | single-kill | multi-kill | mean ret |
|---|---|---|---|---|
| v14 | sample | 20/20 | 0/20 | 70.09 (worse than random!) |
| v14 | det | **0/20** | 0/20 | 37.08 |
| random | — | 20/20 | 0/20 | 81.34 |

Training trajectory: peaked at ep 212 (mean_ret=102.7, max_ret=176, entropy=2.4). Then drifted DOWN to mean_ret=67 at ep 500 (entropy=1.9). Recovered to 88 by ep 2000. **Pure PPO with random init oscillates and never crystallizes a multi-kill strategy.**

Det collapse same as v13: high entropy (2.0-2.4) → flat logits → argmax picks arbitrary action. Sample mode now WORSE than random — policy is biased away from kill.

## v15 (running) — RESUME v14, max_steps=8000, entropy=0.005

Hypothesis: v14 has gargoyle expertise; longer eps + much lower entropy_coef will preserve gargoyle policy AND let multi-kill emerge.

## v17 → KILLED (reward hack discovered)

v17 (BC + PPO with low entropy) found a reward exploit:
- Stay in mini-boss fight forever (FFBF != 0)
- Spam fire button (action 0)
- Get +0.05 per A-press × 8000 steps = **+400** vs +50 for actual kill
- v17 mean_ret climbed to 228, max 422, with cum_kills only 10 in 528 eps

Confirmed via `peek_v17.py`: episodes lasted 8000 steps without dying, with no kills,
just `phase_2/3/4` damage milestones + room exploration. The fire_in_combat reward
turned PPO into a reward hacker.

v15 (running parallel, fresh PPO from v14) didn't find this exploit because it
inherited gargoyle-killer behavior from v14 — but v15 was also stuck at 87% kill rate
single-only (no multi-kill emerging).

## Reward v4 — fix exploits

Removed per-frame rewards that PPO can farm:
- `fire_in_combat`: 0.05 → **0** (the exploit signal)
- `b_button`: 0.02 → **0**
- `dragon_active_step`: 0.005 → **0**

Increased event-based kill rewards to dominate:
- `boss_kill`: 50 → **100**
- `boss_kill_chain`: 75 → **200** (multi-kill should be the biggest reward!)
- `boss_phase_2/3/4`: 5/10/15 → **10/20/40**
- `boss_damage`: 2.0 → **0.5** (DCBB delta is noisy from level timer dual purpose)

Random baseline with reward v4: 30/30 single kills, mean_ret=150 (was 80).
Expected max ret for multi-kill: 100 (kill1) + 200 (chain) + 70 (phases) + ... ≈ 400+.
Stage boss kill: +200. Stage boss splash: +5. Final boss: +1000.

## v18 (running) — BC + PPO with reward v4

- BC pretrained init (kept from v17 attempt)
- Real ROM, gargoyle.state, max_steps=8000, entropy=0.005, pi_lr=1e-4
- 1500 epochs

## Artifacts

- `rl/bc_data/expert_trajectories.jsonl` — 27000 expert (state, action) pairs (gitignored)
- `rl/bc_pretrained.pt` — BC checkpoint (gitignored)
- `rl/ppo_bc_ppo_final.pt` — BC+PPO checkpoint (gitignored)
- `scripts/probes/autoplay_record.lua` — Recording script (committed)
- `rl/penta_rl/bc_data.py`, `bc_train.py`, `bc_eval.py`, `train_bc_ppo.py` — pipeline (committed)
- `rl/RESULTS.md` — this document
