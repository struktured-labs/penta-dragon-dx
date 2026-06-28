# iter 278s / 278s2 — hoist hwoam_recolor + extend STAT IRQ stub (attempted, reverted)

## Summary

After multi-agent workflow investigation (2026-06-27, ultracode-authorized)
identified the root cause as VBlank budget overrun and recommended two
ship-clean fix paths, attempted both:

- **iter 278s**: Hoist hwoam_recolor to FIRST in the wrapper (before
  teleport_routine). 1-line swap. Theory: hwoam_recolor's 40-slot loop
  runs at LY≈145-148 (wide-open mode 1) instead of LY≈153+ where
  writes drop.

- **iter 278s2**: Extend STAT IRQ stub at 0xDB50 to stamp all 4 Sara
  slots (0/1/2/3) with same pal-B value. Compact loop body. Stub
  source relocated from 0x53F2 (36-byte budget) to 0x6A70 (144-byte
  free run in bank 13), STAT_STUB_MAX bumped to 48.

## Results

### iter 278s: hoist
**Visual: SARA IS PINK at f=60/100/300** on stage1_entry_pink_renders.ss0
(vs orange in iter 278e baseline). Race visually FIXED.

But hook: **16 regression tests fail** — crow, moth, orc, gargoyle,
metal_ball_mage_soldier, sara_w_2_metal_ball, sara_w_catfish_*,
sara_w_pink_force_df1f, jet_form_visual_render, death_cinematic_*,
spider, sara_w_right_before_secret_stage_gbc, sara_w_secret_stage_shmup,
spiral_power_active, stage4_live_render.

Root cause of failures: hwoam_recolor's colorizer reads HW OAM TILE
bytes to dispatch palette by tile range. When hoisted to FIRST, it
reads STALE tile bytes (last frame's DMA output). For Sara slots 0-3
this is harmless (Sara's tile range is stable). But for enemy slots
4-39, stale tiles can be from the PREVIOUS frame's enemies, dispatching
wrong palette → 16 tests catch the regression.

The workflow's "tile bytes are 1 frame stale, harmless" prediction
held for Sara but failed for enemies.

### iter 278s2: extend STAT IRQ stub
Visual: SARA PINK at f=60. Race visually FIXED.

But hook: **17 regression tests fail** (similar set + sara_w_pink_render).

Root cause: STAT IRQ stub gets ~132T MORE work per fire (was 44T for
slot 1 stamp only; now ~176T for 4-slot loop). Per iter 8 lesson,
+30T to STAT IRQ stub broke parallax-scroll handler timing. +132T
breaks much more — including Sara render tests because parallax
shift affects SCX/SCY at sample frame, displacing the visible Sara
out of expected pixel region.

## Why this matters

The multi-agent workflow's synthesis recommendation (Option 1: STAT IRQ
at LY=151 specifically, not extending existing handler) was actually
the right idea. iter 278s2's implementation took a shortcut (extend
existing stub) that violates the LY=151 specificity. To do it correctly:

1. Cold-boot installer must set FF45=151 (LYC)
2. STAT register must enable LYC source (FF41 bit 6)
3. Existing STAT IRQ dispatcher must check FF44 (LY) and route
   LYC=151 to new stamp, LYC=0 (existing parallax) to old handler

This is ~60+ bytes of new code plus install logic. Within autonomous-
loop scope but requires careful implementation.

## Build state after revert

Restored to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening (component 4 SHIPPED)
- iter 278l: cursor visible as 'A' character (component 3 SHIPPED)
- iter 278e: 75% Sara race reduction (components 1+2 partial)
- 170 byte-verifier locks pass
- All 116 BG regression tests pass
- Fresh-boot all expectations pass

## /goal status — 10 distinct attempts

| Attempt | Approach | Outcome |
|---|---|---|
| iter 277 | B=20 hwoam_recolor | -480T → broke 4 CRAM |
| iter 278d | inline split-stamp +600T | broke many CRAM |
| iter 278g | CALL sara_stamp +24T | broke 22 CRAM |
| iter 278h | CALL sara_stamp + FFA9 invalidate | VBlank overrun |
| iter 278n | inline sara_stamp + NOP padding (0/20/35) | 6-8 CRAM fails |
| iter 278o | iter 278n + test-side FFA9 force | 8 CRAM (game overwrite) |
| iter 278q | iter 278n + setBreakpoint protection | partial OBP-2 fix, FFC0 crashed |
| iter 278r | colorizer default → sara_palette | 10 enemy tests broke |
| **iter 278s** | **hoist hwoam_recolor to first** | **16 tests broke (stale tile reads)** |
| **iter 278s2** | **STAT IRQ 4-slot stamp** | **17 tests broke (parallax timing)** |

Workflow-recommended remaining path: full LY=151 STAT IRQ implementation
with proper LYC dispatch (~60+ bytes, multiple code locations).
