# Penta Dragon DX

**Game Boy Color colorization of Penta Dragon (ペンタドラゴン)**

This project successfully converts the original DMG (Game Boy) ROM to a fully playable CGB (Game Boy Color) version with vibrant colors while preserving all original gameplay mechanics.

## Status: ✅ WORKING

The colorized ROM is complete and playable. All features implemented:
- ✅ Full CGB compatibility (works on GBC/GBA)
- ✅ 8 background palettes with saturated colors
- ✅ 8 sprite palettes for colorful characters
- ✅ Preserved input handling (all controls work)
- ✅ Display compatibility (fixed white screen freeze)
- ✅ Minimal ROM modifications (18-byte trampoline only)

## Quick Start

### Build the Colorized ROM

**Option 1: Use YAML configuration (recommended)**
```bash
# Edit palettes to your liking
nano palettes/penta_palettes.yaml

# Build ROM with custom palettes
uv run python scripts/create_dx_rom_from_yaml.py
```

**Option 2: Use hardcoded palettes**
```bash
python3 scripts/create_dx_rom.py
```

Output: `rom/working/penta_dragon_dx_FIXED.gb`

### Customize Palettes

```bash
# Interactive palette color converter
python3 scripts/palette_tool.py

# Quick conversions
python3 scripts/palette_tool.py --hex #FF8800  # Orange to BGR555
python3 scripts/palette_tool.py --rgb 255 128 0  # RGB to BGR555
python3 scripts/palette_tool.py --examples  # Show common colors
```

### Test

```bash
mgba-qt rom/working/penta_dragon_dx_FIXED.gb
# Or with savestate:
mgba-qt -t rom/working/lvl1.ss0 rom/working/penta_dragon_dx_FIXED.gb
```

## Technical Overview

### Architecture

The solution uses a minimal trampoline approach that preserves the original input handler while adding CGB palette loading:

```
VBlank Handler (0x06DD)
  └─> CALL 0x0824 (18-byte trampoline)
        ├─> Switch to Bank 13
        ├─> CALL 0x6D00 (Combined function in bank 13)
        │     ├─> Execute original input handler inline
        │     └─> Load CGB palettes (128 bytes)
        └─> Restore Bank 1
```

### ROM Modifications

1. **Display Patch (0x0067)**: CGB detection to prevent LCD freeze
2. **Trampoline (0x0824)**: 18-byte bank-switching stub
3. **Palette Data (Bank 13:0x6C80)**: 128 bytes (8 BG + 8 OBJ palettes)
4. **Combined Function (Bank 13:0x6D00)**: 74 bytes (input + palette loader)

### Key Insight

The ROM has **zero free space** in bank 0 and bank 1. The only safe approach is:
- Use the existing 46-byte slot at 0x0824 (original input handler)
- Place all new code in bank 13 (unused bank)
- Execute input handler code **inline** (not relocated) to avoid state corruption


### Color Palettes

The game uses 16 total palettes (8 background + 8 sprite), fully customizable via `palettes/penta_palettes.yaml`:

**Background Palettes:**
- 0: Dungeon Floors (default green theme)
- 1: Lava & Danger Areas (red/fire theme)
- 2: Water & Ice Areas (blue/ice theme)
- 3: Desert & Sand Areas (yellow/sand theme)
- 4: Forest & Nature Areas (cyan/nature theme)
- 5: Castle & Stone Areas (magenta/purple theme)
- 6: Sky & Clouds (light blue/sky theme)
- 7: Boss & Special Areas (pink/special theme)

**Sprite/Object Palettes:**
- 0: Main Character (Penta Dragon) - orange/brown
- 1: Basic Enemies - green
- 2: Fire Enemies - red
- 3: Ice/Water Enemies - blue
- 4: Flying Enemies - yellow/gold
- 5: Poison/Toxic Enemies - cyan
- 6: Mini-Bosses - magenta/purple
- 7: Main Bosses - bright yellow/orange

Each palette has 4 colors in BGR555 format. Edit `palettes/penta_palettes.yaml` to customize:

```yaml
obj_palettes:
  MainCharacter:
    name: "Penta Dragon (Player)"
    colors: ["0000", "7FFF", "7E00", "4800"]  # Trans→White→Orange→Brown
    notes: "Warm colors for hero"
```

**Color Format:** BGR555 (15-bit)
- 4-digit hex: BBBBBGGGGGRRRRR (5 bits each)
- Example: `7FFF` = white, `001F` = red, `03E0` = green, `7C00` = blue

Use `scripts/palette_tool.py` for easy color conversion!

## Project Structure

```
.
├── rom/
│   ├── Penta Dragon (J).gb          # Original ROM (gitignored)
│   └── working/
│       └── penta_dragon_dx_FIXED.gb # Generated CGB ROM
├── scripts/
│   └── create_dx_rom.py             # ROM generation script
├── src/
│   └── penta_dragon_dx/
│       ├── __init__.py
│       ├── cli.py                   # CLI commands
│       └── display_patcher.py       # Display compatibility patches
└── palettes/
    └── penta_palettes.yaml          # Palette definitions (reference)
```

## Development History

This project went through multiple iterations to solve ROM integration challenges:

1. **v1 (colorful)**: Proved palette loading works, but broke input handling
2. **v2-v3**: Attempted VBlank hooks at 0x07A0, but overwrote active game code
3. **v4**: Tried relocating input handler to bank 13, caused immediate crashes
4. **boot_final**: Boot-time palette injection failed due to lack of free space
5. **FIXED**: ✅ Final solution using inline execution in bank 13 with minimal trampoline

### Lessons Learned

- ROM has absolutely **zero free space** in bank 0 and bank 1
- Cannot relocate and call input handler - must execute inline
- 0x07A0-0x07E0 contains active game code (not free space)
- Bank 13 is the only safe location for new code
- Minimal trampoline (18 bytes) is the key to success


## Legal Notice

You must supply your own legally obtained ROM. This repository does not include copyrighted ROM data. Only the patching tools and generated colorized ROM (for personal use) are included.

## Credits

- Original Game: Penta Dragon (J) - Game Boy
- Colorization: penta-dragon-dx project
- Tools: Python, UV, mGBA
