# Audit — Title Screen + Menu (rendering, DX/attribution feasibility, color bleed)

## 2026-06-18 UPDATE: A-H / I-Z color bleed RESOLVED
The "A B C D E F G H tiles pal 0 (blue-ish) vs I J ... X Y Z tiles pal 1 (red)
color split on menu text" documented in Section 4 below is **fixed** in current
builds. `scripts/build_v301_gdma.py:_bg_table()` now uniformly maps all font
tiles 0x80-0xDF to **pal 1** (verified live in `penta_dragon_dx_v301.gb` at
`bank13:0x7000+0x80`). This is asserted by `dungeon_table_items_and_font`
in `tests/color_regression_tests.yaml` (iter 16; in pre-commit hook). The
"splotches" from logo metatile collisions with non-zero `bg_table` ranges
(43 → pal 1, 3 → pal 6, 2 → pal 5) are still per the original audit, but
their visual impact is minor given pal 1 (red) reads well against the white
background. The historical "title splotches fixed in v3.01" claim stands.

---

# (original 2026-06-14 audit follows)


Static analysis only (no emulator). ROM bytes from `rom/Penta Dragon (J).gb`
(base, DMG) and `rom/working/penta_dragon_dx_v301.gb` (built hack; MD5 of the
current production build is identical to `penta_dragon_dx_FIXED.gb`). Disassembler
helper used: `tmp/gbdis.py`.

Bank map: file is 256 KB = banks 0..15. Bank N maps to file offset `N*0x4000`;
the switchable window 0x4000-0x7FFF reflects the currently-banked-in ROM bank.
Title code runs with **bank 1** banked in for its data tables, and momentarily
switches to **bank 14 (0x0E)** for tile graphics copies.

---

## 1. How the title renders "PENTA DRAGON"

### Entry flow
- `0x39C3` title entry: `XOR A; LD [DD09],A` (unblock input), `CALL 0x0A0E`,
  `CALL 0x492B`, `LD A,1; LD [D880],A` (D880=1 title splash), then:
  - `CALL 0x3AF6` — main title build + cursor loop
  - `CALL 0x3BA2` / `0x39EB` — logo blitter
- `0x39EB` is the **logo blit driver**. It clears the 0x9800 tilemap to tile
  `0x28` (`LD C,0x28; CALL 0x3BE2`) then runs 8 rectangle blits.

### The logo is a tile-based BITMAP, NOT font text
Each blit (`CALL 0x3BCB`) takes:
- `A`  = per-metatile-row VRAM stride (e.g. 0x34, 0x28, 0x20)
- `DE` = VRAM **tilemap** destination (all in the **0x9800** region: 0x9874,
  0x9A48, 0x9860, 0x9A40 — never 0x9C00)
- `HL` = source **index** table in **bank 1** (0x4C29, 0x4C47, 0x4C83, 0x4CD3,
  0x4D23, 0x4D73, 0x4DC3, 0x4E13)
- `BC` = (rows=B, cols=C), e.g. 0x0506 = 5 rows × 6 cols of metatiles

`0x3BCB → 0x3C72` per cell: reads one **index** byte from HL, computes a 4-byte
record pointer `0x5400 + index*4` in **bank 14 (0x0E)**, switches to bank 14
(`LD A,0x0E; CALL 0x0061`), then writes 2 tile IDs to VRAM `[DE]`, advances DE
by 0x1F to the next tile-row, writes 2 more tile IDs. So each index = a **2×2
metatile** (top-left/top-right/bottom-left/bottom-right tile IDs).

`0x3C72` writes **VBK=0 only** (tile IDs) — it never touches the CGB attribute
layer (VBK=1). So the logo blitter contributes no palette attributes.

### Metatile records (the logo "alphabet" of art tiles)
- Location: **bank 14, file offset `0x39400` (= bank14:0x5400)**, 0x70 records ×
  4 bytes. Record `0x32` = `28 28 28 28` (the blank/space metatile). Tile `0x28`
  is the title's blank tile.
- The logo consumes **255 distinct tile IDs (0x01-0xFF)** across the records —
  essentially the *entire* 256-tile VRAM tile bank is unique logo art. There is
  **no spare tile slot in the logo's tile bank**.

### Logo TILE GRAPHICS (2bpp pixels) source
- Decompress/load path: `0x3B0C: LD A,0x34; LD D,0x8C; CALL 0x0D27` plus
  `0x3ABC: LD DE,0x8800; CALL 0x10A1`. `0x0D27 → 0x0D12 → 0x623C` resolves a
  source pointer + bank from `A`. For `A=0x34` the path lands at `0x628F`
  returning **bank 0x0E (14)**, high byte from table `bank1:0x6296`.
- Conclusion: title tile-graphics pixel data lives in **ROM bank 14 (0x0E)**;
  loaded into VRAM tile area starting ~`0x8800/0x8C00`.

### Tilemap region used
- Title BG tilemap = **0x9800** (confirmed: every blit DE is 0x98xx/0x9Axx,
  and the clear at `0x3BE2` targets `LD HL,0x9800`). The 0x9C00 region is the
  game's alternate/double-buffer page used during scrolling gameplay.

### Layout (reconstructed)
The logo occupies roughly tilemap rows 3-10, cols 0-~13 (left-justified).
Rows 0-2, rows ~11-19, and cols ~14-31 are blank (tile 0x28). Plenty of free
tilemap cells exist below and to the right of the logo for added text.

---

## 2. The TITLE TEXT system (menu + copyright) — and the usable FONT

The "OPENING START / GAME START" menu and the copyright lines are NOT part of
the logo bitmap. They are drawn by a separate text engine:

- Command list at **bank1:0x4EA5 .. 0x4F21**, terminated by a **0x9A col-byte at
  0x4F22**. Driver `0x395A` (invoked from `0x3B0F: LD HL,0x4EA5; CALL 0x395A`),
  per-glyph printer `0x3432 → 0x3459`.
- List entry format: `[col] [row] [tile_id ...] 0x9A`. (0x9A as the first
  (col) byte = end of list.)

Decoded entries:

| col | row | text | tiles |
|----|----|------|-------|
| 7 | 3 | (logo bottom continuation) | C1 C2 C3 C4 C5 |
| 7 | 4 | (logo continuation) | D1 D2 D3 D4 D5 |
| 7 | 5 | (logo continuation) | C6 C7 C8 C9 D6 |
| 4 | 8 | `OPENING START` | 8E 8F 84 8D 88 8D 86 00 92 93 80 91 93 |
| 4 | 10 | `GAME    START` | 86 80 8C 84 00 00 00 00 92 93 80 91 93 |
| 4 | 12 | (© mark) | C0 |
| 4 | 13 | `©... YANOMAN` | D0 D7 D8 D9 00 98 80 8D 8E 8C 80 8D |
| 0 | 14 | (© mark) | C0 |
| 0 | 15 | `©... JAPAN ART MEDIA` | D0 D7 D8 D9 00 89 80 8F 80 8D 00 80 91 93 00 8C 84 83 88 80 |
| 0 | 17 | `LICENSED BY NINTENDO` | 8B 88 82 84 8D 92 84 83 00 81 98 00 8D 88 8D 93 84 8D 83 8E |

### Font mapping (CONFIRMED)
- **Uppercase A-Z = tile IDs 0x80..0x99** (A=0x80, G=0x86, I=0x88, N=0x8D,
  O=0x8E, P=0x8F, S=0x92, T=0x93, R=0x91, Z=0x99). Space = 0x00.
- This font tileset is loaded on the title (it renders the existing menu/©).
  Loaded via the `0x3364`/`0x33B3` graphics copies from **bank 14** into the
  0x8000-0x9000 VRAM tile area.
- A SECOND, different font exists for boss-name splashes: **A=0x01..Z=0x1A**,
  table `bank2:0x7A78` (9 × 16 bytes). That font is NOT loaded on the title
  (the title's 0x01-0xFF tile bank is logo art), so it is not usable here.

### Where glyphs land (rendering path)
`0x3459` (when `DCE2 != 0`, which the title sets via `0x3AFB: LD A,1; LD
[DCE2],A`) calls `0x34B2` to compute the destination **inside the 0xC1A0 tile
buffer** (40 cols/row): `HL = 0xC1A0 + (row+1)*40 + (col+1)`, then `LD [HL],A`.
So title text is written into the **0xC1A0 staging buffer**, and the **inline
tile+attr copy hook at bank1:0x42A7** later flushes that buffer into the 0x9800
tilemap, writing both the tile ID (VBK=0) and the CGB attribute (VBK=1, palette
= `bg_table[tile_id]`). (When `DCE2 == 0` the same routine instead uses an
OAM/sprite path at 0xC000 — that is the in-game floating-letter mode; on the
title DCE2=1 so it is the BG-tile path.)

---

## 3. The COLORIZE HANDLER and title/menu gating (ground truth)

Built handler at **bank13:0x6E00** (file 0x36E00). Disassembled from the shipped
ROM:

```
36E00 save VBK; VBK=0
36E06 DF02 magic-byte cold-boot check (0x5A)
        cold path: DF02=0x5A, DF00=0, DF0A=0, copy bg_table 0x7000->WRAM 0xDA00 (256B)
36E27 CALL cond_pal (0x6C90)         ; ALWAYS (loads all 8 BG + OBJ palettes; hash-cached)
36E2A attr-cleaner (DF08 sentinel / DF07 row counter)
        ; clears 32 attr bytes in BOTH 0x9800 and 0x9C00, one row/frame,
        ; for 32 frames after cold boot, then ~12T no-op
36E6E LDH A,[FFC1]; OR A; JR Z,36E7C  ; <-- FFC1 GATE
36E73   CALL bg_sweep   (0x6CD0)      ; gameplay only
36E76   CALL shadow_main(0x69D0)      ; OBJ colorizer, gameplay only
36E79   CALL FF80       (OAM DMA)     ; gameplay only
36E7C restore VBK; RET
```

Key correction to a misleading source comment: the build comment in
`scripts/build_v301_gdma.py` (around line 350) says "bg_sweep ... run on title
too" because it NOPs bg_sweep's *internal* FFC1 prefix
(`assert sweep[:4]==F0 C1 B7 C8; sweep[0:4]=00 00 00 00`). BUT the colorize
**handler** still gates `CALL bg_sweep` behind its own `FFC1` check at 0x36E6E.
Net effect in the shipped ROM: **bg_sweep does NOT run on the title/menu**
(FFC1=0 there). Only `cond_pal` + the attr-cleaner run on the title.

### So what colors the title?
1. `cond_pal → palette_loader` loads all 8 BG palettes every relevant frame
   (title included). Title therefore has real colored BG palettes available.
2. Title BG **attributes** come ONLY from:
   - the **inline hook at 0x42A7** flushing the 0xC1A0 buffer with
     `bg_table[tile_id]` attrs (this is how the menu/© text and the background
     fill get a palette), and
   - the **attr-cleaner** zeroing stale 0xFF attrs to pal 0 for 32 frames.
   The logo blitter (0x3C72) writes no attrs, so logo metatiles inherit
   whatever attr the buffer/cleaner left (mostly pal 0; the 0x3AA6 memset of
   0xC1A0 to 0xDF + the 0x3AD8 `CALL 0x42A5` initial flush tags the background
   fill via bg_table[0xDF]=pal 1).

### pal7 override
`build_v301()` copies `bg_data[0:8]` into `bg_data[56:64]` so **BG pal 7 == BG
pal 0** (verified in the built ROM: both = white/blue/slate/black). This hides
stale CGB-boot attr bytes (0xFF → pal 7) by making pal 7 visually identical to
the default pal 0. This is in effect on the title.

---

## 4. COLOR-BLEED on the title/menu — IS IT PRESENT?

YES — a real, structural bleed exists for any text rendered through the
`bg_table` attr path, including the existing menu. The inline hook tags every
flushed tile with `bg_table[tile_id]`, and the font glyph tiles 0x80-0x99 split
across two palettes:

| Font tiles | Letters | bg_table palette |
|---|---|---|
| 0x80-0x87 | A B C D E F G H | **pal 0** (white / blue / slate / black) |
| 0x88-0x99 | I J ... X Y Z | **pal 1** (white / RED / dark-red / black) |

Built-ROM palette colors (bank13:0x6800):
- pal 0 = `#f8f8f8, #a0a0f8, #505078, #000000` (blue-ish)
- pal 1 = `#f8f8f8, #f80000, #900000, #000000` (red)

So letters A-H draw blue-ish and letters I-Z draw red whenever the glyph uses
color index 1/2. This means the EXISTING "OPENING START / GAME START" /
copyright lines already have a per-letter color split (it is mild because the
glyphs are mostly index-1 strokes on index-0 white, and pal 1 red vs pal 0 blue
are both readable — which is why it has not been flagged as a bug). Any NEW text
will inherit the same A-H/I-Z color split.

Logo metatiles also collide with the dungeon `bg_table`: 48 logo tiles fall in
non-zero `bg_table` ranges (43 → pal 1, 3 → pal 6, 2 → pal 5). Because the logo
blitter writes no attrs, these only matter if the inline hook flush ever stamps
those cells — i.e., title coloring is *incidental* (driven by tile-ID/`bg_table`
coincidence), not a deliberate title palette map. This is the root of the
historical "title splotches" and the v3.01 fix that re-added pal 5 entries
(0x2A-0x2E, 0x3A-0x3D) so those hazard-ID logo cells render a color instead of
invisible white-on-white.

### "Repeating stage-screen intro" symptom — NOT present in production
The known failure where the STAGE 01 splash loops forever (FFBD stuck at 5,
D880 stuck at 0/0x18) is documented in `docs/v301_regression_stage_load_stuck.md`.
Its cause is main-loop CPU **starvation** when the heavy `attr_comp` (≥23 rows)
+ `GDMA` path runs every VBlank, leaving <25K T for the game's STAGE LOAD →
dungeon transition. In the **shipped** v3.01/FIXED build these are **dead code**:
`CALL gdma (CD 80 6D)` and `CALL attr_comp (CD 00 71)` are **NOT FOUND** in the
ROM (verified by byte search; matches `docs/FINDINGS_2026_06_07_gdma_is_dead_code.md`).
So production does NOT exhibit the repeating-intro starvation. Re-enabling
attr_comp/GDMA would reintroduce it. No action needed for production.

---

## 5. Feasibility — add "DX" after "PENTA DRAGON"

**Two options.**

### Option A (LOW effort, font text): append "DX" to the title text list
- Add an entry to the list at `bank1:0x4EA5` before the 0x9A terminator at
  `0x4F22`. Entry bytes: `[col] [row] 83 97 9A` where `D=0x83`, `X=0x97`.
- The list driver `0x395A` reads until a 0x9A *col* byte, so we must (a) write
  our new entry where the current terminator is (0x4F22) and (b) move the
  terminator after it. Free bytes immediately after 0x4F22 are CODE
  (`E5 F5 FA A3 DD ...`), so we **cannot grow the list in place**.
- Bank-1 free-space census: the bank is essentially full (no >=24-byte free
  runs in the 0x4000-0x7FFF data, only 4 free bytes at the tail). The ONE
  usable home is the **inline-hook region**: the build only uses 117 of its
  199-byte budget at 0x42A7, leaving **82 free bytes at bank1:0x431C-0x436D**.
  That is enough for the entire relocated text list plus the DX and attribution
  entries.
- Implementation: **repoint `0x3B10` (the `LD HL,0x4EA5` operand) to a
  relocated list placed at bank1:0x431C**, write the existing entries followed
  by the new `DX` entry, then the 0x9A terminator. Do this in
  `scripts/build_v301_gdma.py` (it already writes the inline hook there; append
  the list after `inline_code` and patch rom[0x3B10:0x3B12]).
- Color: D=0x83 (pal 0, blue) and X=0x97 (pal 1, red) → the two letters would
  be different colors. To make "DX" one color, add a `bg_table` override (see
  §7).
- Placement: put "DX" at the right end of the logo's last text row, e.g.
  col 13-14, row 9 or 10 (free cells), sized to the font (8×8 each).

### Option B (HIGHER effort, matched art): extend the logo bitmap
- Edit the logo metatile records at `bank14:0x5400` and the index tables at
  `bank1:0x4C29..` to append a "DX" drawn in the same chunky logo style. This
  requires (a) new 2bpp tile graphics in bank 14 — but the logo already uses ALL
  256 tile slots, so there is **no free tile slot** unless we reclaim some (the
  records show several all-`0x28` filler tiles whose IDs could be repurposed),
  and (b) extending the blit list in `0x39EB`. Significantly more work; only
  worth it for pixel-perfect logo matching.

**Recommendation: Option A.** It is a small, well-understood edit (list +
optional bg_table override) and uses the existing loaded font.

---

## 6. Feasibility — add a "STRUKTURED LABS" attribution line

- Font: same uppercase tileset (0x80-0x99). Lowercase does NOT exist, so use
  uppercase "STRUKTURED LABS". Space=0x00.
- Tile bytes: `S T R U K T U R E D` = `92 93 91 94 8A 93 94 91 84 83`,
  `L A B S` = `8B 80 81 92`.
- Free row: the title has blank tilemap rows below the copyright. Good targets:
  **row 18 or 19** (bottom of screen), or **row 11/12** (between logo and menu).
  Row 18-19 keeps it clearly an attribution footer. 20 chars fit within the
  visible 20-col window (cols 0-19) with `LICENSED BY NINTENDO` proving a
  20-char line fits at col 0.
- Add as a new entry in the (relocated/extended) text list at 0x4EA5:
  e.g. `[col=3] [row=18] 92 93 91 94 8A 93 94 91 84 83 00 8B 80 81 92 9A`
  ("STRUKTURED LABS").
- Color: per §4, letters split pal 0 (E, D, A, B) vs pal 1 (S, T, R, U, K, L).
  For a single clean color, add a `bg_table` override (see §7), OR accept the
  red/blue split.

---

## 7. How to colorize added title text cleanly

The attr for each flushed tile = `bg_table[tile_id]` (table at bank13:0x7000 in
ROM, copied to WRAM 0xDA00; the inline hook at 0x42A7 reads WRAM 0xDA00). To
force all font glyphs to a single palette:

- In `scripts/build_v301_gdma.py::_bg_table()`, set the font range to one
  palette, e.g.:
  ```python
  for i in range(0x80, 0x9A):   # A..Z
      table[i] = N               # pick a palette index 0..7
  ```
  This overrides the current `range(0x88,0xE0) -> pal 1` for letters I-Z and
  also assigns A-H. Pick `N` whose color index 1/2 give the desired text color
  (define/repurpose a palette in `palettes/penta_palettes_v097.yaml`).
- Caveat: tiles 0x88-0xDF currently also serve in-dungeon "items" → pal 1.
  Re-tagging 0x80-0x99 changes those item tiles too if any item uses an ID in
  0x80-0x99. Check item tile IDs before re-tagging; if there is overlap, instead
  add a dedicated free palette and choose font tile IDs outside the item range
  (not possible since the font is fixed at 0x80-0x99) — so the safe route is to
  pick a palette N whose colors are acceptable for BOTH the title font and any
  in-dungeon tiles in that ID range, or accept the existing split.
- pal 7 is currently overridden to == pal 0; pal 6 (slate) and a spare YAML
  palette could be dedicated to "title text" if no dungeon tile in 0x80-0x99 is
  visible. This needs a quick in-dungeon tile-ID census (probe) to be safe.

---

## 8. Concrete ROM locations (summary)

| Item | Location |
|---|---|
| Title entry | bank0 `0x39C3` |
| Logo blit driver | bank0 `0x39EB` (clear 0x9800 + 8 blits) |
| Logo blit routine | bank0 `0x3BCB`; per-cell `0x3C72` |
| Logo index tables | bank1 `0x4C29, 0x4C47, 0x4C83, 0x4CD3, 0x4D23, 0x4D73, 0x4DC3, 0x4E13` |
| Logo metatile records (2×2) | bank14 `0x5400` (file `0x39400`), 0x70 × 4 bytes; blank = idx 0x32 |
| Logo tile graphics (pixels) | bank14 (0x0E), via `0x0D27/0x623C`, → VRAM ~0x8800 |
| Title BG tilemap region | **0x9800** (not 0x9C00) |
| Blank/space tile | `0x28` |
| Title TEXT command list | bank1 `0x4EA5 .. 0x4F21`, terminator (0x9A) at `0x4F22` |
| Text list driver / printer | `0x395A` → `0x3432` → `0x3459` → addr calc `0x34B2` (writes into 0xC1A0 buffer, 40 cols) |
| Text-list pointer operand | `0x3B10` (`21 A5 4E` = `LD HL,0x4EA5`) |
| Title font | **A=0x80 .. Z=0x99**, space=0x00 (loaded via `0x3364/0x33B3` from bank14) |
| Boss-name font (NOT on title) | A=0x01 .. Z=0x1A; table bank2 `0x7A78` |
| Colorize handler | bank13 `0x6E00` (file `0x36E00`); FFC1 gate at `0x36E6E` |
| cond_pal | bank13 `0x6C90` |
| bg_sweep (gated off on title) | bank13 `0x6CD0` |
| attr-cleaner | inline in handler `0x36E2A`; state DF07 (row), DF08 (sentinel) |
| bg_table (attr lookup) | bank13 `0x7000` (ROM) → WRAM `0xDA00` |
| inline tile+attr copy hook | bank1 `0x42A7` (entries `0x42A0` H=0x9C, `0x42A5` H=0x98) |
| pal7=pal0 override | `build_v301()` `bg_data[56:64]=bg_data[0:8]` |

## 9. Files to change for the DX/attribution features
- `scripts/build_v301_gdma.py` — patch the text list (relocate+extend, or
  repoint 0x3B10), and optionally `_bg_table()` font-range override.
- `palettes/penta_palettes_v097.yaml` — optional dedicated title-text palette.
- (No new VRAM tiles needed; the uppercase font is already loaded.)
