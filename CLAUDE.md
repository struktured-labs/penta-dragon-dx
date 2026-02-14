# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Penta Dragon DX is a Game Boy Color colorization project that converts the original DMG (Game Boy) ROM of Penta Dragon (ペンタドラゴン) into a CGB version with full color support.

**Current Status**: v2.38 STABLE - Active-tilemap-only BG + scroll-edge + flip detection

**What Works in v2.38** (fixes over v2.37):
- **Active-tilemap-only BG**: Writes attributes to only the ACTIVE tilemap (LCDC bit 3)
  - 3x throughput vs v2.37's dual-tilemap approach (26M/tile vs 48M/tile)
  - ~128 tiles per VBlank, full 1024-tile sweep in ~8 frames
  - 99.4% BG accuracy during scrolling (vs v2.37's ~60%)
- **Flip detection**: When game swaps active tilemap (LCDC bit 3 changes),
  automatically resets sweep counter to re-color the new tilemap from scratch
- **Scroll-edge column**: Instantly colorizes the 32-tile edge column when SCX/8 changes
- **HRAM temp for palette**: Uses FFEE to avoid clobbering C register (tilemap base)
- All v2.37 features: ROM lookup table, both-buffer OBJ, input debounce, bosses
- **Conservative tile categorization**:
  - Palette 0: Floor/edges/platforms (0x00-0x3F), arches/doorways (0x60-0x87)
  - Palette 1: Items (0x88-0xDF, bright gold)
  - Palette 6: Wall fill blocks (0x40-0x5F), decorative (0xE0-0xFD)
- **Game mode detection**: Skips BG coloring on menus/title (0xFFC1 check)
- **Multi-boss palette system** (table-based lookup for 8 distinct bosses)
- Per-entity projectile colors based on verified tile mapping
- Powerup-based Palette 0 colors (0xFFC0 flag)

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
- **Boss detection** via 0xFFBF flag with table-based palette loading (v2.33):
  - 8 bosses supported via palette table + slot table lookup
  - Gargoyle (flag=1), Spider (flag=2), Crimson (flag=3), Ice (flag=4),
    Void (flag=5), Poison (flag=6), Knight (flag=7), Angela (flag=8)
  - Each boss loads custom colors into its assigned palette slot (6 or 7)
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
| v2.38 | `v2.38` | **STABLE (BEST)** | Active-tilemap-only BG + scroll-edge + flip detection |
| v2.37 | `v2.37` | Obsolete | Dual-tilemap scroll-edge (~60% scroll accuracy) |
| v2.36 | `v2.36` | Stable | Input fix + 48-tile BG + both-buffer OBJ |
| v2.35 | `v2.35` | Broken | Bad input debounce + inverted FFCB buffer selection |
| v2.34 | `v2.34` | Stable | Full BG colorization + STAT-safe VRAM access |
| v2.33 | `v2.33` | Stable | Multi-boss table (8 bosses) + turbo powerup |
| v2.32 | `v2.32` | Stable | Per-entity projectile colors + powerup support |
| v2.31 | `v2.31` | Stable | Dynamic projectile colors (Sara W=pink, Sara D=green) |
| v2.30 | `v2.30` | Broken | Wrong jump offsets caused flickering |
| v2.29 | `v2.29` | Broken | Direction-dependent colors, BG flashing |
| v2.28 | `v2.28` | Stable | Stage detection + jet form colors + BG items + bosses |
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

**Tile-based palette assignment** (v2.32+):
```
Projectiles (per-entity detection):
  Tile 0x0F:           Palette 2 (Sara W - pink)
  Tiles 0x06,0x09,0x0A: Palette 1 (Sara D - green)
  Tiles 0x00-0x01:     Palette 3 (Enemy - dark blue)
  Tiles 0x02-0x05,etc: Palette 0 (Dynamic - powerup colors)
Effects (tiles 0x10-0x1F):     Palette 4 (yellow/white)
Sara W (tiles 0x20-0x27):      Palette 2 (skin/pink)
Sara D (tiles 0x28-0x2F):      Palette 1 (green/dragon)
Crows (tiles 0x30-0x3F):       Palette 3 (dark blue)
Hornets (tiles 0x40-0x4F):     Palette 4 (yellow/orange)
Orcs (tiles 0x50-0x5F):        Palette 5 (green/brown)
Humanoids (tiles 0x60-0x6F):   Palette 6 (purple) or 7 (boss)
Special (tiles 0x70-0x7F):     Palette 7 (catfish)
```

**Boss detection** (v2.33 table-based):
```
0xFFBF = 0: Normal mode (tile-based palettes)
0xFFBF = 1-8: Boss mode (table lookup)
  - Boss slot table (8 bytes at 0x68C0): maps boss_flag → palette slot (6 or 7)
  - Boss palette table (64 bytes at 0x6880): maps boss_flag → 8-byte palette data
  - Loader: reads slot from table, computes OCPS target, loads 8 bytes from palette table
  - All enemy sprites forced to boss's palette slot via E register override
```

**Dynamic palette loading** (v2.33):
```
When boss_flag != 0:
  - Index into boss_slot_table[flag-1] to get target slot (6 or 7)
  - Index into boss_palette_table[flag-1] to get 8 color bytes
  - Write to OCPS/OCPD to load boss colors into target slot
  - Shadow colorizer sets E = slot for all non-Sara sprites
```

**BG Tile Colorization** (v2.38):
```
Active-tilemap-only colorizer with ROM lookup table (VBlank-first):
- ROM lookup table at 0x6B00 (256-byte tile→palette table in bank 13)
- Writes ONLY to active tilemap (reads LCDC bit 3 to determine 0x9800 or 0x9C00)
- Flip detection: when LCDC bit 3 changes, resets sweep counter to 0
- ~128 tiles per VBlank (26M/tile), full 1024-tile sweep in ~8 frames
- Scroll-edge: instantly colorizes 32-tile column when SCX/8 changes
- Uses HRAM FFEE as temp to avoid clobbering C register (tilemap base)
- Skips menus via 0xFFC1 gameplay flag check
- Tile categories (via lookup table at 0x6B00):
    Floor/edges (0x00-0x3F):   Palette 0 (blue-white)
    Wall fill (0x40-0x5F):     Palette 6 (blue-gray stone)
    Arches/doors (0x60-0x87):  Palette 0 (blend with floor)
    Items (0x88-0xDF):         Palette 1 (gold/yellow)
    Decorative (0xE0-0xFD):    Palette 6 (structural)
    Void (0xFE-0xFF):          Palette 0
```

**Dynamic Palette 0** (v2.29+):
```
Projectile colorization via dynamic palette loading:
- Read powerup flag (0xFFC0) first - powerup overrides Sara form
  - 0x01: Spiral (cyan), 0x02: Shield (gold), 0x03: Turbo (orange)
- If no powerup, read Sara form flag (0xFFBE)
  - Sara W (0xFFBE=0): Pink/red projectile colors
  - Sara D (0xFFBE≠0): Green projectile colors
- Tile colorizer assigns Palette 0 to tiles 0x00-0x07 (Sara projectiles)
- Enemy projectiles (0x08-0x0F) use Palette 3 (blue/dark)
```

## Common Commands

### Build the Colorized ROM

```bash
# Build v2.38 (BEST - active-tilemap BG + scroll-edge + flip detection)
uv run python scripts/create_vblank_colorizer_v238.py

# Build v2.36 (fallback - fixed input + 48-tile BG + both-buffer OBJ)
uv run python scripts/create_vblank_colorizer_v236.py

# Build v2.34 (fallback - STAT-safe BG colorization)
uv run python scripts/create_vblank_colorizer_v234.py

# Build older versions
uv run python scripts/create_vblank_colorizer_v233.py  # v2.33 (multi-boss, no BG)
uv run python scripts/create_vblank_colorizer_v232.py  # v2.32 (per-entity projectiles)
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

**CRITICAL: NEVER show the emulator GUI unless the user explicitly asks to see/play it.**
All automated testing and verification MUST be headless. Use bash with proper headless settings for ALL emulator operations:

```bash
# Standard headless pattern - use this for ALL automated emulator runs
rm -f DONE && unset DISPLAY && unset WAYLAND_DISPLAY && \
  QT_QPA_PLATFORM=offscreen SDL_AUDIODRIVER=dummy \
  timeout 30 xvfb-run -a mgba-qt rom.gb -t state.ss0 --script script.lua -l 0
```

MCP tools (mgba_run, mgba_read_range, etc.) may be used for non-GUI operations like ROM analysis (mgba_xxd, mgba_search_bytes). For emulator execution that involves rendering frames, prefer bash with the headless pattern above to guarantee no GUI window appears on the user's desktop (especially on KDE Wayland where Qt may try to connect to the compositor).

| Tool | Description | Safe for headless? |
|------|-------------|-------------------|
| `mgba_xxd` | Hex dump ROM bytes | Yes (no emulator) |
| `mgba_search_bytes` | Search ROM for patterns | Yes (no emulator) |
| `mgba_run` | Run ROM, capture screenshot | Use bash instead |
| `mgba_read_memory` | Read memory addresses | Use bash instead |
| `mgba_read_range` | Read memory range | Use bash instead |
| `mgba_dump_oam` | Dump OAM sprite data | Use bash instead |
| `mgba_run_lua` | Execute Lua script | Use bash instead |
| `mgba_run_sequence` | Run with inputs | Use bash instead |

**To launch for user testing (GUI)**: Only when explicitly asked:
```bash
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb -t save_states_for_claude/some_state.ss0
```

## Architecture

### ROM Layout (Bank 13)

```
0x6800-0x683F: BG palettes (64 bytes, 8 palettes x 8 bytes)
0x6840-0x687F: OBJ palettes (64 bytes, 8 palettes x 8 bytes)
0x6880-0x68BF: Boss palette table (64 bytes, 8 bosses x 8 bytes)
0x68C0-0x68C7: Boss slot table (8 bytes, maps boss_flag → palette slot 6/7)
0x68D0-0x68D7: Sara Witch Jet palette (8 bytes)
0x68D8-0x68DF: Sara Dragon Jet palette (8 bytes)
0x68E0-0x68E7: Spiral projectile palette (8 bytes)
0x68E8-0x68EF: Shield projectile palette (8 bytes)
0x68F0-0x68F7: Turbo projectile palette (8 bytes)
0x6900:        Palette loader (~194 bytes, boss table + powerup chain)
0x69D0:        Shadow colorizer main (~50 bytes, boss flag + loop setup)
0x6A10:        Tile-based colorizer (~134 bytes)
0x6B00-0x6BFF: BG tile lookup table (256 bytes, tile_id → palette)
0x6C00-0x6C85: BG colorizer (~134 bytes, inline palette logic, VBlank-first)
0x6D00:        Combined function (~13 bytes, BG first + palette + OBJ + DMA)
```

### Memory Map (Game Boy)

| Address | Purpose |
|---------|---------|
| `0xC000-0xC09F` | Shadow OAM 1 (40 sprites x 4 bytes) |
| `0xC100-0xC19F` | Shadow OAM 2 (alternate buffer) |
| `0xC200-0xC2FF` | Level/tilemap buffer data (NOT entities) |
| `0xFE00-0xFE9F` | Hardware OAM |
| `0xFFBE` | Sara form: 0=Witch, non-zero=Dragon |
| `0xFFBF` | Boss flag: 0=normal, 1-8=boss index (v2.33: 8 bosses) |
| `0xFFC0` | Powerup state: 0=none, 1=spiral, 2=shield, 3=turbo |
| `0xFFCB` | DMA buffer toggle: alternates 0/1 each frame |
| `0xFFD0` | **Stage flag: 0=Level 1, 1=Bonus stage** (v2.28+) |
| `0xFFEA` | BG colorizer position counter low byte (v2.35+) |
| `0xFFEB` | BG colorizer position counter high byte (0-3) (v2.35+) |
| `0xFFEC` | Saved LCDC bit 3 for flip detection (0x00 or 0x08) (v2.38+) |
| `0xFFED` | Previous SCX/8 for scroll-edge detection (0-31) (v2.37+) |
| `0xFFEE` | BG colorizer temp palette storage (v2.38+) |
| `0xFFC1` | Gameplay active flag: 0=menu, non-zero=gameplay (v2.34+) |
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
│   ├── create_vblank_colorizer_v233.py  # Current best (v2.33)
│   ├── create_vblank_colorizer_v232.py  # v2.32 fallback
│   ├── create_vblank_colorizer_v225.py  # v2.25 reference
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
uv run python scripts/create_vblank_colorizer_v233.py && \
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

1. **Per-level BG palettes** - Different BG themes for Levels 1-5 (needs level address research; requires save states from levels 2+)
2. **Game code patching** - Patch ROM projectile rendering to set CGB palette bits at source, enabling true per-entity projectile colors without tile heuristics
3. **Regression test suite** - Automated color verification using save states
4. **More enemy variety** - Fine-tune palettes for specific enemy subtypes
