# iter 241 — white-flicker / half-orange-Sara quantified

## Context
User reported 2026-06-22: "the stage 1 game play is very bad. sprites are
half one color half another. theres white flickering, its slow, etc."

Five prior iter cycles (229, 233-235, 238, 240) attempted fixes via build
modifications — all reverted because teleport.gb's VBlank budget is too
tight for new code paths.

Iter 241 took a different angle: **diagnose, don't fix**. Built a
headless mGBA probe (`scripts/diagnostics/probe_white_flicker.lua`)
that tracks per-frame:
- CRAM cell flickering near white (detect palette oscillation)
- OAM slot presence toggles (sprites coming/going)
- OAM attribute palette changes per slot (same slot, pal flips)
- LCDC register bit-level toggles (tilemap area swap)

## Findings on `stage1_entry_pink_renders.ss0` over 540 frames

| Signal | Result | Interpretation |
|---|---|---|
| CRAM cells flickering to/from white | 0 events | NOT a palette CRAM issue |
| OAM slot presence toggles | 3 events | Normal sprite entry/exit |
| LCDC OBJ enable (bit 1) toggles | 0 | OBJ never disabled |
| LCDC tile-map (bit 3) toggles | 68 | Normal parallax mechanism |
| Slot 0 (Sara tile 24) ATTR changes | 32 | ~6% flicker rate |
| **Slot 2 (Sara tile 27) ATTR changes** | **121** | **~22% flicker rate** |
| Slot 1, 3 ATTR changes | 4-6 | Minor flicker |

## The "half orange Sara" mechanism
Slot 2 alternates between OAM attribute palette indices 2 and 4:
- Pal 2 = Sara W skin/pink (hwoam_recolor's intended stamp)
- Pal 4 = Hornets yellow/orange (game's source-OAM default)

The visible result: Sara's torso flickers pink ↔ orange every few frames.
This is precisely the user's reported "half orange Sara" — except it's
not a static half-and-half split, it's a temporal alternation that the
human visual system integrates as half-tone (or as flicker, depending on
the alternation frequency).

## Root cause confirmed (matches iter 151 hypothesis)
hwoam_recolor at bank13:0x7F40 stamps OBJ palette indices for the Sara
slots POST-DMA. But:
- The game's main OAM DMA continues each VBlank, overwriting attrs.
- hwoam_recolor's per-frame restamp is RACING the DMA.
- Some frames the stamp wins (pal 2); some frames the DMA wins (pal 4).
- 22% loss rate on slot 2 confirms the race is real and severe.

## Why probe didn't trigger CRAM-flicker alarms
The "white flickering" the user described visually probably is NOT a
literal palette-white event. More likely it's the OAM attr alternation
itself: pal 2 (Sara W) and pal 4 (Hornets) have different luminance
profiles, so the eye sees the difference as flicker even though no
palette actually goes white.

Alternative source: LCDC bit 3 toggling 68× per 540 frames swaps
between BG tilemaps at 0x9800 and 0x9C00. If the inactive tilemap
contains stale/uninit tiles, the screen would show garbage briefly
during the swap. This is a secondary candidate for "white flickering"
but no direct evidence yet.

## Useful for regression suite
The probe could be promoted to a regression test:
- "slot 0-3 ATTR alternation < 5 changes per 600 frames" — would FAIL
  on current teleport.gb, documenting the known bug.
- After a future fix, this test would gate against re-regressions.

For now, the probe is checked in as a diagnostic tool. Future iters
can use it to validate any candidate hwoam_recolor improvements.

## What this CHANGES vs the iter 151 status quo
- iter 151 hypothesis was BC variant (B=10 vs B=40) — true but partial.
  The root cause is DMA-vs-stamp racing, not loop bound.
- Quantitative measurement: 22% race-loss rate on the worst-affected slot.
- Probe gives us a reliable signal for any future fix attempt:
  - "Run probe → if slot 2 ATTR changes drop from 121 to <5, fix works."

## What this does NOT solve
- The bug itself remains (no code change committed).
- The fix likely needs hwoam_recolor to run AFTER the game's OAM DMA
  in the VBlank handler, not before. Or via STAT IRQ on a scanline
  past where DMA completes. Both are timing-sensitive changes that
  risk the iter 235 / iter 238 / iter 240 failure pattern.

Next iter should investigate hwoam_recolor's CALL position in the
teleport routine and whether moving it later in the VBlank avoids
the race without breaking regression tests.
