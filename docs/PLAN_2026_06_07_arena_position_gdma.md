# Plan — arena position-based colorization via GDMA (2026-06-07)

Incorporates the Letta review (docs/REVIEW_2026_06_07_arena_gdma_plan.md).
Goal ("holy grail"): kill BOTH the boss-arena color alternation AND the
shared boss/background tile bleed.

## Why the current tile-ID approach can't (proven)
- Boss is BG-layer, colored by tile ID (inline hook 0x42A7 + bg_sweep).
- Alternation: 1-row/frame sweep can't keep up with boss animation; cells
  show stale palettes between passes (probe: 134 alt tiles, ATTR-FLIP with
  tile+D880 stable).
- Shared tiles: one tile ID reused on boss + background → one color.
- Both are inherent to tile-ID keying.

## The fix (cell-indexed position map, blitted via GDMA)
1. CELL-indexed static map per arena: one palette per screen cell, by the
   boss's STABLE footprint (probe_arena_footprint.lua: a cell is "boss" if
   boss in >=40% of animation frames; palette = position band by mean row).
   NOT tile-ID keyed (that's the bug). Background cells = 0 (default).
2. On D880 0x02 -> 0x0C..0x14 (arena entry), expand the compact map into the
   D000 attr buffer (WRAM bank 2), ONCE.
3. Every frame in the arena, GDMA-blit D000 -> VRAM bank1. Atomic => no
   staleness => no alternation. Cell-indexed => no shared-tile bleed.
4. Reuse ONLY the GDMA transfer routine (0x6D80) — do NOT reuse attr_comp
   (0x7100), which is tile-ID keyed (the bug). Gate the whole path to
   D880 0x0C..0x14 so dungeon scrolling is untouched.

## Risks / must-do (from Letta review)
- GDMA has hardware-freeze history (docs/v301_gdma_freeze_diagnosis.md:
  stale FF99 -> ISR bank corruption). Current transfer avoids the footguns
  (DI around FF70, no FF99 write, general-mode) BUT must be re-verified on
  MiSTer hardware, not just mGBA.
- Size the GDMA to the full boss height. Current blit = 256B/8 rows
  (HDMA5=0x0F); Shalamar footprint is rows 0..8 (9 rows); other bosses span
  more. Size per arena or to a safe max (e.g. 14 rows).
- C1A0 is NOT a clean tilemap mirror (probe) — don't read it for cell data.

## Footprint reference (Shalamar, probe 240 frames, >=40% threshold)
rows 0..8; per-row palette grid (0=bg):
  R0  00000004444444444444   R1  00000000044444444440
  R2  00000004444444444444   R3  00000066666666666666
  R4  00000006666666666666   R5  00000005555555555555
  R6  00000005555555555555   R7  00000000333300033330
  R8  00000000030000000300

## Build order
1. [done] footprint probe (cell-indexed map), Shalamar verified.
2. Tour-probe all 9 arenas -> compact per-arena cell maps (RLE: per-row
   col-runs, ~1KB total, fits bank 13).
3. ROM: map storage + D000 expansion on arena entry + per-frame GDMA blit,
   D880-gated, sized to boss height.
4. Verify mGBA (alternation gone, no bleed) -> then MiSTer hardware check
   BEFORE promotion (freeze history).
