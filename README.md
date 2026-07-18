# Penta Dragon DX

**Game Boy Color colorization of Penta Dragon (ペンタドラゴン)**

Converts the original DMG ROM into a CGB build with semantically-aware
palettes for floors, walls, items, hazards, and sprites — plus an O(1)
Shadow OAM intercept system that eliminates VBlank overflow flickering.

---

## Status: ✅ v3.01-o2 — O(1) Shadow OAM Intercept + Per-Monster Palettes

All five visible-regression categories verified passing on
`rom/working/penta_dragon_dx_FIXED.gb` and `rom/working/penta_dragon_dx_teleport.gb`:

| Bug                       | Probe                                        | v3.01 result        |
|---------------------------|----------------------------------------------|---------------------|
| Title screen white        | `scripts/probes/verify_title_color.py`       | PASS (2 colors)     |
| Phantom sound on items    | `scripts/probes/verify_phantom_d887.py`      | 0 transitions (baseline: 18) |
| BG colorization           | `scripts/probes/verify_gameplay_palette.py`  | PASS                |
| Mini-boss colors          | `scripts/probes/verify_miniboss_color.py`    | PASS                |
| Scroll tearing            | `scripts/probes/verify_scroll_tearing.py`    | PASS (0.00/s)       |
| Sprite orange flicker     | `scripts/diagnostics/verify_sprite_flicker.py`| 0% (120 frames)    |

Tagged `v3.01-o2`. Latest release tag.

---

## Key features

### O(1) Shadow OAM Intercept (v3.01)
Replaces the old hwoam_recolor post-process (53K cycles/VBlank) with a
71-byte HW-OAM stamper at bank13:0x6DB0 running ~375 cycles — **141× speedup**.

Three WRAM-resident trampoline hooks intercept the game's native shadow OAM
writes and inject CGB OBJ palette attributes at the source. No more VBlank
overflow, no more orange sprite flickering.

### Per-Monster-Type Palette LUT
A 256-byte static lookup table at bank13:0x6B00 replaces the old 19-byte
CP-cascade assembly. Monster palette assignments are driven by
`palettes/monster_palette_map.yaml`:

| Monster     | Tile range | Palette |
|-------------|-----------|---------|
| Crow        | 0x30-0x3F | 6 (purple) |
| Orc         | 0x40-0x4F | 5 (blue) |
| Hornet      | 0x50-0x5F | 4 (orange) |
| Soldier     | 0x70-0x7F | 7 (red) |
| Sara Witch  | 0x10-0x2F | Dynamic (FFBE→pal 2) |
| Sara Dragon | 0x10-0x2F | Dynamic (FFBE→pal 1) |
| Projectile  | 0x00-0x01 | 3 (yellow) |

### Arena-Dispatched Inline Hook
The inline hook at bank1:0x42A7 dispatches based on scene:
- D880 < 0x02 (title screen) → tile-only, no attr writes
- D880 < 0x0C (dungeon) → full tile+attr (pickup items red immediately)
- D880 >= 0x0C (boss arena) → tile-only (position sweep owns attrs)

### Teleport + Boss Debugging
The `penta_dragon_dx_teleport.gb` ROM adds SELECT+START combo to teleport
between all 9 boss arenas. Enabled by a WRAM landing pad at 0xDB00 with
stack-redirect mechanism. Debug-only — not in the production build.

---

## Quick start

### Build

#### Production ROM (FIXED.gb):
```bash
python3 scripts/build_v301_gdma.py
# → rom/working/penta_dragon_dx_FIXED.gb (via v301.gb)
```

#### Teleport ROM (with boss debug):
```bash
python3 scripts/build_v301_teleport.py
# → rom/working/penta_dragon_dx_teleport.gb
```

### Test in mGBA

```bash
# Human testing (desktop)
scripts/palette_session.sh start

# Or raw launch (KDE Wayland + NVIDIA):
XAUTHORITY=/run/user/1000/xauth_vYbeWX DISPLAY=:0 QT_QPA_PLATFORM=xcb mgba-qt rom/working/penta_dragon_dx_teleport.gb
```

### Run verification probes

```bash
# Title screen (must show 2+ colors, >5% non-white)
python3 scripts/probes/verify_title_color.py rom/working/penta_dragon_dx_teleport.gb

# Gameplay palette (must show 10+ distinct BG palette words)
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_teleport.gb

# Miniboss colorization
python3 scripts/probes/verify_miniboss_color.py rom/working/penta_dragon_dx_teleport.gb

# Scroll tearing (must be ≤0.50 changes/s)
python3 scripts/probes/verify_scroll_tearing.py rom/working/penta_dragon_dx_teleport.gb

# Phantom sound (must be ≤1.5× vanilla baseline)
python3 scripts/probes/verify_phantom_d887.py rom/working/penta_dragon_dx_teleport.gb

# Orange sprite flicker (PyBoy, 120 frames, must be 0%)
python3 scripts/diagnostics/verify_sprite_flicker.py
```

### Teleport to boss arenas (teleport ROM only)

In-game at a dungeon scene, press **SELECT + START** to cycle through
bosses 0-8 (Shalamar → Riff → Crystal Dragon → Cameo → Ted → Troop →
Faze → Angela → Penta Dragon).

---

## Live palette editing session

```bash
scripts/palette_session.sh start
```

This boots:
1. mGBA-qt with `penta_dragon_dx_teleport.gb` and `live_palettes.lua`
2. A Python HTTP server at localhost:8077 serving the color-picker UI
3. A browser tab pointed at the UI

Stop with `scripts/palette_session.sh stop`.

---

## Architecture

```
scripts/
├── build_v301_gdma.py          # Production ROM builder
├── build_v301_teleport.py       # Teleport ROM builder (extends gdma)
├── patch_oam_intercept.py       # O(1) intercept + trampoline installer
├── bg_experiment.py             # Colorizer codegen utilities
├── probes/                      # Verification probes (5 main + extras)
│   ├── verify_title_color.py
│   ├── verify_gameplay_palette.py
│   ├── verify_miniboss_color.py
│   ├── verify_scroll_tearing.py
│   └── verify_phantom_d887.py
└── diagnostics/                 # Diagnostic harnesses
    ├── verify_sprite_flicker.py
    └── verify_title_cursor_pixels.py

palettes/
├── bg_tile_categories.yaml      # BG tile category → palette mapping
├── monster_palette_map.yaml     # Per-monster-type palette assignments
└── penta_palettes_v097.yaml     # CGB palette color definitions

docs/
├── o1_oam_intercept_plan.md     # O(1) intercept architecture
├── per_monster_palette_plan_v2.md  # Per-monster palette design
├── VBLANK_HOOK_LIMITATIONS.md   # VBlank hook constraint documentation
└── inline_hook_analysis_v300.md # Inline hook design analysis
```

---

## Toolchain

- Python 3.12+
- `pyboy` (headless emulation for probes)
- `Pillow` (screenshot capture and analysis)
- GBDK-2020 / SDCC (for future C-based features)
