# Speed Optimization Plan v2

> **Status**: Planning phase — synthesized from full source review of v3.01 teleport
> build chain (build_v301_gdma.py, build_v301_teleport.py, patch_oam_intercept.py).

## Problem Statement

The v3.01 teleport ROM (penta_dragon_dx_teleport.gb) has two user-visible
performance issues:

1. **~2-second white screen on cold boot** — the colorize handler's cold-boot
   path (bg_table ROM→WRAM copy, attr_cleaner 32-frame rollout) delays the
   title screen's first render.

2. **Stage intro ditty plays twice** — sound-timing shift from our patches'
   instruction overhead changes the game's internal timing enough that the
   sound engine dispatches the intro music twice.

## Current VBlank Chain (in order)

Every VBlank frame, the hook at 0x0824:
```
MBC switch to bank 13
  └─ wrapper (joypad read, ~96T)
       └─ teleport_routine (bank13:0x6E80):
            ├─ scene_detect (~16T fast, ~4100T on change)
            ├─ lava_override (~50T guard, ~300T fire)
            ├─ cold-boot copy check (LUT+tramp+pad, ~3000T once)
            ├─ combo read + guard (~50T)
            ├─ DF1F colorize-skip dec (~30T)
            └─ JP colorize
       └─ colorize_handler:
            ├─ VBK save (~12T)
            ├─ DF02 cold-boot check (~20T)
            ├─ cold-boot path (bg_table copy ~4100T) [rare]
            ├─ cond_pal (~200T cached)
            ├─ attr_cleaner (only first 32 frames, ~400T then ~12T)
            ├─ FFC1 gate:
            │   ├─ bg_sweep (~600T, 1 row + viewport)
            │   ├─ shadow_main (~300T OBJ colorizer) — DEAD with O(1) tramps
            │   └─ OAM DMA (~200T)
            └─ VBK restore (~12T)
  MBC restore
```

### What the O(1) trampolines already handle

Three WRAM-resident trampolines intercept OBJ attr writes at sprite-emission
time (not VBlank). They assign the correct CGB OBJ palette based on the tile
ID → OBJ_PAL_WRAM (0xD900) LUT. This means:

- **shadow_main (OBJ colorizer) is fully redundant during gameplay.**
- **bg_sweep is partially redundant** — it writes BG attrs, which the O(1)
  tramps do NOT touch (they only handle OBJ attrs). But bg_sweep's logic
  re-inspects the entire tilemap every frame regardless of scene changes.
- **scene_detect's 256-byte copy** — only meaningful on D880 transition,
  wasted every other frame.

## Proposed Gating Strategy

### Gate 1: shadow_main → only during title/transition

**Condition**: D880 >= 0x0C (arena) OR D880 == 0x02 with DF1D > 0
(teleport settling). Or more simply: skip when O(1) traps are active.

**Implementation**: The colorize handler at bank13:0x6E00 currently has:
```
F0 C1 B7       ; LDH A,[FFC1]; OR A
28 xx          ; JR Z, skip_ffc1
CD sweep       ; CALL bg_sweep
CD shadow      ; CALL shadow_main (stamper/colorizer)
CD 80 FF       ; CALL OAM_DMA
```

Replace the shadow_main CALL with:
```
; Only run shadow_main on title/menu (FFC1=0 implies title screen).
; On title, O(1) trampolines haven't been cold-boot-copied yet,
; so OBJ colorization still needs shadow_main.
; Everything under FFC1=1 uses O(1) tramps.
F0 C1 B7       ; LDH A,[FFC1]; OR A
28 xx          ; JR Z, do_shadow (title → run it)
00 00 00       ; NOP NOP NOP (skip shadow_main during gameplay)
```

**Savings**: ~300T/frame during gameplay.

### Gate 2: bg_sweep → gate by D880 range

**Problem**: bg_sweep writes 1 row of tile-ID→attr per frame (rolling).
This is correct for the dungeon where the inline hook writes tile-only
attribution is needed. But during arenas (D880 >= 0x0C), the position
sweep or the inline hook's tile-ID attrs should be the sole writer.
bg_sweep's tile-ID method disagrees with posmap → writes wrong palette
on the boss → flicker.

**Already done**: The inline hook already gating (arena_neutralize_d880=0x0C
→ tile-only in arenas). But bg_sweep STILL runs inside FFC1 gate and writes
tile-ID attrs over the position sweep's posmap attrs. This must be gated.

**Condition**: D880 < 0x0C (dungeon only) — title is already gated by FFC1.

**Implementation**: In the FFC1 gate section:
```
; Gate bg_sweep to dungeon only (D880 < 0x0C)
FA 80 D8       ; LD A, [D880]
FE 0C          ; CP 0x0C
30 xx          ; JR NC, skip_sweep (arena → skip bg_sweep)
CD sweep       ; CALL bg_sweep (dungeon only)
```

But wait — this breaks the existing FFC1 check. Better: keep FFC1 gate as-is
but gate bg_sweep inside it. OR: already handled by the arena path's position
sweep which replaces bg_sweep entirely during arenas.

**Actual state of affairs**: The colorize handler's FFC1 gate calls bg_sweep,
which is the *tile-ID* sweep (legacy, always reads the table in WRAM 0xDA00).
During arenas, scene_detect keeps 0xDA00 set to the arena-specific table. The
position sweep (POSSWEEP_ADDR) is NOT called from the colorize handler — it's
dead code.

**Recommendation**: In the FFC1 gate, replace the bg_sweep CALL with a
conditional dispatch: D880 < 0x0C → CALL bg_sweep (tile-ID sweep, dungeon),
D880 >= 0x0C → CALL position_sweep (posmap sweep, arena). OR, simpler:
just keep bg_sweep but swap the table it reads to 0xDA00 (which scene_detect
keeps current). This is already the case (the sweep was re-patched to read
WRAM 0xDA00 instead of ROM 0x7000).

**Savings**: None direct — bg_sweep still runs. But the flicker fix is
correctness, not speed.

### Gate 3: scene_detect → gate to D880 transitions only

**Problem**: scene_detect runs every frame (~20T overhead to read/comparison,
~4100T on scene change). The fast-path is only ~16T (read + compare + RET),
but even that's wasted when D880 is stable.

**Recommendation**: Keep it as-is. It's 16T/frame invested in correctness
(needed because the stage-load WRAM clear re-zeroes DF02, which would
make the cold-boot copy re-copy the dungeon table over the arena table).
The gating logic would add more complexity than the 16T savings.

### Gate 4: Cond_pal caching — already implemented

The conditional palette handler caches the previous palette → ~200T on cache
hit, ~2000T on cache miss (room change). This is fine.

### Gate 5: Attr_cleaner — only first 32 frames

Already gated via DF07/DF08. After 32 frames it's 4-byte read + RET Z (~12T).
Leave as-is.

## Stage Intro Ditty Fix

The double-ditty happens because our patches shift instruction timing enough
that the sound engine's scene-dispatch sequence fires twice. Specifically:
the game writes D880 via RST 20, our hook runs mid-write, and the extra cycle
cost pushes the sound init into a second trigger window.

**Proposed fix**: Inspect whether the sound channel registers (NR10-NR52) are
already initialized when the sound engine dispatches. The simplest mechanical
fix: add a debounce at the NR52 level — only trigger sound init if NR52 bits
0-3 (channel enable) are all zero, meaning the engine is truly starting from
silence, not re-triggering during a playback.

**Alternative**: Remove the DMG NOPs that were skipped in patch_oam_intercept.py
(line 162-168). The comment says "DMG NOPs skipped (would break sound timing)"
but we may need to ADD them back if they were responsible for the original
timing shift. Check with: `diff <(xxd rom/Penta\ Dragon\ \(J\).gb) <(xxd
rom/working/penta_dragon_dx_teleport.gb) | grep 'FF47\|FF48\|FF49'`.

**Easier fix**: Add a `CALL` to a tiny NR52 debounce at the start of the
scene-detect scene-change path. When D880 changes and we're about to update
the sound state, skip if NR52 shows active channels.

## White Screen on Boot Fix

The ~2-second white screen after cold boot comes from the attr_cleaner's
32-frame rollout — each frame it clears one row of attrs in both tilemap
regions. The white screen IS the game waiting for attrs to reach the
visible area.

**Fix**: Replace the attr_cleaner's per-frame rollout with a single-shot
clear at cold-boot. Disable LCD (LCDC bit 7 = 0), clear all 2048 bytes
of attrs in both 0x9800 and 0x9C00 tilemaps while LCD is off (no STAT
waiting needed — ~40µs total), then re-enable LCD. This is safe because
cold-boot only happens once.

The current attr_cleaner is:
```
First 32 frames: per-row clear in both tilemap regions
Frame 33+: read DF07, OR A, RET Z (~12T no-op)
```

Replace with single-shot inside the cold-boot path:
```
; At DF02 cold-boot check (inside colorize handler):
; If cold-boot:
;   1. DF02 = 0x5A (sentinel)
;   2. Disable LCD
;   3. VBK=1, clear 0x9800-0x9FFF (2048 bytes, both tilemaps)
;      Actually just do 0x9800 + 0x9C00 = 4096 bytes of writes
;      Takes ~2000T at 4 cycles/store (unrolled 16-bit stores)
;   4. VBK=0, re-enable LCD
;   5. bg_table copy (existing)
;   6. Skip attr_cleaner entirely (set DF07=0, DF08=0x5A)
```

But — disabling LCD on cold-boot might cause a visible flash. However,
the screen is already white (uninitialized CGB palette = 0x7FFF white),
so disabling/re-enabling during boot is invisible (all-white-to-all-white).

**Savings**: ~400T/frame for 32 frames (was per-row clear) → 0T after cold-boot.

## Cycle Budget Summary

| Component | Current | Optimized | Savings |
|-----------|---------|-----------|---------|
| shadow_main (gameplay) | 300T | 0T | **300T** |
| attr_cleaner (32 frames) | 400T×32 | ~2000T once | **~10,800T total** |
| bg_sweep (arena) | 600T | 0T (gated) | **600T/frame in arena** |
| scene_detect | 16T | 16T | 0T (keep) |

### Per-frame steady-state savings (after 32 frames, dungeon playing):

| Component | Before | After |
|-----------|--------|-------|
| joypad + wrapper | ~96T | ~96T |
| scene_detect | ~16T | ~16T |
| lava_override | ~50T | ~50T |
| cold-boot copy check | ~2T | ~2T |
| DF1F dec + guard | ~30T | ~30T |
| VBK save | ~12T | ~12T |
| cond_pal | ~200T | ~200T |
| attr_cleaner | ~12T | ~12T |
| bg_sweep (dungeon) | ~600T | ~600T |
| shadow_main | ~300T | **0T** |
| OAM DMA | ~200T | ~200T |
| VBK restore | ~12T | ~12T |
| **Total** | **~1530T** | **~1230T** |

Dungeon savings: ~300T/frame (shadow_main). ~2% of total frame budget.

### Arena steady-state:

Same as above but bg_sweep gated too:
| Component | Before | After |
|-----------|--------|-------|
| bg_sweep (arena) | ~600T | **0T** |
| shadow_main | ~300T | **0T** |
| **Total** | ~900T | **0T** |

Arena savings: ~900T/frame. ~1.3% of frame budget.

### Cold-boot savings:

| Component | Before (32 frames) | After (1 frame) |
|-----------|---------------------|------------------|
| attr_cleaner | 32×400T = 12,800T | ~2000T once |
| **Total** | **12,800T** | **~2000T** |

Boot saves ~10,800T. This directly eliminates the 2-second white screen.

## Implementation Plan

### Phase 2a: Gate shadow_main (trivial — 3 NOPs)

In build_v301_gdma.py `build_v301()` at the colorize handler FFC1 gate
(lines 767-769):
```
code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
```
→ Conditional: only CALL shadow_main if FFC1==0 (title screen).

### Phase 2b: Single-shot attr_clear at cold-boot (moderate)

Replace the rolling attr_cleaner in `build_v301_gdma.py` with a single-shot
clear in the cold-boot path. Remove the DF07/DF08 rolling state entirely.

### Phase 2c: Gate bg_sweep during arenas

Inside the colorize handler FFC1 gate, dispatch: D880 < 0x0C → bg_sweep
(tile-ID, dungeon), D880 >= 0x0C → position_sweep (posmap, arena).

But `build_v301_teleport.py` line 925-927 already has:
```python
# Repoint the colorize handler's `CALL bg_sweep (0x6CD0)` -> position sweep.
# [DISABLED: Using standard tile-ID bg_sweep directly for clean background/claws separation]
```

So this was tried and reverted. Reason: the position sweep's fixed posmap
washes out the boss's background/claws separation. The per-cell fixed palette
can't distinguish boss body from background elements that share a cell. The
tile-ID sweep can, because different boss-body tiles map to different palettes.

**Revised recommendation for bg_sweep**: Keep bg_sweep everywhere but use the
per-scene 0xDA00 table (already done — scene_detect keeps it current). The
tile-ID sweep is correct for both dungeon and arena; the arena flicker is
caused by scene_detect's table swap, which was the actual fix. bg_sweep on
its own never caused flicker — the stale dungeon table did.

### Phase 2d: Stage intro ditty double-fire fix

Add a simple NR52 check before the sound engine's D880 dispatch. Patch the
sound engine's init sequence to skip if channels are already running.

## Non-goals

- Removing scene_detect (required for per-frame lava override + DF02 reassert)
- Removing cond_pal (required for room-change palette transitions)
- GDMA-based attr copy (proven problematic in earlier v3.01 iteration)

## Verification

After implementation:
1. `./scripts/test_dx.sh --build` — all 5 tests must pass
2. Manual: start ROM in mgba, verify no white screen on boot
3. Manual: reach stage 1 intro, verify ditty plays once
4. Manual: reach arena, verify no BG attr alternation
5. Manual: title screen, verify no splotches
