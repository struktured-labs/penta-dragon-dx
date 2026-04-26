# Penta Dragon RL

LLM-coached PPO for Penta Dragon DX (Game Boy), via PyBoy.

## Quick Start

```bash
cd rl
uv venv .venv && source .venv/bin/activate
uv pip install -e .
# Generate save states for combat training
python -m penta_rl.savestate
# Train (single env, fast)
python -m penta_rl.train_simple 50 1024 4 simple
# Eval
python -m penta_rl.eval ppo_simple_final.pt 5
# Combat-focused (loads gargoyle save state, every episode = combat)
python -m penta_rl.train_combat 200 512 4 combat
```

## Architecture

### Observation Space (59-dim float32)

| Group | Dims | Source | Normalization |
|-------|------|--------|---------------|
| Scene one-hot | 4 | D880 ∈ {0x02, 0x0A, 0x17, 0x18} | binary |
| Scalars | 6 | level, room, form, powerup, gameplay, miniboss | / max |
| Combat | 3 | boss_hp, player_hp, section | / max |
| Scroll | 6 | spawn_ptr_lo/hi, scroll_pos, scy, scx, active_entity | /255 |
| Entity slots | 40 | DC85, DC8D, DC95, DC9D, DCA5 × 8 bytes each | /255 |

### Action Space (12 discrete)

| ID | Buttons |
|----|---------|
| 0 | A (fire projectile) |
| 1 | B |
| 2 | Select |
| 3 | Start |
| 4-7 | Right / Left / Up / Down |
| 8-11 | UP+A, DOWN+A, LEFT+B, RIGHT+B (combos) |

### Reward Function

Configurable in `penta_rl/reward.py`. Default emphasizes:
- **Boss kill**: +5 per unique (level, miniboss) pair killed
- **Unique room visit**: +2 per first-time (level, room) — anti-cheese
- **Section advance**: +1 per DCB8 increment
- **Section max reached**: +1 per new high-water mark
- **Boss damage**: +0.5 per 16-HP chunk
- **Player damage**: -0.3 per 256-unit
- **Death**: -5
- **Powerup pickup**: +1
- **Fire projectile**: +0.05 per A press
- **Step penalty**: -0.001

### PPO Hyperparameters

- 3-layer MLP, hidden=256
- gamma=0.99, lambda=0.95, clip=0.2
- lr=3e-4, train_iters=10
- entropy_coef=0.03 (combat: 0.05)
- batch=256

### Save States (`saves/`)

- `gameplay_start.state` — D880=0x02, just past title menu
- `gargoyle.state` — FFBF=1, gargoyle spawned, DCBB=0xFF
- (extensible to spider, crimson, ..., boss16)

Save states cut episode startup from 500 frames → 1 frame; combat training is ~10x faster than menu-nav-from-scratch.

### Curriculum (`penta_rl/curriculum.py`)

5 stages with auto-advancement on metric thresholds:
1. **survive** — pos step penalty, room/scroll rewards, no boss reward
2. **navigate** — bigger room/section rewards
3. **engage** — combat rewards activate
4. **combat** — heavy boss reward
5. **master** — full game

NOTE: stages don't currently propagate to vec_env workers (they keep initial RewardConfig). Fix: add control message channel for runtime reward updates.

### LLM Coach (`penta_rl/coach.py`)

Sends recent metrics + event samples to Claude API every N epochs, receives JSON guidance:
- `reward_cfg_delta` — runtime reward shaping
- `subgoal` — string description of next goal
- `diagnosis` — stuck-pattern analysis
- `action_bias` — multipliers per action_idx
- `patches` — ROM-byte patches to test hypotheses

Falls back to a heuristic coach if `ANTHROPIC_API_KEY` not set. The heuristic detects "no boss kills + low return" and boosts combat rewards.

## Empirical Results (Day 1-4 build)

### Single env (no save state)

```
ep 1/3:  reward=366
ep 2/3:  reward=392
ep 3/3:  reward=415
```

PPO learning works end-to-end.

### 4-env vec, 30 epochs, full curriculum

```
ep   1: stage=survive  ret=0     bosses=0
ep   5: stage=navigate ret=675   bosses=0  ← curriculum advanced
ep  10: stage=engage   ret=771   bosses=0  ← curriculum advanced
ep  30: stage=engage   ret=909   bosses=0  ← stuck at 0 kills
```

**Diagnostic eval**: action histogram showed agent learned a degenerate room-cycle policy (action 0 = A button used <1% of time, mostly LEFT+B and UP). Reward function was over-rewarding "any room change," so agent oscillated rooms 1↔3↔5↔7 instead of advancing sections.

### Fix: unique-room reward + fire-projectile bonus

Capped agent's room-cycle exploit. Mean return dropped to ~140 but exploration improved. Still 0 boss kills in 200 epochs of combat-focused training — this game is hard for sparse-reward PPO without expert demonstrations.

## Open Issues

1. **Curriculum stages don't propagate to workers** — stage transitions are tracked in main process but workers keep using the RewardConfig they were spawned with. Fix: add a control-message channel.
2. **Boss-kill reward sparsity** — even with save-state combat starts, reward signal is too sparse for PPO to bootstrap. Imitation learning from existing `autoplay_full_game.lua` (which kills 15/16 bosses heuristically) would be the right next step.
3. **PyBoy ROM patching** — `pb.gamerom` is just a filename string, not byte access. Workaround: pre-patch ROM file (see `rom/Penta Dragon (J) [A-fix-boss16-patched].gb`) and load that for boss-16 experiments.
4. **Stdout buffering when redirected** — must use `python3 -u` or `PYTHONUNBUFFERED=1` for live progress logs.

## Suggested Next Steps

### Imitation Learning Pre-Train

The existing `tmp/autoplay_full_game.lua` (1085 lines) kills 15/16 bosses via hand-coded heuristics. Recipe to use it:

1. Modify Lua to log `(state_addrs, action)` tuples to JSON every game step
2. Run autoplay once via `mgba-qt --script autoplay_full_game.lua` to record ~1M trajectories
3. Convert to numpy: `(N, 59)` obs + `(N,)` int actions
4. Behavioral cloning: minimize `-log P(action_expert | obs)` for K epochs
5. PPO fine-tune from BC-init weights → much faster convergence

### Boss-16 Specifically

Use `rom/Penta Dragon (J) [A-fix-boss16-patched].gb` (zero bytes in 0x2D7F entry replaced with 0x04). If RL agent kills boss 16 with patched ROM but NOT unpatched, that confirms the `[type, hitbox, anim]` 3-byte sub-record interpretation.

Prerequisite: agent must reliably kill non-patched bosses first — otherwise can't separate "training failure" from "patch ineffective."

### Real Hardware (MiSTer)

Per memory: MiSTer game input is broken (BLISS-BOX needed). Once that's fixed, the trained policy could drive a real cart. Until then, PyBoy-only training is fine for validating game mechanics hypotheses.

## Files

| File | Purpose |
|------|---------|
| `penta_rl/env.py` | Gymnasium env over PyBoy |
| `penta_rl/state.py` | State vector extraction |
| `penta_rl/reward.py` | Reward fn + tracker |
| `penta_rl/ppo.py` | PPO trainer |
| `penta_rl/vec_env.py` | Multiprocess vec env |
| `penta_rl/train.py` | Single-env trainer |
| `penta_rl/train_vec.py` | Parallel trainer |
| `penta_rl/train_simple.py` | Non-curriculum trainer (recommended for first runs) |
| `penta_rl/train_combat.py` | Save-state combat-focused trainer |
| `penta_rl/train_curriculum.py` | Full curriculum trainer (workers don't get stage updates yet) |
| `penta_rl/curriculum.py` | 5-stage curriculum schedule |
| `penta_rl/coach.py` | LLM coach (Claude API + heuristic fallback) |
| `penta_rl/eval.py` | Deterministic policy evaluation |
| `penta_rl/savestate.py` | Capture save states for instant respawn |
| `penta_rl/smoke.py` | Random-policy smoke test |
| `pyproject.toml` | uv deps |
| `saves/` | PyBoy state snapshots (ignored from git) |
