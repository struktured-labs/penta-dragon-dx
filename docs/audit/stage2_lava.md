# Stage-2+ Lava Dungeon — REACHED & TILE IDs IDENTIFIED

> **Update 2026-07-23:** implemented with stricter containment than the
> original shared-table proposal. Stages 2–4 and 6 use a neutral table; only
> audited Stage 5/7 field IDs receive lava palette 5. Fresh visible-map probes
> and 8,000-frame-per-stage soaks report zero unsafe attributes or lava
> mismatches. The analysis below is retained as the discovery record.

Date: 2026-06-14. Method: dynamic mGBA probe on `rom/working/penta_dragon_dx_teleport.gb`
(built via `python3 scripts/build_v301_teleport.py`). This resolves the open
blocker in `docs/audit/hazard_tile_colorization.md` §3/§6 (stage-2 lava tile
IDs were "UNKNOWN — no static data"). Later stages ARE reachable, they DO use a
distinct tileset, and the molten/field tile IDs OVERLAP stage-1 floor/wall IDs.

---

## TL;DR

- **Reached later stages** (FFBA = 1..6) as live, rendering dungeon rooms
  (FFC1=1) via the in-game **LEVEL-SELECT** path (the cleanest, no-RE-needed
  reproducible hack — see §1). The mini-boss/spawn-pointer hack (FFAC/FFAD in
  `tmp/autoplay_full_game.lua`) does NOT change the tileset; level-select does.
- **Later stages decompress a DIFFERENT tile sheet into the SAME VRAM tile-ID
  slots.** Confirmed by pixel-decoding the same tile IDs across stages — they
  are byte-different graphics. This validates `gap_tile_decompression.md`
  (4:1 LUT → same IDs, different pixels per stage).
- **The later-stage dungeon FLOOR is a mottled / bubbly field texture** (the
  "lava"/magma look). Its tile IDs OVERLAP stage-1 floor & wall IDs:
  - Stage 5 (FFBA=4) field: **`0x02 0x03 0x12 0x13`** (+ `0x04 0x05 0x14 0x15`)
  - Stage 7 (FFBA=6) field: **`0x19`** (dominant, 201/360 cells) + **`0x1A`**
  - In stage 1 those exact IDs are structured floor (`0x02-0x05`) and solid
    wall blocks (`0x12-0x15`, `0x19`, `0x1A`).
- **Because lava reuses stage-1 floor/wall IDs, a single shared dungeon
  bg_table CANNOT make them lava in later stages without breaking stage 1.**
  The fix is a **per-FFBA dungeon-table swap in `scene_detect`** (audit §4
  option (a)) — see §5. BG5 (`7FFF 03FF 001F` = white/yellow/red) is already a
  lava palette and is currently FREE (spikes were moved to pal 6 metallic).
- Screenshots: `tmp/lava_stage4_ffba3.png`, `tmp/lava_stage5_ffba4.png`,
  `tmp/lava_stage7_ffba6.png` (rendered in the blue dungeon palette — the point
  of the per-stage table is to retint these to orange/red).

Caveat on "lava color": the original is a DMG (monochrome) game; later stages
are not literally red in the source. "Lava" here = the molten/field tile SHAPES
that later stages use for ground. Making them read as lava is a palette choice
(BG5), which is exactly what the bg_table change in §5 does.

---

## 1. The reproducible hack (LEVEL-SELECT) — Lua snippet

Game-start dispatch at ROM `0x3B41` does `LD DE,DCFD; LD A,(DE); AND A;
JP NZ,0x7393`. If **DCFD != 0** when you confirm "start", control goes to the
**level-select routine at 0x7393** instead of a new game. Level-select clears
FFBA to 0, runs an input loop at `0x73C3` where **UP increments FFBA / DOWN
decrements**, and **A confirms**: the confirm path (`0x7413`) reads FFBA, and
for FFBA>0 copies a 0x20-byte checkpoint from SRAM (slot table at ROM `0x75F3`
→ `0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8`) into `0xDCBB`, then resumes
the game — loading **that stage's dungeon (with its own decompressed tileset)**.

So: force DCFD=1, press START at the title, force FFBA to the target stage,
seed the SRAM slot so the checkpoint copy is sane, press A. mGBA Lua:

```lua
-- Reach stage N dungeon (N = FFBA = 1..8) and dump its VRAM tiles.
local TARGET = 4            -- FFBA: 1=stage2 ... 6=stage7 (lava-ish), etc.
local KEY_A, KEY_START = 0x01, 0x08
local f, phase, seeded, started, conf = 0, "title", false, false, 0

local function seedSRAM()    -- 6 checkpoint slots; payload = DCBB(0xFF)+zeros
  emu:write8(0x0000, 0x0A)   -- MBC: enable cartridge SRAM
  for _,b in ipairs({0xBF00,0xBF28,0xBF50,0xBF78,0xBFA0,0xBFC8}) do
    emu:write8(b, 0xFF); for i=1,0x1F do emu:write8(b+i, 0x00) end
  end
end

callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)                       -- force level-select branch
  if not seeded and f >= 100 then seedSRAM(); seeded = true end
  local d880, ffc1 = emu:read8(0xD880), emu:read8(0xFFC1)

  if phase == "title" then                        -- splash → title, then START
    if f >= 300 and f < 306 then emu:setKeys(KEY_START)
    elseif f >= 360 and f < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if f >= 330 then phase = "ls" end
    return
  end
  if phase == "ls" and not started then           -- in level-select input loop
    emu:write8(0xFFBA, TARGET); seedSRAM()        -- force stage, keep SRAM sane
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A) else emu:setKeys(0) end
    if ffc1 == 1 or d880 == 0x18 then started = true; conf = f; phase = "play" end
    return
  end
  if phase == "play" then                          -- in the stage-N dungeon
    emu:write8(0xDCDD,0x17); emu:write8(0xDCDC,0xFF); emu:write8(0xDCBB,0xF0)
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0x10 + ((f % 4 < 2) and KEY_A or 0))  -- walk right, fire
    if f > conf + 700 then
      emu:write8(0xFF4F, 0)                        -- VBK=0 for BG tile reads
      local fh = io.open("/tmp/stageN_vram.bin","wb")
      for a = 0x8000, 0x97FF do fh:write(string.char(emu:read8(a))) end; fh:close()
      emu:screenshot("/tmp/stageN.png"); emu:stop()
    end
  end
end)
```

Run headless:

```bash
QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy timeout 90 \
  xvfb-run -a /home/struktured/bin/mgba-qt \
  rom/working/penta_dragon_dx_teleport.gb --script probe.lua -l 0 >/dev/null 2>&1
```

State bytes that get you there: **DCFD=0x01** (forced, selects level-select),
**FFBA = target stage 1..8** (forced in the level-select loop), SRAM slots
`0xBF00 + n*0x28` seeded with `FF 00*0x1F`. After confirm the engine sets
D880=0x18 (stage splash) then drops into the dungeon (D880=0x02..0x08; with the
all-zero checkpoint it tends to land in an active sub-state 0x04/0x06/0x08 —
still FFC1=1 and rendering the correct stage tileset).

Working probes used to gather this: `tmp/lava/ls_clean.lua`,
`tmp/lava/vram_capture.lua` (MODE=ls), decoder `tmp/lava/decode_tiles.py`.

### Approaches that did NOT change the tileset
- **FFAC/FFAD spawn-pointer switch** (`tmp/autoplay_full_game.lua`): swaps the
  per-level *enemy/boss spawn* table only; the BG tileset stays stage 1.
- **Boss teleport (SELECT+START combo)**: jumps to a boss *arena* (D880=0x0C..),
  not a later *dungeon*; arena art is its own tables (0x7200+), not the dungeon.
- **Forcing a boss "kill" via DCBB=0/1**: triggers the death cinematic
  (D880=0x17) and resets FFBA, not clean post-boss progression. (PyBoy probe
  `tmp/lava/pyboy_advance.py` from a curriculum arena state confirms this.)

---

## 2. Proof the tileset changes per stage (pixel decode)

VRAM bank-0 tile dump (`0x8000-0x97FF`, 384×16B). LCDC bit4=0 for all dungeon
captures → BG IDs 0-127 live at `0x9000` (signed). Same tile ID, different
stage = different pixels. Color values: `.`=0 `:`=1 `+`=2 `#`=3.

**Tile `0x12`** (stage 1 = a solid WALL block; later stages = molten FIELD):

```
        STAGE 1 (FFBA=0)     STAGE 5 (FFBA=4)     STAGE 7 (FFBA=6)
        ########             :.:::.:.             .+:#:+#.
        ########             ::.:.:.:             ..+#:##:
        ########             .::::.:.             .+:#:#.+
        ########             ..::::.:             +:.#:.+#
        ########             .::..:::             .+#+:+##
        ++++++++             ::....:.             ..#:###+
        ::::::::             :.:...::             .+#+##+#
        ........             .:.:..:.             +:.####:
```

**Tile `0x19`** (stage 1 = solid WALL block; stage 7 = repeating molten field —
this is the dominant on-screen tile in the FFBA=6 room, 201/360 cells):

```
        STAGE 1 (FFBA=0)     STAGE 7 (FFBA=6)
        ########             .+:..+:.
        ########             ..+++:..
        ########             .+:..+:.
        ########             +:....++
        ########             .+:..+:.
        ++++++++             ..+++:..
        ::::::::             .+:..+:.
        ........             +:....++
```

**Tile `0x2A`** (stage 1 = the rotating-spike barber-pole; later stage = an
unrelated dense pattern — the spike IDs are ALSO reused):

```
        STAGE 1 (FFBA=0)     STAGE 5 (FFBA=4)
        ::.+++++             ::.:.::#
        :.++++++             #:::::+#
        .+++++..             .#::::++
        +++++.::             .#:::::+
        +++++.::             .#:::::+
        +++..:::             :.#:::++
        ++.:::::             :.#+++##
        ++.:::::             :.######
```

Whole-tileset diff (16-byte tile slots that differ): stage1 vs FFBA=4 = **205**
of 384; stage1 vs FFBA=6 = **207**. The BG tile sheet is wholesale replaced.

---

## 3. Lava (molten/field) tile IDs per stage, and OVERLAP analysis

On-screen tile-ID histogram of the captured dungeon room per stage (top IDs):

| Stage (FFBA) | Dominant FIELD tile IDs (the "lava"/ground) | Same IDs mean in STAGE 1 |
|---|---|---|
| Stage 5 (4) | **`0x02 0x03`** + **`0x12 0x13`** (floor pair-rows); also `0x04 0x05 0x14 0x15` | `0x02-0x05` = floor; `0x12-0x15` = wall blocks |
| Stage 7 (6) | **`0x19`** (201) + **`0x1A`** (73) | `0x19 0x1A` = wall edge/blocks (stage-1 pal-6 wall set) |

Overlap with the **rotating-spike set** `0x2A-0x2E, 0x3A-0x3D`
(`hazard_tile_colorization.md` §2): the spike IDs are also reused per stage
(see `0x2A` decode above) and appear sparsely in later rooms (doorway/edge),
but the later-stage **FIELD** tiles are the floor/wall IDs `0x02-0x05`,
`0x12-0x15`, `0x19`, `0x1A` — i.e. they **overlap stage-1 FLOOR and WALL, not
primarily the spikes.**

Conclusion for the audit's decision (§4): **lava REUSES stage-1 floor/wall
IDs.** A single static dungeon table cannot color tile `0x12` as "wall" in
stage 1 and "lava" in stage 5/7. → must use a **per-FFBA table swap** (§5).

---

## 4. Palette CRAM today (teleport ROM, file 0x36800)

```
BG0 7FFF 7E94 3D4A 0000  dungeon floor: white / lt-blue / teal / black
BG1 7FFF 001F 0012 0000  items/font: cherry red
BG2 7FFF 7E1F 3807 0000  purple        <- FREE for dungeon use
BG3 7FFF 03E0 0160 0000  green         <- FREE
BG4 7FFF 7FE0 3D80 0000  cyan/teal     <- FREE
BG5 7FFF 03FF 001F 0000  white / YELLOW / RED / black   <- LAVA-ready, FREE
BG6 7FFF 6F7B 2D4A 0000  slate / blue-gray (walls + spikes now metallic)
BG7 7FFF 7E94 3D4A 0000  clone of BG0  <- FREE
```

Note vs the older audit: spikes are now **pal 6 (metallic)**, so **BG5
(white/yellow/red) is FREE** and already reads as lava. For a more molten ramp
use `["7FFF","021F","000F","0000"]` (white-hot / orange / dark red / black).

---

## 5. Recommended bg_table change (per-FFBA dungeon table swap)

Because lava IDs overlap stage-1 floor/wall, do option (a) from
`hazard_tile_colorization.md` §4: add a **per-FFBA dungeon table** alongside the
existing per-D880 arena tables, and branch in `scene_detect`.

1. **New lava dungeon table page(s)** in bank 13. The arena tables occupy
   `0x7200-0x7AFF` and posmap RLE starts at `0x7B00`
   (`build_v301_teleport.py:59` `POSMAP_DATA_ADDR = 0x7B00`). The posmaps use
   `0x7B00-0x7DF2` (limit 0x7FE0). There is room at **`0x7DF2-0x7FE0`** (~0x1EE
   bytes ≈ one 256B page) for a single shared "lava dungeon" table, or relocate
   posmaps to free a clean 0x7E00 page. Build it like the dungeon table at
   `0x7000` but map the molten field IDs to **pal 5 (lava)**:
   - Stage-5 style field: `0x02 0x03 0x04 0x05 0x12 0x13 0x14 0x15` → pal 5
   - Stage-7 style field: `0x19 0x1A` → pal 5
   - keep walls/edges that are NOT the field on pal 6, items on pal 1.
   (Capture the exact per-stage field-ID set per FFBA before finalizing — the
   set differs by stage; §3 lists the two observed.)

2. **Extend `scene_detect`** (`build_v301_teleport.py:165 build_scene_detect`).
   It currently dispatches on **D880**: arena (0x0C..0x14) → arena table,
   else → dungeon table at `0x7000`. Add: when it would pick the dungeon table
   (non-arena scene), also read **FFBA**; for the lava stages (e.g. FFBA>=4,
   or a specific set) copy the **lava dungeon table** into WRAM `0xDA00`
   instead of `0x7000`. Keep DF0D as the change-detect cache, but include FFBA
   in the "did it change" test so the swap re-runs on stage change, not just
   D880 change.
   - Cheapest variant if one shared lava look is acceptable for all later
     stages: a single `0x7E00` lava table + `if FFBA >= 4: use lava else
     dungeon`. If each stage needs its own field-ID map, make it FFBA-indexed
     like the arena pages (one 256B page per stage that has lava).

3. **Stage-1 stays untouched** (FFBA=0 → 0x7000 table → walls metallic/floor
   blue, spikes pal 6). Only later FFBA stages get the lava table, so tile
   `0x12` is "wall" in stage 1 and "lava field" in stage 5/7 with no conflict.

4. Mirror any `_bg_table()` constants in `scripts/build_v301_gdma.py` if that
   path is also built; the teleport build imports it (`build_v301_teleport.py`
   top imports `build_v301`/`create_inline_tile_copy_tileonly`).

Effort: MEDIUM (one new bank-13 page that dodges `POSMAP_DATA_ADDR`, plus an
FFBA branch in `scene_detect`). Risk: tile IDs that are dual-use within a single
later stage (field vs a real wall using the same ID) — verify per-stage by
capturing a few rooms before locking the field-ID list. Validate by re-running
the §1 level-select probe per FFBA and screenshotting; the field should render
orange/red (BG5) instead of blue.

---

## 6. Files / artifacts

- Screenshots: `tmp/lava_stage4_ffba3.png`, `tmp/lava_stage5_ffba4.png`,
  `tmp/lava_stage7_ffba6.png` (also `tmp/lava/*.png`).
- VRAM dumps: `tmp/lava/vram_normal_stage1_vram.bin` (stage 1 baseline),
  `tmp/lava/vram_ls_ffba4_vram.bin` (stage 5), `tmp/lava/vram_ls_ffba6_vram.bin`
  (stage 7); tilemaps `*_tilemap.bin`; headers `*_hdr.txt`.
- Probes: `tmp/lava/ls_clean.lua`, `tmp/lava/vram_capture.lua`,
  `tmp/lava/ls2_probe.lua`, `tmp/lava/ls3_probe.lua`.
- Decoder: `tmp/lava/decode_tiles.py`
  (`diff a.bin b.bin`, `show a.bin 0x12 0x19 ...`, `tilemap map.bin`).
- All under a gitignored `tmp/` — not committed.
