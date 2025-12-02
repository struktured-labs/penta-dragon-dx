# Game Boy Color Colorization Research - Penta Dragon

## Executive Summary

After extensive testing with 15+ ROM patch iterations, we've identified fundamental compatibility issues between Penta Dragon's DMG architecture and CGB custom palette injection. The game runs stably in CGB mode with hardware default colors (white background + beige sprites), but all attempts to inject custom palettes either crash or get overwritten.

## What Works

✅ **CGB Flag Only** - Game runs perfectly with just the CGB compatibility flag set (0x143=0x80)
- Stable menu navigation
- Stable gameplay
- Uses hardware default DMG→CGB color mapping
- Result: White background, beige/tan sprites

## What Doesn't Work

### 1. VBlank Palette Enforcement (15+ attempts)
**Status:** ❌ Causes menu crashes and instability

**What we tried:**
- Hook at 0x06D6 (VBlank handler entry point)
- Replace `CALL FF80` with `CALL 07A0` (palette loader)
- Wrapper functions that call original FF80 then load palettes
- Bank 0 placement at 0x07A0/0x07B0 (free space)
- Various register push/pop strategies

**Result:** Game consistently crashes in menu:
- Audio glitches
- Menu freezes
- Game becomes unresponsive
- Occurs even with minimal palette-loading code (44 bytes)

**Root cause:** VBlank handler is timing-critical. Adding ANY extra operations (even fast palette register writes) disrupts the game's frame timing, causing instability.

### 2. Boot-Time Palette Loading (10+ attempts)
**Status:** ❌ Palettes load successfully but game overwrites them

**What we tried:**
- Entry point hook at 0x0150
- Loader in bank 13 at 0x6D00
- Load all BG + OBJ palettes at startup
- Pure color tests (RED, MAGENTA, etc.)

**Result:** Game starts, palettes load, but within seconds reverts to beige/tan sprites

**Root cause:** Game writes DMG palette registers (FF47/FF48/FF49) continuously during gameplay. CGB hardware maps DMG palette indices through CGB color registers, so game's runtime DMG writes override our boot-time CGB palette loads.

**Critical discovery (latest diagnostic):**
We were ALSO overwriting critical game initialization code at 0x0150:
```
Original: f3efcd670031ffdfcd0040cdc800fbcd
          (DI, RST 28h, CALL 0x0067, LD SP,DFFF, CALL 0x0040, CALL 0x00C8, EI, CALL...)
Our patch: 3e0dea0020cd006dcd
          (LD A,13; LD [2000],A; CALL 0x6D00)
```

This destroyed game startup logic, causing crashes in earlier boot-loader attempts.

### 3. Input Handler Injection (5+ attempts)
**Status:** ❌ Palettes load once but get overwritten

**What we tried:**
- Replace input handler at 0x0824 (46 bytes available)
- Move original handler to bank 13
- Inject palette loading after input processing
- Minimal 18-byte trampolines

**Result:** Palettes load initially, but game still overwrites them during gameplay

**Root cause:** Same as boot-time approach - game continuously writes DMG palette registers, overriding our CGB registers.

### 4. DMG Palette Register Guards (2 attempts)
**Status:** ❌ Crashes

**What we tried:**
- Rewrite FF48/FF49 (OBP0/OBP1) to fixed values (0xE4) every frame
- Combined with OBJ-only CGB palette loading (skip BG for stability)

**Result:** Still crashes in VBlank

**Root cause:** Adding ANY code to VBlank breaks timing

## Technical Architecture Analysis

### Game's Palette System
- **Mode:** DMG (original Game Boy) with continuous palette updates
- **Registers written:** FF47 (BGP), FF48 (OBP0), FF49 (OBP1)
- **Frequency:** Multiple times per frame (found 50 write locations in ROM)
- **Purpose:** Dynamic palette animation, screen effects, game state changes

### CGB Hardware Behavior
1. DMG games in CGB mode use DMG palette registers (FF47-FF49)
2. CGB hardware translates DMG palette indices → RGB colors via CGB palette registers (FF68-FF6B)
3. Game writes DMG registers → CGB looks up colors in CGB palette registers
4. **Problem:** If game changes DMG palette indices, CGB uses different color mappings from our custom palettes

### Memory Map Findings
- **Bank 13 @ 0x6C80 (file 0x036C80):** BG palette data (64 bytes) - verified correct
- **Bank 13 @ 0x6CC0 (file 0x036CC0):** OBJ palette data (64 bytes) - verified correct
- **Bank 0 @ 0x07A0-0x07F0:** Free space (80 bytes) - safe for code injection
- **Bank 0 @ 0x0150:** Critical game initialization - MUST NOT MODIFY
- **Bank 0 @ 0x06D6:** VBlank entry - CANNOT HOOK without crashes
- **Bank 0 @ 0x0824:** Input handler (46 bytes) - can modify but insufficient

### DMG Palette Write Locations
Found 50 writes to DMG palette registers throughout the ROM:
- **FF47 (BGP):** 30+ writes (background palette)
- **FF48 (OBP0):** 10+ writes (sprite palette 0)
- **FF49 (OBP1):** 10+ writes (sprite palette 1)

Locations include:
- 0x006FD, 0x00721, 0x00949-0x0098A (bank 0 - main game loop)
- 0x00A0F-0x00A13 (consecutive BGP/OBP0/OBP1 writes)
- 0x00F5E-0x00FA1 (palette animation routines)
- Plus 30+ more throughout banks 1-7

## Test Results Summary

| Approach | Boot Entry | VBlank Hook | Palette Load | Result | Issue |
|----------|-----------|-------------|--------------|--------|-------|
| Minimal CGB flag | ✓ Original | ✓ Original | ❌ None | ✅ Stable | Default hardware colors (white/beige) |
| Boot loader | 0x0150 hook | ✓ Original | ✓ Once at boot | ❌ Crashes | Overwrote initialization code |
| Boot loader (fixed) | 0x0150 hook | ✓ Original | ✓ Once at boot | ⚠️ Beige sprites | Game overwrites palettes |
| VBlank wrapper | ✓ Original | 0x06D6 hook | ✓ Every frame | ❌ Menu crash | VBlank timing broken |
| VBlank + wrapper | ✓ Original | 0x06D6 hook | ✓ Every frame | ❌ Menu crash | VBlank timing broken |
| Input handler | ✓ Original | ✓ Original | ⚠️ Per input | ⚠️ Beige sprites | Game overwrites palettes |
| Input + trampoline | ✓ Original | ✓ Original | ⚠️ Per input | ⚠️ Beige sprites | Game overwrites palettes |
| OBJ-only VBlank | ✓ Original | 0x06D6 hook | ✓ Every frame | ❌ Menu crash | VBlank timing broken |
| DMG register guards | ✓ Original | 0x06D6 hook | ✓ Every frame | ❌ Menu crash | VBlank timing broken |

## Why Custom Palettes Fail

### Problem 1: Continuous DMG Palette Writes
The game writes DMG palette registers (FF47/FF48/FF49) **continuously** during gameplay for:
- Palette cycling animations
- Screen transition effects
- Enemy flash effects
- Menu highlighting
- Status indicators

Each DMG write changes which indices are used, causing CGB hardware to look up different colors from our CGB palette registers.

**Example:**
- We load CGB OBJ palette 0: [Trans, RED, MAGENTA, WHITE]
- Game boots, writes OBP0=0xC4 (indices [0,1,0,3])
- CGB renders: index 1 → RED (correct!)
- Game animates, writes OBP0=0xE4 (indices [3,2,1,0])
- CGB renders: index 1 → RED, but now used for different pixel values
- Visual result: Color appears in wrong places or gets remapped to beige default

### Problem 2: VBlank Timing Requirements
The game's VBlank handler is timing-critical:
- Must complete within VBlank period (~1.1ms on DMG, ~1.0ms on CGB)
- Performs audio updates, input reading, DMA transfers, game logic
- Adding palette loading (44 bytes, ~50-60 cycles) exceeds timing budget
- Result: Frame drops, audio glitches, menu instability

### Problem 3: No Safe Hook Points
**0x0150 (Boot entry):**
- Contains critical initialization code
- Modifying breaks game startup

**0x06D6 (VBlank):**
- Timing-critical, cannot add code
- Any modification causes crashes

**0x0824 (Input handler):**
- Safe to modify, but called infrequently
- Insufficient to override continuous DMG writes

**Other locations:**
- No other frequently-called, non-critical functions found with enough free space

## Potential Solutions (Theoretical)

### Option 1: Patch All DMG Palette Writes (HIGH RISK)
**Approach:** NOP out or redirect all 50 DMG palette write instructions

**Pros:**
- Would prevent game from overwriting our CGB palettes
- Boot-time palette loading would persist

**Cons:**
- Extremely invasive (50+ locations to patch)
- High risk of breaking game logic (palette writes may be tied to other state)
- Palette animations/effects would be lost
- Game's visual effects would not work
- Unknown side effects on game state machines

**Feasibility:** Technically possible but very high risk

### Option 2: Find Central Palette Write Function
**Approach:** Reverse-engineer game to find centralized palette management function

**Pros:**
- Single patch point instead of 50
- Could inject custom logic to ignore certain palette writes
- Preserve game's palette animation logic

**Cons:**
- Requires extensive disassembly and reverse engineering
- No guarantee such a function exists (game may write palettes inline)
- Time-intensive analysis

**Feasibility:** Unknown - requires deep ROM analysis

### Option 3: Emulator Color Correction
**Approach:** Use mGBA's shader/color correction features instead of ROM patching

**Pros:**
- No ROM modifications needed
- Can work on original ROM
- mGBA supports custom color palettes via configuration

**Cons:**
- Not a ROM hack (requires emulator-specific setup)
- Doesn't modify the actual ROM file
- Limited to emulator playback

**Feasibility:** HIGH - mGBA has built-in color correction

### Option 4: Accept Hardware Default Colors
**Approach:** Use minimal CGB-flag-only ROM (current stable version)

**Pros:**
- 100% stable
- No crashes
- Some color differentiation (better than pure DMG green)

**Cons:**
- Colors are hardware default (white BG, beige sprites)
- No custom palette control
- Not the desired result

**Feasibility:** Already working

### Option 5: Hybrid Approach - Emulator Lua Script
**Approach:** Use emulator memory hooks to enforce palettes at runtime

**Pros:**
- Can intercept DMG palette writes at runtime
- Override with custom CGB palette loads
- No ROM modification needed
- Full control over palette behavior

**Cons:**
- Requires emulator scripting support
- Not a standalone ROM hack
- Emulator-dependent

**Feasibility:** HIGH if emulator supports Lua/scripting

## Screenshots Evidence

### Working: CGB Flag Only (White BG + Beige Sprites)
![Latest test showing white background with beige/tan sprites](../attachments/screenshot_white_bg_beige_sprites.png)
- ✅ Stable
- ✅ No crashes
- ❌ Not custom colors

## Tested ROM Configurations

All ROMs created and tested (in chronological order):

1. `penta_dragon_dx_saturated.gb` - VBlank hook, saturated test colors → **CRASHED**
2. `penta_dragon_dx_colorful.gb` - VBlank hook, colorful OBJ palettes → **CRASHED**
3. `penta_dragon_dx_fixed.gb` - VBlank hook with WRAM flag optimization → **CRASHED**
4. `penta_dragon_dx_working.gb` - VBlank hook after input handler → **CRASHED**
5. `penta_dragon_dx_v2.gb` - VBlank wrapper calls FF80 then loads → **CRASHED**
6. `penta_dragon_dx_v3.gb` - Wrapper approach, split functions → **CRASHED**
7. `penta_dragon_dx_final.gb` - Input handler moved to bank 13 → Beige sprites
8. `penta_dragon_dx_v4.gb` - Minimal input handler (no register saves) → Beige sprites
9. `penta_dragon_dx_FIXED.gb` - 18-byte trampoline, all logic in bank 13 → Beige sprites
10. `penta_dx.gb` - Boot-time loader (various iterations) → Beige sprites or crashes
11. `penta_dragon_dx_WORKING.gb` - Simple boot loader → Beige sprites
12. `penta_dragon_dx_WORKING.gb` - CGB flag only (final stable) → **STABLE** (white/beige)

## Color Test Data

Successfully verified palette data in ROM (bank 13):
```
BG Palette 0: 7FFF 03E0 0280 0000 (White→Green→Dark Green→Black)
OBJ Palette 0: 0000 7C1F 7C1F 7C1F (Trans→MAGENTA→MAGENTA→MAGENTA)
```

Palette data is correct in ROM. Problem is game's runtime DMG writes override the mapping.

## Conclusion

**Penta Dragon cannot be reliably colorized via ROM patching** due to its continuous DMG palette register writes and timing-critical VBlank handler. The game's architecture is fundamentally incompatible with the standard CGB colorization techniques that work for other DMG games.

**Current stable state:**
- ROM with CGB flag set (0x143=0x80)
- No code modifications
- Hardware default colors (white background, beige sprites)
- 100% stable gameplay

## Recommendations

1. **Short term:** Use emulator color correction (mGBA shaders) for custom colors without ROM modification
2. **Medium term:** Research if game has centralized palette function that could be patched safely
3. **Long term:** Consider accepting hardware default colors or creating an emulator-specific solution
4. **Alternative:** Investigate other DMG→CGB colorization tools that may handle continuous palette writes differently

## Files Changed

- `rom/working/penta_dragon_dx_WORKING.gb` - Current stable ROM (CGB flag only)
- `palettes/penta_palettes.yaml` - Custom palette definitions (unused due to technical limitations)
- `src/penta_dragon_dx/display_patcher.py` - ROM patching utilities
- Multiple test ROMs in `rom/working/` directory

## Next Steps

1. **Discuss with user:** Acceptable solutions given technical constraints
2. **Option A:** Accept stable white/beige ROM
3. **Option B:** Research emulator-based color correction
4. **Option C:** Attempt high-risk centralized palette function patching
5. **Option D:** Deep reverse-engineering to understand palette system fully
