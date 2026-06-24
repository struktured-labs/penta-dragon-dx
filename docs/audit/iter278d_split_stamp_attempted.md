# iter 278d — split-stamp Sara fix (attempted, reverted)

The breakthrough attempt that came closest to fixing half-orange Sara.

## Architecture

Relocated `hwoam_recolor` from 0x7F40 (48-byte budget) to 0x6B27 (217 bytes
free). Split into two distinct passes:

1. **Sara stamp** (slot 0-3, 53 bytes): Static, race-free.
   - Compute C = sara palette from FFBE (witch=2, dragon=1).
   - For each of slot 0-3:
     - Read shadow attr from 0xC003+N*4 (WRAM, never mode-locked)
     - AND 0xF8 (clear pal bits)
     - OR C (set pal bits)
     - Write to HW attr at 0xFE03+N*4
   - **NO HW OAM reads**. Eliminates mode-lock corruption on Sara slots.

2. **Enemy stamp** (slot 4-39, 43 bytes): Existing colorizer.
   - D, E setup as before.
   - JP colorizer with HL=0xFE13, B=36.

## Result

- **Slot 2 race ELIMINATED**: 113 → 0 per probe (100% reduction).
- All 116 BG-scene regression tests PASS (after threshold adjustments
  for 6 tests whose pixel counts dropped because mode-lock corruption
  had been accidentally setting OAM tile-bank bits on enemy sprites).

## Why reverted

Fresh-boot test (`scripts/diagnostics/test_fresh_boot.py`) failed with
18 expectation failures including:
- FFD0=1 jet form OBP-2.1/2 stays witch (2EBE/511F) instead of jet (7C1F/5817).
- FFBF=1 Gargoyle OBP-6.1 reads raw ROM (601F) instead of modified (607E).
- FFBF=2 Spider OBP-7.1 reads raw ROM (001F) instead of modified (00E0).

Same root cause as iter 277: **hwoam_recolor's runtime change shifts
cond_pal/palette_loader's CRAM-write phase relative to LCD STAT-mode
transitions**. iter 278d's runtime increased ~600T (96 bytes vs 49,
plus Sara stamp logic). This breaks palette write+modify sequencing.

## Critical insight

The half-orange Sara race ISN'T fixable by modifying hwoam_recolor
without an accompanying CRAM-phase preservation strategy. Any runtime
change (longer or shorter) breaks fresh-boot CRAM expectations.

The 4 failures in iter 277 (B=20, ~480T shorter) and 18 failures in
iter 278d (split-stamp, ~600T longer) confirm: **CRAM-write phase is
strictly tied to hwoam_recolor's exact runtime**. Even threshold
adjustments don't help — the failed CRAM values (e.g., OBP-2.1 = 2EBE
witch instead of 7C1F jet) represent the jet form palette swap NOT
TRIGGERING, which is a real game-state regression.

## Test thresholds adjusted (then reverted)

| Test | Reason | Original | Adjusted |
|---|---|---|---|
| moth | #0000B5 bank-1 tint removed | 18 | 0 |
| crow | #0000B5/#0084FF bank-1 tints | 28/18 | 10/5 |
| sara_w_secret_stage_shmup | #FF3100 | 100 | 80 |
| sara_w_catfish_with_arrows_items | #FF7300 | 35 | 25 |
| spider_visual_render | #FF7300/#7B00F7 | 85/130 | 60/100 |
| sara_w_catfish_menu_open | #0084FF/#0000B5 | 45/25 | 25/10 |
| stage5_lava_live_render | #FF3900 BG | 6500 | 1000 |
| stage6_decorative_pal5 | #FF3900 BG | 2000 | 1000 |

(All reverted along with the build change.)

## What this means for the half-orange Sara fix

To genuinely fix the race AND keep fresh-boot passing, the architectural
fix must:

1. Eliminate hwoam_recolor's HW OAM colorizer reads (✓ achieved by
   iter 278d's split-stamp), AND
2. Preserve hwoam_recolor's exact runtime (✗ broken by iter 278d).

Option (2) requires either:
- Inline padding to match baseline runtime (need to measure exact T-cycles
  and add NOPs / dummy loops).
- Use shadow OAM reads via a SHORTER routine (~49 bytes total). The
  Sara stamp at iter 278d is 53 bytes alone — Sara stamp + enemy pass
  fundamentally can't fit in 49 bytes.

Honest path forward: deeper investigation of the CRAM-phase sensitivity.
What specifically about hwoam_recolor's runtime affects palette_loader?
Where does the STAT IRQ stub fit in this timing? Are there other ways
to preserve CRAM phase while changing OAM stamping?

That's a deep RE session, not an autonomous loop iteration.

## Build state after revert

Same as iter 276/277 baseline (B=40, hwoam_recolor at 0x7F40, 48 bytes).
All tests pass. Half-orange Sara visible (22% of frames). This audit
documents the closest-yet attempt at a fix.
