# Per-Monster-Type Palette Assignment — O(1) System Extension

**Goal**: Extend the current tile-range-based O(1) stamper to assign distinct CGB OBJ palettes per monster type, per Sara form, and per projectile type — without breaking the O(1) performance guarantee.

## Current Limitation

The current O(1) stamper uses a flat 256-byte LUT at bank13:0x6B00 mapping `tile_id → palette_index`. All sprites sharing the same tile range get the same palette. An orc (tile 0x45) and a crow (tile 0x35) that both fall in the 0x30-0x4F range both get pal_3. You cannot distinguish them.

## Proposed Architecture

### New Data Structure: Monster-Type Palette Table

A 256-byte table `monster_pal_table` at bank13:0x6C00 mapping `entity_type_id → palette_index`.

The entity type ID is read from the WRAM entity table at `0xC200`. Each entity in the game's WRAM table has a 24-byte structure with a `FE FE FE` header followed by the entity type ID at offset +3 (documented in `docs/ENTITY_DATA_STRUCTURE.md`).

```
WRAM entity table (0xC200):
  C200: FE FE FE 17 ...  ← type 0x17 = regular enemy
  C300: FE FE FE 1D ...  ← type 0x1D = miniboss
  ...
```

### Entity-to-OAM Slot Mapping

The critical missing piece: we need to know which WRAM entity slot corresponds to each OAM slot 0-39. The game maintains this mapping somewhere in its sprite rendering pipeline. There are two approaches:

**Approach A (Weak):** Track OAM slot assignments by monitoring which entity spawn writes result in which OAM slots. The trampoline already intercepts shadow OAM writes — we can add a small ring buffer that records `[OAM_slot, entity_address]` pairs.

**Approach B (Strong):** Scan the game's sprite commit function to find where it reads entity data and writes it to OAM slots. This function exists somewhere — it reads an entity's X/Y/tile from the WRAM entity struct and writes it to the shadow OAM at `C000 + slot*4`. If we hook this function, we know exactly which entity is writing to which OAM slot.

**Recommended: Approach A (simpler, non-invasive).**

### Approach A Details

The current trampoline at bank0:$10D3 intercepts the 4-byte sprite write (Y, X, tile, attr) to shadow OAM. We know the OAM slot from the write address. We don't know the entity yet — but we can correlate.

Add a **8-byte ring buffer** at WRAM 0xD940 that stores `[frame_count_low, oam_slot, tile_id, guessed_entity_type]` entries. After each frame's VBlank, a small post-process walks the ring buffer and for each unique (tile_id, oam_slot) pair, records what tile was written. 

Actually, simpler: **the entity type is inferrable from the tile ID.** The game uses consistent tile ranges per monster type (documented in the palette YAML). When the trampoline sees tile 0x45, it can look up the tile→monster_type mapping from a small table. This is dirt cheap — 6 cycles, one LUT read.

### The Final LUT Chain

Per-sprite stamp becomes:

```
1. Read tile ID from OAM entry (+2)          → already in trampoline
2. Read entity_type from tile→type LUT       → NEW (1 lookup)
3. Read palette from monster_pal_table[type]  → NEW (1 lookup)
4. Merge palette bits into attr byte         → already in trampoline
5. Write attr byte to OAM entry (+3)         → already in trampoline
```

**Cycle cost increase**: ~30 cycles per sprite (40 sprites × 30 = 1200 cycles total). Still under the O(1) budget of ~375 cycles for the current stamper? No — the current stamper is ~375 cycles for all 40 sprites. Adding 1200 more cycles brings it to ~1575. Still well under the 53K-cycle VBlank budget (hwoam_recolor territory), but no longer "free" in the main loop.

### Optimized Implementation

Instead of two separate lookups (tile→type, then type→palette), **fuse them into a single 512-byte table**: `tile_id → palette_index` where each palette index is set per-monster-type during the codegen phase. This eliminates the type lookup entirely.

The tile range assignment table is already built by `build_obj_pal_table()` — we just need to make it per-monster-type aware. During build, instead of:
```python
table[0x45] = 3  # tile 0x45 → pal_3 (generic enemy)
```
We'd use:
```python
# Known: tile 0x45 belongs to orc type → orc gets pal 5
table[0x45] = 5  # tile 0x45 → pal_5 (orc blue)
table[0x35] = 6  # tile 0x35 → pal_6 (crow purple)
```

This requires a **monster_tile_map.yaml** that specifies which tile ranges belong to which monster type and what palette they should get. The build script reads this and generates the fused 512-byte LUT.

### New Config: `palettes/monster_palette_map.yaml`

```yaml
# Monster type → tile ranges → desired palette
monsters:
  - name: orc
    tiles: [0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49]
    palette: 5  # blue

  - name: crow
    tiles: [0x30, 0x31, 0x32, 0x33, 0x34, 0x35]
    palette: 6  # purple

  - name: hornet
    tiles: [0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57]
    palette: 4  # orange (keep as-is)

  - name: soldier
    tiles: [0x70, 0x71, 0x72, 0x73, 0x74, 0x75]
    palette: 7  # red

  - name: gargoyle_miniboss
    tiles: [0x60, 0x61, 0x62, 0x63, 0x64, 0x65]
    palette: 7  # red (miniboss gets boss slot)

  - name: sara_w
    tiles: [0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
             0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17]
    palette: sara_palette  # resolved at runtime from FFBE

  - name: sara_d
    tiles: [0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F,
             0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F]
    palette: sara_palette  # resolved at runtime from FFBE

  - name: projectile_sara
    tiles: [0x00, 0x01]
    palette: 3  # yellow

  - name: projectile_enemy
    tiles: [0x0F]
    palette: 1  # red
```

### Backward Compatibility

The current 256-byte LUT at bank13:0x6B00 remains the primary lookup. The monster_palette_map.yaml would generate a **separate 256-byte override table** at bank13:0x6D00 that is checked FIRST. If the override table returns 0xFF (no override), fall through to the default tile-range LUT. This means:

- **Monster types explicitly mapped** → get their specific palette
- **Monster types NOT mapped** → keep the current tile-range-based assignment (no regression)
- **New monsters added** → just add an entry to the yaml, no code changes

The override check costs exactly: `LD A,[HL]; INC A; JR Z,use_default; DEC A; ...` = ~12 cycles per sprite. Negligible.

### Implementation Plan

**Phase 1**: Create `palettes/monster_palette_map.yaml` with the known monster tile mappings from reverse-engineering (the OG showcase data already confirms tiles 0x08-0x0F are decorative, tiles 0x20-0x2F are Sara, etc.)

**Phase 2**: Modify `build_obj_pal_table()` in `build_v301_gdma.py` to read the yaml and generate the override table at bank13:0x6D00.

**Phase 3**: Add the override check to the O(1) stamper trampoline at bank13:0x6DB0. The trampoline currently does:
```
read tile → LUT[bank13:0x6B00] → merge attr → write
```
Change to:
```
read tile → check override[0x6D00] → if valid, use it; else LUT[0x6B00] → merge attr → write
```

**Phase 4**: Update the cold-boot copy to include the override table in the WRAM copy.

**Phase 5**: Verify with the existing probes + visual check on mGBA. 

### Risk Assessment

- **O(1) performance maintained**: +12 cycles per sprite, ~480 cycles total for 40 sprites. Still under 2000 cycles, far below the 53K VBlank budget.
- **No timing changes to existing paths**: The override table is a simple check-or-fallthrough. Existing trampoline paths unchanged.
- **Backward compatible**: Unmapped monsters keep their current colors.
- **No codegen changes to the C runtime**: All changes are in the Python build scripts and the WRAM-copied trampoline.
