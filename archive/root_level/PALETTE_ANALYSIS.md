# Palette Injection Analysis - December 1, 2025

## Current Status

### ✅ Successfully Verified
- ROM palette data injection: All 8 OBJ palettes correctly written to bank 13 @ 0x6CC0
- Trampoline mechanism: Input handler at 0x0824 correctly calls bank 13 combined function
- Combined function: Loads palettes after ~60 frame delay (1 second)
- YAML → ROM pipeline: Palettes now read from YAML and match binary data in ROM

### 🔍 Key Findings

#### Palette Usage (from live mGBA capture)
**All visible sprites use OBJ Palette 0:**
- Sprites 0-3: Player character (4 sprites = 16x16 metasprite)
- Sprites 8-11: Monster/enemy (4 sprites = 16x16 metasprite)

**OBJ Palette 0 in CGB RAM (after game modification):**
```
Expected: 0000 7C1F 7C1F 7C1F  (pure magenta test palette)
Captured: 0000 7C1F 7E00 4800  (magenta → orange → brown gradient)
```

#### Analysis
1. **Game overwrites palette data**: The game writes new CGB palette data after our loader runs
2. **Single palette for all sprites**: Both player and monsters use palette 0
3. **Cannot separate via palette index**: Differentiation must come from the actual color values, not palette assignment

### 🎯 Next Steps

1. **Identify palette write locations**: Find where game writes to FF68/FF69 (BG) and FF6A/FF6B (OBJ)
2. **Hook or patch palette writes**: Either:
   - Hook the write routine to modify colors on-the-fly
   - Patch palette data tables in ROM before game reads them
3. **Implement per-entity colors**: Once we control the palette data source, create distinct colors for:
   - Player character (palette 0, indices 1-3)
   - Different monster types (same palette 0, but we can have multiple "versions")

### 📊 Current Palette Configuration

**OBJ Palette 0 (MainCharacter) - from YAML:**
```yaml
colors: ["0000", "7C1F", "7C1F", "7C1F"]
notes: "TEST: All pure magenta - if player uses this, they'll be BRIGHT MAGENTA"
```

**OBJ Palettes 1-7 (Enemies):**
- Palette 1 (EnemyBasic): Pure yellow `7FE0`
- Palette 2 (EnemyFire): Pure red `001F`
- Palette 3 (EnemyIce): Pure cyan `03FF`
- Palette 4 (EnemyFlying): Pure green `03E0`
- Palette 5 (EnemyPoison): Pure blue `7C00`
- Palette 6 (MiniBoss): Pure white `7FFF`
- Palette 7 (MainBoss): Orange `03FF`

**Status**: All correctly injected into ROM but overwritten by game at runtime.

### 🔧 Tools Created
1. `scripts/verify_palette_data.py` - Binary ROM verification against YAML
2. `scripts/verify_palettes.lua` - mGBA Lua script to capture runtime palette state
3. `scripts/verify_palette_injection.py` - Automated verification runner (needs mgba-qt)

### 📝 Notes
- Game uses DMG palette registers (FF47/FF48/FF49) which CGB translates via palette RAM
- OBP0/OBP1 writes affect which colors from CGB palette RAM are used
- Need to trace where game stores source palette data (likely in ROM or WRAM tables)
