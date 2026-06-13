# FINDINGS 2026-06-13 — dungeon wall-flicker root cause + Riff colorization

Two results from this session, plus the diagnostic methods that found them.
Both are baked into the gold-standard tags `v8.6-gold-flicker-fixed` and
`v8.7-gold-riff-purple`.

## 1. Dungeon wall-flicker (teleport build) — ROOT CAUSE + FIX

**Symptom:** `penta_dragon_dx_teleport.gb` flickered the dungeon walls *while
roaming/scrolling* (not when stationary). `penta_dragon_dx_v301.gb` (the base,
no teleport) never flickered. Many speculative "fixes" failed.

**Root cause (measured):**
- The teleport build adds `scene-detect` (bank13 ~0x6FB0), which copies the
  256-byte tile→palette table into WRAM `0xDA00` *only on scene change*,
  caching the current scene id in a WRAM byte. It was supposed to fast-`RET Z`
  every other frame.
- That cache byte was at **`0xDF23`**, which sits **inside `bg_sweep`'s
  per-frame scratch buffer `0xDF10–0xDF2F`** (bg_sweep stages 32 tile IDs of a
  swept row there). So `bg_sweep` overwrote `0xDF23` with tile data **every
  frame**.
- Result: scene-detect's `D880 == cache` check always failed → it ran the full
  **256-byte copy every frame (~23 scanlines)** → this pushed the colorize
  BG-attribute write **out of VBlank into mid-screen active display (LY ~24–35)**
  → the wall tiles being drawn there got corrupted = flicker.
- Why only while roaming: when stationary, the swept row is all floor tile
  `0x02`, which happens to equal `D880`(`0x02`), so the check passed by luck and
  no per-frame copy happened. Moving makes the swept row contain varied tiles →
  cache clobbered with a non-`0x02` value → 256B copy every frame.

**Fix:** moved the cached-scene byte to **`0xDF0D`** (below the buffer, beside
the already-safe `DF0C`/`DF0E`). One line in `scripts/build_v301_teleport.py`
(`DF23_PREV_SCENE = 0xDF0D`).

**Verification (LY-timing probe):** colorize attribute-write moved from LY 24–35
(active display) back to LY ~2 (VBlank), matching v301; 256B copies/frame went
300→0 while roaming; dungeon colorization still correct; arena table-swap on
boss entry still works.

### RULE: keep custom WRAM scratch OUT of `0xDF10–0xDF2F`
That range is bg_sweep's swept-row buffer and is clobbered every frame. The
teleport fire-path bytes (DF1D/DF1F/DF20/DF21) also live there but survive only
because colorize is gated off during the fire sequence — fragile; don't add more.

## 2. Diagnostic methodology (this is the reusable part)

- **Timing bugs are INVISIBLE to headless PyBoy.** PyBoy doesn't enforce VRAM
  access windows, so a VBlank-overrun that corrupts tiles on real hardware/mgba
  renders "fine" in PyBoy screenshots. Do **not** trust headless captures to
  rule out flicker.
- **LY-timing probe** (the tool that cracked it): `pyboy.hook_register(bank,
  addr, cb, ctx)` on bg_sweep entry (`13, 0x6CD0`) and its attribute-write phase
  (`13, 0x6D37`); in the callback read `mem[0xFF44]` (LY). VBlank is LY 144–153.
  If writes land at LY < 144, they corrupt active display. Good build: writes at
  LY ~146→1-4. Bad build: LY 24–35.
- **Deterministic A/B frame diff:** PyBoy is deterministic. Run identical input
  from boot in two builds; while a full game-state fingerprint
  (DC81/FFCF/SCX/SCY/D880/FFBD) stays synced, the rendered frames are
  pixel-identical iff there's no logic/data regression. Differences that appear
  only after state drift are not regressions. This proved the flicker was timing,
  not colorization data.
- **Reading VRAM bank 1 / banked reads in PyBoy:** `pyboy.memory[1, addr]` reads
  the BG attribute map. The banked slice has a size/limit guard and rejects
  slices ending at `0xA000` (e.g. tilemap base `0x9C00`) — read row-by-row (32B)
  or byte-by-byte.
- **Reading CGB BG palette RAM:** set `mem[0xFF68]=index` then read `mem[0xFF69]`
  (64 bytes = 8 palettes × 4 colors × RGB555); restore FF68 after. Don't sample
  the rendered image at fixed positions to infer palette colors — animating
  tiles/sprites will fool you (this caused a misdiagnosed "palette shift").

## 3. Riff arena colorization (1st pass)

**Before:** crude table mapped `0x20–0x7F→green(3)`, `0x80–0xFF→gold(1)`. This
produced: a green/red "xmas tree" split, a sharp horizontal line at the
`0x7F/0x80` tile-row boundary, a yellow whisker (whisker tiles ≥ `0x80`), and the
floor colored like the monster (floor tile `0xCC` is in `0x80–0xFF`).

**Arena structure (measured):** Riff is a full-screen BG image — the tilemap is a
near-linear run of unique tile IDs (row N = `0xN0..0xNF`). Body tiles appear
1–4×; floor is the heavily-repeated `0x00` (empty, 448×) and `0xCC` (floor, 286×)
plus `xC–xF` border tiles.

**1st pass (shipped, `arena_tables_data.py['riff']`):** single **purple
(palette 2)** body; floor/frame (`0x00`, `0xCC–0xCF`, `0xDC–0xDF`, `0xEC–0xEF`,
`0xFC–0xFF`, `0xD3`, `0xE9`) left at palette 0 so the floor reads distinctly.
Body-vs-floor was classified empirically by tile-ID frequency in the live arena.

## 4. TODO / follow-ups

- **Riff OBJ tendrils:** the ~32 attack-tendril SPRITES are non-uniform (blue
  with random yellow/orange). OBJ-palette / sprite-attribute issue, separate from
  the bg_sweep BG table.
- **Riff 2nd pass:** optional multi-color along Riff's actual anatomy — but NOT
  on a tile-row boundary (that's what made the original split look like a hard
  horizontal line).
