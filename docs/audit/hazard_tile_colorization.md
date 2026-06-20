# Audit: Hazard Tile Colorization (rotating spikes + stage-2 lava)

## 2026-06-18 UPDATE: rotating spike palette FIXED + stage-5/7 lava handled
The "rotating spike cylinders (tiles 0x2A 0x2B 0x2C 0x2D 0x2E + 0x3A 0x3B 0x3C
0x3D) currently pal 5 reads as fire/lava, desired metallic (slate/steel)"
issue from the 2026-06-14 TL;DR is **RESOLVED**. These tiles now map to pal 6
(metallic) in the deployed builds (`dungeon_table_spikes_metallic` regression
test in the pre-commit hook locks this in — iter 16 fix).

Stage-5/7 LAVA was also added without conflicting with spike tiles, via a
**per-frame override at bank13:0x7E00** that patches 0xDA00 only when FFBA
matches the lava-stage levels (5 or 7). The override is asserted by tests
`lava_stage5_override`, `lava_stage7_override`, and `lava_off_at_ffba0`
(iter 17 fix). The "single-table architecture constraint" was sidestepped
by making the dispatch run-time (FFBA-conditional, scene-local) instead of
table-side.

Stage-2 lava (still UNKNOWN per the original audit) is independent: the
v8.9-lava milestone (2026-06-14) shipped the stages-5/7 fix; stage-2 lava
remains untreated because no stage-2 BG dump exists in the repo.

## 2026-06-20 UPDATE (iter 107-108): exhaustive stage-2-to-6 lava audit — ONLY stages 5+7 are lava

Reached all 6 dungeon stages (FFBA=1..6 = stages 2-7) via the level-
select probe from `docs/audit/stage2_lava.md` §1. Histograms +
screenshots show:

| Stage (FFBA) | Top BG tiles                              | Distinctive color    | Lava-styled? |
|--------------|-------------------------------------------|----------------------|--------------|
| 2 (FFBA=1)   | 0x07=205 (20.0%), 0x01=85                 | #A52100=88           | NO           |
| 3 (FFBA=2)   | 0x11=245 (23.9%), 0x01=110, 0x02=38       | #AD29B5=164 (purple) | NO           |
| 4 (FFBA=3)   | 0x13=51, 0x12=51, 0x11=43, 0x10=43        | #A52100=114          | NO           |
| 5 (FFBA=4)   | 0x12=65, 0x13=65, 0x02=64, 0x03=62        | molten field         | **YES**      |
| 6 (FFBA=5)   | 0x3D=58, 0x3E=58, 0x6A=31, 0x6B=31        | #A52100=61           | NO           |
| 7 (FFBA=6)   | 0x19=201 (dominant), 0x1A=73              | molten field         | **YES**      |

Only stages 5 and 7 have the molten field-tile pattern that the
existing `build_lava_override` covers (LAVA_STAGE5_IDS + LAVA_STAGE7_IDS
in `build_v301_teleport.py:173-174`). Other stages have distinct BG
art (purple in stage 3, diagonal stripes in stage 6, brown-red rock
outline accents in stages 2/4) but none has a large molten-field area
that needs pal 5 repainting.

**The lava coverage is COMPLETE.** No new overrides needed for stages
2/3/4/6. The "stage-2 lava (still UNKNOWN)" reference in MEMORY.md /
older audits is now fully resolved: every stage characterized.

---

# (original 2026-06-14 audit follows)


Static analysis only. Goal: give DISTINCT colors to the rotating SPIKE
hazard and to stage-2 LAVA via the dungeon bg_table at bank13:0x7000.

Date: 2026-06-14. Auditor: RE subagent.

---

## TL;DR

| Element | Tile IDs | Confidence | Current pal (deployed v3.01) | Current look | Desired |
|---|---|---|---|---|---|
| Rotating spike cylinders | `0x2A 0x2B 0x2C 0x2D 0x2E`, `0x3A 0x3B 0x3C 0x3D` | **HIGH** (pixel-verified) | **pal 5** (BG5 = white/yellow/red) | reads as fire/lava | metallic (slate/steel) |
| Thrusting wall spikes | `0x47 0x57` | **LOW** (yaml-claimed, NOT observed in any dump) | pal 6 (wall slate) | wall gray | metallic — already close |
| Stage-2 LAVA | **UNKNOWN** | **NONE** — needs a dynamic probe | n/a (no stage-2 data exists) | n/a | orange/red |

Net: the spikes are CURRENTLY painted with the lava palette (pal5 = yellow/red).
That is exactly backwards from the goal. Lava tile IDs are unidentified and
**cannot be determined statically** — every captured BG dump is level 1
(FFBA=00); there is zero stage-2 tile data in the repo.

There is also a **single-table architecture constraint** (see "Critical
constraint" below) that makes "spikes metallic AND lava orange" only
trivially achievable if spikes and lava use disjoint tile IDs. If lava
reuses 0x2A-0x3D (likely, given the game's heavy tile-ID reuse across
areas), the dungeon bg_table alone cannot separate them.

---

## 1. Where the dungeon bg_table lives and how it is consumed

- ROM location: **bank 13 (0x0D), CPU 0x7000** → file offset **0x37000**,
  256 bytes (one palette index per tile ID).
- Source of truth: `scripts/build_v301_gdma.py` function `_bg_table()`
  (lines 35-75). `BG_TABLE_BYTES` is written at `w(bg_table_addr, ...)`
  with `bg_table_addr = 0x7000` (build_v301_gdma.py:426, :454).
- Runtime path: the colorize handler's cold-boot copies ROM `0x7000` → WRAM
  `0xDA00` (build_v301_gdma.py:529-538). The **inline tile+attr copy at
  bank1:0x42A7** then does, per tile, `B=0xDA; C=tile_id; A=[BC]` to fetch
  the attr/palette byte and writes it to VRAM bank-1 (docs/inline_tile_attr_copy.md:107-126).
  `bg_sweep` (bank13:0x6CD0) is the safety net and also reads WRAM 0xDA00.
- Per-scene swap: in the teleport build (`scripts/build_v301_teleport.py`),
  `scene_detect` (build at :165) overwrites WRAM 0xDA00 with a per-BOSS
  table when D880 ∈ 0x0C..0x14; otherwise it restores the dungeon table at
  0x7000. **Dispatch is on D880 (scene), NOT on FFBA (stage/level).** All
  dungeon roaming — every stage — uses the one 0x7000 table.

Verified deployed bytes (both `penta_dragon_dx_v301.gb` and `..._FIXED.gb`,
byte-identical at file 0x37000):

```
pal1: 0x88..0xDF                         (items)
pal5: 0x2A 0x2B 0x2C 0x2D 0x2E 0x3A 0x3B 0x3C 0x3D   (spike cylinders)
pal6: 0x14 0x16 0x17 0x18 0x19 0x1A 0x1C 0x1E
      0x25 0x26 0x34 0x35 0x36 0x37 0x38
      0x41 0x42 0x44 0x45 0x46 0x47 0x48 0x49
      0x54 0x55 0x56 0x57 0x59             (walls/corners, incl. 0x47/0x57)
pal0: everything else (131 tiles — floor/void/default)
```

NOTE: `docs/inline_tile_attr_copy.md:124` and
`docs/inline_hook_analysis_v300.md:111` say `0x47, 0x57` are pal5 — those
docs are **STALE**. The live `_bg_table()` (build_v301_gdma.py:55-65) puts
0x47/0x57 in the pal-6 wall list and EXCLUDES them from the pal-5 hazard
list, and the shipped ROM bytes confirm pal6. The 2026-05-23 regression note
(build_v301_gdma.py:38-46) is the authority: 0x47/0x57=pal5 caused visible
orange wall-corner artifacts and was reverted.

---

## 2. Rotating spike tile IDs — HIGH confidence (pixel-verified)

Three independent sources agree:

1. **bg_table source comment** (build_v301_gdma.py:61-65): "Hazards: spike
   cylinders only → pal 5 … `0x2A,0x2B,0x2C,0x2D,0x2E,0x3A,0x3B,0x3C,0x3D`".
2. **Authoritative category map** `palettes/bg_tile_categories.yaml:86-96`
   — `hazards_spike_cylinder: tiles [42,43,44,45,46,58,59,60,61]` =
   `0x2A-0x2E, 0x3A-0x3D`, "Rotating spike cylinders".
3. **Pixel decode of a real capture.** `tmp/bg_dumps/dump_level1_cat_fish_moth_spike_hazard_orb_item.txt`
   (the dump behind the screenshot `cal_level1_cat_fish_moth_spike_hazard_orb_item.png`,
   captured at D880=02 dungeon, FFBA=00, FFBD=03). Decoding the 2bpp TILE
   patterns for 0x2A/0x2B/0x2C/0x2D and 0x3A/0x3B/0x3C/0x3D shows the
   classic diagonal barber-pole "rotating cylinder" graphic:

   ```
   tile 0x2A          tile 0x2B          tile 0x2C (bright)   tile 0x3C (bright)
   .. :::::           ::::: ..           ::.#####            ##.:::::
   . ::::::           :::::: .           :.######            ##.:::::
    :::::             ::::: ..           .#####..            ###..:::
   ::::: ..           .. :::::           #####.::            #####.::
   ```
   0x2A/0x2B (top half) + 0x3A/0x3B (bottom half) = one 2×2 metatile
   rotation phase; 0x2C/0x2D + 0x3C/0x3D = the highlighted animation frame
   (color 3 = brightest). `0x2E` is a horizontal bar tile (spike base/rail).

- Cross-room consistency: the 0x2A graphic is byte-identical in FFBD=03 and
  FFBD=07 dumps (same decompressed VRAM pattern), so these IDs mean "spike
  cylinder" throughout the level-1 dungeon, not a per-room coincidence.
- Frequency: spike tiles appear in FFBD=03 (72), 03-alt (58), 07 (249),
  05 (10) across the dumps — a real, recurring hazard, not a one-off.

**Confidence: HIGH.** These nine tile IDs ARE the rotating spikes.

### Thrusting wall spikes 0x47/0x57 — LOW confidence
`bg_tile_categories.yaml:99-106` claims 0x47/0x57 are "Thrusting wall
spikes," but **neither ID appears in ANY of the 16 BG dumps** (verified:
0x47/0x57 absent from the spike-room dump and all others). They are used as
wall corners far more often (hence the pal6 revert). Do NOT recolor them as
hazards without a dynamic probe that catches a thrusting-spike room.

---

## 3. Stage-2 LAVA tile IDs — UNKNOWN (no static data)

- **No stage-2 data exists in the repo.** All 16 `tmp/bg_dumps/dump_*.txt`
  are FFBA=00 (level 1). There is no lava/fire/magma dump, screenshot, or
  documented tile ID anywhere in `docs/` or `reverse_engineering/notes/`.
- `reverse_engineering/notes/gap_banks_4_to_11.md:248-252` only speculates
  that banks 6-9 hold "animated tile graphics (water, lava, fire cycles)";
  no tile IDs are pinned.
- **Doc disagreement on whether stage 2 even exists as a distinct tileset:**
  - Project MEMORY.md: "7 stages."
  - `reverse_engineering/notes/game_memory_map.md:82`: "The game is one
    continuous dungeon with 7 interconnected rooms — there are no separate
    'levels 2-5'." Room warps change enemy/event behavior, NOT the tilemap.
  - `docs/stage_detection.md` treats FFD0=0x01 as the bonus jet stage and
    0x02-0x04 as "presumably Levels 2-5 (not yet tested)".
  Reconciliation: FFBA (0-8) is the boss/level counter that advances as you
  beat bosses; later FFBA values likely re-skin rooms (lava theme) by
  decompressing a different tile SHEET into the SAME VRAM IDs. That is the
  decompression model in `gap_tile_decompression.md` (4:1 LUT at 0xA400 →
  same tile-ID slots, different pixels per stage). If true, **stage-2 lava
  almost certainly reuses tile IDs that are floor/spikes in stage 1.**

**Confidence on lava IDs: NONE.** A dynamic probe is mandatory (see §6).

---

## 4. Critical constraint — one dungeon table for all stages

The dungeon bg_table at 0x7000 is the ONLY table used while roaming, for
EVERY stage (scene_detect dispatches on D880, not FFBA — build_v301_teleport.py:165-227).
Consequences:

- If lava and spikes use DISJOINT tile IDs → easy: give each its own pal in
  the single table. Done.
- If lava REUSES spike/floor IDs (likely) → a single static table cannot
  make tile 0x2A "metallic" in stage 1 AND "lava" in stage 2. You would
  need either:
  (a) a per-STAGE table swap keyed on FFBA (extend scene_detect to also read
      FFBA and pick a "dungeon-stage-2" table), or
  (b) accept one shared hazard color for both (e.g., spikes = lava orange,
      which is the CURRENT behavior), or
  (c) distinguish by the decompressed pixels rather than the tile ID
      (not feasible with the current ID-indexed table).

Option (a) is the clean fix and reuses the existing 256-byte-page table
infrastructure (0x7200+ already holds 9 arena tables); a "dungeon stage 2"
table is just one more page plus an FFBA branch in scene_detect. But it is
blocked on knowing the lava tile IDs (§3/§6).

---

## 5. Palettes — current CRAM and what's free

Deployed BG CRAM (bank13:0x6800, file 0x36800; matches penta_palettes_v097.yaml):

```
BG0 7FFF 7E94 3D4A 0000  Dungeon: white / light blue / teal / black   (floor)
BG1 7FFF 001F 0012 0000  cherry red                                   (items)
BG2 7FFF 7E1F 3807 0000  purple/magenta        <- UNUSED by dungeon table
BG3 7FFF 03E0 0160 0000  green                 <- UNUSED by dungeon table
BG4 7FFF 7FE0 3D80 0000  cyan/teal             <- UNUSED by dungeon table
BG5 7FFF 03FF 001F 0000  white / YELLOW / RED / black  (spikes today = lava-ish)
BG6 7FFF 6F7B 2D4A 0000  slate / blue-gray / dark slate (walls)
BG7 7FFF 7E94 3D4A 0000  clone of BG0          <- effectively UNUSED (=pal0)
```

Free palette slots for a new hazard color: **BG2, BG3, BG4, BG7**.

A fitting **metallic spike** ramp (steel/gunmetal, BGR555):
`["7FFF", "5294", "2529", "0000"]` (bright steel highlight, mid gunmetal,
dark steel, black). This reads distinctly "metal," not red.

The existing **BG5** (`7FFF 03FF 001F` = white/yellow/red) is already a fine
LAVA palette. For a more molten look use
`["7FFF", "021F", "000F", "0000"]` (white-hot / orange / dark red / black).

---

## 6. Probes needed (the only blockers)

1. **Lava tile IDs (mandatory).** Reach a lava area (advance FFBA past
   stage 1, or load a stage-2 save state) and dump the BG tilemap + tile
   patterns exactly like the existing dumps. Reuse the dump format that
   produced `tmp/bg_dumps/dump_level1_*.txt` (HIST + TILE + TILEMAP lines).
   Then ASCII-render the patterns (as in this audit) to identify the molten
   tile IDs and record FFBA at the time. Also record whether those IDs
   overlap the spike set 0x2A-0x3D — this decides §4 option (a) vs (b).
   Ask the user for a stage-2 / lava save state to anchor this; none exist
   in the repo.

2. **Thrusting-spike confirmation (optional).** Capture a room with active
   thrusting spikes to confirm whether 0x47/0x57 (or other IDs) are the
   real thrusting-spike graphic before recoloring them.

3. **Stage-table architecture decision (depends on #1).** If lava reuses
   spike IDs, confirm FFBA value(s) for the lava stage so scene_detect can
   branch dungeon-table vs lava-table on FFBA.

---

## 7. Feasibility + plan

### Part A — make rotating spikes METALLIC (READY, no probe needed)

The spike IDs are known with high confidence. Two equally simple options:

**A1 (recommended): repoint spikes to a free palette, leave BG5 as lava.**
- In `scripts/build_v301_gdma.py` `_bg_table()` (lines 61-65), change the
  spike loop from `table[i] = 5` to a free slot, e.g. `= 2` (or 3/4/7).
  Tiles: `0x2A 0x2B 0x2C 0x2D 0x2E 0x3A 0x3B 0x3C 0x3D`.
- In `palettes/penta_palettes_v097.yaml`, set that palette's `colors` to the
  metallic ramp `["7FFF","5294","2529","0000"]` (e.g. repurpose BG2, which
  is currently the unused purple slot).
- Result: spikes = steel; BG5 stays free to be the lava palette later.
- Mirror the same one-byte-per-tile change in
  `scripts/build_v301_teleport.py` (it imports a different `_bg_table`
  path — verify it builds the dungeon 0x7000 table from the same source or
  patch both) and in `tmp/bg_dumps/analyze.py:204-211` if that generator is
  ever re-run.

**A2 (smallest diff): recolor BG5 itself to metal.** One YAML edit
(`BG5.colors → ["7FFF","5294","2529","0000"]`), no bg_table change. But this
forfeits BG5 as the lava palette, so only choose A2 if lava will get a
different free slot.

Effort: SMALL. Risk: a tile that is dual-use (e.g. 0x2E "bar") would also
change color — verify 0x2E is only ever the spike rail (it rendered as a
plain horizontal bar; low risk). Build then mGBA/MiSTer screenshot the
spike room (FFBD=03/07, the `cat_fish_moth_spike_hazard` scene) to confirm.

### Part B — give stage-2 LAVA its own orange/red (BLOCKED on probe #1)

1. Run probe #1 to get lava tile IDs + the FFBA value of the lava stage.
2. If lava IDs are DISJOINT from spike IDs: add `table[id] = 5` (BG5
   yellow/red, or the molten ramp above) for the lava IDs in `_bg_table()`.
   One table, done. Effort SMALL.
3. If lava IDs OVERLAP spike/floor IDs: extend `scene_detect`
   (build_v301_teleport.py:165) to also read FFBA and, for the lava
   stage(s), copy a NEW "dungeon-lava" 256-byte table (place it on a free
   bank-13 page, e.g. 0x7B00 region after the arena tables / posmaps — check
   for collision with `POSMAP_DATA_ADDR = 0x7B00`, build_v301_teleport.py:59)
   into WRAM 0xDA00 instead of the 0x7000 table. In that lava table, the
   shared IDs map to BG5 (lava); the stage-1 0x7000 table keeps them
   metallic/floor. Effort MEDIUM (new table page + FFBA branch + free-page
   allocation that dodges posmap data).

---

## 8. Exact file changes

- `scripts/build_v301_gdma.py` — `_bg_table()` lines 61-65: change spike
  palette index (Part A). For lava (Part B option 2) add a lava-ID loop.
- `palettes/penta_palettes_v097.yaml` — BG-palette `colors` for the spike
  palette (metallic) and/or BG5 (lava). Lines 85-91 (BG5/BG6 block).
- `scripts/build_v301_teleport.py` — only if pursuing per-stage tables
  (Part B option 3): extend `build_scene_detect` (lines 165-227) with an
  FFBA branch + a new dungeon-lava table page; verify free-page placement
  vs `POSMAP_DATA_ADDR` (line 59).
- (Housekeeping) fix stale `0x47/0x57 = pal5` claims in
  `docs/inline_tile_attr_copy.md:124` and `docs/inline_hook_analysis_v300.md:111`.
- (Optional) `tmp/bg_dumps/analyze.py:204-218` generator if regenerating the
  table from dumps.

---

## 9. Confidence summary

- Rotating spike tile IDs `0x2A-0x2E, 0x3A-0x3D`: **CONFIDENT** (pixel-decoded
  from a real level-1 capture + 2 corroborating source maps).
- Spikes currently get **pal5 (BG5 = white/yellow/red)** — CONFIDENT
  (deployed ROM bytes at file 0x37000).
- Thrusting spikes `0x47/0x57`: NOT confident — yaml-claimed, never observed;
  currently pal6 (wall). Needs probe.
- Stage-2 lava tile IDs: **UNKNOWN** — no stage-2 data exists; mandatory
  dynamic probe (§6 #1). The single-table architecture (§4) means the lava
  fix is only "easy" if lava IDs are disjoint from spike IDs, which a probe
  must confirm.
