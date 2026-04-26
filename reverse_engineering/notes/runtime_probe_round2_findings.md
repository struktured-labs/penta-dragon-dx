# Runtime Probe Round 2 Findings (April 2026)

Deeper probes that close out several major mysteries.

## DEFINITIVE: Boss 16 IS Killable Via Direct DCBB Write

### Setup
- Patched ROM 0x3402F to 0x7B (boss 16 spawn-id) BEFORE boot
- Forced fresh section: DCB8=0, DCBA=0x01, FFD6=0x1E
- Once FFBF != 0 (boss spawn detected), wrote DCBB -= 0x10 every 5 frames

### Result Timeline (boss 16, FFBF=0x10, DC04=0x7B)
| Frame | DCBB | D880 | Event |
|-------|------|------|-------|
| 15 | 0xFF | 0x02 | SPAWNED — FFBF=0x10 |
| 15 | 0xEF | 0x02 | first damage write |
| 23 | 0xDF | **0x0A** | game transitioned to mini-boss state |
| 91 | 0x00 | 0x0A | DCBB hit 0 (after 16 damage ticks) |
| **535** | 0x00 | **0x17** | **DEATH CINEMATIC fired** |

### Comparison: Gargoyle (control) — same protocol
| Frame | DCBB | D880 | Event |
|-------|------|------|-------|
| 15 | 0xFF | 0x02 | SPAWNED — FFBF=0x01, DC04=0x30 |
| 23 | 0xDF | 0x0A | mini-boss state |
| 91 | 0x00 | 0x0A | DCBB hit 0 |
| **271** | 0x00 | **0x17** | death cinematic fired (faster than boss 16) |

### Conclusion

**Boss 16 is NOT inherently unkillable.** The death pipeline (`DCBB=0 → D880=0x17`) works for ANY value of FFBF, including 16.

The "boss 16 unkillable in normal combat" observation is specifically a **projectile-collision-detection failure**:

- Normal combat: player projectile hits boss sprite in OAM → collision detector calls 0x1004 → 0x1024 (`SUB B; LD (DCBB),A`)
- Boss 16: entity AI table entry at 0x2D7F (`04 00 03 03 00 ...`) likely fails to populate a valid hitbox in OAM/entity slots, so the collision never registers
- Bypassing collision (direct DCBB write) skips this issue and the boss dies normally

**Architectural implication**: the damage path is generic — there is NO boss-index validation in the death pipeline. Any code that drives DCBB to 0 triggers cinematic via 0x4A44.

### Suggested Fix (revised)

Two viable options to make boss 16 properly killable in normal play:
1. **Patch entity AI table entry 16** at file 0x2D7F to copy entry 15's pattern (this populates a valid hitbox)
2. **Clamp FFBF ≤ 15** at 0x0C18 (forces boss 16 to use boss 15's AI)

Both would route boss 16 through a working collision path.

## Boss 16 Entity Slot Population Confirmed

In probe 4, after boss 16 spawn:

| Frame | Slot 1 (DC85+) |
|-------|----------------|
| 10-150 | `00 02 FE E6 01 20 4A 0E` (inactive — byte 0 = 0x00) |
| 160 | `10 04 48 10 7F 01 0B 0E` (became active — byte 0 = 0x10!) |
| 170 | `10 03 50 10 7F 01 09 0E` (byte 2 advanced 0x48→0x50 — Y position?) |
| 180 | `10 03 5C 10 7F 01 06 0E` (byte 2 = 0x5C) |
| 190 | `10 03 64 10 7F 01 04 0E` (byte 2 = 0x64) |
| 200 | `10 00 68 10 7F 01 01 0E` |
| 210 | `10 05 68 1F 7F 02 0A 0E` (byte 3 jumped 0x10 → 0x1F — X moved) |
| 240 | `10 05 68 42 7F 02 03 0E` |

**Boss 16 IS rendered as a moving entity**. It walks around. But evidently its sprite/hitbox combination doesn't register in projectile collision.

### Entity Slot Byte Map (inferred from active boss 16)

| Offset | Inferred meaning | Evidence |
|--------|------------------|----------|
| 0 | Active flag | 0x00 = inactive, 0x10 = active |
| 1 | Animation frame counter | varies 0-9 cyclically |
| 2 | Y position (or Y delta) | monotonically advanced 0x48→0x68 |
| 3 | X position | jumped after entity reached destination |
| 4 | Some constant flag | 0x7F stable |
| 5 | Direction/speed | toggled 0x01/0x02 |
| 6 | Sub-counter | varies |
| 7 | Sprite/tile-base index | 0x0E stable per entity |

## D880 State Machine — Final Confirmed Behavior

### Live D880 values observed
**Only**: `0x00 (boot uninit), 0x02 (gameplay), 0x0A (mini-boss), 0x17 (death cinematic)`

### Direct write test
- Wrote D880=0xA1..0xAE for 30 frames; reads returned the written value
- **D880 is NOT continuously reset by the game** — writes persist
- Stage boss arena force (D880=0x0E etc) reverted on next frame because some game state immediately re-set it to 0x02 (likely the dispatch routine itself sees no valid scene config and defaults back)

### State 0x02-0x09 reachability
The "data-driven 3-substate structure for state 0x08" decoded earlier appears to be **dead code or jump-table noise**. None of states 0x02-0x09 (other than 0x02) are reached during normal gameplay. The jump table entries exist but are unreferenced by live D880 transitions.

### DDA8 substate counter — DOES NOT EXIST as theorized
DDA8 stayed at 0x00 throughout all probes including state 0x0A combat. **Not a substate counter.**

## D880 → D881 Mirror

`bank3:0xC02C: LD ($D881),A` after reading D880 confirms D881 = "previous D880" for change detection. The dispatch routine probably re-runs only when D880 != D881.

## Frame Counters and Timers Found

After writing FFC0=2 and watching HRAM 30 frames:
- **FFCB, FFCC, FFCD** all decremented 1→0 once (single-trigger flags, not periodic timers)
- **FFD1**: dropped 0x5C → 0x4A (-18 over 30 frames). Plausible frame-counter, not powerup-specific.
- **FFD4, FFD5**: incremented +29 each — cumulative game timer
- **FFFC**: unchanged (powerup timer hypothesis confirmed FALSE)

Conclusion: **No HRAM byte clearly serves as the powerup expiration timer.** Powerups likely persist until overwritten.

## Sound Stream D894 Decremental Timer

After D887=5:
- D894 loaded with 0x0B, decrements ~1 per frame to 0
- D896 advanced 0x4A → 0x48 (stream pointer moved)
- D898/D899 stable (envelope/channel state)

**D894 = note duration counter** — verified empirically.

## Summary Table — All Empirical Findings

| Claim | Status | Evidence |
|-------|--------|----------|
| Boss 16 unkillable | PARTIAL — only via collision; direct DCBB writes work | f=535 D880=0x17 |
| Boss 16 spawns properly | TRUE | FFBF=0x10, DC04=0x7B at f=15 |
| Boss 16 renders as moving entity | TRUE | slot 1 byte 2/3 advance over frames |
| D880 cycles 0x02-0x09 | FALSE | only 0x02, 0x0A, 0x17 observed |
| D880 = 3 substates for state 0x08 | FALSE | DDA8 stays 0; D880=0x08 never reached |
| FFAC/FFAD per-level | FALSE | constant $4000 |
| Powerup HRAM 0xFC timer | FALSE | unchanged after FFC0 write |
| FFBF=1 → D880=0x0A | TRUE | f=23 transition confirmed |
| FFBF=16 → D880=0x0A | TRUE | f=23 transition confirmed |
| DCBB=0 → D880=0x17 | TRUE | for both gargoyle and boss 16 |
| Sound D894 = note duration | TRUE | decremented 0x0B → 0 |

## Open Questions Still

- Exact contents of boss 16's entity AI table entry that breaks hitbox population (need to probe entry 0x2D7F vs entry 0x2D6F (gargoyle))
- Why D880=0x17 cinematic fires 180 frames later for gargoyle but 444 frames later for boss 16 (delay scales with boss-specific data?)
- The CGB boot palette mechanism (need BCPS/BCPD watchpoints during early frames)
- FFAC/FFAD values during ACTUAL level transitions (need to navigate level select)
