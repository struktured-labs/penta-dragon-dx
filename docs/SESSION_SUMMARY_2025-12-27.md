# Penta Dragon DX - Session Summary (December 27, 2025)

## Major Achievement: Stable Flicker-Free Colorization

Successfully implemented a **stable 5-color sprite system** with **zero flickering** for Penta Dragon DX (Game Boy to Game Boy Color conversion).

## The Breakthrough: Triple OAM Modification

The key insight that solved the flickering problem was modifying **all three OAM locations** for redundancy:
- `0xFE00` - Actual OAM (hardware sprite memory)
- `0xC000` - Shadow buffer 1
- `0xC100` - Shadow buffer 2

The game uses dual shadow buffers and DMA transfers, so modifying only one location caused race conditions and flickering. By patching all three, we ensure palette assignments persist regardless of which buffer the game reads from.

## Technical Architecture

### Slot-Based Palette Assignment (v0.52+)
Instead of tile-based lookup (which caused direction-dependent color changes), we use **OAM slot position** to determine palette:

```
Slots 0-7:   Palette 1 (Sara W - protagonist)
Slots 8-15:  Palette 2 (Monster group 1)
Slots 16-23: Palette 3 (Monster group 2)
Slots 24-31: Palette 4 (Monster group 3)
Slots 32-39: Palette 5 (Monster group 4)
```

### Bank 13 Memory Layout
All custom code lives in Bank 13 (file offset 0x034000):
```
0x6800: Palette data (128 bytes) - 8 BG + 8 OBJ palettes
0x6880: OAM palette loop (~243 bytes) - triple modification code
0x6A20: Palette loader (32 bytes) - CGB palette register writes
0x6A50: Combined function (~53 bytes) - original input + our code
```

### Trampoline at 0x0824
16-byte trampoline replaces original input handler:
1. Switch to Bank 13
2. Call combined function (original input + palette code)
3. Restore Bank 1
4. Return

## Current Palette Configuration (v0.64)

### Sara W (Protagonist) - Palette 1
```yaml
colors: ["0000", "0000", "03E0", "0280"]  # Trans, Black, Green, Dark green
```

### Monster Groups - Palettes 2-5
```yaml
Monsters1: ["0000", "5294", "2108", "0000"]  # Black and gray shades
Monsters2: ["0000", "02FF", "01DF", "00BF"]  # Orange shades
Monsters3: ["0000", "7C1F", "5010", "2808"]  # Purple shades
Monsters4: ["0000", "7FE0", "5EC0", "3D80"]  # Cyan shades
```

### Background - Dungeon
```yaml
colors: ["7FFF", "5AD6", "294A", "0000"]  # White, Light blue-gray, Dark blue-gray, Black
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/create_vblank_colorizer.py` | Main ROM builder - creates the colorized ROM |
| `palettes/penta_palettes.yaml` | Palette definitions (edit this to change colors) |
| `src/penta_dragon_dx/display_patcher.py` | CGB display compatibility patches |

## Build & Deploy Commands

```bash
# Build and deploy to local + MiSTer
uv run python scripts/create_vblank_colorizer.py && \
cp rom/working/penta_dragon_dx_FIXED.gb ~/gaming/roms/GBC/penta_dragon_dx_vX.XX.gbc && \
scp rom/working/penta_dragon_dx_FIXED.gb root@mister:/media/fat/games/GBC/penta_dragon_dx_vX.XX.gbc

# Tag in git
git add palettes/penta_palettes.yaml && git commit -m "vX.XX: description" && git tag vX.XX
```

## Version History (Today's Releases)

| Version | Changes |
|---------|---------|
| v0.52 | Stable 5-color system (8 slots each), no flickering |
| v0.60 | Sara W: Trans, Black, Red, Dark yellow |
| v0.61 | Sara W: Black body with dark yellow accents |
| v0.62 | Sara W black/green, Monsters1 black/gray |
| v0.63 | Sara W with 3 distinct colors (black, green, dark green) |
| v0.64 | Blue-gray dungeon background (replaced green) |

## Failed Approaches (For Reference)

1. **v0.44 - Code order swap**: Running palette code before input handler crashed because original handler has absolute jumps to itself
2. **v0.48 - Tile-based lookup**: Caused monsters to change color when facing different directions (tiles differ per direction)
3. **v0.51 - Memory overlap**: OAM loop grew to 378 bytes and overwrote palette loader - fixed by relocating addresses

## What's Working
- CGB mode detection and compatibility
- Stable sprite palette loading (no flickering)
- 5 distinct monster color groups
- Background palette loading
- Sara W has distinct palette from monsters
- MiSTer FPGA compatibility (use .gbc extension)

## What's Left To Do
- Map different level tiles to different BG palettes (currently all use Dungeon palette)
- Fine-tune individual monster colors based on actual monster appearances
- Potentially identify specific monster types for even more distinct coloring

## Color Format Reference (BGR555)

```
Format: BBBBBGGGGGRRRRR (5 bits each, max 0x7FFF)

Common colors:
  0000 = Black/Transparent
  7FFF = White
  001F = Red
  03E0 = Green
  7C00 = Blue
  03FF = Yellow
  7C1F = Magenta
  7FE0 = Cyan
  5294 = Medium gray
  2108 = Dark gray
```

## Quick Start for Next Session

1. Edit `palettes/penta_palettes.yaml` to adjust colors
2. Run `uv run python scripts/create_vblank_colorizer.py` to build
3. Test with `mgba-qt rom/working/penta_dragon_dx_FIXED.gb`
4. Deploy to MiSTer with `scp` (use .gbc extension!)
5. Tag releases in git for version tracking
