# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Penta Dragon DX Remake** — a full ground-up rewrite of Penta Dragon (ペンタドラゴン) in C targeting Game Boy Color hardware using GBDK-2020. The goal is a faithful recreation of the original DMG game with native GBC color support.

**Current Status**: v0.1.0 — Proof of concept (boots, displays colored tiles + Sara sprite)

### Why a Remake?

The original approach (in `penta-dragon-dx-claude`) patched the DMG ROM with VBlank hooks to inject CGB palette loading. After reaching v2.84.2 with 100% BG accuracy and full sprite colorization, we hit fundamental limitations:
- Zero free ROM space in banks 0-1; all custom code crammed into bank 13
- VBlank timing fights (game services interrupts during LCD rendering)
- Per-level BG palettes impossible without more reverse engineering + tight timing budgets
- Every new feature is a hack layered on hacks

A native GBC rewrite gives us color as a first-class citizen with no timing constraints.

### Toolchain

- **GBDK-2020 v4.5.0** installed at `~/gbdk`
- **SDCC 4.5.1** (included with GBDK)
- Compiler driver: `~/gbdk/bin/lcc`

## Common Commands

### Build

```bash
make              # Build ROM -> rom/working/penta_dragon_dx.gbc
make clean        # Clean build artifacts
```

### Test (headless)

```bash
make test         # Build + run headless with screenshot capture
```

### Play (GUI)

```bash
make play         # Build + launch mGBA for human testing
```

### Extract Assets

```bash
uv run python scripts/extract_assets.py   # Re-extract tiles from original ROM
```

## Architecture

### Project Structure

```
penta-dragon-remake/
├── src/
│   ├── main.c              # Entry point, game loop, demo background
│   ├── palettes.h          # All palette definitions (BG, OBJ, boss, powerup)
│   └── palettes.c          # Palette loading functions
├── assets/
│   └── extracted/          # Tiles/sprites extracted from original ROM (gitignored)
│       ├── bg/include/     # BG tile C headers
│       ├── sprites/include/# Sprite tile C headers
│       ├── tilemaps/       # Tilemap data
│       └── sheets/         # Visual preview PNGs
├── palettes/
│   └── penta_palettes_v097.yaml  # Master palette definitions (BGR555)
├── scripts/
│   └── extract_assets.py   # Asset extraction from original ROM
├── rom/
│   └── working/            # Build output (.gbc)
├── reverse_engineering/    # Disassembly analysis from original project
├── save_states_for_claude/ # Test save states
├── tmp/                    # Temporary test files
└── Makefile
```

### Color System

Native CGB palettes — no VBlank hacks needed:

**8 BG Palettes:**
| Palette | Usage | Colors |
|---------|-------|--------|
| 0 | Dungeon floor/platform | Blue-white |
| 1 | Items/pickups | Gold/yellow |
| 2 | Decorative | Purple/magenta |
| 3 | Nature/organic | Green |
| 4 | Water/ice | Cyan/teal |
| 5 | Fire/lava | Red/orange |
| 6 | Stone/castle walls | Blue-gray |
| 7 | Mystery/special | Deep blue |

**8 OBJ Palettes:**
| Palette | Usage |
|---------|-------|
| 0 | Enemy projectiles (blue) |
| 1 | Sara Dragon (green) |
| 2 | Sara Witch (skin/pink) |
| 3 | Sara W projectile + Crows (red) |
| 4 | Hornets (yellow/orange) |
| 5 | Orc/ground (green/brown) |
| 6 | Humanoid/soldier (purple) |
| 7 | Catfish/special (cyan) |

**Dynamic palettes:** Boss palettes (8 bosses), powerup palettes (3 types), jet form palettes (2 Sara forms) — all loaded on demand via `load_boss_palette()` / `load_powerup_palette()`.

### BG Tile Palette Lookup

256-byte table maps tile_id → CGB palette number:
- 0x00-0x3F: Floor/edges → Palette 0
- 0x40-0x5F: Wall fill → Palette 6
- 0x60-0x87: Arches/doorways → Palette 0
- 0x88-0xDF: Items → Palette 1
- 0xE0-0xFD: Decorative → Palette 6
- 0xFE-0xFF: Void → Palette 0

### Sprite Tile Ranges

| Range | Entity | Palette |
|-------|--------|---------|
| 0x00-0x1F | Effects/projectiles | 0 |
| 0x20-0x27 | Sara Witch | 2 |
| 0x28-0x2F | Sara Dragon | 1 |
| 0x30-0x3F | Crows | 3 |
| 0x40-0x4F | Hornets | 4 |
| 0x50-0x5F | Orcs | 5 |
| 0x60-0x6F | Humanoids | 6 |
| 0x70-0x7F | Special (catfish) | 7 |

## Original Game Knowledge (from reverse engineering)

### Game Structure
- Single continuous dungeon with 7 interconnected rooms (FFBD = room counter)
- 6 sections per room (DCB8 = section cycle 0-5)
- Boss detection: `boss_number = (DC04 - 0x30) / 5 + 1` (DC04 from level data table in bank 13)
- 8 bosses: Gargoyle, Spider, Crimson, Ice, Void, Poison, Knight, Angela

### Key Memory Addresses (original game)
| Address | Purpose |
|---------|---------|
| FFBD | Room/section counter (0=title, 1-7=rooms) |
| FFBE | Sara form (0=Witch, 1=Dragon) |
| FFBF | Boss flag (0=normal, 1-8=boss) |
| FFC0 | Powerup state (0=none, 1=spiral, 2=shield, 3=turbo) |
| FFC1 | Gameplay active (0=menu, 1=gameplay) |
| FFCB | DMA buffer toggle |
| FFD0 | Stage flag (0=normal, 1=bonus) |
| DCBB | Countdown timer |
| DCDC/DCDD | Health system (sub/main HP) |
| DCB8 | Section cycle counter |
| DC04 | Section descriptor (boss type from level data) |

### Asset Extraction Notes
- Tile data is **compressed in ROM** — extracted at runtime from VRAM via emulator
- Sprite tiles load dynamically (only visible entities in VRAM at any time)
- BG tiles for Level 1 are stable across gameplay states (255/256 non-empty)
- Original ROM: 256KB (16 banks), MBC type varies

## Dependencies

- GBDK-2020 v4.5.0 (`~/gbdk`)
- Python >=3.11 + uv (for asset extraction scripts)
- pillow, numpy, pyyaml (Python deps)
- mGBA (testing)

## Next Steps

1. **Extract actual dungeon tileset** — Current BG tiles are text/font; need to capture dungeon graphics from gameplay state
2. **Scrolling engine** — Implement horizontal scrolling dungeon
3. **Player physics** — Gravity, jumping, collision detection
4. **Enemy system** — Spawn, AI, tile-based palette assignment
5. **Level data format** — Design level storage for multiple rooms
6. **Sound** — Music and SFX system

## Legal Notice

The repository does NOT include the original ROM. Users must supply their own legally obtained copy for asset extraction.
