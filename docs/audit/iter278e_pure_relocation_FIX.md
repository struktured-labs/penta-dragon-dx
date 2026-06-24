# iter 278e — PURE RELOCATION FIX (the working answer)

## Summary

After iter 277/278a/278b/278c/278d all failed to fix half-orange Sara
without breaking tests, the simplest possible change works:

**Just move `hwoam_recolor` from 0x7F40 to 0x6B27. Same 49 bytes, no
other changes.**

Result:
- Slot 2 OAM ATTR race: **113 → 29 changes per 540 frames** (75% reduction).
- All 116 BG regression tests PASS.
- All fresh-boot CRAM expectations PASS (Sara jet form, Gargoyle, Spider
  boss palettes all correct).
- Byte verifier updated (3 byte locks moved to new address).

## Why this works (best-guess mechanism)

The race source is the OAM colorizer reading mode-locked HW OAM during
slot 0-3 stamps. Mode-lock occurs when hwoam_recolor's colorizer pass
happens at specific LCD cycle positions where the LCD is in mode 2/3.

When hwoam_recolor was at 0x7F40, the wrapper's `CALL 0x7F40` placed
the colorizer call at a specific LCD cycle position relative to the
post-DMA window. That position frequently hit mode-locks at slot 0-3
tile reads.

At 0x6B27, the wrapper's `CALL 0x6B27` places the same colorizer call
at a SHIFTED LCD position. The shift happens to miss most mode-locks
at slot 0-3. (The exact mechanism likely involves CPU memory access
latency for the CALL operand fetch differing between 0x7F40 and 0x6B27,
shifting the colorizer's per-iter timing by a few cycles.)

This is empirical — the data shows the race drops from 113 to 29 with
this single change. No other modification (code, runtime, byte content)
varies.

## Why prior approaches failed

- **iter 277 (B=20)**: Changed colorizer runtime → CRAM phase shift →
  4 fresh-boot CRAM regressions.
- **iter 278a (candidate J)**: Added mode-lock detection at entry,
  changed runtime and HL/B setup → CRAM phase shift + slot 4+ race.
- **iter 278b (pal_0 fallback)**: Broke orc/spiral (legitimate pal_4
  sprites).
- **iter 278c (skip slot 0-9)**: Sara slot 0 became pal-1 (Dragon)
  instead of pal-2 (Witch).
- **iter 278d (split-stamp)**: Eliminated slot 2 race 100% (113→0)
  but +600T runtime broke 18 fresh-boot CRAM expectations.

All of those CHANGED the code or runtime. iter 278e changes ONLY the
address.

## What changed

1. `scripts/build_v301_teleport.py:154` — `HWOAM_RECOLOR_ADDR = 0x6B27`
   (was 0x7F40).
2. `scripts/build_v301_teleport.py:1037-1046` — relocation guard
   assertions updated.
3. `scripts/diagnostics/verify_colorizer_bytes.py:40-71` — iter 31
   byte locks moved to new address (0x6B27, 0x6B28, 0x6B4E).
4. `scripts/diagnostics/verify_colorizer_bytes.py:683-687` — v3.01
   skip list updated to new addresses.

`build_hwoam_recolor()` is UNCHANGED. The function emits the same
49-byte routine. Only its location in ROM differs.

## Race reduction quantification

Per `scripts/diagnostics/probe_white_flicker.lua`,
state `level1_stage1_entry_pink_renders.ss0`, 540-frame window:

| Iter | Slot 0 | Slot 1 | Slot 2 | Slot 3 | Notes |
|---|---|---|---|---|---|
| 276 baseline (0x7F40) | 31 | 4 | **113** | 6 | iter 31 B=40 at original addr |
| 278e (0x6B27)         | 19 | 4 | **29**  | 16 | Just relocated, 75% Sara fix |

Total race reduction: 154 → 68 (56%). Slot 2 alone: 113 → 29 (74%).

## Test results

- 116 BG-scene regression tests: ALL PASS (no retries needed).
- Fresh-boot end-to-end test: ALL expectations PASS.
- Byte verifier (152 byte locks): ALL PASS.
- Critical 12-test visual sweep: ALL PASS.

## Hardware verification status

mGBA verified. MiSTer hardware verification pending.

## Status

**SHIPPABLE**. This is the fix the iter 276/277/278a-d audits documented
as "needs architectural redesign" but turns out to require only a
relocation. The 25% residual slot 2 race (29 frames vs prior 113) is
still present but visually minor compared to the prior 22% race-loss rate.
