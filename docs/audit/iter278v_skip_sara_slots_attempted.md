# iter 278v — hwoam_recolor B=36 skip Sara slots (attempted, reverted)

## Summary

After 2026-06-30 user discussion of "clean working version" trade-off (FIXED.gb
had clean Sara but no enemy colorization), tried iter 278v: make
hwoam_recolor START at slot 4 (HL=0xFE13, B=36) to SKIP Sara slots 0-3
entirely. Theory: Sara is colorized via shadow_main → DMA path (shadow OAM
has correct pal-2 attrs); hwoam_recolor only restamps slot 4-39 (enemies).
No race on Sara because we never touch her slots. Enemy colorization preserved.

## Result: theory invalidated, 38 tests broke

`sara_w_alone` failure: "Slot 0: expected palette 2, got 1 (tile=0x20)".

**Without hwoam_recolor B=40 stamping Sara slots, they end up at pal-1
(dragon green), not pal-2 (witch).** Even when Sara is in witch form
(FFBE=0 in savestate).

## Why my hypothesis was wrong

The shadow_main → DMA path does NOT leave Sara at pal-2. SOMETHING writes
pal-1 to slots 0-3 attrs between shadow_main and final display:

- Possibility A: Game's main-loop OAM rebuild writes pal-1 to Sara slots
  (game thinks Sara is currently dragon? unclear why)
- Possibility B: shadow_main's colorize reads stale tile and dispatches wrong
- Possibility C: Double-buffer DMA picks the "wrong" buffer that has pal-1

**Key finding**: hwoam_recolor B=40 isn't just compensating for game's pal-0
overwrite (which would render Sara as default OBP-0). It's actively
RESTAMPING over pal-1 (dragon) to keep Sara at pal-2 (witch).

This means hwoam_recolor stamping for Sara slots is **essential**, not just
a race-prone bonus. The 5% orange flicker is the cost of essential work,
not gratuitous overhead.

## Architectural implications

The user's earlier question — "why is orange a problem vs the clean working
version with bg colors and some sprite colorization" — has a refined answer:

**The FIXED.gb "clean version" preserves Sara via a different path** that we
don't fully understand yet. Either:
1. FIXED.gb's shadow_main writes pal-2 reliably (no pal-1 overwrite happens)
2. FIXED.gb has a different game-side OAM update path  
3. The savestate testing isn't catching FIXED.gb's actual flicker

Worth investigating: probe FIXED.gb's slot 0-3 attr stability over many
frames to see if it really is clean, or if iter 241's race quantification
was hwoam_recolor-specific.

## Build state after revert

Restored to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening (component 4 SHIPPED)
- iter 278l: cursor visible as 'A' character (component 3 SHIPPED)
- iter 278e: 75% Sara race reduction (component 1+2 partial)

## /goal status — 13 distinct attempts now documented

iter 277/278d/g/h/n/o/q/r/s/s2/t/u/v all reverted.

## Open question for next session

What writes pal-1 to Sara slots 0-3 after shadow_main but before display?
Knowing this would tell us:
- Whether the "Sara slots need restamping" is structural (game design) or
  fixable (some other code path overwrites incorrectly)
- Whether FIXED.gb actually has a different mechanism or just doesn't show
  the bug on tested savestates

A probe: hook PC=write to FE03/FE07/FE0B/FE0F via Mesen2's
addMemoryCallback (per dr-mario-rl's tip + reference_mesen2_gbc_alternative.md
memory), log who writes pal-1 vs pal-2 over a fresh-boot stage 1 sequence.
This would identify the actual culprit, not just confirm the race.
