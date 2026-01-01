# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Penta Dragon DX is a Game Boy Color colorization project that converts the original DMG (Game Boy) ROM of Penta Dragon (ペンタドラゴン) into a CGB version with colors.

**Current Status**: v0.96 STABLE - Slot-based palette assignment with boss detection working. v0.97 experimental (entity-based) in progress.

### What Works
- CGB mode detection and compatibility
- Background palette loading (blue-gray dungeon theme)
- Sprite palette loading (8 distinct palettes)
- **Flicker-free** sprite colorization via triple OAM modification
- Sara W has distinct palette (palette 1) from monsters
- Boss detection - all enemies turn red (palette 7) when boss flag is set
- YAML-based palette configuration (`palettes/penta_palettes.yaml`)
- MiSTer FPGA compatibility (use .gbc extension)

### Current Versions

| Version | Status | Description |
|---------|--------|-------------|
| v0.96 | **STABLE** | Slot-based: Sara=1, Enemies=4/7 (boss) |
| v0.97 | Experimental | Entity-based with HRAM palette array (has issues) |

### Key Technical Architecture

**Triple OAM Modification** - The game uses dual shadow OAM buffers. We modify all three:
- `0xFE00` - Hardware OAM
- `0xC000` - Shadow buffer 1
- `0xC100` - Shadow buffer 2

**Slot-based palette assignment** (v0.96):
```
Slots 0-3:   Palette 1 (Sara)
Slots 4-39:  Palette 4 (regular enemies) or 7 (boss mode)
```

**Entity-based palette assignment** (v0.97 experimental):
```
HRAM 0xFF80-0xFF8F: Palette array for slots 0-15
  - Slots 0-3: Sara (palette 1)
  - Slots 4-15: Entity type lookup from 0xC200+ data
Slots 16+: Boss flag determines palette (4 or 7)
```

## Common Commands

### Build the Colorized ROM

```bash
# Build v0.96 stable (recommended)
uv run python scripts/create_vblank_colorizer.py

# Build v0.97 experimental (entity-based, may have issues)
uv run python scripts/create_vblank_colorizer.py --experimental
```

Output ROM: `rom/working/penta_dragon_dx_FIXED.gb`

### Testing & Verification

```bash
# Run with emulator
mgba-qt rom/working/penta_dragon_dx_FIXED.gb

# Run with savestate
mgba-qt -t rom/working/penta_dragon_dx_FIXED.ss1 rom/working/penta_dragon_dx_FIXED.gb

# Headless automated testing
timeout 20 xvfb-run mgba-qt rom/working/penta_dragon_dx_FIXED.gb --script tmp/quick_test.lua -l 0
```

### MCP Tools (mgba-mcp)

The project includes an MCP server for programmatic mGBA control. After configuring `.mcp.json`, these tools are available:

| Tool | Description |
|------|-------------|
| `mgba_run` | Run ROM for N frames, capture screenshot |
| `mgba_read_memory` | Read specific memory addresses |
| `mgba_read_range` | Read contiguous memory range |
| `mgba_dump_oam` | Dump all 40 OAM sprite entries |
| `mgba_dump_entities` | Dump entity data from WRAM |
| `mgba_run_lua` | Execute custom Lua script |

## Architecture

### ROM Layout (Bank 13)

```
0x6800: Palette data (128 bytes) - 8 BG + 8 OBJ palettes
0x6880: Entity-type-to-palette table (256 bytes) [v0.97]
0x6980: OAM processing loop / Entity scanner
0x69F0: Palette loader (~28 bytes)
0x6A20: BG attribute modifier (optional)
0x6AA0: Combined function (original input + colorization)
```

### Memory Map (Game Boy)

| Address | Purpose |
|---------|---------|
| `0xC000-0xC09F` | Shadow OAM 1 (40 sprites x 4 bytes) |
| `0xC100-0xC19F` | Shadow OAM 2 (alternate buffer) |
| `0xC200-0xC2FF` | Entity data (10 entities x 24 bytes) |
| `0xFE00-0xFE9F` | Hardware OAM |
| `0xFF80-0xFF8F` | HRAM palette array [v0.97] (game uses 0xFF90+) |
| `0xFFBF` | Boss flag (non-zero = boss mode) |

### Entity Data Structure (0xC200+)

Each entity is 24 bytes. Key fields identified:
- Offset 3: Entity type ID (0x17=regular, 0x1D=miniboss, etc.)
- Structure varies during gameplay vs title screen

### OAM Sprite Entry (4 bytes)

| Offset | Field | Notes |
|--------|-------|-------|
| 0 | Y position | 0 or >160 = hidden |
| 1 | X position | |
| 2 | Tile ID | |
| 3 | Flags | Bits 0-2 = palette |

## Known Issues & Constraints

### HRAM Conflict
The game uses HRAM 0xFF90+ for its own purposes. The v0.97 entity scanner can only use 0xFF80-0xFF8F (16 slots) for the palette array.

### ROM Constraints
- Zero free space in banks 0 and 1
- Bank 13 is the only safe location for new code
- VBlank handler is timing-critical
- Input handler cannot be relocated

### Unsafe Hook Points
- `0x0190`: Main initialization - crashes
- `0x06D6`: VBlank handler - crashes with modifications
- `0x0824`: Input handler - can only trampoline, not replace

## Project Structure

```
penta-dragon-dx-claude/
├── mgba-mcp/              # MCP server for mGBA (git submodule)
├── palettes/              # YAML palette definitions
├── rom/                   # ROM files and savestates
│   └── working/           # Output ROMs
├── scripts/               # Build and analysis scripts
│   ├── create_vblank_colorizer.py  # Main ROM builder
│   ├── analyze_entity_data.lua     # Entity structure analysis
│   └── ...
├── src/penta_dragon_dx/   # Python package
├── docs/                  # Strategy documents
├── reverse_engineering/   # Disassembly and analysis
└── tmp/                   # Temporary test files
```

## Development Workflow

### Quick Iteration
```bash
# Build and test
uv run python scripts/create_vblank_colorizer.py && \
timeout 20 xvfb-run mgba-qt rom/working/penta_dragon_dx_FIXED.gb --script tmp/quick_test.lua -l 0

# Check results
cat tmp/v097_quick.txt
```

### Debugging with Lua
Create diagnostic scripts in `tmp/` that dump memory and quit:
```lua
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame == 60 then
        emu:screenshot("tmp/test.png")
        -- Dump memory, OAM, etc.
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

1. **Fix v0.97 black screen issue** - Entity scanner or batch OAM loop has a bug
2. **Identify entity type field** - Find correct offset in 0xC200+ structure for monster type
3. **Map entity types to palettes** - Create lookup table for distinct monster colors
4. **Sara form detection** - Detect Sara W vs Sara D for different palettes
