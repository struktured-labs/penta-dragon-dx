# Per-Monster-Type Palette Assignment — v2 Merged Spec

**Derived from review of v1 (docs/per_monster_palette_plan.md) against the existing O(1) OAM intercept architecture, GBC hardware constraints, and codebase reality.**

---

## 1. Key Correction: No Entity-Lookup Needed

**v1 error**: The plan proposed a 256-byte `monster_pal_table` indexed by `entity_type_id` (read from WRAM entity table at 0xC200), which requires a costly entity-to-OAM-slot mapping — an unsolved reverse-engineering problem.

**Reality**: The *existing* WRAM trampolines in `patch_oam_intercept.py` (sites 1, 2, 3) already intercept at sprite-emission time with the tile ID available. They look up the WRAM-resident OBJ palette LUT at 0xD900 (copied from bank13:0x6B00 at cold boot). The lookup is purely tile-ID-based.

**Decision**: Discard the entity-type-ID approach entirely. The per-monster-type distinction is achieved by making the **tile-ID→palette LUT itself per-monster-aware at codegen time**. The trampoline code doesn't change at all — only the *contents* of the 256-byte OBJ palette LUT (bank13:0x6B00 → WRAM 0xD900).

This is the critical simplification: **no new tables, no override mechanism, no entity lookup**.

---

## 2. How It Actually Works

### Current state
```
build_obj_pal_table() → 256-byte table at bank13:0x6B00
  tile 0x30 → 3 (enemy range)
  tile 0x31 → 3
  ...
  tile 0x45 → 3 (orc falls in range)
  tile 0x35 → 3 (crow falls in same range)
```

### Proposed state
```
build_obj_pal_table() generates tile-precise assignments:
  tile 0x30 → 6  (crow purple, pal 6)
  tile 0x31 → 6
  tile 0x32 → 6
  tile 0x33 → 6
  tile 0x34 → 6
  tile 0x35 → 6
  tile 0x36-0x3F → 6 (remaining crow tiles, or fallback per existing cascade)
  
  tile 0x40 → 5  (orc blue, pal 5)
  tile 0x41 → 5
  ...
  tile 0x49 → 5
  tile 0x4A-0x4F → 5 (remaining orc tiles)
```

The trampoline code at sites 1/2/3 does not change. It still does:
```
read tile → LUT[WRAM 0xD900+tile] → merge attr → write
```

The only change is in `build_obj_pal_table()` and a new `palettes/monster_palette_map.yaml`.

---

## 3. New Config: `palettes/monster_palette_map.yaml`

```yaml
# Per-monster-type tile→palette assignments.
# These override the coarse tile-range cascade at codegen time.
# Tiles NOT listed here retain their existing cascade assignment.
monsters:
  - name: crow
    tile_ranges:
      - [0x30, 0x3F]
    palette: 6   # purple

  - name: orc
    tile_ranges:
      - [0x40, 0x4F]
    palette: 5   # blue

  - name: hornet
    tile_ranges:
      - [0x50, 0x5F]
    palette: 4   # orange (unchanged, explicit for clarity)

  - name: soldier
    tile_ranges:
      - [0x70, 0x7F]
    palette: 7   # red

  - name: projectile_sara
    tile_ranges:
      - [0x00, 0x01]
    palette: 3   # yellow

  - name: projectile_enemy
    tile_ranges:
      - [0x0F, 0x0F]
    palette: 1   # red

  # Sara tiles remain dynamic (resolved at runtime via FFBE in trampoline).
  # DO NOT assign literal palettes here — the trampoline's 0xFF sentinel +
  # FFBE check handles this.
```

---

## 4. Sara Dynamic Palette: Stays as-is

The existing trampolines (patch_oam_intercept.py lines 56-65, 85-93, 114-122) already handle Sara correctly:

```
tile 0x10-0x2F → LUT value 0xFF → trampoline sees 0xFF → resolves via FFBE
  FFBE=0 → pal 2 (Sara Witch)
  FFBE≠0 → pal 1 (Sara Dragon)
```

**v1's `sara_palette` YAML value was ambiguous**. The correct treatment is: the YAML omits Sara tiles entirely (or documents them as `palette: dynamic_ffbe`), and the LUT builder writes 0xFF for Sara tile ranges. No code change needed.

The existing obj_colorizer cascade in bg_tile_categories.yaml already has the correct ranges:
- tiles 0x10-0x1F → sara_palette (resolved from reg D, caller-supplied)
- tiles 0x20-0x2F → sara_palette

The `build_obj_pal_table()` function must already handle 0xFF for Sara (it does in the existing architecture per patch_oam_intercept.py line 48: `CP $FF; JR Z, sara`).

---

## 5. Boss Override Interaction

**Critical edge case v1 missed**: When `boss_flag` (FFBF) is non-zero, the existing system wants ALL enemies (tiles 0x30+) to use the boss palette slot. With per-monster-type assignments, we'd lose that.

**Resolution**: The override belongs at the **codegen level**, not at runtime. Two tables are generated:

1. **Normal table** (bank13:0x6B00, normal use): Per-monster-type assignments
2. **Boss table** (bank13:0x6B00+BOSS_OFFSET, loaded by palette_loader when boss_flag≠0): Overrides all enemy tiles to the boss palette slot

OR, simpler: the palette_loader (at 0x6900, which runs on scene change / boss_flag change) already swaps OBJ CRAM palettes. Boss palettes replace palettes 6 and 7 with boss-specific colors. If the orc uses pal 5 (blue) and the soldier uses pal 7 (red), then when a boss is active:
- pal 7 gets swapped to boss colors → soldier looks like a boss-matching enemy
- pal 5 (orc) stays normal blue → fine (not boss-controlled)
- pal 6 (crow) could optionally be swapped if boss uses both slots

**Recommendation**: Accept this interaction. The boss system swaps CRAM slots 6/7 during boss fights. Any monster assigned to pal 6 or 7 will pick up boss colors automatically. This is a feature, not a bug — miniboss-themed enemies can use pal 6/7 to visually participate in the boss fight. Don't add runtime override logic.

---

## 6. Bank 13 Layout — Addressed

**v1's proposed addresses 0x6C00 and 0x6D00 conflict with existing allocations**:

| Address range | Current occupant | v1 claim | Verdict |
|---|---|---|---|
| 0x6B00-0x6BFF | `tile_pal_addr` — tile→palette LUT (256 bytes) | "primary lookup" | Correct — this stays |
| 0x6C00-0x6C8F | (free gap before cond_pal) | "monster_pal_table" | **0x6C00 is free** (~144 bytes before cond_pal at 0x6C90) |
| 0x6C90-0x6CCF | `cond_pal_addr` — conditional palette cache | Not addressed | EXISTS |
| 0x6CD0-0x6D7F | `bg_sweep_addr` — sweep safety net | Not addressed | EXISTS |
| 0x6D80-0x6DFF | `gdma_addr` — GDMA transfer routine | "override table at 0x6D00" | **CONFLICT** — 0x6D00 is inside GDMA code |
| 0x6E00-0x6E7F | `colorize_addr` — VBlank colorize handler | Not addressed | EXISTS |

But this doesn't matter because **we no longer need a separate override table**. The single 256-byte LUT at 0x6B00 is sufficient — we just change its contents.

---

## 7. The `build_obj_pal_table()` Function

**v1 stated** this lives in `build_v301_gdma.py`. **It does not exist there.** The import chain is:

```
patch_oam_intercept.py:
  from build_v301_teleport import build_obj_pal_table, ...
```

But `build_v301_teleport.py` does NOT define `build_obj_pal_table` — the import is *broken* (confirmed by runtime import error). This function exists in older colorizer scripts (`create_vblank_colorizer_v*.py`) under different names (`create_tile_to_palette_subroutine`).

**What exists today:**
- `create_tile_to_palette_subroutine()` in `bg_experiment.py` (line 264) — builds actual asm for the old VBlank loop, not a static LUT
- The static 256-byte table `BG_TABLE_BYTES` in `build_v301_gdma.py` (line 35) — but this is for BG, not OBJ
- The OBJ palette LUT is baked by `create_tile_based_colorizer()` in `build_v301_gdma.py` (imported from `bg_experiment.py`), written at `tile_pal_addr = 0x6B00`

**Action needed**: Find or create the actual function that builds the 256-byte OBJ LUT. It may be `create_tile_to_palette_subroutine()` which generates *code* (not a static table) — the obj_colorizer cascade in bg_tile_categories.yaml (lines 107-159) describes the actual codegen.

**Decision**: The YAML-driven codegen in `bg_experiment.py` → `create_tile_based_colorizer_from_yaml()` (if it exists) or the literal cascade in `create_tile_based_colorizer()` is the actual "table builder." Modify that codegen to accept per-monster-type overrides from the new YAML.

---

## 8. Cold-Boot Copy Implications

The existing cold-boot path (in colorize handler, lines ~629-647 of `build_v301_gdma.py`):
1. Copies bg_table (256 bytes) from bank13:0x7000 → WRAM 0xDA00
2. Does NOT copy the OBJ palette LUT to WRAM — that's done by the teleport routine's cold-boot copy in `patch_oam_intercept.py` (line 238-245): bank13:0x6B00 → WRAM 0xD900

Since we're NOT adding a new table, the cold-boot copy doesn't change.

**But**: The OBJ palette LUT copy (0x6B00 → 0xD900) is gated on the same DF1E sentinel as the trampoline copy. If the per-monster-type table is placed at a different ROM address, the copy source needs updating. If it stays at 0x6B00, no change needed.

---

## 9. Unmapped Tiles / Fallthrough Behavior

Tiles outside the mapped ranges keep their existing cascade assignment. The obj_colorizer cascade in `bg_tile_categories.yaml` (the CP-against-threshold chain at 0x30/0x40/0x50/0x60/0x70/0x80) is the production codegen path.

When a new per-monster-type YAML provides a specific palette for a tile, the codegen overrides that tile's entry in the LUT. Unspecified tiles keep the cascade result.

**Important**: The override MUST be applied at codegen time, not at runtime. The built LUT at 0x6B00 is the merged output. The trampoline does not branch.

---

## 10. Revised Implementation Plan

### Phase 0: Find the actual table builder
- Search for `create_tile_to_palette_subroutine()` return value — does it return a 256-byte static table, or asm code?
- If asm code: the "table" at 0x6B00 is actually emitted assembly, not data. The per-monster-type override would be applied by modifying the asm generator's tile-range dispatch or by writing a separate 256-byte data table that the asm loads from.
- **Risk**: If 0x6B00 is assembly code (not a static table), the entire plan's "just change table contents" approach is wrong. Verify by reading ROM dump.

### Phase 1: Create `palettes/monster_palette_map.yaml`
- Use the tile ranges from v1's YAML example
- Map all known monster types
- Document Sara tiles with `palette: dynamic_ffbe` (not a literal value)
- Stop at the tile ranges verified by OG showcase data

### Phase 2: Modify the table/codegen builder
- Change `create_tile_to_palette_subroutine()` or equivalent to read the per-monster-type YAML
- Apply overrides on top of the existing cascade
- Output the merged LUT

### Phase 3: Verify
- Check that the WRAM copy at cold boot picks up the new LUT
- Verify that existing trampolines (sites 1/2/3) still work unchanged
- No trampoline code changes needed

### What we DO NOT do:
- No entity table lookup (removes Approach A/B entirely)
- No override table at 0x6D00 (removes conflict with GDMA)
- No override-check code in the trampoline (removes +12 cycles/sprite)
- No new cold-boot copy (removes cold-boot implications)
- No runtime boss-override logic (boss CRAM swap handles it naturally)

---

## 11. Risk Assessment (Revised)

| Risk | v1 assessment | v2 assessment |
|---|---|---|
| O(1) performance | +12 cycles/sprite for override check | **Zero additional cycles.** Trampoline unchanged. Only LUT contents change. |
| Bank 13 space | 0x6D00 free (wrong) | **No new space needed.** Single 256-byte LUT at 0x6B00 is sufficient. |
| Cold-boot copy | Needs update | **No change needed.** Same LUT, same copy. |
| Sara palette | "resolved at runtime from FFBE" (vague) | **Already works correctly.** Existing 0xFF sentinel + FFBE check. |
| Boss override | Not addressed | **Natural interaction.** Boss swaps CRAM slots 6/7; monsters using those slots pick up boss colors. Document the behavior. |
| Missing table builder | References non-existent function | **Real risk.** The 0x6B00 "LUT" may be emitted asm, not static data. Phase 0 must verify. |
| Entity mapping | Implemented two complex approaches | **Removed entirely.** Tile-ID inference at codegen time replaces runtime entity tracking. |

---

## 12. Open Questions

1. **Is 0x6B00 a static table or emitted asm?** Read the ROM dump to determine. If it's asm code, the LUT model is wrong and a different approach is needed.

2. **What tiles overlap between monster types?** The v1 YAML assumes clean tile ranges, but the actual game may have tile reuse across entity types (e.g., tile 0x47 used by both orc *and* wall spike cylinder). This needs runtime probe validation.

3. **What about the stage-detect bonus-stage mode (FFD0)?** The existing system swaps Sara's palette to jet form when stage_flag=0x01. Per-monster assignments may need stage-specific palette overrides (e.g., a future "dark world" stage where enemies get different colors). This is Phase 2+.
