# LLM-Assisted RL Game Exploration — Design Proposal

## Motivation

We've extracted ~92% of Penta Dragon's architecture via static analysis + 8 rounds of passive runtime probes. The remaining 8% requires **active gameplay agency** that can:

- Fire projectiles (verify boss-16 collision-fix patches)
- Navigate menus (test stage boss arena entry via legitimate path)
- Trigger level transitions (verify FFAC/FFAD updates)
- Score-attack (find optimal play patterns)
- Discover unintended interactions (RL exploration finds glitches static analysis misses)

We already have the **emulator agency primitives**:
- mgba Lua: `setKeys()` for input injection (verified working in title-menu auto-start)
- mgba Lua: state read/write for any WRAM/HRAM/OAM/ROM byte
- Headless mode for parallel rollouts
- 4 existing autoplay scripts (incl. `autoplay_full_game.lua` that already kills 15/16 bosses)

What we DON'T have is the **policy + LLM coaching layer** to convert random/scripted exploration into goal-directed learning.

## Proposed Architecture

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│  ┌──────────┐    actions    ┌──────────────┐        │
│  │  Policy  │──────────────▶│ mgba (×8     │        │
│  │  (PPO)   │               │  parallel)   │        │
│  │          │◀──────────────│  via Lua     │        │
│  └─────▲────┘   obs+reward  └──────┬───────┘        │
│        │                           │                │
│        │ updates                   │ state dumps    │
│        │                           ▼                │
│  ┌─────┴────┐                ┌──────────────┐       │
│  │ Trainer  │                │ State        │       │
│  │ (PPO     │                │ summarizer   │       │
│  │  loop)   │                │ → embedding  │       │
│  └─────▲────┘                └──────┬───────┘       │
│        │                            │                │
│        │ goals/rewards              │ summaries      │
│        │                            ▼                │
│  ┌─────┴───────────────────────────────────┐        │
│  │  LLM Coach (Claude API)                 │        │
│  │  - inspects rollouts every N episodes   │        │
│  │  - sets sub-goals (room transitions,    │        │
│  │    boss kills, item pickups)            │        │
│  │  - shapes reward function dynamically   │        │
│  │  - debugs stuck behaviors               │        │
│  └─────────────────────────────────────────┘        │
│                                                      │
└──────────────────────────────────────────────────────┘
```

## Component Detail

### 1. Emulator Wrapper (`drmario_rl/env.py` style)

Subclass gymnasium.Env wrapping headless mgba via subprocess + IPC. Each step:
- Action → write to a Lua-controlled WRAM byte that the keysRead callback reads
- Wait N frames (default 4, configurable for frame-skip)
- Read state vector from agreed WRAM/HRAM addresses
- Compute reward from delta

State vector (~100 dims):
- Player: position, HP, form, powerup
- Scroll/scene: SCX, SCY, FFBD (room), D880 (scene), FFCF (section)
- Entities: 5 slots × 8 bytes (DC85+) flattened
- OAM aggregate: enemy sprite count, projectile count
- Combat: FFBF, DCBB, FFD3 event index
- Meta: frame counter delta, score (FFFB?)

Action space (12 discrete):
- 8 buttons individually + 4 common combos (UP+A, DOWN+A, LEFT+B, RIGHT+B)

### 2. Reward Function (game-specific)

```python
def compute_reward(state_t, state_t1):
    r = 0
    # Progress
    if state_t1.unique_bosses_killed > state_t.unique_bosses_killed: r += 5
    if state_t1.room != state_t.room: r += 1
    if state_t1.section_advanced: r += 0.5
    # Combat
    if state_t1.boss_hp < state_t.boss_hp: r += 0.5
    # Survival
    if state_t1.player_hp < state_t.player_hp: r -= 0.3
    if state_t1.player_dead: r -= 5
    # Step penalty
    r -= 0.001
    # Powerup pickup
    if state_t1.powerup != state_t.powerup and state_t1.powerup != 0: r += 0.5
    return r
```

### 3. PPO Policy

Reuse `dr_mario_rl` PPO architecture (already proven on similar task). Key adaptations:
- Larger MLP (state vector ~100D, hidden 512×3)
- Recurrent (LSTM cell) for partial observability — game has hidden state in DC0B-DC0F that affects scrolling
- Frame-skip 4 default
- 8 parallel envs
- 1M frames for first viable policy

### 4. LLM Coach Loop

Every 100 episodes, dump:
- Recent trajectory summaries (state + action sequences)
- Reward breakdown
- Stuck patterns (e.g., agent dies in same room repeatedly)
- Current policy entropy

Send to Claude API with prompt like:
```
You are an RL coach for an agent playing Penta Dragon (Game Boy).
Recent stats: {boss_kills: 3/16, current_room: 4, deaths: 47, mean_episode_length: 312}
Stuck pattern: dies in room 4 within 50 frames most episodes.
Architecture context: room 4 has gargoyle miniboss (FFBF=1).
Suggest: (a) sub-goals for next 100 episodes, (b) reward shaping changes, (c) hypotheses for the stuck pattern
```

Claude returns structured suggestions:
- New sub-goals (curriculum learning)
- Reward shaping deltas
- Specific WRAM addresses to add to state vector
- Lua scripts to inject (e.g., temporarily disable mini-boss to learn room navigation first)

### 5. Curriculum

Phase 1: Survive 1000 frames (learn movement)
Phase 2: Reach room 2 (learn scroll handling)
Phase 3: Pick up first powerup
Phase 4: Kill gargoyle
Phase 5: Kill spider (mini-boss 2)
Phase 6: Reach level 2
... etc up to Phase 16: kill all bosses

## Specific Targets We Could Verify

1. **Boss 16 collision fix**: train agent to fire projectiles at boss 16. If patched AI table works, agent should reduce DCBB normally.
2. **Stage boss arena entry**: agent navigates through level 1 to natural FFBA=0 → arena setup. Capture which event-sequence values land it in D880=0x0C-0x14.
3. **Powerup expiration mechanism**: agent picks up shield, observes if it ever auto-expires.
4. **CGB palette workaround**: train agent to navigate menus without seeing them (tests if game logic works under all-white palette).
5. **Optimal route**: discover fastest route through all 8 levels.

## Effort Estimate

- Day 1: Env wrapper + reward fn + state vector design (~400 LOC Python)
- Day 2: PPO baseline running on 1 env, parallelize to 8 envs
- Day 3: First curriculum phase (survival) + LLM coach loop integration
- Day 4: Run overnight, iterate based on LLM feedback
- Day 5+: Full curriculum, target boss-16 verification

## Existing Assets to Leverage

| Asset | Use |
|-------|-----|
| `dr_mario_rl/src/drmario/ppo.py` | Drop-in PPO trainer |
| `tmp/autoplay_full_game.lua` | Reference for level switching, state observation |
| `scripts/probes/runtime_probe*.lua` | State observation patterns |
| `reverse_engineering/penta_dragon_architecture.md` | Knowledge of every WRAM/HRAM byte |
| Memory file (project_v290_milestone.md) | v290 build with clean audio = good RL substrate |
| MiSTerClaw MCP | If MiSTer game-input ever fixed, can run on real hardware |

## Why LLM Coaching Specifically

Pure PPO would learn but slowly (millions of frames per phase). LLM coaching accelerates by:
- Injecting domain knowledge (e.g., "FFBF must be 0 for game to advance section")
- Catching pathological patterns earlier (Claude reads transcript, sees agent stuck in death loop)
- Generating exploration bonuses for novel state regions
- Writing inline Lua patches to test hypotheses without waiting for policy to discover them

## What I'd Build First (Minimum Viable)

A 200-LOC `penta_explore.py` that:
1. Spawns 1 mgba subprocess with a Lua script
2. Implements a simple step loop (action → frames → state)
3. Random policy baseline (no learning)
4. Logs trajectories
5. After 100 episodes, sends summary to Claude API
6. Claude returns "next 100 episodes try X"
7. Apply X (could be reward shaping, action masking, or seed fixing)

Even with random policy + LLM coaching, this would verify the env works and start producing useful trajectories.

## Recommendation

**This is a multi-day project.** It's high-value (would close most of the remaining 8% of unknowns) but requires sustained focus. I'd suggest:

1. (Now) Commit the FFAC/FFAD correction
2. (Optional) Build the minimum viable explorer (200-LOC) and run 1 hour to validate plumbing
3. (Decision point) If results look good, scale to PPO + curriculum
4. (Major commit) Run overnight or for days, iterate based on LLM feedback

What's your appetite — minimum viable first, or commit to the full multi-day build?
