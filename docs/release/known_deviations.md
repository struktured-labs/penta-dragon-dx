# Known deviations from the original game (release notes source)

Operator-reviewed list of measured, accepted differences between Penta
Dragon DX and the original DMG game. Anything NOT listed here that differs
from the original is a defect, not a deviation.

## 1. Dungeon pace: ~6% slower (ACCEPTED 2026-08-17)

Measured by `gameplay_speed_parity` (input-identical boot, main-loop
throughput): Stage 1 ratio 0.943, Stage 5 0.939; Stage 7 direction-real but
magnitude confounded by route divergence (scroll 62/103). Mechanism is
distributed — colorize VBlank ISR ≈2% of frame, copier HBlank-wait
amplification ≈1%, remainder spread across per-frame services — with no
single lever (full accounting: `docs/speed_optimization_plan_v3.md`).
Operator decision: acceptable for 1.0; revisit only if players report it.

## 2. Boss arenas: at original speed or slightly faster (direction-only)

The arena loop (bank2:$406F) measures at-or-faster than the original on
five of nine bosses, crystal_dragon ~+3% slower, riff/penta ≈parity.
Magnitudes are direction-only: cross-ROM boss comparisons ride save-state
pairs whose arena phases differ, and DMG↔CGB states cannot be cross-loaded
(`docs/FINDINGS_2026_08_16_boss_speed_instrumentation.md`). No player-visible
pacing complaint is expected in either direction; not release-blocking.

## 3. Crystal Dragon: one wrap phase-seam cell

The portal's cached dual-tilemap colorization allows exactly one
entry-layout cell (row 4, col 15) to sit on either side of a native camera
wrap, depending on serialization order. The strict verifier permits one such
cell and rejects two or more (`boss_geometry_contract.py`). Invisible in
practice.

## 4. Native visual states the original hides in grayscale

Colorization makes some original-game intermediate states visible that DMG
grayscale masked (e.g., Ted's camera-wrap half-frame, fixed by atomic
dual-GDMA publication in the Ted rework; pose cells that are detached in the
native art, such as Ted pose 4's floating orbs, are preserved as-is).
Anything of this class that remains should be indistinguishable from the
original's own animation when compared side-by-side in grayscale.

## 5. Title screen footer

`DX V3.01 STRUK LABS` replaces the original copyright row — intentional
branding, custom 2bpp digits.

## Gate bookkeeping note

`boss_publication_cadence`'s per-boss slowdown percentages are event-rate
measurements on phase-mismatched pairs (see deviation 2). Until the gate is
re-scoped to direction-only or phase-matched pairs, its numeric slowdown
output must not be quoted as a speed claim; `gameplay_speed_parity` is the
speed authority. (Re-scope pending; the file is under active Ted-lane edit.)
