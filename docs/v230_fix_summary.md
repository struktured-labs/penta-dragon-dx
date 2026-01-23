# v2.30 Fix Summary

## Issues in v2.29

You reported two critical issues:

1. **Direction-dependent projectile colors** - Projectiles changed color based on Sara's facing direction
2. **Purple flashing BG tiles** - Background tiles were flickering purple

## Root Causes

### Issue 1: Direction-Dependent Colors

The projectile sub-range split (CP 0x08) was incorrect. Projectiles use different tile IDs based on direction:
- Example: Sara W left-facing projectile = 0x02, right-facing = 0x05
- Our threshold split these inconsistently

**v2.29 logic**:
```
IF tile < 0x08: Sara projectile (Palette 0)
ELSE: Enemy projectile (Palette 3)
```

This caused some directions to get Sara colors, others to get enemy colors.

### Issue 2: Purple Flashing BG

The C register was used to store Sara form state in the palette loader, but C is likely used by other game code. This caused interference with BG palette operations.

## v2.30 Solution

### Fix 1: Simplified Projectile Detection

**Removed sub-range detection entirely:**
```
ALL projectiles (0x00-0x0F): Palette 0 (dynamic)
```

**Trade-off**: Enemy projectiles are now also colored based on Sara's form:
- Sara W: All projectiles are pink/red
- Sara D: All projectiles are green

This is less ideal than distinct colors, but provides:
- ✅ Consistent colors (no direction dependency)
- ✅ Form-based coloring still works
- ✅ No crashes or flickering

### Fix 2: Register Usage

**Changed from C register to stack:**
```asm
; v2.29 (broken):
LDH A, [0xFFBE]
LD C, A  ; Used C register (conflict!)

; v2.30 (fixed):
LDH A, [0xFFBE]
PUSH AF  ; Save on stack
; ... later ...
POP AF   ; Restore when needed
```

This avoids register conflicts with game code.

## What to Test

### Test 1: Direction Independence

**Save state**: `level1_sara_w_alone.ss0`

**Steps**:
1. Fire projectiles facing left
2. Fire projectiles facing right
3. Observe colors

**Expected**: Projectiles should be **consistently pink/red** regardless of direction

**Regression check**: If colors still vary by direction, there's a deeper issue

### Test 2: BG Flashing Gone

**Save state**: Any level 1 save state

**Steps**:
1. Play for 30-60 seconds
2. Observe background tiles

**Expected**: No purple flashing on background tiles

**Regression check**: If flashing persists, different root cause

### Test 3: Form-Based Coloring

**Save states**: `level1_sara_w_alone.ss0` and `level1_sara_d_alone.ss0`

**Steps**:
1. Load Sara W save state → Fire projectiles
2. Load Sara D save state → Fire projectiles

**Expected**:
- Sara W: Pink/red projectiles
- Sara D: Green projectiles

### Test 4: Enemy Projectiles

**Save state**: `level1_sara_w_4_hornets.ss0`

**Steps**:
1. Observe hornet projectiles
2. Compare to Sara W projectiles

**Expected**:
- Both will be **pink/red** (same as Sara W)
- This is the trade-off for fixing direction issue

**Ideal future**: Once we map tile usage correctly, we can restore distinct enemy colors

## Quick Test Command

```bash
# Rebuild ROM
uv run python scripts/create_vblank_colorizer_v230.py

# Test
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb -t save_states_for_claude/level1_sara_w_alone.ss0
```

## Success Criteria

- ✅ No direction-dependent projectile colors
- ✅ No purple flashing BG tiles
- ✅ Projectiles are pink for Sara W, green for Sara D
- ✅ All v2.28 features still work (bosses, jet forms, BG items)

**Trade-off accepted**:
- ⚠️ Enemy projectiles also colored by Sara's form (not distinct)

## Next Steps

If v2.30 works well:

### Option A: Keep Simple Approach
- Mark v2.30 as STABLE
- Accept that all projectiles share Sara's color
- Move to powerup-based coloring (Phase 4)

### Option B: Investigate Tile Usage
- Use MCP/Lua to dump projectile tiles per direction
- Map exact tile ranges:
  * Sara W left: 0x?? - 0x??
  * Sara W right: 0x?? - 0x??
  * Sara D left: 0x?? - 0x??
  * Sara D right: 0x?? - 0x??
  * Enemy projectiles: 0x?? - 0x??
- Create v2.31 with correct sub-range detection

### Option C: Alternative Approach
- Use sprite position or animation frame to distinguish
- More complex, may hit VBlank timing limits

## Files Changed

- `scripts/create_vblank_colorizer_v230.py` - Simplified projectile detection + register fix
- No changes to palettes or documentation (approach is temporary)

## Version Comparison

| Version | Status | Projectile Colors | Issues |
|---------|--------|-------------------|--------|
| v2.28 | Stable | White/gray (all same) | No projectile coloring |
| v2.29 | BROKEN | Direction-dependent | BG flashing, inconsistent colors |
| v2.30 | TESTING | Form-based (all same as Sara) | Enemy projectiles not distinct |

## Recommendation

Test v2.30 thoroughly. If it fixes both issues:

1. Use v2.30 as stable base
2. Document tile usage patterns for future refinement
3. Consider Option A (accept trade-off) vs Option B (investigate further)

The simplified approach in v2.30 prioritizes **stability** over **ideal coloring**. We can always refine later once tile patterns are better understood.
