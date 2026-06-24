# iter 278 — candidate J at 0x6B27 (attempted, reverted)

## Summary

Relocated `hwoam_recolor` from 0x7F40 (48-byte budget) to 0x6B27
(217 bytes free) and implemented candidate J: mode-lock detection at
entry, adaptive HL/B (skip slot 0-3 when OAM read-locked, full 0-39
otherwise). Slot 2 race dropped **113 → 12 (89% reduction)** — better
than iter 277's B=20. But the colorizer's PER-ITER tile reads ALSO
hit mode-lock, causing slot 4+ to still race. spiral_power_active +
gargoyle_visual_render BREAK.

## Result

| Slot | Baseline B=40 | iter 277 B=20 | iter 278 candidate J |
|---|---|---|---|
| 0 | 31 | 30 | 12 |
| 1 | 4 | 14 | 0 |
| 2 | **113** | **23** | **12** |
| 3 | 6 | 16 | 6 |
| 22 | — | — | 6 |
| 23 | — | — | 10 |

Total: 315 (B=40) → 199 (B=20) → **46 (candidate J)** = 85% reduction.

## Why it fails the tests

The candidate J head detects mode-lock at hwoam_recolor ENTRY by
reading slot 0 tile. If 0xFF, OAM is locked → set HL=0xFE13, B=36
(skip slot 0-3). Then JP to colorizer.

**The colorizer ALSO reads HW OAM per-iter (40 slots, ~24T each).**
If OAM is mode-locked at hwoam_recolor entry, it stays locked for
hundreds of cycles (mode 2 = 80T, mode 3 = up to 289T). The colorizer's
slot 4 tile read at ~96T into the pass STILL returns 0xFF → pal_4
fallback → race on slot 4-39 too.

So candidate J fixes slot 0-3 race but slot 4+ continues to race when
mode-lock persists. Test impact:

| Test | Status | Reason |
|---|---|---|
| sara_w_alone | PASS | Sara's slot 0-3 race fixed by candidate J |
| spider_miniboss_sara_d | PASS | (likely transient passing) |
| orc, moth | PASS | Sara slots fixed |
| **spiral_power_active** | **FAIL** | Spiral projectile at slot 10+, racing to pal-4 |
| **gargoyle_visual_render** | **FAIL** | Gargoyle body at slot 4+, racing to pal-4 |
| **soldier** | **FAIL** | Soldier orange accents at slot 4+, racing |

## Mechanism (now better understood)

The fundamental problem: **OAM mode-lock during VBlank overrun
contaminates ALL colorizer reads**, not just slot 0. The colorizer at
0x6A10 reads each slot's tile from HW OAM (`DEC HL; LD A,[HL]; INC HL`).
When OAM is mode-locked (mode 2 or 3), every tile read returns 0xFF,
dispatching to the pal_4 fallback.

A hwoam_recolor entry-level mode-lock check (candidate J) can detect
the start of a mode-locked window but can't avoid the colorizer's
per-iter reads from hitting it.

## Possible genuine fixes

### Fix 2 — pal_0 fallback (ATTEMPTED, REVERTED)

Tried changing `bg_experiment.py:137` from `emit([0x3E, 0x04])`
(LD A, 4 → pal_4 fallback) to `emit([0x3E, 0x00])` (LD A, 0 →
pal_0 fallback). Result:

- Slot 2 race: 113 → 59 (~48% reduction, less than candidate J).
- **orc test FAIL**: #0000B5 dark-blue count 22 → 8 (orcs use
  legitimate tile-0x80+ → pal_4 → blue accent dispatch).
- **spiral_power_active FAIL**: #0000B5 count 44 → 0 (spiral
  projectiles also use tile-0x80+ → pal_4).

The game GENUINELY uses tile-0x80+ → pal_4 fallback for orc + spiral.
Changing to pal_0 breaks both. REVERTED.

### Other untried fixes

1. **Source tile reads from SHADOW OAM (0xC000+)** — never mode-locked,
   but requires colorizer rewrite to use TWO pointers (one for shadow
   source, one for HW dest). ~80-100 bytes of new code.

2. **Reduce other VBlank work** so hwoam_recolor reliably fits within
   mode 1. Save ~400T from BG sweep or DMA setup.

3. **Pre-cache tile data** from shadow OAM into HRAM at start of
   hwoam_recolor, then colorizer reads HRAM (always available).

All three are substantial changes requiring careful verification. Not
within the bounds of a single autonomous-loop iteration.

## What changed

Reverted. Build state same as iter 276/277 (B=40, hwoam_recolor at
0x7F40). Only deliverable is this audit + the iter 278 visual
validation audit ([iter278_visual_validation.md](iter278_visual_validation.md)).

## Status

- Probe-verified: candidate J reduces slot 2 race 89% (113→12).
- Test-verified: candidate J breaks 3 slot-4+ visual tests
  (spiral_power_active, gargoyle_visual_render, soldier).
- Documented: mode-lock affects ALL colorizer per-iter reads when it
  persists, not just slot 0.
- Next step (NOT taken in iter 278): Try fix #2 (replace pal_4 fallback
  with pal_0) — single-byte change, easy to test.
