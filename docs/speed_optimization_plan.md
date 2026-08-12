# Penta Dragon DX — Speed Optimization Plan (Merged)

> Generated: 2026-07-19
> Sources: `scripts/build_v301_gdma.py`, `build_v301_teleport.py`, `build_v302_title_fix.py`
> Baseline ROM: `rom/working/penta_dragon_dx_FIXED.gb` (v3.02)
> Current ROM: `rom/working/penta_dragon_dx_teleport.gb` (v3.02 base before title-fix)

## 1. VBlank handler chain (measured per-frame costs)

### The full per-frame call path (gameplay, FFC1=1)

```
0x0824 hook → map bank 13 → CALL wrapper(0x6F30)
  wrapper: joypad read (~80T)
    → CALL teleport(0x6E80)
        → CALL scene_detect(0x6FB0)  ~16T fast path (~4100T on scene change)
        → CALL lava_override(0x7E00) ~20T fast path (~200T on lava)
        → cold-boot copy (one-shot, ~first 7 VBlanks)
        → combo check/guard          ~120T
        → DF1D/DF1F decrement        ~30T
        → JP colorize(0x6E00)

  colorize(0x6E00):
    → save VBK + set VBK=0           ~16T
    → cold-boot check + copy          ~5T fast / ~2600T cold (one-shot)
    → CALL cond_pal(0x6C90)          ~200T (cached fast path)
    → attr cleaner                   ~12T (after first 32 frames)
    → FFC1 gate:
        → CALL bg_sweep(0x6CD0)     ~600T (1 row × 32 attrs + viewport)
        → CALL shadow_main(0x69D0)  ~300T (OBJ colorizer, 10 sprites)
        → CALL $FF80 (OAM DMA)      ~160T
    → restore VBK                    ~10T
```

### Cost table (gameplay frame)

| Component         | T-cycles | % of VBlank | Status     |
|-------------------|----------|-------------|------------|
| Wrapper joypad    | ~80      | 2%          | Required (teleport) |
| scene_detect      | ~16      | 0.4%        | Already optimal |
| lava_override     | ~20      | 0.4%        | Already optimal |
| combo+guard       | ~120     | 2.6%        | Required (teleport) |
| DF1D/DF1F dec     | ~30      | 0.7%        | Required (teleport) |
| cond_pal          | ~200     | 4.4%        | Already optimal |
| attr cleaner      | ~12      | 0.3%        | Negligible |
| bg_sweep          | ~600     | 13%         | **Optimizable** |
| shadow_main       | ~300     | 6.6%        | Negligible |
| OAM DMA           | ~160     | 3.5%        | Required |
| **Total**         | **~1538**| **34%**     | Well within VBlank |

VBlank budget: ~4560 T-cycles. Our handler uses ~34%.

## 2. Identified optimization targets

### 2a. bg_sweep gate restoration (FFC1=0 skip) — SAFE

**Current state**: In `build_v302_title_fix.py` line 218-221, bg_sweep's FFC1
gate is NOP'd:
```python
sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # DMG NOPs removed
```
This makes bg_sweep run every frame including title screen (~600T/frame).

**Analysis**: The inline tile+attr hook at bank1:0x42A7 is UNGATED in v3.02
(title_gate=None) — it writes tile+attr on every tile copy, including the
title screen. Title tiles are fully handled by this hook. bg_sweep on title
is redundant: it writes attrs for title tiles based on the **dungeon** bg_table
(0xDA00) because scene_detect is not running title-mode tables. Title tiles
get dungeon-appropriate (but wrong-for-title) attrs from bg_sweep, then the
inline hook's attr phase overwrites them moments later.

**Hardware risk**: None. The inline hook covers title tiles atomically (tile
write followed by attr write in the same DI window). bg_sweep running on top
is at best a redundant write and at worst a race candidate.

**Action**: Re-instate the FFC1 gate. bg_sweep still runs during gameplay
(FFC1=1). On title (FFC1=0) it early-RETs.
- Savings: ~600T/frame on title (but title screen is not performance-critical)
- Primary value: cleaner code, matches documented intent in `build_v301_gdma.py` line 764

### 2b. bg_sweep during gameplay: must keep

bg_sweep catches tiles written by code paths that bypass 0x42A7:
- Door transitions (room layout decompression)
- Boss entrance/exit floor tiles
- Item spawns during gameplay
- Post-death reload
Mini-boss probe (`verify_miniboss_color.py`) is a timing dependency on bg_sweep.

**Can it be gated during gameplay?** No. The stale-attr window (boot-ROM pal7)
would be visible on newly revealed tiles for up to 32 frames. D880 transitions
reset scene context, and the colorize handler's cold-boot copy would re-load
the dungeon table — but tiles written by game code between sweeps would show
pal7 white. This is the exact bug that v3.00's inline hook was designed to fix.

### 2c. scene_detect gating: already optimal

Fast path is 3 instructions: `LD A,[D880]; CP [HL]; RET Z` — ~16T. This runs
every frame regardless. The only cost is on scene change (~4100T for 256-byte
copy). Scene changes happen at most a few times per second (room transition,
boss entry). 4100T on a scene-change frame is well within VBlank.

**Action**: None needed.

### 2d. lava_override: already optimal

Fast path in non-lava stages: ~20T (D880 guard check fails early). On lava
stages, it's ~200T to walk the small tile-ID list. Negligible.

### 2e. cond_pal (conditional palette loader): already optimal

Cached path is ~200T (check sentinel, return). pal_loader is a warm-only call
and caches its T-cycle cost well.

### 2f. Attr cleaner: keep as-is

~12T per frame after the first 32 frames. Handles the stale CGB boot-ROM
0xFF attrs. Already negligible.

## 3. The real bottleneck: inline hook dual STAT wait

**This is NOT a VBlank optimization.** The inline hook at 0x42A7 contains TWO
STAT wait loops per group — one for the tile phase, one for the attr phase.
Each wait is ~250-350T. With 24 rows × 6 groups = 144 groups, the second wait
adds ~36K-50K T of CPU stall during **active display**.

This is the main performance lever per `CLAUDE.md` line 33-35:
> *"If GB-speed parity is ever the goal, the real lever is the hook's
> second (attr-phase) STAT mode-0 wait per group"*

**Hardware HDMA** could eliminate the attr-phase entirely — write attrs via
GDMA during VBlank instead of in the inline hook. This was the v3.01
`create_gdma_transfer()` approach, but the `attr_computation` (~50K T) made
it worse. The right approach would be:

1. Keep the **tile-only** inline hook (single STAT wait = vanilla speed)
2. Pre-compute attrs into a ROM or WRAM table at room-load time (NOT per frame)
3. GDMA the pre-computed table to VRAM attr bank in VBlank (~2048T)

This trades ~50K T of per-frame attr_computation for a one-time room-load cost
and ~2K T of GDMA per frame. Huge net win.

**Not pursued here** — this is a separate project (would need room-table
generation from the game's room data, which requires RE work).

## 4. Implementation plan for v3.03

### Changes

**File**: `scripts/build_v302_title_fix.py` (or a new `build_v303.py`)

1. **Restore bg_sweep FFC1 gate** — undo the NOP patch:
   ```python
   # Instead of:
   # sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])
   
   # Keep the FFC1 gate intact:
   # sweep[:4] is: F0 C1 B7 C8 (LDH A,[FFC1]; OR A; RET Z)
   # This is the ORIGINAL behavior from create_bg_sweep_viewport_gated()
   ```

   But wait — the v3.00 base (build_v296) already strips the gate. Let's check
   what `create_bg_sweep_viewport_gated()` actually produces vs what we want.

   From `build_v301_gdma.py` line 595-598:
   ```python
   sweep = bytearray(create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr))
   assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])  # FFC1 gate!
   sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOP it out
   ```

   So the FUNCTION produces code WITH the FFC1 gate, and the BUILDER strips it.
   For the optimization: simply **don't strip it**. Remove lines 218-221 from
   `build_v302_title_fix.py` (the `sweep[0:4] = bytearray(...)` assignment).

   Actually, looking at `build_v302_title_fix.py` line 217-221:
   ```python
   sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
   assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
   sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # DMG NOPs removed
   ```

   Remove the `sweep[0:4] = bytearray(...)` line (and the assert above it if
   desired, since the gate is now expected).

### Files to modify

| File | Change | Risk |
|------|--------|------|
| `scripts/build_v302_title_fix.py` lines 217-221 | Remove bg_sweep FFC1 gate NOP | Low — inline hook covers title |
| — (keep 0x42A7 inline hook ungated) | No change | Title tiles still get attrs from inline hook |

### Verification

1. Build ROM → `rom/working/penta_dragon_dx_FIXED.gb`
2. Run all 5 probes:
   - `verify_title_screen_integration.py` (0=PASS: PENTA DRAGON DX text visible)
   - `verify_title_color.py` (0=PASS: title has colors)
   - `verify_phantom_d887.py` (≤27 baseline)
   - `verify_gameplay_palette.py` (0=PASS: colors correct)
   - `verify_miniboss_color.py` (0=PASS: mini-boss colored)
   - `verify_scroll_tearing.py` (0/PASS: palette stable)
3. mGBA-qt visual confirm: title screen, gameplay, boss arena
4. mGBA-qt visual confirm: cursor 'A' at tile 0x73 visible on title

### If the FFC1 gate causes title issues

The inline hook (v3.02's key fix) writes tile+attr on the title screen
already. bg_sweep was redundant on title. But if removing it reveals any
uncolored spots, the fallback is to keep the gate NOP'd as-is.

## 5. Conclusion

The VBlank handler is well within budget (~34% utilization). The real
performance lever is the inline hook's dual STAT wait (~36K-50K T during
active display), which would require a GDMA-based attr-transfer redesign.

For v3.03: restore the bg_sweep FFC1 gate. This saves ~600T/frame on title
(cosmetic, not meaningful) but is architecturally correct. The production
build is already performant enough.

### Verification checklist
- [ ] bg_sweep FFC1 gate restored (skips on title)
- [ ] Inline hook remains ungated (writes tile+attr on title)
- [ ] O(1) trampolines (C000-C09F intercepts) preserved
- [ ] All probes pass
- [ ] mGBA-qt visual confirm: title screen colors present
- [ ] mGBA-qt visual confirm: gameplay colors present
- [ ] mGBA-qt visual confirm: boss arena colors present (position sweep active)
- [ ] mGBA-qt visual confirm: cursor 'A' visible (tile 0x73, pal 7)
