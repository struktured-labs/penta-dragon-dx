# Projectile Tile Mapping - v2.29

## Overview

This document describes the projectile tile range assumptions used in v2.29. These ranges are **educated guesses** based on:
- The existing tile range 0x00-0x1F for effects/projectiles
- The current implementation that treats all < 0x10 as projectiles
- Logical subdivision of the projectile range

**Status**: AWAITING VERIFICATION
These ranges need to be tested and may require adjustment.

## Tile Range Assumptions

### Projectile Tiles (0x00-0x0F)

| Range | Source | Palette | Color |
|-------|--------|---------|-------|
| 0x00-0x07 | Sara projectiles | 0 (dynamic) | Pink (Sara W) or Green (Sara D) |
| 0x08-0x0F | Enemy projectiles | 3 | Blue/dark (same as Crow) |

### Extended Effects (0x10-0x1F)

| Range | Type | Current Handling |
|-------|------|------------------|
| 0x10-0x1F | Effects/explosions | Falls through to default palette (4) |

**Note**: These tiles may also be projectiles. Further testing needed.

## Dynamic Palette 0 System

### How It Works

1. **Palette Loader** reads Sara form flag (0xFFBE) at initialization
2. **Based on Sara form**, loads different colors into Palette 0:
   - Sara W (0xFFBE = 0) → Pink/red projectile colors
   - Sara D (0xFFBE ≠ 0) → Green projectile colors
3. **Tile Colorizer** assigns Palette 0 to tiles 0x00-0x07 (Sara projectiles)

### Palette Data

**SaraProjectileWitch (Pink/Red)**
```yaml
colors: ["0000", "7C1F", "5817", "3010"]
# Trans, Bright pink, Pink-red, Dark red
```

**SaraProjectileDragon (Green)**
```yaml
colors: ["0000", "03E0", "01C0", "0000"]
# Trans, Bright green, Dark green, Black
```

## Colorizer Logic

### Tile Detection Flow

```
For each sprite tile ID:
  IF tile < 0x10:
    IF tile < 0x08:
      → Sara projectile (Palette 0 - dynamic)
    ELSE:
      → Enemy projectile (Palette 3 - blue/dark)
  ELSE IF tile < 0x20:
    → Effect/explosion (default palette)
  ELSE:
    → (Continue with entity tile ranges...)
```

### Assembly Implementation

```asm
; Projectile sub-range check (tiles 0x00-0x0F)
check_projectile_subrange:
    LD A, C             ; Get tile ID
    CP 0x08             ; Compare to 0x08
    JR C, sara_projectile  ; If < 0x08, Sara projectile

enemy_projectile:
    LD A, 3             ; Palette 3 (Crow - blue/dark)
    JR apply_palette

sara_projectile:
    LD A, 0             ; Palette 0 (dynamic)
    JR apply_palette
```

## Testing Requirements

### Critical Tests

1. **Sara W firing projectiles**
   - Save state: `level1_sara_w_alone.ss0`
   - Expected: Pink/red projectiles
   - Verify tiles are in 0x00-0x07 range

2. **Sara D firing projectiles**
   - Save state: `level1_sara_d_alone.ss0`
   - Expected: Green projectiles
   - Verify tiles are in 0x00-0x07 range

3. **Enemy projectiles**
   - Save states: `level1_sara_w_4_hornets.ss0`, `level1_sara_w_crow.ss0`
   - Expected: Blue/dark projectiles
   - Verify tiles are in 0x08-0x0F range

4. **Form switching**
   - Collect dragon powerup while firing
   - Expected: Projectile color changes from pink to green
   - Verify Palette 0 contents update on form change

### Fallback Plan

If tile ranges are incorrect:

**Option A**: Adjust tile range boundaries
- Change CP 0x08 threshold based on actual tile usage
- May need 0x04, 0x06, or other values

**Option B**: All projectiles same color initially
- Set both projectile ranges to Palette 0
- Focus on dynamic palette loading (already works)
- Defer sub-range detection until more data available

**Option C**: No sub-range detection
- All tiles < 0x10 use Palette 0 (dynamic)
- No distinction between Sara and enemy projectiles
- Simplest fallback, still provides form-based coloring

## Known Limitations

1. **Tile ranges are assumptions** - Need OAM dump verification
2. **No powerup-based colors yet** - Requires finding powerup memory address
3. **Extended effects (0x10-0x1F)** - Not yet handled, fall through to default
4. **Boss projectiles** - Tiles 0x78+ not affected by this system

## Future Enhancements

### Powerup-Based Palette 0 (Phase 4)

Once powerup address is found (e.g., 0xFFC3), expand palette loading:

```asm
; Check powerup state
LDH A, [0xFFC3]
OR A
JR Z, no_powerup

; Powerup active - load special palette
CP 0x01  ; Spiral?
JR NZ, +skip
; Load cyan spiral palette into Palette 0
+skip:
CP 0x02  ; Shield?
JR NZ, +skip
; Load gold shield palette into Palette 0
+skip:
; (More powerup types...)

no_powerup:
; Load normal Sara projectile palette based on form
```

### Extended Effects (0x10-0x1F)

Potential color assignments:
- 0x10-0x13: Small explosions → Palette 0
- 0x14-0x17: Large explosions → Palette 4 (yellow/orange)
- 0x18-0x1F: Special effects → Palette 3 (blue)

## Version History

- **v2.29**: Initial projectile sub-range implementation
  - Dynamic Palette 0 based on Sara form
  - Sara projectiles (0x00-0x07) vs enemy projectiles (0x08-0x0F)
  - Awaiting testing and verification

## Files Modified

- `scripts/create_vblank_colorizer_v229.py` - Implementation
- `palettes/penta_palettes_v097.yaml` - Projectile palettes added
- `docs/projectile_tile_mapping.md` - This document
