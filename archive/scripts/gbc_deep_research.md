# GBC Deep Research - 100% Sprite Palette Override

## Current Problem Analysis

**Current Approach:**
- Modifies OAM once per input handler call (0x0824)
- Runs BEFORE game code
- Game code overwrites our changes

**GBC Hardware Facts:**
1. OAM DMA occurs during HBlank (line-by-line)
2. OAM is locked during rendering (lines 0-143)
3. OAM can be modified during VBlank (lines 144-153)
4. STAT interrupt can fire at specific scanlines

## New Approach: Post-Game OAM Modification

**Key Insight:** Modify OAM AFTER game writes but BEFORE rendering.

**Strategy Options:**

### Option 1: VBlank Interrupt Hook (Most Reliable)
- Hook VBlank interrupt (0x0040)
- Modify OAM during VBlank (safe window)
- Problem: We've had crashes before - need careful implementation

### Option 2: STAT Interrupt (LCD Mode Change)
- Hook STAT interrupt (0x0048)
- Trigger on mode 0 (HBlank) or mode 1 (VBlank)
- Modify OAM during safe periods
- More granular control

### Option 3: Multiple Passes Per Frame
- Run sprite loop multiple times per input handler call
- After game code AND before next frame
- Problem: Performance impact

### Option 4: Shadow OAM + DMA
- Maintain shadow OAM copy
- Trigger OAM DMA ourselves during VBlank
- Full control but complex

## Recommended: VBlank Hook with Careful Implementation

**Why VBlank:**
- Guaranteed safe window (OAM not locked)
- Runs every frame (60Hz)
- Standard technique for sprite updates

**Implementation:**
1. Hook VBlank interrupt (0x0040)
2. Save all registers immediately
3. Modify OAM for target sprites
4. Restore registers
5. Call original VBlank handler

**Safety:**
- Minimal register usage
- Fast execution (< scanline time)
- No conflicts with game code

## Alternative: STAT Interrupt on VBlank Mode

**Why STAT:**
- More control over timing
- Can detect VBlank start precisely
- Less likely to conflict

**Implementation:**
1. Hook STAT interrupt (0x0048)
2. Check if mode == 1 (VBlank)
3. Modify OAM
4. Continue to original handler

## Performance Considerations

- VBlank: ~4560 cycles available (safe)
- Our sprite loop: ~200-300 cycles (40 sprites)
- Multiple passes: Still well within VBlank window

## Testing Strategy

1. Implement VBlank hook carefully
2. Test stability first (no crashes)
3. Verify OAM modifications persist
4. Measure performance impact
5. Verify 100% color override

