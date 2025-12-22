# Professional GBC Colorization Approach

## Goal
Colorize Penta Dragon for Game Boy Color with at least 2 unique colors per monster type.

## Current Problem
We cannot reliably inject 2 different color palettes into 2 sprites. The verification shows 14.3% accuracy, meaning colors aren't matching.

## Professional Approach (Like FF Adventure DX)

### Phase 1: Minimal Working Test (ONE sprite, ONE palette)

**Step 1.1: Understand the Hardware**
- GBC has 8 OBJ palettes (0-7), each with 4 colors (BGR555 format)
- OAM (0xFE00-0xFE9F): 40 sprites × 4 bytes each
  - Byte 0: Y position
  - Byte 1: X position  
  - Byte 2: Tile ID
  - Byte 3: Flags (bits 0-2 = palette index)
- Palette RAM: 0xFF68-0xFF6B (BG), 0xFF6A-0xFF6B (OBJ)

**Step 1.2: Minimal Boot Loader**
- Load ONE palette (Palette 1: green/orange for SARA_W) at boot
- Write directly to palette RAM (0xFF6A-0xFF6B)
- Hook at 0x0150 (after boot, before game starts)
- Verify with mGBA debugger: read 0xFF6A-0xFF6B, should see palette values

**Step 1.3: Manual Sprite Assignment**
- Find ONE SARA_W sprite in OAM (tile 4-7)
- Manually set its palette bit to 1
- Verify visually: sprite should show green/orange
- If it works: proceed. If not: debug palette loading.

**Step 1.4: Automated Sprite Loop**
- After Step 1.3 works, automate:
  - Iterate OAM (0xFE00-0xFE9F)
  - If tile ID is 4-7: set palette bit to 1
  - Run this loop after game updates OAM (hook OAM DMA completion)

### Phase 2: Add Second Sprite/Palette

**Step 2.1: Load Second Palette**
- Load Palette 0 (red/black for DRAGONFLY) at boot
- Verify both palettes are loaded

**Step 2.2: Assign Second Sprite**
- Find DRAGONFLY sprites (tile 0-3)
- Set their palette bit to 0
- Verify both sprites show correct colors

**Step 2.3: Expand Sprite Loop**
- Update sprite loop to handle both:
  - Tiles 0-3 → Palette 0
  - Tiles 4-7 → Palette 1

### Phase 3: Verification & Debugging

**Critical Checks:**
1. **Palette Loading**: Use mGBA debugger to verify palettes are in RAM
   - Breakpoint at palette loader
   - Read 0xFF6A-0xFF6B after loader runs
   - Values should match YAML definitions

2. **OAM Assignment**: Verify sprites have correct palette bits
   - Breakpoint at sprite loop
   - Read OAM entries (0xFE00 + sprite_index * 4)
   - Byte 3 bits 0-2 should match expected palette

3. **Timing**: Ensure sprite loop runs AFTER game updates OAM
   - Hook OAM DMA completion (0x4197)
   - Game updates OAM → DMA completes → Our loop runs → Palette bits set

4. **Visual Verification**: Use automated screenshot comparison
   - Capture frame where sprite is centered
   - Compare pixel colors to reference
   - Accuracy should be >80%

## Key Principles

1. **Start Simple**: ONE sprite, ONE palette. Get it perfect before adding complexity.

2. **Verify Each Step**: Don't assume code works. Use debugger to confirm:
   - Palettes are loaded
   - Sprites are assigned
   - Colors match expectations

3. **Incremental**: Add one thing at a time. Test after each addition.

4. **Debugging Tools**:
   - mGBA debugger: Breakpoints, memory inspection
   - Lua scripts: Log palette values, OAM state
   - Screenshot comparison: Visual verification

5. **Timing Matters**: GBC palette/OAM updates must happen at safe times:
   - Boot: Safe for palette loading
   - VBlank: Safe for OAM updates
   - OAM DMA completion: Safe for palette bit assignment

## Current Issues to Fix

1. **Palette Loading**: Verify palettes are actually loaded (use debugger)
2. **Sprite Assignment**: Verify sprite loop is running and setting palette bits
3. **Timing**: Ensure sprite loop runs at the right time (after OAM DMA)
4. **Address Calculations**: Verify bank switching and address calculations are correct

## Next Steps

1. Create minimal test ROM: ONE palette, ONE sprite assignment
2. Use mGBA debugger to verify palette loading
3. Use mGBA debugger to verify sprite assignment
4. Visual verification: Does sprite show correct colors?
5. If yes: Add second palette/sprite
6. If no: Debug why (palette not loaded? sprite not assigned? wrong timing?)

