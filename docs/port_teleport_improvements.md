# Port Plan: Teleport Good Parts → Production-Plus Build

**Goal**: Extract the 8 GOOD changes from `build_v301_teleport.py` that improve colorization quality (arena boss colors, title screen attrs, cursor visibility, scene-aware table switching, lava, HUD) and merge them into `build_v301_gdma.py` (which produces `penta_dragon_dx_FIXED.gb`), WITHOUT the teleport combo handler (SELECT+START), landing-pad/stack-redirect, or any VBlank-overhead features that cause instability.

**Target output**: `rom/working/penta_dragon_dx_production_plus.gb` — a stable build with the gold-standard teleport features, safe for MiSTer.

---

## 1. GOOD changes (port to production)

### G1: Arena-dispatched inline hook (179 bytes, tile+attr on title/dungeon, tile-only in boss arenas)

**Where in teleport**:
- `build_v301_teleport.py` line 43 — imports `create_inline_tile_copy_tileonly` from `build_v301_gdma`
- `build_v301_teleport.py` lines 1194-1199 — calls `create_inline_tile_copy_tileonly(arena_neutralize_d880=None)` and writes to `rom[0x42A7]`. Note: currently passes `None` (no arena dispatch), so it writes a plain tile+attr copy identical to the production hook at `create_inline_tile_copy_tileonly` line 90.

**Wait — the teleport actually writes the SAME hook.** The arena dispatch (arena_neutralize_d880 parameter) is not currently active. Let me verify: teleport line 1194: `neut = create_inline_tile_copy_tileonly(arena_neutralize_d880=None)`. This is equivalent to the tile+attr copy without arena dispatch — i.e., the same hook as production.

**Actual G1 fix**: The production build uses `create_inline_tile_copy_pure_tileonly()` (line 899 of gdma.py) — a 56-byte hook that copies tiles ONLY. The teleport uses `create_inline_tile_copy_tileonly()` — a ~179-byte hook that copies tiles AND attrs with bg_table lookup.

**What needs to happen**: Replace the `create_inline_tile_copy_pure_tileonly()` call at gdma.py line 899 with `create_inline_tile_copy_tileonly()`. Both functions exist in `build_v301_gdma.py` already. The tile+attr version is ~179 bytes (fits in the 199-byte budget at 0x42A7-0x436D).

**Files affected**:
- `build_v301_gdma.py` lines 899-909: change from `create_inline_tile_copy_pure_tileonly()` to `create_inline_tile_copy_tileonly()`

**Why this is GOOD**: The tile+attr hook writes attrs immediately when the game writes tiles to VRAM. This is critical for the title screen — animated title tiles get attrs immediately rather than waiting for bg_sweep latency. Without it, real hardware shows white stripes + colored sprite letters on the title screen (the old "splotch" bug). The pure-tile-only hook was a workaround for v3.01's GDMA+attr_comp architecture, which we're removing anyway.

**Minimal patch**:

In `build_v301_gdma.py`, replace:
```python
    inline_code = create_inline_tile_copy_pure_tileonly()
```
with:
```python
    inline_code = create_inline_tile_copy_tileonly()
```

This is a 1-line change. Both functions exist in the same file.

---

### G2: Boss bg_tables (all 9 boss arena palette tables)

**Where in teleport**:
- `build_v301_teleport.py` lines 217-237 — defines `_table_from_dict()` and per-boss builders that load from `arena_tables_data.py`
- `build_v301_teleport.py` lines 1020-1041 — writes 9 × 256-byte tables to bank13 at `0x7200` through `0x7A00` (256 bytes apart)
- `scripts/arena_tables_data.py` — the full data dict

**What needs to happen**: Copy the 9 boss bg_table definitions into `build_v301_gdma.py` and write them to bank13 in the same layout. These tables are the O(1) tile→palette lookup data that scene_detect loads per arena. The production build has only the dungeon bg_table at 0x7000.

**Files affected**:
- `build_v301_gdma.py` — add import of `arena_tables_data`, add 9 table builders, add write logic for 0x7200-0x7A00
- Must import `arena_tables_data.py` (already exists in scripts/)

**Bank13 layout change**:
```
0x7000  dungeon bg_table (existing, 256 bytes)
0x7200  Shalamar    bg_table (256 bytes)
0x7300  Riff        bg_table
0x7400  Crystal Dragon
0x7500  Cameo
0x7600  Ted
0x7700  Troop
0x7800  Faze
0x7900  Angela
0x7A00  Penta Dragon
```

**Minimal patch**: Add to `build_v301_gdma.py`:

```python
from arena_tables_data import ARENA_TILE_PAL

# Per-boss bg_table builders (same as teleport)
def _table_from_dict(name: str) -> bytes:
    t = bytearray(256)
    for tile_id, pal in ARENA_TILE_PAL.get(name, {}).items():
        t[tile_id & 0xFF] = pal & 7
    t[0xFF] = 0
    return bytes(t)

ARENA_NAMES = ["shalamar", "riff", "crystal_dragon", "cameo", "ted",
               "troop", "faze", "angela", "penta_dragon"]
ARENA_BASE_ADDR = 0x7200

# After the dungeon bg_table write at line 567:
for i, name in enumerate(ARENA_NAMES):
    addr = ARENA_BASE_ADDR + i * 0x100
    table = _table_from_dict(name)
    assert len(table) == 256
    off = bank13 + (addr - 0x4000)
    rom[off:off+256] = table
```

---

### G3: Position sweep system for boss arenas

**Where in teleport**:
- `build_v301_teleport.py` lines 1137-1184 — parses posmaps from `FOOTPRINT_LOG`, RLE-compresses them, writes blob + pointer table to bank13, writes RLE expander at 0x6D80, writes position_sweep at 0x7100
- `build_v301_teleport.py` line 1188: `patched_sweep = True` but the actual repoint is **DISABLED** (comment: "DISABLED: Using standard tile-ID bg_sweep directly for clean background/claws separation")

**TELEPORT CURRENTLY HAS POSITION SWEEP DEAD CODE.** The performance audit confirms this:
> "The dead position-sweep at bank13:0x7100 is NEVER CALLed. Whole-ROM scan finds ZERO callers/jumpers to 0x7100."

The position sweep is present in the ROM but never reached. The live colorize handler calls bg_sweep at 0x6CD0, not the position sweep.

**What this means for porting**: The position sweep code, RLE expander, posmap blob, and pointer table are ~950 bytes of dead bank13 space in teleport. They take up space but don't affect runtime. Since the arena inline hook (G1) + scene_detect (G4) + per-arena bg_tables (G2) already solve the arena alternation problem (scene_detect keeps 0xDA00 in sync, the tile+attr hook reads 0xDA00, bg_sweep reads 0xDA00), **the position sweep is not needed**.

**Recommendation**: DO NOT port position sweep. It is dead code in the teleport ROM too. The three-phase fix (arena inline dispatch + per-arena tables + WRAM bg_table sync) is the proven solution. The ~950 bytes of bank13 space can be reclaimed for the good features.

---

### G4: scene_detect routine

**Where in teleport**:
- `build_v301_teleport.py` lines 242-344 — `build_scene_detect()` function
- Called from `build_teleport_routine()` at line 742: `CALL SCENE_DETECT_ADDR`

**What it does**: Reads D880, compares to DF0D (previous scene). If same, fast-path RET (~16T). If different, copies the correct bg_table (dungeon, arena, splash) from bank13 ROM → WRAM 0xDA00. Also suppresses the colorize cold-boot copy (DF02=0x5A) to prevent the dungeon table from overwriting the arena table.

**Why needed**: Without scene_detect, WRAM 0xDA00 always has the dungeon bg_table. The inline hook and bg_sweep both read from 0xDA00. In arenas, the boss tiles would get dungeon palette mapping → wrong colors. Arena tables at 0x7200-0x7A00 are meaningless without a dispatcher.

**Files affected**: `build_v301_gdma.py` — add `build_scene_detect()` function and write it to bank13 at 0x6FB0.

**Minimal patch**: Copy the `build_scene_detect()` function from teleport (lines 242-344) and its constants. Place it in `build_v301_gdma.py` and write the result to 0x6FB0.

Add to build_v301_gdma.py:

```python
SCENE_DETECT_ADDR = 0x6FB0
DF23_PREV_SCENE = 0xDF0D       # below bg_sweep scratch (0xDF10-0xDF2F)

def build_scene_detect(dungeon_addr: int, arena_base_addr: int,
                       splash_addr: int) -> bytes:
    # ... (copy entire function from teleport lines 242-344)
```

Then after writing bg_table:
```python
sd = build_scene_detect(bg_table_addr, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR)
# verify it fits between 0x6FB0 and 0x7000
assert SCENE_DETECT_ADDR + len(sd) <= bg_table_addr
w(SCENE_DETECT_ADDR, sd)
```

---

### G5: Cursor tile fix (0x73 → 0x80)

**Where in teleport**:
- `build_v301_teleport.py` lines 961-970 — 1-byte ROM patch at 0x3C59

**What it does**: Changes the tile ID written by the cursor handler from 0x73 (which maps to pal-0 in the dungeon bg_table → invisible) to 0x80 (maps to pal-1 red → visible). The user must press UP/DOWN at the title menu once to trigger the draw.

**Why GOOD**: The dungeon bg_table maps tile 0x80 → pal 1 (red). Without this fix, the cursor arrow at the title menu is invisible (white-on-white), making navigation impossible to see.

**Minimal patch**: Add to `build_v301_gdma.py` (same assertion + byte patch as teleport):

```python
assert rom[0x3C58:0x3C5A] == bytes([0x3E, 0x73]), \
    f"cursor LD A,0x73 site shifted: got {rom[0x3C58:0x3C5A].hex()}"
rom[0x3C59] = 0x80  # tile 0x73 → tile 0x80 (red in dungeon table)
```

---

### G6: Title screen header text (PENTA DRAGON DX + STRUKTURED LABS)

**Where in teleport**:
- `build_v301_teleport.py` lines 939-958 — builds a `title_list` byte sequence and writes it to bank1 at 0x4EA5

**What it does**: Replaces the default title text with "PENTA DRAGON DX" (game name on row 6), preserves logo, OPENING/GAME START menu, (c) JAPAN ART MEDIA credit, adds "STRUKTURED LABS" attribution on row 17. Fits within the original 126-byte region at 0x4EA5.

**Why GOOD**: Cosmetic branding improvement. The stock title screen has no spelled-out game name. This makes the ROM identifiable as Penta Dragon DX.

**Minimal patch**: Copy the exact title_list construction + write from teleport (lines 939-958) into `build_v301_gdma.py`:

```python
E = 0x9A
def _txt(s):
    return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
       0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]
title_list = bytes(
    [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]
    + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]
    + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]
    + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]
    + [0x04, 0x08] + _txt("OPENING START") + [E]
    + [0x04, 0x0A] + _txt("GAME    START") + [E]
    + [0x00, 0x0E, 0xC0, E]
    + [0x00, 0x0F] + JAM + [E]
    + [0x03, 0x11] + _txt("STRUKTURED LABS") + [E]
    + [E]
)
assert len(title_list) <= 126
assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
```

**Step 13**: Re-patch bg_sweep to read WRAM 0xDA00 (for per-scene table support):

```python
sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOP the FFC1 gate
w(bg_sweep_addr, bytes(sweep))
```

This replaces the production build's bg_sweep (which reads the ROM dungeon table at 0x7000) with one that reads WRAM 0xDA00. Since scene_detect keeps 0xDA00 in sync with the current scene, bg_sweep now writes correct arena attrs.

**Step 14**: Replace the colorize handler's bg_sweep → position sweep repoint (DON'T — keep bg_sweep).

Leave the colorize handler calling bg_sweep at 0x6CD0 (as it does in the production build). Do NOT repoint to the position sweep — the teleport's `patched_sweep = True` was explicitly DISABLED for good reason (background/claws separation with tile-ID mode is better).

## 5. Risk assessment

| Change | Risk | Rationale |
|--------|------|-----------|
| G1: tile+attr inline hook | **Low** — exists in v3.00, tested | Reverts a v3.01 regression back to known-working v3.00 behavior. 1-line change. |
| G2: boss bg_tables | **Low** — ROM data only | 9 × 256-byte tables, written to unused bank13 space. No runtime code change. |
| G3: position sweep | **Excluded** — dead code in teleport too | Position sweep was never called; the triple-fixture (inline hook + scene_detect + WRAM bg_sweep) is the proven solution. |
| G4: scene_detect | **Medium** — new code path | Adds ~56T/VBlank fast-path and ~4100T on scene change. The DF0D fix (moved outside bg_sweep scratch) is critical — without it, bg_sweep clobbers the cache byte. |
| G5: cursor tile fix | **Low** — 1-byte patch | Single byte change, proven in teleport. |
| G6: title header | **Low** — data only | Text in ROM, no code. |
| G7: STAT IRQ WRAM stub | **Medium** — timing impact | The iter 43 regression (slots 0/2 flip) was specifically with the ROM-resident prelude. The WRAM placement (0xDB50) should avoid it, per iter 10 findings. The cold-boot copy adds ~400T to the first VBlank. |
| G8: lava override | **Low** — small code, scene-guarded | Only runs in lava stages. The DF02=0x5A re-assert prevents the cold-boot race. |

## 6. Build order

1. Create `scripts/build_v301_production_plus.py` from `build_v301_gdma.py` with all 12 steps above
2. Run: `python scripts/build_v301_production_plus.py`
3. Output: `rom/working/penta_dragon_dx_production_plus.gb`
4. Test: compare byte-by-byte against teleport for the shared good features (boss tables, scene_detect, lava_override)
5. Test: verify title screen renders attrs (the v3.01 "splotch" test)
6. Test: verify cursor is visible at title menu (UP/DOWN press)
7. Test: full hook suite (65/114 tests that the teleport passes vs 62/114 for v3.01 production)
] + JAM + [E]
    + [0x03, 0x11] + _txt("STRUKTURED LABS") + [E]
    + [E]
)
assert len(title_list) <= 126
rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
```

---

### G7: WRAM stubs for STAT IRQ and level-select

**Where in teleport**:
- **STAT IRQ WRAM stub**: `build_v301_teleport.py` lines 419-461 — `build_stat_irq_wram_stub()`. Written to bank13 at 0x53F2, cold-boot copied to WRAM 0xDB50. STAT IRQ vector at 0x0048 patched to JP 0xDB50.
- **Level-select attr-clear stub**: `build_v301_teleport.py` lines 464-513 — `build_levelsel_attr_clear_stub()`. Written to bank13 at 0x53C2, cold-boot copied to WRAM 0xDB28. JP NZ at 0x3B47 patched to target WRAM stub.
- **Cold-boot copy**: lines 760-804 — sentinel-gated (DF0E=0x5A) copies from ROM to WRAM, part of the teleport routine.

**Teleport import in gdma.py iter 43**: build_v301_gdma.py lines 994-1017 already has a STAT-stub installation block (STAT_STUB_ROM_ADDR=0x53F2, STAT_STUB_WRAM=0xDB50) — it writes `build_stat_irq_wram_stub()` and patches the IRQ vector. The production gdma.py does NOT have this (it was part of the reverted iter 43 experiment).

**What needs to happen**:
- Add `build_stat_irq_wram_stub()` to gdma.py (or import from teleport)
- Write it to bank13 at 0x53F2
- Patch STAT IRQ vector at 0x0048 to JP 0xDB50
- Add cold-boot WRAM copy (but WITHOUT the teleport landing-pad mechanism — use a simpler approach)

**Why GOOD for boss arenas**: The STAT IRQ WRAM stub fixes Sara slot-1 alternation in boss fights by re-stamping OAM slot 1 with Sara's correct form palette on every STAT IRQ. The WRAM placement (vs ROM-resident) avoids the timing regression that affected dungeon scenes.

**Simpler port approach**: The teleport uses complex cold-boot copy from bank13 → WRAM via the teleport routine. For a production build, we can add a simpler cold-boot init block in the colorize handler's cold-boot path. Add a 4th cold-boot copy block (after the bg_table ROM→WRAM copy at gdma.py line 645).

**Level-select stub** — lower priority. The teleport's attr-clear for level-select is a workaround for stale attrs bleeding between screens. Evaluate whether the production build has this issue. The GDMA transfer should already handle stale attrs by overwriting VRAM every frame. Skip unless testing shows the level-select screen has visible color bleed.

---

### G8: Lava override for stages 5/7

**Where in teleport**:
- `build_v301_teleport.py` lines 347-416 — `build_lava_override()` function
- Called from teleport routine line 747: `CALL LAVA_OVERRIDE_ADDR`

**What it does**: After scene_detect copies the dungeon table to 0xDA00, this overwrites specific tile IDs with pal5 (BG5 = orange/red lava CRAM) for lava stages (FFBA=4 for stage 5, FFBA=6 for stage 7). Guards against non-dungeon scenes and non-lava stages.

**Why GOOD**: In later stages (5, 7), the game reuses dungeon tile IDs for molten/lava fields. The dungeon table maps these to pal0 (floor default) so the lava renders in floor colors. This override gives them pal5 (lava CRAM) which is correct.

**Minimal patch**: Copy `build_lava_override()` and write to bank13 at an appropriate location (e.g., 0x7E00 as in teleport). Call it from the colorize handler's warm path, right after scene_detect (or in a new wrapper-style frame setup). Needs to run every frame (the stage-load WRAM clear can re-zero DF02, triggering a cold-boot re-copy of the plain dungeon table).

**Important**: The lava override also re-asserts DF02=0x5A to suppress the cold-boot copy race (same mechanism as scene_detect). This is critical for correctness.

---

## 2. BAD changes (exclude from production)

### B1: Teleport combo handler (SELECT+START)

**Where in teleport**:
- `build_v301_teleport.py` lines 719-920 — `build_teleport_routine()` 
  - Lines 808-813: reads FF93, checks for 0x0C (SELECT+START bits)
  - Lines 830-862: cycles FFBA boss index, sets HP, debounce

**Why exclude**: The teleport combo check adds ~80T per VBlank (read FF93, AND, CP, conditional branches). This is consumed every frame even when the combo is not pressed. It's the entry point for the entire stack-redirect mechanism.

**Teleport path without combo**: The teleport routine's "not_combo" path (line 885) clears debounce and falls through to JP COLORIZE (line 1207). But the scene_detect/lava/banner calls at the beginning (lines 742-758) still run. These are the GOOD parts we want.

**How to keep the GOOD while removing B1**: Instead of calling the teleport routine, call the scene_goodies directly from the wrapper or colorize handler:
```
wrapper → CALL scene_detect → CALL lava_override → JP colorize
```
No combo check, no debounce, no stack redirect.

---

### B2: hwoam_recolor at B=40

**Where in teleport**:
- `build_v301_teleport.py` lines 516-595 — `build_hwoam_recolor()`
- Called from wrapper line 1264: `CALL HWOAM_RECOLOR_ADDR`

**VBlank overflow**: The teleport performance audit (teleport_performance_audit.md lines 3-29) documents that hwoam_recolor with B=40 adds ~2,600-4,375T per VBlank, pushing the teleport build to ~10,120T/VBlank (222% of the 4,560T window). The split-VBlank toggle (DF09, processing 20 slots each frame) reduces per-frame cost to ~1,300-2,200T but the total is still ~40% over VBlank.

**Why exclude**: The whole point of the O(1) OBJ colorization project is to ELIMINATE the need for hwoam_recolor by moving the palette lookup from a per-frame OAM scan (O(n)) to a per-tile-ID lookup table (O(1)). The O(1) stamper at 0x6DB0 is the teleport's PREPARATION for this fix, but hwoam_recolor is the OLD method. The production build should use the O(1) approach instead.

**Also**: hwoam_recolor causes the "Sara half-orange" regression at B=10 and, at B=40, causes timing shifts that break slots 0/2 attr alternation (the iter 43 regression documented in gdma.py lines 775-811).

**In the production-plus build**: Exclude hwoam_recolor entirely. The O(1) stamper (OBJ_STAMPER_ADDR at 0x6DB0 in teleport) is a separate good-faith improvement that should be ported IF it has been tested. But it's not part of the 8 good changes list.

---

### B3: Landing pad / stack-redirect mechanism

**Where in teleport**:
- `build_v301_teleport.py` lines 686-716 — `build_landing_pad()`, executed at WRAM 0xDB00
- Line 868-878: stack redirect — reads SP+22, overwrites with LANDING_PAD_WRAM

**Why exclude**: The landing pad is the mechanism by which the teleport combo redirects program flow from the VBlank IRQ back to main-loop context (so it can CALL 0x1A2B for arena init). It modifies the return address on the stack (SP+14/22) and JP to WRAM 0xDB00 after the RETI. If the teleport combo handler is excluded (B1), the landing pad has no caller.

**The cold-boot WRAM copies**: The teleport routine also uses the landing pad's cold-boot check block (DF0E sentinel at lines 760-804) to copy the STAT stub and levelsel stub to WRAM. Without the teleport routine, these copies need a different mechanism. The cleanest approach: add them to the colorize handler's existing cold-boot path (the DF02/DF07/DF08 block in gdma.py lines 628-664), or use a simpler inline copy.

---

## 3. Architectural design for production-plus

The key insight: the teleport routine (`build_teleport_routine`, ~200 bytes at 0x6E80) is a monolithic function that bundles GOOD features (scene_detect, lava_override, banner_override, cutscene_override) with BAD features (combo check, landing-pad copy, stack redirect). We need to extract only the good calls.

### New call chain

```
VBlank IRQ at 0x06D1
  → hook at bank0:0x0824 (FF99 save, map bank 13, CALL wrapper, restore)
  → wrapper at bank13:0x6F40 (PUSH regs, joypad read, CALL colorize_prelude, POP regs, RET)
  → colorize_prelude at bank13:0x6F00 (NEW: scene_detect + lava_override + JP [old colorize entry])
  → colorize handler at bank13:0x6E00 (VBK save, cold-boot init, cond_pal, attr-cleaner,
                                         FFC1 gate { bg_sweep, shadow_main, OAM-DMA },
                                         VBK restore, RET)
```

The "colorize_prelude" is the replacement for the teleport routine. It:

1. CALLs scene_detect at 0x6FB0 (16T fast-path, ~4100T on scene change)
2. CALLs lava_override at 0x7E00 (tiny for non-lava, ~200T for lava stages)
3. CALLs banner_override at 0x7F70 (tiny for non-banner, ~800T for banner)
4. CALLs cutscene_override at 0x7FB0 (tiny for non-cutscene, ~400T for cutscene)
5. JP colorize entry

NO combo check. NO landing pad. NO stack redirect. NO DF1F/DF1D decrement.

### Cold-boot WRAM copy changes

The STAT IRQ WRAM stub copy needs a cold-boot mechanism that doesn't go through the teleport routine. The colorize handler already has a cold-boot path (DF02 sentinel at gdma.py lines 628-664). Add a 4th copy block:

```
DF02 cold-boot path (existing):
  1. Set DF02 = 0x5A
  2. Copy bg_table from ROM → WRAM 0xDA00 (existing)
  [NEW] 3. Copy STAT stub from bank13:0x53F2 → WRAM 0xDB50
  [NEW] 4. Set sentinel DF0E = 0x5A
```

This keeps the cold-boot WRAM copies self-contained within the colorize handler, no dependency on the teleport routine.

## 4. Proposed diff/patch script

### File: `scripts/build_v301_production_plus.py`

Create a new build script at `scripts/build_v301_production_plus.py` that:

```
1. Inherits from build_v301 (calls build_v301() to get base ROM)
2. Applies GOOD changes:
   a. Replace inline hook: create_inline_tile_copy_pure_tileonly() → create_inline_tile_copy_tileonly()
   b. Add 9 boss bg_tables at 0x7200-0x7A00
   c. Add scene_detect at 0x6FB0
   d. Add cursor tile fix at 0x3C59
   e. Add title screen header at 0x4EA5
   f. Add STAT IRQ WRAM stub at bank13:0x53F2 + IRQ vector patch at 0x0048 
   g. Add lava_override at 0x7E00
   h. Add colorize_prelude at bank13 that calls scene_detect + lava_override then JP colorize
   i. Add cold-boot STAT stub copy to colorize handler
   j. Re-patch bg_sweep to read WRAM 0xDA00 instead of ROM 0x7000
3. Excludes BAD changes:
   - No teleport combo handler
   - No position sweep (dead code anyway)
   - No hwoam_recolor
   - No landing pad or stack redirect
   - No banner_override (unless testing shows need)
   - No cutscene_override (unless testing shows need)
```

### Step-by-step:

**Step 1**: Copy `scripts/build_v301_gdma.py` → `scripts/build_v301_production_plus.py`

**Step 2**: Add imports:

```python
from arena_tables_data import ARENA_TILE_PAL
```

**Step 3**: Add constants (after BG_TABLE_BYTES / WRAM_BG_TABLE section):

```python
ARENA_BASE_ADDR = 0x7200
ARENA_NAMES = ["shalamar", "riff", "crystal_dragon", "cameo", "ted",
               "troop", "faze", "angela", "penta_dragon"]

def _table_from_dict(name: str) -> bytes:
    t = bytearray(256)
    for tile_id, pal in ARENA_TILE_PAL.get(name, {}).items():
        t[tile_id & 0xFF] = pal & 7
    t[0xFF] = 0
    return bytes(t)

SCENE_DETECT_ADDR = 0x6FB0
DF23_PREV_SCENE = 0xDF0D
SPLASH_TABLE_ADDR = 0x7E40
LAVA_OVERRIDE_ADDR = 0x7E00
LAVA_STAGE5_IDS = [0x02, 0x03, 0x04, 0x05, 0x12, 0x13, 0x14, 0x15]
LAVA_STAGE7_IDS = [0x19, 0x1A]
STAT_STUB_ROM_ADDR = 0x53F2
STAT_STUB_WRAM = 0xDB50
STAT_STUB_MAX = 36
```

**Step 4**: Copy function `build_scene_detect()` (from teleport lines 242-344)

**Step 5**: Copy function `build_lava_override()` (from teleport lines 347-416)

**Step 6**: Copy function `build_stat_irq_wram_stub()` (from teleport lines 419-461)

**Step 7**: Copy function `build_banner_override()` (from teleport lines 598-643) — optional

**Step 8**: Copy function `build_cutscene_override()` (from teleport lines 646-683) — optional

**Step 9**: In `build_v301()`:

After the existing bg_table write (line 567), add boss bg_tables:

```python
for i, name in enumerate(ARENA_NAMES):
    addr = ARENA_BASE_ADDR + i * 0x100
    table = _table_from_dict(name)
    assert len(table) == 256
    w(addr, table)
```

After the bg_sweep write (line 586), add scene_detect:

```python
sd = build_scene_detect(bg_table_addr, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR)
assert SCENE_DETECT_ADDR + len(sd) <= bg_table_addr
w(SCENE_DETECT_ADDR, sd)
```

Add lava override:

```python
lava = build_lava_override(LAVA_OVERRIDE_ADDR)
w(LAVA_OVERRIDE_ADDR, lava)
```

Add splash table + stage intro letter patches (copy from teleport lines 1062-1088):

```python
off = bank13 + (SPLASH_TABLE_ADDR - 0x4000)
rom[off:off + 256] = bytes(256)  # all pal0
STAGE_INTRO_LETTERS = [0x30, 0x31, 0x40, 0x4A, 0x4B, 0x50, 0x51, 0x52,
                       0x53, 0x54, 0x55, 0x58, 0x5A, 0x5B, 0x6D, 0x6E,
                       0x6F, 0x7D, 0x7E, 0x7F]
for tile in STAGE_INTRO_LETTERS:
    rom[off + tile] = 0x01  # pal-1 (red)
```

Add STAT IRQ WRAM stub:

```python
stat_stub = build_stat_irq_wram_stub()
off = bank13 + (STAT_STUB_ROM_ADDR - 0x4000)
rom[off:off + len(stat_stub)] = stat_stub

# Patch IRQ vector at 0x0048
assert rom[0x0048] == 0xC3, f"STAT vector not JP at 0x0048: {rom[0x0048]:02X}"
rom[0x0049] = STAT_STUB_WRAM & 0xFF
rom[0x004A] = (STAT_STUB_WRAM >> 8) & 0xFF
```

Add cold-boot STAT stub copy to the colorize handler's cold-boot path (after line 651):

```python
# Copy STAT IRQ WRAM stub to WRAM (cold-boot only)
code.extend([0x21, STAT_STUB_ROM_ADDR & 0xFF, (STAT_STUB_ROM_ADDR >> 8) & 0xFF])
code.extend([0x11, STAT_STUB_WRAM & 0xFF, (STAT_STUB_WRAM >> 8) & 0xFF])
code.extend([0x06, STAT_STUB_MAX])
stat_loop = len(code)
code.extend([0x2A, 0x12, 0x13, 0x05])
offset = stat_loop - (len(code) + 2)
code.extend([0x20, offset & 0xFF])
```

**Step 10**: Replace the inline hook:

Change line 899 from:
```python
inline_code = create_inline_tile_copy_pure_tileonly()
```
to:
```python
inline_code = create_inline_tile_copy_tileonly()
```

**Step 11**: Add cursor tile fix (after the inline hook block, around line 909):

```python
assert rom[0x3C58:0x3C5A] == bytes([0x3E, 0x73])
rom[0x3C59] = 0x80
```

**Step 12**: Add title screen header (after cursor fix, or at any point before the checksum):

```python
E = 0x9A
def _txt(s):
    return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
       0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]
title_list = bytes(
    [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]
    + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]
    + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]
    + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]
    + [0x04, 0x08] + _txt("OPENING START") + [E]
    + [0x04, 0x0A] + _txt("GAME    START") + [E]
    + [0x00, 0x0E, 0xC0, E]
    + [0x00, 0x0F