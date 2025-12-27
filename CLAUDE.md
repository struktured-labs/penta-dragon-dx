# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Penta Dragon DX is a Game Boy Color colorization project that converts the original DMG (Game Boy) ROM of Penta Dragon (ペンタドラゴン) into a CGB version with colors.

**Current Status**: ✅ **Stable Colorization Complete!** - Flicker-free 5-color sprite system with slot-based palette assignment.

### What Works
- ✅ CGB mode detection and compatibility
- ✅ Background palette loading (blue-gray dungeon theme)
- ✅ Sprite palette loading (5 distinct color groups)
- ✅ **Flicker-free** sprite colorization via triple OAM modification
- ✅ Sara W has distinct palette from monsters
- ✅ YAML-based palette configuration (`palettes/penta_palettes.yaml`)
- ✅ MiSTer FPGA compatibility (use .gbc extension)

### Current Version: v0.64
- Sara W: Black body, green/dark green accents
- Monsters: 4 color groups (gray, orange, purple, cyan)
- Background: Blue-gray dungeon theme

### Key Technical Breakthrough
The game uses **dual shadow OAM buffers** (0xC000 and 0xC100). To eliminate flickering, we modify **all three** OAM locations:
- 0xFE00 (actual OAM - hardware)
- 0xC000 (shadow buffer 1)
- 0xC100 (shadow buffer 2)

**Slot-based palette assignment** (not tile-based) prevents direction-dependent color changes:
```
Slots 0-7:   Palette 1 (Sara W)
Slots 8-15:  Palette 2 (Monster group 1)
Slots 16-23: Palette 3 (Monster group 2)
Slots 24-31: Palette 4 (Monster group 3)
Slots 32-39: Palette 5 (Monster group 4)
```

## Common Commands

### Build the Colorized ROM

**Main colorizer (recommended):**
```bash
uv run python scripts/create_vblank_colorizer.py
```

Output ROM: `rom/working/penta_dragon_dx_FIXED.gb`

**Build and deploy to MiSTer:**
```bash
uv run python scripts/create_vblank_colorizer.py && \
cp rom/working/penta_dragon_dx_FIXED.gb ~/gaming/roms/GBC/penta_dragon_dx_vX.XX.gbc && \
scp rom/working/penta_dragon_dx_FIXED.gb root@mister:/media/fat/games/GBC/penta_dragon_dx_vX.XX.gbc
```

### Testing & Verification

```bash
# Run with emulator (Nvidia/XCB systems)
QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia mgba-qt rom/working/penta_dragon_dx_FIXED.gb

# Alternative launch (Wayland)
mgba-qt rom/working/penta_dragon_dx_FIXED.gb

# Run with savestate
QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia mgba-qt -t rom/working/lvl1.ss0 rom/working/penta_dragon_dx_FIXED.gb

# Headless automated testing
timeout 90 xvfb-run mgba-qt --fastforward --script scripts/quick_test2.lua rom/working/penta_dragon_dx_FIXED.gb

# Automated color verification (captures screenshots, analyzes colors)
python3 scripts/auto_verify_colors.py

# Comprehensive testing framework
python3 scripts/comprehensive_test_framework.py

# Quick ROM verification
python3 scripts/quick_verify_rom.py
```

### Palette Tools

```bash
# Interactive palette color converter
python3 scripts/palette_tool.py

# Quick conversions
python3 scripts/palette_tool.py --hex #FF8800      # Orange to BGR555
python3 scripts/palette_tool.py --rgb 255 128 0    # RGB to BGR555
python3 scripts/palette_tool.py --examples         # Show common colors
```

### CLI Commands

The project includes a CLI tool (`penta-colorize`) defined in `src/penta_dragon_dx/cli.py`:

```bash
# Verify ROM integrity
uv run penta-colorize verify --rom rom/Penta\ Dragon\ \(J\).gb

# Inject palettes with display patches
uv run penta-colorize inject --rom <input> --palette-file palettes/penta_palettes.yaml --out <output> --fix-display

# Analyze ROM (free space, header info)
uv run penta-colorize analyze --rom <input>

# Build IPS patch
uv run penta-colorize build-patch --original <orig> --modified <mod> --out <patch.ips>

# Development loop (inject + launch emulator)
uv run penta-colorize dev-loop --rom <input> --palette-file <yaml> --emu mgba-qt
```

## Architecture

### Core Technical Approach

The colorization uses a **minimal trampoline approach** that preserves the original input handler while adding CGB palette loading. This was necessary because the ROM has **zero free space** in banks 0 and 1.

**Critical Constraint**: Cannot relocate and call the input handler - must execute it inline to avoid state corruption.

### ROM Layout

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
4. **Combined Function (Bank 13:0x6D00)**: 74 bytes (input handler + palette loader)

### Module Organization

```
src/penta_dragon_dx/
├── cli.py                   # Click-based CLI commands
├── display_patcher.py       # CGB display compatibility patches
├── palette_injector.py      # Main palette injection logic
├── palette_loader.py        # YAML palette loading
├── palette_wrapper.py       # Palette wrapper utilities
├── injector.py              # Generic injection utilities
├── vblank_injector.py       # VBlank hook injection
├── rom_utils.py             # ROM reading/writing/analysis utilities
└── patch_builder.py         # IPS patch generation
```

### Palette System

The game uses 16 total palettes in BGR555 format (15-bit color):

**Background Palettes (0-7)**: Different area themes (dungeon, lava, water, desert, forest, castle, sky, boss)

**Sprite Palettes (0-7)**: Different monster types and character

Palettes are defined in `palettes/penta_palettes.yaml` with each palette having 4 colors.

**Color Format (BGR555)**:
- Format: BBBBBGGGGGRRRRR (5 bits each channel)
- Examples: `7FFF` = white, `001F` = red, `03E0` = green, `7C00` = blue
- Use `scripts/palette_tool.py` for RGB ↔ BGR555 conversion

## Current Challenges & Known Issues

### Main Problem: Per-Monster Palette Assignment

The game continuously overwrites OAM (sprite) data, including palette bits. Attempts to assign different palettes to different monster types get overwritten by the game's code.

**Failed Approaches**:
1. **Input handler modification** - Runs too infrequently (only on button press)
2. **VBlank hooks** - Timing-critical, causes crashes
3. **Runtime OAM modification** - Game overwrites our changes

**Proposed Solutions** (documented in `docs/`):
1. **Tile-to-Palette Lookup Table** (`SCALABLE_PALETTE_APPROACH.md`) - Use a 256-byte lookup table with VBlank hook
2. **Patch Game's Palette Assignment Code** (`RELIABLE_APPROACH.md`) - Find and patch where game assigns palettes (tedious but reliable)
3. **GBC-Native Approach** (`GBC_NATIVE_APPROACH.md`) - Hook/disable DMG palette writes, let CGB hardware handle it

### Critical ROM Constraints

- **Zero free space** in banks 0 and 1
- 0x07A0-0x07E0 contains active game code (not actually free)
- Bank 13 is the only safe location for new code
- Input handler cannot be relocated - must execute inline
- VBlank handler is timing-critical

### Unsafe Hook Points (DO NOT USE)

- **0x0190**: Main initialization - causes direct crash
- **0x06D6**: VBlank handler - crashes with modifications
- **0x0824**: Input handler - crashes if replaced (can only trampoline)
- **0x0150-0x0A0F**: Entire initialization sequence is unsafe

## Development Workflow

### Iteration Pattern

The project has many iterative ROM generation scripts showing the evolution:
- `scripts/penta_cursor_dx_iter*.py` - Various iteration attempts
- `scripts/penta_cursor_dx_breakthrough.py` - Breakthrough approach
- `scripts/create_dx_rom.py` - Main working version

### Testing Scripts

- `scripts/auto_verify_colors.py` - Automated screenshot-based color verification
- `scripts/comprehensive_test_framework.py` - Full testing suite
- `scripts/breakthrough_test.py` - Test specific approaches
- `scripts/quick_verify_rom.py` - Fast ROM validation

### Analysis Tools

- `scripts/analyze_monsters.py` - Monster sprite analysis
- `scripts/trace_oam_writes.lua` - mGBA Lua script to trace OAM modifications
- `scripts/disassemble_function.py` - Disassemble ROM functions

## Reverse Engineering Resources

The `reverse_engineering/` directory contains detailed analysis:

- `analysis/` - Call graphs, memory maps, function traces
- `notes/PROJECT_PLAN.md` - 28-day project timeline
- `disassembly/` - Disassembled code sections
- `maps/` - Memory maps

Key strategy documents in `docs/`:
- `RELIABLE_APPROACH.md` - Patching game code directly
- `GBC_NATIVE_APPROACH.md` - CGB vs DMG palette system
- `SCALABLE_PALETTE_APPROACH.md` - Lookup table strategy
- `CGB_COLORIZATION_FINDINGS.md` - Research findings

## Project Dependencies

Managed via `pyproject.toml` with uv:
- Python >=3.11
- click (CLI framework)
- pillow (image processing)
- numpy (numerical operations)
- pyyaml (YAML parsing)
- pytesseract (OCR for testing)

Code style:
- Black formatter (line-length=100)
- Ruff linter (line-length=100)

## Legal Notice

The repository does NOT include the original ROM. Users must supply their own legally obtained copy of "Penta Dragon (J).gb" in the `rom/` directory (gitignored).

## Next Steps for Contributors

The primary goal is to achieve **distinct colors per monster type**. Focus areas:

1. Implement tile-to-palette lookup table approach (see `SCALABLE_PALETTE_APPROACH.md`)
2. Find safe VBlank hook point that doesn't crash
3. Alternative: Reverse engineer and patch game's OAM write locations
4. Test with first 3 monsters: Sara W, Sara D, Dragon Fly
