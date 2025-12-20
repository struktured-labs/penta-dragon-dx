# 100% Reliable Approach for Distinct Colors Per Monster Type

## Current Problem Analysis

### What's Preventing Distinct Colors:

1. **Game overwrites OAM continuously** - Our runtime modifications get overwritten
2. **Input handler runs too infrequently** - Only when buttons pressed, not every frame
3. **VBlank hooks crash** - Timing-critical, any modification breaks the game
4. **Multiple sprite loop passes slow down game** - Running 10x per input causes slowdown

### Root Cause:
We're trying to **override** the game's behavior at runtime, but the game's code runs **after** ours and overwrites our changes.

## 100% Reliable Solution: Patch Game's Palette Assignment Code

Instead of overriding at runtime, **patch the game's own code** that assigns palettes to sprites.

### Approach: Find and Patch Palette Assignment Locations

The game has ~50 locations where it writes DMG palette registers (FF48/FF49). We need to:

1. **Find where the game assigns palettes to sprites** (not just writes DMG registers)
2. **Patch those locations** to use our tile-to-palette lookup table
3. **This is tedious but 100% reliable** because we're modifying the game's own logic

### Implementation Strategy:

#### Step 1: Reverse Engineer Palette Assignment
- Use mGBA Lua scripts to trace where OAM palette bits are written
- Find the functions that set sprite attributes
- Map tile IDs → palette assignments in game code

#### Step 2: Create Tile-to-Palette Lookup Table
- 256-byte table: `table[tile_id] = palette_id`
- Store in Bank 13 @ 0x6E00
- 0xFF = don't modify (keep game's original)

#### Step 3: Patch Game Functions
- Find each location where game sets sprite palette
- Replace with: `palette = lookup_table[tile_id]`
- This ensures game's own code uses our palettes

### Why This Works:

✅ **100% Reliable**: Game's code uses our palettes, no runtime override needed
✅ **No Timing Issues**: Runs at game's natural pace, not forced
✅ **No Slowdown**: No multiple passes needed
✅ **Extensible**: Just update lookup table for new monster types
✅ **Stable**: No VBlank hooks or input handler modifications

### Trade-offs:

❌ **Tedious**: Need to find and patch multiple locations
❌ **Requires Reverse Engineering**: Need to understand game's code structure
❌ **Time-Intensive**: May take days to find all locations

### Alternative: Patch DMG Palette Write Functions

Instead of patching sprite assignment, patch where game writes DMG palettes:

1. Find all 50 locations that write FF48/FF49
2. Replace with: Load CGB palettes instead
3. This prevents game from overwriting our CGB palettes

**Pros**: Simpler - just replace palette writes
**Cons**: May break palette animations/effects

### Recommended Path Forward:

1. **Short-term (this week)**: Use Lua script to trace OAM writes
   - Find where game sets sprite palette attributes
   - Document all locations

2. **Medium-term (next week)**: Implement lookup table + patch first location
   - Test with Sara W only
   - Verify stability

3. **Long-term (following weeks)**: Expand to all monster types
   - Patch all palette assignment locations
   - Full colorization

### Tools Needed:

- mGBA Lua scripting for tracing
- Disassembler (BGB or custom) to analyze code
- ROM patching tools
- Test framework for verification

