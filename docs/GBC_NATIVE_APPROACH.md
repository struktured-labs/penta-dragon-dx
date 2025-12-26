# GBC-Native Palette Approach

## Key Difference: GB vs GBC Palette System

### GB (DMG) Approach:
- Uses **DMG palette registers** (FF47/FF48/FF49)
- Single palette for all sprites (monochrome)
- Game continuously writes to these registers
- OAM palette bits are ignored (only 2 shades)

### GBC-Native Approach:
- Uses **CGB palette RAM** (FF68-FF6B)
- 8 separate OBJ palettes (0-7), each with 4 colors
- Palettes loaded ONCE at startup into palette RAM
- OAM palette bits (bits 0-2 of flags byte) select which palette (0-7)
- NO writes to DMG palette registers during gameplay

## Current Problem

The game is written for GB and:
1. Continuously writes to FF47/FF48/FF49 (DMG registers)
2. These writes interfere with CGB palette RAM
3. Causes palette conflicts and overwrites

## Solution: Make it GBC-Native

1. **Patch DMG palette register writes** → Make them no-ops or redirect
2. **Load CGB palettes once** → Already doing this
3. **Set OAM palette bits** → Already doing this
4. **Let CGB hardware handle the rest** → Natural palette selection

## Implementation Strategy

### Option 1: Hook DMG Register Writes
- Intercept writes to FF47/FF48/FF49
- Make them no-ops (do nothing)
- Let CGB palette RAM work naturally

### Option 2: Redirect DMG Writes
- Redirect FF47/FF48/FF49 writes to CGB palette RAM
- Map DMG palette values to CGB palettes

### Option 3: Patch at Source
- Find functions that write to FF47/FF48/FF49
- Replace with NOPs or CGB-compatible code

## Recommended: Option 1 (No-Op DMG Writes)

Simplest and most reliable:
- Hook writes to FF47/FF48/FF49
- Replace with RET or NOP
- CGB palettes work naturally via OAM bits

