# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Penta Dragon DX is a Game Boy Color colorization project that converts the original DMG (Game Boy) ROM of Penta Dragon (ペンタドラゴン) into a CGB version with full color support.

**Current Status**: v2.28 STABLE (Fixed) - Stage detection + jet form palettes + BG items + tile-based monsters + boss detection.

**Recent Fixes**:
- Spider miniboss palette assignment (was Sara W pink, now red/black)
- Boss flag flickering (read once per VBlank instead of twice)

### What Works
- CGB mode detection and compatibility
- Background palette loading (colorful Level 1 theme)
- Sprite palette loading (8 distinct palettes for different entity types)
- **Flicker-free** sprite colorization via pre-DMA shadow buffer modification
- **Tile-based monster coloring**: Hornets, Orcs, Humanoids, Crows, etc. each have distinct palettes
- **Sara W/D distinction**: Sara Witch (tiles 0x20-0x27) and Sara Dragon (tiles 0x28-0x2F) have different palettes
- **Stage detection** (v2.28): Reads 0xFFD0 to determine current level
  - Level 1 (0x00): Normal dungeon palettes
  - Bonus stage (0x01): Jet form palettes for Sara
- **Jet form colors** (v2.28): Sara W jet = magenta/purple, Sara D jet = cyan/blue
- **Boss detection** via 0xFFBF flag with dynamic palette loading:
  - Gargoyle (flag=1): Dark magenta palette loaded into slot 6
  - Spider (flag=2): Red/orange palette loaded into slot 7
  - **Bug fix (v2.28)**: Boss flag now read once per VBlank to prevent flickering
- **BG Item colorization**: Items (tiles 0x88-0xDF) get gold/yellow BG palette
  - Potions, health, extra lives, powerups all stand out from blue floor
  - Runs after DMA to win race condition against game's attribute reset
- YAML-based palette configuration (`palettes/penta_palettes_v097.yaml`)
- BG tile category mapping (`palettes/bg_tile_categories.yaml`)
- MiSTer FPGA compatibility (use .gbc extension)

### Version History

| Version | Tag | Status | Description |
|---------|-----|--------|-------------|
| v2.28 | `v2.28` | **STABLE** | Stage detection + jet form colors + BG items + bosses (BEST) |
| v2.26 | - | Stable | BG items + OBJ tile-based + boss detection |
| v1.12 | `v1.12` | Stable | BG items gold + OBJ tile-based + boss detection |
| v1.09 | `best-colorization-jan2026` | Stable | Tile-based + dynamic boss palettes |
| v1.07 | `v1.07` | Stable | Tile-based + boss flag detection |
| v1.05 | `v1.05` | Stable | Tile-based coloring only (no boss detection) |
| v0.99 | - | Legacy | Dynamic palettes but entity-based (unstable) |
| v0.96 | - | Legacy | Slot-based: Sara=1, Enemies=4/7 |

### Key Technical Architecture

**Pre-DMA Shadow Colorization** - We modify sprite palettes in shadow OAM BEFORE DMA copies to hardware:
- `0xC000` - Shadow buffer 1 (modified pre-DMA)
- `0xC100` - Shadow buffer 2 (modified pre-DMA)
- `0xFE00` - Hardware OAM (receives colored data via DMA)

**Tile-based palette assignment** (v1.05+):
```
Sara W (tiles 0x20-0x27):   Palette 2 (skin/pink)
Sara D (tiles 0x28-0x2F):   Palette 1 (green/dragon)
Effects (tiles 0x00-0x1F):  Palette 0 (white/gray)
Crows (tiles 0x30-0x3F):    Palette 3 (dark blue)
Hornets (tiles 0x40-0x4F):  Palette 4 (yellow/orange)
Orcs (tiles 0x50-0x5F):     Palette 5 (green/brown)
Humanoids (tiles 0x60-0x6F): Palette 6 (purple) or 7 (boss)
Special (tiles 0x70-0x7F):  Palette 3 (cyan)
```

**Boss detection** (v1.07+):
```
0xFFBF = 0: Normal mode (tile-based palettes)
0xFFBF = 1: Gargoyle mode (all enemies palette 6, load dark magenta)
0xFFBF = 2: Spider mode (all enemies palette 7, load red/orange)
```

**Dynamic palette loading** (v1.09):
```
When boss_flag != 0:
  - Load special boss colors into palette 6 or 7 via OCPS/OCPD
  - Override tile-based assignment for all enemies
```

**BG Item Colorization** (v1.12):
```
Item tiles (0x88-0xDF) -> BG palette 1 (gold/yellow)
- Runs AFTER DMA to win race against game's attribute reset
- Scans 20x18 visible tile area each VBlank
- Items include: potions, health, extra lives, powerups
```

## Common Commands

### Build the Colorized ROM

```bash
# Build v2.28 (current best - stage detection + jet colors + BG items)
uv run python scripts/create_vblank_colorizer_v228.py

# Build older versions
uv run python scripts/create_vblank_colorizer_v226.py  # v2.26 (no stage detection)
uv run python scripts/create_vblank_colorizer_v112.py  # v1.12 (BG items)
uv run python scripts/create_vblank_colorizer_v109.py  # v1.09 (OBJ only)
```

Output: `rom/working/penta_dragon_dx_FIXED.gb`

### Testing & Verification

```bash
# Run with emulator (use project launcher script)
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb

# Run with savestate (many available in save_states_for_claude/)
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb -t save_states_for_claude/level1_sara_w_4_hornets.ss0

# Launch in background (when testing multiple builds)
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb &

# Headless automated testing (for Claude's verification tools)
timeout 20 xvfb-run mgba-qt rom/working/penta_dragon_dx_FIXED.gb \
  -t save_states_for_claude/level1_sara_w_gargoyle_mini_boss.ss0 \
  --script tmp/quick_test.lua -l 0
```

### Available Save States

Located in `save_states_for_claude/`, covering:
- **Sara forms**: `level1_sara_w_alone.ss0`, `level1_sara_d_alone.ss0`
- **Enemies**: `level1_sara_w_4_hornets.ss0`, `level1_sara_w_orc.ss0`, `level1_sara_w_soldier.ss0`, `level1_sara_w_moth.ss0`, `level1_sara_w_crow.ss0`
- **Minibosses**: `level1_sara_w_gargoyle_mini_boss.ss0`, `level1_sara_w_spier_miniboss.ss0`, `level1_sara_d_spider_miniboss.ss0`
- **Items/Effects**: `level1_sara_w_flash_item.ss0`, `level1_sara_w_dragon_powerup_item.ss0`
- **Special**: `level1_cat_fish_moth_spike_hazard_orb_item.ss0`, `level1_sara_w_in_jet_form_secret_stage.ss0`

### MCP Tools (mgba-mcp)

The project includes an MCP server for programmatic mGBA control.

**CRITICAL**: ALWAYS use MCP tools for ALL emulator operations. NEVER use bash/xvfb-run unless MCP tools are completely unavailable:
- MCP tools run headless automatically (no windows, no desktop clutter)
- MCP tools handle SDL audio dummy driver automatically
- MCP tools are faster and more reliable than bash approaches
- **USE THESE**: `mcp__mgba__mgba_run`, `mcp__mgba__mgba_read_range`, `mcp__mgba__mgba_run_lua`, etc.

| Tool | Description | Common Use Cases |
|------|-------------|------------------|
| `mgba_run` | Run ROM for N frames, capture screenshot | Visual verification, frame capture |
| `mgba_read_memory` | Read specific memory addresses | Check flags, read state |
| `mgba_read_range` | Read contiguous memory range | Scan HRAM/WRAM, find addresses |
| `mgba_dump_oam` | Dump all 40 OAM sprite entries | Verify palette assignments |
| `mgba_dump_entities` | Dump entity data from WRAM | Debug entity behavior |
| `mgba_run_lua` | Execute custom Lua script | Complex testing, automation |
| `mgba_run_sequence` | Run with button inputs, periodic screenshots | Gameplay testing, stability |

**Fallback only if MCP broken**: Use bash with proper headless settings:
```bash
unset DISPLAY
SDL_AUDIODRIVER=dummy xvfb-run -a mgba-qt rom.gb --script script.lua -l 0
```

## Architecture

### ROM Layout (Bank 13)

```
0x6800: Palette data (128 bytes) - 8 BG + 8 OBJ palettes
0x6880: Boss palette data (16 bytes) - Gargoyle + Spider colors
0x6900: Palette loader with dynamic boss swap (~80 bytes)
0x6980: Shadow colorizer main (boss flag check + loop setup)
0x69D0: Tile-based colorizer routine
0x6A80: Combined function (original input + colorization call)
```

### Memory Map (Game Boy)

| Address | Purpose |
|---------|---------|
| `0xC000-0xC09F` | Shadow OAM 1 (40 sprites x 4 bytes) |
| `0xC100-0xC19F` | Shadow OAM 2 (alternate buffer) |
| `0xC200-0xC2FF` | Entity data (10 entities x 24 bytes) |
| `0xFE00-0xFE9F` | Hardware OAM |
| `0xFFBF` | Boss flag: 0=normal, 1=Gargoyle, 2=Spider |
| `0xFFD0` | **Stage flag: 0=Level 1, 1=Bonus stage** (v2.28+) |
| `0xFF6A` | OCPS - Object Color Palette Specification |
| `0xFF6B` | OCPD - Object Color Palette Data |

### Tile ID Ranges (Sprites)

| Range | Entity Type | Default Palette |
|-------|-------------|-----------------|
| 0x00-0x1F | Effects/projectiles | 0 (white/gray) |
| 0x20-0x27 | Sara W (Witch) | 2 (skin/pink) |
| 0x28-0x2F | Sara D (Dragon) | 1 (green) |
| 0x30-0x3F | Crow/flying | 3 (dark blue) |
| 0x40-0x4F | Hornets | 4 (yellow/orange) |
| 0x50-0x5F | Orcs/ground | 5 (green/brown) |
| 0x60-0x6F | Humanoid (soldier/moth/mage) | 6 (purple) |
| 0x70-0x7F | Special (catfish) | 3 (cyan) |

### OAM Sprite Entry (4 bytes)

| Offset | Field | Notes |
|--------|-------|-------|
| 0 | Y position | 0 or >160 = hidden |
| 1 | X position | |
| 2 | Tile ID | Used for palette lookup |
| 3 | Flags | Bits 0-2 = palette (modified by colorizer) |

## Known Issues & Constraints

### ROM Constraints
- Zero free space in banks 0 and 1
- Bank 13 is the only safe location for new code
- VBlank handler is timing-critical
- Input handler cannot be relocated (trampoline only)

### Miniboss Tiles
Minibosses use tiles from multiple ranges (e.g., both 0x60-0x6F and 0x70-0x7F), which caused color alternation in tile-only detection. Solved via 0xFFBF boss flag.

### First Frame Colors
Save states may show incorrect colors on the very first frame before the colorizer runs. This is expected behavior.

## Project Structure

```
penta-dragon-dx-claude/
├── mgba-mcp/                    # MCP server for mGBA (git submodule)
├── palettes/                    # YAML palette definitions
│   └── penta_palettes_v097.yaml # Current palette config
├── rom/
│   ├── versions/                # Tagged ROM releases (.gbc)
│   └── working/                 # Build output
├── save_states_for_claude/      # Test save states (55+ scenarios)
├── scripts/
│   ├── create_vblank_colorizer_v109.py  # Current best
│   ├── create_vblank_colorizer_v107.py  # Boss flag + tile-based
│   ├── create_vblank_colorizer_v105.py  # Tile-based only
│   └── ...
├── src/penta_dragon_dx/         # Python package
├── docs/                        # Strategy documents
├── reverse_engineering/         # Disassembly and analysis
└── tmp/                         # Temporary test files
```

## Development Workflow

### Quick Iteration
```bash
# Build and test with specific savestate
uv run python scripts/create_vblank_colorizer_v109.py && \
mgba-qt rom/working/penta_dragon_dx_FIXED.gb \
  -t save_states_for_claude/level1_sara_w_gargoyle_mini_boss.ss0
```

### Debugging with Lua
```lua
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame == 60 then
        emu:screenshot("tmp/test.png")
        -- Check OAM palettes
        for i = 0, 39 do
            local flags = emu:read8(0xFE00 + i*4 + 3)
            local pal = flags & 0x07
            console:log(string.format("Sprite %d: palette %d", i, pal))
        end
        emu:quit()
    end
end)
```

## Dependencies

Managed via `pyproject.toml` with uv:
- Python >=3.11
- click, pillow, numpy, pyyaml
- mcp (for mgba-mcp server)

## Legal Notice

The repository does NOT include the original ROM. Users must supply their own legally obtained copy of "Penta Dragon (J).gb" in the `rom/` directory.

## Next Steps

1. **Regression test suite** - Automated color verification using save states
2. **Level 2+ palettes** - Different BG/sprite palettes for other levels
3. **Sara form-specific effects** - Different projectile colors per form
4. **More enemy variety** - Fine-tune palettes for specific enemy subtypes
