# Runtime Probe Findings (April 2026)

Empirical results from headless mgba probes that overturn or refine several earlier static-analysis claims.

## Probe Setup

- ROM: `Penta Dragon (J) [A-fix].gb`
- Tooling: mgba-qt headless (`QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy xvfb-run`)
- Lua scripts: `tmp/probes/runtime_probe.lua` + `runtime_probe2.lua`
- Game state: A-fix ROM boots straight into D880=0x02 (gameplay state) on this build, allowing read-only probes from frame 1

## 1. D880 NEVER cycles 0x02-0x09 (CRITICAL CORRECTION)

Static search of all `LD A,n; LD ($D880),A` (0x3E n EA 80 D8) sites:

```
D880 = 0x01  at file 0x0039CE
D880 = 0x1B  at file 0x003A9C
D880 = 0x15  at file 0x003B4B
D880 = 0x1C  at file 0x003BA3
D880 = 0x17  at file 0x004A4C
D880 = 0x0B  at file 0x004F6F
D880 = 0x0A  at file 0x004F77
D880 = 0x19  at file 0x0054C1
D880 = 0x1A  at file 0x005514
D880 = 0x16  at file 0x005530
D880 = 0x18  at file 0x0075B6
D880 = 0x0C-0x14  at file 0x00886E-0x008C46  (boss arenas)
```

**No D880 writer for values 0x02-0x09 exists in the ROM.** Also no `LD HL,$D880` (no INC/DEC HL-based mutation). D880 read sites: only 2 (bank3:0xC029 dispatch + bank3:0xC179 change-detect).

**Implication**: the "data-driven 3-substate structure for state 0x08" decoded earlier from the jump table at bank3:0x4A5A is NEVER REACHED during gameplay. Either:
- States 0x02-0x09 are dead/unreachable code from an earlier game design
- A different mechanism (not D880) routes execution through them
- The "jump table" interpretation was wrong (might be data with coincidental structure)

The only D880 values observed live in our probes: **0x02 (gameplay), 0x0A (mini-boss)**.

## 2. FFBF → D880 Transition Confirmed

Verified: writing `FFBF=1` causes D880 to transition `0x02 → 0x0A` within 2 frames. Matches the disassembly at 0x4F63-0x4F77:
- if FFBF == 0: D880 = (FFB7) (normal scene)
- if FFBF != 0: D880 = 0x0A (mini-boss fight)

Also confirmed: `FFBF=16` (boss 16) is treated identically — D880 → 0x0A. No FFBF range check at this dispatch.

## 3. FFAC/FFAD is NOT Per-Level

Static read with FFBA cycling 0-8 (writing FFBA without re-init):
```
FFBA= 0  FFAC=0x00  FFAD=0x40   →  pointer = $4000
FFBA= 1  FFAC=0x00  FFAD=0x40
... (constant for all FFBA)
```

**FFAD:FFAC = $4000** at game start. Likely a generic "current-bank-base" data pointer, NOT a per-level spawn-table pointer as previously hypothesized. Writing FFBA alone doesn't trigger re-init; need to actually transition through the level-load sequence.

## 4. Powerup HRAM Expiration Timer NOT at FFFC

After writing `FFC0 = 2` (shield), HRAM diff over 30 frames:

| Address | Before | After | Delta |
|---------|--------|-------|-------|
| FFC0 | 0x00 | 0x02 | +2 (we wrote it) |
| FFCB | 0x01 | 0x00 | -1 |
| FFCC | 0x01 | 0x00 | -1 |
| FFCD | 0x01 | 0x00 | -1 |
| FFD1 | 0x5C | 0x4A | -18 |
| FFD4 | 0x09 | 0x26 | +29 |
| FFD5 | 0x1B | 0x38 | +29 |

**FFFC did NOT change.** Earlier "powerup timer at HRAM 0xFC" claim was wrong.

FFCB/FFCC/FFCD going 1→0 once is suspicious (could be powerup-related state flags), but neither monotonically decrements over a longer 120-frame watch. **No clean periodic countdown timer was found.** Most likely: **powerups have no auto-expiration**; they persist until overwritten by next pickup or explicit clear at 0x7AC9.

## 5. Sound Stream D894 IS the Note Duration Counter

Wrote `D887 = 5` (sound command), watched D894-D899 over 60 frames:

| Frame | D887 | D894 | D895 | D896 | D897 | D898 | D899 |
|-------|------|------|------|------|------|------|------|
| 0 | 05 | 00 | 0F | 4A | 00 | ED | 47 |
| 1 | 00 | 0B | 07 | 48 | 00 | ED | 47 |
| 2 | 00 | 0A | 07 | 48 | 00 | ED | 47 |
| ... | 00 | (counts down 0B→00) |  |  |  |  |  |
| 9+ | 00 | 00 | 07 | 48 | 00 | ED | 47 |

- **D887** = command mailbox (sound engine consumed `5` immediately, cleared to 0)
- **D894** = note-duration counter (loaded with 0x0B, decrements once per frame, halts at 0)
- **D895** = current note pitch / channel state
- **D896** = pointer offset into sound stream (changed 0x4A → 0x48 = stream advanced)
- **D898/D899** = stable channel state (envelope?)

**Confirms**: sound streams use D894 as note-length timer. When D894=0, next stream byte is consumed.

## 6. Boss 16 Spawn Probe Inconclusive

Patched ROM 0x3402F to 0x7B (boss 16 spawn-id), forced DCB8=2 + DCBA=1 + FFD6=0x1E. **Result**: no spawn — DC04 stayed at 0x04 (already-spawned entity), FFBF stayed at 0. Section advance didn't re-read the patched spawn table.

Direct test: `FFBF=16, DC04=0x7B` writes succeeded; D880 transitioned to 0x0A normally. **State machine accepts boss 16**.

The actual unkillability still likely lies in the entity AI table at 0x2C8F (entry 16 has `00` bytes that may be no-op entity types) — but this needs runtime verification with a proper boss-16 spawn (requires forcing a fresh section transition, not just patching mid-section).

## Summary of Updates Needed in Architecture Doc

1. **Section 7.7 (D880 state machine)**: Note that values 0x02-0x09 are not directly written; the in-game observed values are 0x02, 0x0A, 0x0B-0x14, 0x15-0x1C only.
2. **Section 12.5 (FFAC/FFAD)**: Constant $4000 at game start; not per-level. Need separate probe for after-level-transition.
3. **Section 12.19 (Powerup state machine)**: Remove HRAM 0xFC timer claim; powerups likely don't auto-expire.
4. **Sound section**: D894 = note duration counter (verified empirically).

## Tooling Created

- `tmp/probes/runtime_probe.lua` — probes 1: initial state, FFBA cycle, entity slots, shield write, sound, DDA8 watch
- `tmp/probes/runtime_probe2.lua` — probes 2: HRAM diff, FFBF=1 force, boss-16 spawn, FFBF=16 direct, full HRAM watch
- `tmp/probes/results.json` + `results2.json` — JSON outputs
