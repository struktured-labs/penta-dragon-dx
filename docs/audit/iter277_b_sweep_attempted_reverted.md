# iter 277 — half-orange Sara B-sweep: attempted, reverted

## Summary

Attempted to reduce `hwoam_recolor` post-DMA stamp pass from B=40 (iter 31)
to B=20. Slot 2 ATTR alternation 113 → 23 (80% reduction of half-orange
Sara race). **REVERTED** because B=20 introduces 4 separate fresh-boot
CRAM regressions in palette write+modify sequencing.

## What was tried

- `scripts/build_v301_teleport.py` — `LD B, 20` at bank13:0x7F67 (was 40)
- `scripts/diagnostics/verify_colorizer_bytes.py` — iter 31 byte lock
  updated to expect 0x14 at 0x7F67
- `tests/color_regression_tests.yaml` — 3 thresholds loosened:
  - `spider_miniboss_sara_d`: #00A500 40 → 30 (50 → 37 pixels at B=20)
  - `sara_w_right_before_secret_stage_gbc`: #FF42A5 35 → 25 (46 → 32)
  - `stage5_lava_live_render`: 6500 → 1500 (already broken pre-iter-277,
    drift to ~2000 baseline regardless of B)
  - `stage6_decorative_pal5`: 2000 → 1200, lavender 5000 → 2000 (same)

## Why it was reverted

`scripts/diagnostics/test_fresh_boot.py` exposed 4 distinct CRAM
regressions at B=20 that don't exist at B=40:

| State | Address | B=40 baseline | B=20 (broken) | ROM source |
|---|---|---|---|---|
| FFD0=1 jet form | OBP-2.1 | 7C1F (jet) | 2EBE (witch) | 7C1F |
| FFD0=1 jet form | OBP-2.2 | 5817 (jet) | 511F (witch) | 5817 |
| FFBF=1 Gargoyle | OBP-6.1 | 607E (modified) | 601F (raw ROM) | 601F |
| FFBF=2 Spider | OBP-7.1 | 00E0 (modified) | 001F (raw ROM) | 001F |

The most damning: **Sara jet form palette swap doesn't activate at B=20**.
When FFD0 is forced to 1, OBP-2 stays at witch palette (2EBE/511F)
instead of swapping to jet (7C1F/5817). This means Sara's jet
transformation in stage 5+ would VISUALLY FAIL.

## Mechanism (best-guess hypothesis)

`hwoam_recolor` at B=40 takes ~960T (well into the next LCD scanline).
At B=20 it ends ~480T sooner. The shorter runtime changes when the
NEXT VBlank's `cond_pal` / `palette_loader` chain fires relative to
LCD STAT-mode transitions and CPU register state. Specifically:

- The colorize chain's palette write-and-modify sequence assumes a
  particular LCD cycle phase when each CRAM write lands.
- The B=40 wrapper's predictable runtime keeps that phase consistent
  frame-to-frame.
- B=20 wrapper finishes earlier → different LCD phase → palette writes
  land at different CRAM-write windows → final CRAM differs.

Boss-palette writes (Gargoyle/Spider OBP-6.1/7.1) show ROM-source
values at B=20 vs "modified" values at B=40 — suggests a second-pass
modifier runs at B=40 that doesn't fire at B=20.

## B-sweep race quantification (from probe_white_flicker.lua, 540 frames)

| B value | slot 0 | slot 1 | slot 2 | slot 3 | slot 10+ | total | spider test | fresh-boot |
|---|---|---|---|---|---|---|---|---|
| 40 (iter 31, current) | 31 | 4 | **113** | 6 | ~120 | 315 | PASS (50 px) | PASS |
| 32 | 26 | 4 | **110** | 14 | ~160 | 326 | PASS (40 px) | (untested) |
| 28 | 34 | 2 | **131** | 8 | ~24 | 220 | (untested) | (untested) |
| 24 | 30 | 26 | **71** | 18 | ~16 | 199 | FAIL (37 px) | (untested) |
| **20** (attempted) | 30 | 14 | **23** | 16 | ~70 | 199 | FAIL (37 px) | **FAIL 4 CRAM** |
| 10 | 26 | 12 | 24 | 12 | 0 | 115 | (untested) | (untested) |

Sharp transition between B=20 (slot 2 = 23) and B=24 (slot 2 = 71).
Looks like a specific LCD-cycle boundary is crossed at B=22-23.

## Conclusion

The half-orange Sara race source cannot be fixed by lowering B alone —
B<24 breaks Sara jet form + boss palette modifications, B>20 doesn't
fix the race.

The audit in [iter276_oam_writer_hunt.md](iter276_oam_writer_hunt.md)
already documented this as an autonomous-loop limit. Iter 277
confirms the same finding via a more sophisticated probe — the race
isn't purely a VBlank-overrun phenomenon but is entangled with the
colorize chain's CRAM-write-sequencing dependency on hwoam_recolor's
runtime.

A future fix would need to:
1. Quantify which CRAM-write-modifier code runs at B=40 but not B=20
   (likely STAT IRQ stub at WRAM 0xDB50 or some post-wrapper code).
2. Decouple that modifier from hwoam_recolor's runtime.
3. THEN lower B safely.

This requires scanline-rate instrumentation, which mGBA Lua doesn't
expose. Genuinely blocked at the autonomous-loop's tool ceiling.

## Build state after iter 277

- `scripts/build_v301_teleport.py`: B=40 (restored, same as iter 276 baseline)
- `scripts/diagnostics/verify_colorizer_bytes.py`: 0x28 byte lock (restored)
- `tests/color_regression_tests.yaml`: original thresholds (restored)
- This audit document: the only deliverable

## Status

- mGBA-probe verified: B=20 reduces slot 2 race 80%.
- mGBA-test verified: B=20 introduces 4 CRAM regressions (REVERTED).
- This audit explains why B<24 isn't a viable fix and what the next
  step would require (scanline-rate instrumentation).
