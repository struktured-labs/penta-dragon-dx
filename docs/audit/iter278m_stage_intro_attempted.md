# iter 278m — stage intro brighten via splash_table (attempted, reverted)

## Summary

After /goal directive "stage intro screen colors wrong", attempted
to brighten "STAGE 01" letters by patching `splash_table[0xCA..0xFF] = pal-1`
in `bg_experiment.create_splash_table()`. Reasoning: 0xCA-0xFF is
the banner-letter tile range per banner_override context, and patching
there would leave stage 6 unaffected (stage 6 uses 0x40-0x7F lavender).

## What was probed

Dumped BG tilemap at `save_states_for_claude/splash_stage1_d880_18.ss0`
(LCDC=0x83, BG enabled, OBJ enabled, no window) frame=200:

```
tilemap 0x9800 rows 4-5 (where "STAGE 01" renders):
  r04: ..  ..  6E 7D 30 31 4A 4B 40 6D 58 6F  ..  ..  2C 2D 43 45  ..  ..
  r05: ..  ..  7E 51 54 55 5A 5B 50 53 52 7F  ..  ..  3C 51 54 55  ..  ..
```

**"STAGE 01" tile range: 0x30-0x7F** (specifically 0x30, 0x31, 0x40,
0x4A, 0x4B, 0x50-0x55, 0x58, 0x5A, 0x5B, 0x6D-0x6F, 0x7D-0x7F).

NOT in 0xCA-0xFF range. Patch had zero effect on visible letters.

## Why broader range patches fail

Patching `splash_table[0x30..0x80] = pal-1` would brighten "STAGE 01"
but iter 234 audit confirms this leaks via WRAM 0xDA00 savestate cache
into stage 6's BG tile mapping: lavender pixel count drops 7822 → 5554.

Per iter 234 audit:
> "scene_detect's fast-path (RET Z when scene unchanged) keeps splash_table
> cached in WRAM 0xDA00 across savestate-captured transitions, so iter
> 234's pal-1 letters bleed into stage 6 BG render"

## The architectural ceiling

Stage intro brightening requires per-scene BG tile-palette overrides
that don't share WRAM 0xDA00 state across scene transitions. Two
paths exist, both blocked:

1. **Mid-frame STAT IRQ override for D880=0x18**: per iter 238 audit,
   any per-frame CALL addition broke 14 regression tests via VBlank
   budget overrun (~27T+ per frame intolerable).

2. **scene_detect post-copy stamp**: per iter 263 audit, even
   on-scene-change writes (+36T per transition) broke CRAM-load
   timing for OBP-2 pink-red and OBP-1 green palettes.

3. **Direct CRAM palette substitution**: requires finding where
   splash CRAM palette 0 colors load and patching the load values
   (deep RE of bank's palette table).

## Build state after revert

Same as before iter 278m attempt:
- iter 278e (75% Sara race reduction)
- iter 278l (cursor 1-byte tile patch — fires only when cursor
  handler at 0x3C52 dispatches, NOT initial title render)
- No stage intro brightening

## /goal status (consolidated)

| Component | Status | Blocker |
|---|---|---|
| White flicker | 75% reduction (iter 278e) | 100% blocked by CRAM phase coupling |
| No orange in Sara | Same 75% reduction | Same CRAM phase ceiling |
| Title cursor — initial | NOT fixed | Per iter 126 audit, original ROM has no visible title cursor (Japanese-design original); requires NEW draw routine |
| Title cursor — UP/DOWN | iter 278l patch | Cursor handler at 0x3C52 likely fires only on submenu, not main title — needs probe to confirm visual effect |
| Stage intro colors | NOT fixed | WRAM 0xDA00 savestate cache leaks splash_table patches into stage 6 BG render |

All 4 components hit the autonomous-loop architectural ceiling:
- CRAM phase coupling (Sara fix)
- WRAM 0xDA00 cross-scene leakage (splash patches)
- ROM-side new-routine requirement (initial cursor)
- Per-frame CALL budget overrun (any stamp-on-scene approach)

## Future directions (NOT attempted in autonomous loop)

1. **Cycle-precise NOP padding** to preserve EXACT wrapper runtime
   while adding sara_stamp (per iter 278g audit suggestion). Requires
   scanline-rate instrumentation Lua probe + iterative tuning.

2. **scene_detect cache-clear on transition out of D880=0x18/0x1B**:
   force WRAM 0xDA00 reload so splash_table patches don't leak into
   subsequent stage 6 captures.

3. **Title menu BG-write augmentation**: add a 12-byte routine that
   writes cursor tile to BG tilemap at title init (D880=0x1C first
   frame) before per-frame CALL overrun limit hits.

All three require either deep RE or scanline-precise instrumentation
beyond the autonomous loop's iteration ceiling.
