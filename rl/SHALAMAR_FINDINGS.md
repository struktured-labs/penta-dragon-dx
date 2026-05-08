# Shalamar Arena Combat — Investigation Findings

## Summary

Captured all 8 stage boss arena save states. Trained PPO for 100+ epochs from Shalamar arena. **0 successful kills (FFBA advance).** Boss takes damage but never dies via natural agent play.

## Key Memory Discoveries

### DCBB is multi-purpose
- **In corridor:** corridor death timer (decrements over time and from boss attacks).
- **In stage arena:** appears to function as **player damage timer** primarily (NOT boss HP).
- Idle in arena (no input, no godmode): DCBB drops 0xFF → 0x07 in 1500 frames.
- Player attacks accelerate DCBB drop (~1 per attack frame).
- DCBB hit 0 → triggers death cinematic 0x4A44 → D880=0x17 → game over.

### Boss HP location: UNKNOWN
- Wide scan of WRAM 0xC000-0xDFFF for monotonic decreases during 5000 frames B-spam: only DCBB.
- No separate boss HP found in standard memory ranges.
- Possible the boss has HP encoded elsewhere (HRAM, OAM attribute byte, or behind banks).

### Phase reset mechanism
- When DCBB drops below threshold (~0x20), brief D880=0x0B transition (boss death intermediate).
- Game reverts D880=0x0D and DCBB=0xFF — boss "rebirths" with full HP.
- Pattern repeats every ~1200 frames during sustained spam_a.
- After 3-4 phase resets, agent stops damaging boss (boss may move out of attack range).

### Aggressive godmode test
- Pumped DCBB to 0xFF every tick + random inputs for 30000 frames.
- D880 stayed at 0x0D, FFBA stayed at 1.
- **Player can survive forever, but boss never dies via random play.**

## ROM-Level Findings

### Arena setup routines (ROM 0x886E-0x8C46)
9 routines, one per FFBA value 0-8. Each writes:
1. `LD A, arena_value (0x0C-0x14); LD [D880], A; LDH [FFB7], A`
2. `LD HL, boss_x; LD [DD85/86], A`
3. `LD HL, boss_y; LD [DD87/88], A`
4. `CALL 0x063E` — common arena init (palette, sprites)

### FFBA increment dispatcher (ROM 0x01A87)
- Reads FFBA, compares with 6 (`F0 BA FE 06`)
- If FFBA < 6: JR C +0x16 → INC FFBA (`3C E0 BA`)
- If FFBA == 6: JP Z 0x54C0 (game complete?)
- If FFBA > 6: SET FFBA = 5, then continue
- **No direct CALLers found** — reached via computed jump or fallthrough.

### D880=0x18 (boss splash) writes at ROM 0x075B6, 0x075E2
- Both routines: clear LCDC bit 3, reset scroll, CALL 0x4B52, then set D880=0x18
- Reached via what I believe is the post-boss-death sequence
- **No direct callers found**

### What naturally advances FFBA?
- Probed gameplay_start with 60k frames of random play + light_godmode: **FFBA never advanced from 0**.
- Sara stuck on event 0x28 (padding) at FFD3=0x18.
- Without specific trigger condition, FFBA stays put.

## RL Training Results (v6)

### Setup
- ShalamarArenaEnv loaded into Shalamar arena (FFBA=1, D880=0x0D)
- Godmode: pumps player HP, FFE6 invuln, but allows DCBB to drop in arena
- Reward: -0.005 step penalty, +0.2 per DCBB drop in arena, +500 success bonus on FFBA advance
- Pure numpy MLP forward pass (avoids torch+PyBoy deadlock)
- Chunked training (2 epochs/chunk, 60s timeout) — handles intermittent hangs

### Outcomes
- Trained 103+ epochs (~206 episodes total).
- Mean returns plateau ~50-65, max ~95.
- Deterministic eval: 0/10 kills. min_DCBB ~0x01-0x20.
- Action distribution: 94% A button, 5.6% Up+A.
- Policy converged to "spam A button from initial position".

## User Hints

1. **"Stage bosses have very specific spots or moments they can be damaged"** — RL needs to discover positional/timing patterns.
2. **"Beating Angela gives max stars and max dragon items"** — Angela is hidden boss in SHMUP-style stages; significant reward.
3. **"Walk through the right door with no mini bosses live"** — natural arena entry via specific door (location undisclosed).

## What's Missing

1. **Door discovery for natural arena entry.** User will demonstrate.
2. **Boss kill mechanism.** May require user demo to identify the specific damage windows / patterns.
3. **Hidden stages' SHMUP gameplay** — different mechanics than action stages.

## Test Strategies Tried (none triggered FFBA advance)

| Strategy | Frames | Min DCBB | Final D880 | Result |
|----------|--------|----------|------------|--------|
| Random | 5000 | 0xFF (no damage) | 0x2A (left arena) | Sara walked out |
| spam_A | 5000 | 0x09 | 0x2 (left arena) | DCBB phase reset before kill |
| spam_B | 15000 | various | 0x01 (game over) | Player died via DCBB=0 |
| movement_A | 5000 | 0x00 | 0x17 (death cin) | DCBB hit 0, no advance |
| spam_combos | 5000 | 0x03 | 0x02 | Almost killed boss |
| Force DCBB=0 | direct | 0x00 | 0x0D (arena) | Game ignored, kept arena |
| Force D880=0x18 | direct | n/a | reverts to 0xD | Game forces back to arena |
| Force FFBA=2 | direct | n/a | 0x01 (title) | Game went to title screen |
| spam_B + A on cinematic | 15000 | 0x00 → 0xff cycle | 0x01 (title) | Player died |
| Aggressive godmode + random | 30000 | n/a (pumped 0xff) | 0x0D | Boss never died |

## Conclusion

Without user demonstration of the actual boss kill pattern, RL training plateaus at the "damage but don't kill" local optimum. The boss has a specific kill condition (positional/timing-sensitive damage windows per user) that random/PPO exploration hasn't discovered in 100+ epochs.
