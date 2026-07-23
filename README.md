# Penta Dragon DX

**Game Boy Color colorization of Penta Dragon (ペンタドラゴン)**

Converts the original DMG ROM into a CGB build with semantically-aware
palettes for floors, walls, items, hazards, and sprites — plus an O(1)
Shadow OAM intercept system that eliminates VBlank overflow flickering.

---

## Status: ✅ v3.01-stream-rc3 — livestream release candidate

The current release workflow builds `rom/working/penta_dragon_dx_FIXED.gb`
with the exact title footer `DX V3.01 STRUK LABS`. The ROM is intentionally
excluded from Git; the builder, probes, and documentation are versioned.

| Release gate | Probe | RC3 result |
|--------------|-------|------------|
| Title footer and palette | `verify_title_screen_integration.py`, `verify_title_color.py` | PASS |
| `STAGE XX` timing/ditty | `verify_stage_intro_timing.py` | 156 frames and 233 timer ticks, exactly matching vanilla |
| Item-menu HP/MEDICAL attributes | `verify_menu_hud_and_combo.py` | PASS, 0 contaminated cells |
| BG colorization | `verify_gameplay_palette.py` | PASS, 15 palette words / 3 indices |
| Phantom sound | `verify_phantom_d887.py` | PASS, 2 transitions versus vanilla's 18 |
| Scroll stability | `verify_scroll_tearing.py` | PASS, 0.00 changes/s |
| `SELECT+START` safety | `verify_menu_hud_and_combo.py` | PASS, no scene change or freeze |

Tagged `v3.01-stream-rc3`.

---

## Key features

### Stream-safe title, transitions, and HUD (v3.01-stream-rc3)

- Exact `DX V3.01 STRUK LABS` release footer with a native-style period glyph.
- Intentional white-to-blue-gray title palette with no accidental red text.
- Vanilla-length `STAGE XX` card: the colorizer yields during the stock
  frame-synchronized wait, preventing the intro ditty from repeating.
- Clean item-menu HP bar, `MEDICAL` separator, and full-health `F` marker on
  either hardware window map.
- The unstable IRQ-stack `SELECT+START` teleport is removed from production.

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
- Hardware window enabled (item menu) → tile-only, preserving palette-0 HUD attrs

### Legacy teleport debugging

The older `penta_dragon_dx_teleport.gb` debug build contains the retired
IRQ-stack teleport experiment. It is not a release artifact and must not be
used for livestream/release validation. A safe main-loop browser teleport can
be added later without restoring the stack redirect.

---

## Quick start

### Build

#### Stream release candidate (`FIXED.gb`)

```bash
python3 scripts/build_v302_title_fix.py
# → rom/working/penta_dragon_dx_FIXED.gb
```

### Test in mGBA

```bash
# Verified human-testing launch (KDE Wayland + NVIDIA):
DISPLAY=:0 XAUTHORITY=/run/user/1000/xauth_vYbeWX QT_QPA_PLATFORM=xcb \
  /home/struktured/bin/mgba-qt \
  /home/struktured/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_FIXED.gb
```

### Run verification probes

```bash
# Title screen (must show 2+ colors, >5% non-white)
python3 scripts/probes/verify_title_color.py rom/working/penta_dragon_dx_FIXED.gb

# Exact STAGE XX/ditty duration versus the original ROM
python3 scripts/probes/verify_stage_intro_timing.py rom/working/penta_dragon_dx_FIXED.gb

# Title, menu HUD, and retired SELECT+START safety
python3 scripts/probes/verify_menu_hud_and_combo.py rom/working/penta_dragon_dx_FIXED.gb

# Gameplay palette (must show 10+ distinct BG palette words)
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_FIXED.gb

# Miniboss colorization
python3 scripts/probes/verify_miniboss_color.py rom/working/penta_dragon_dx_FIXED.gb

# Scroll tearing (must be ≤0.50 changes/s)
python3 scripts/probes/verify_scroll_tearing.py rom/working/penta_dragon_dx_FIXED.gb

# Phantom sound (must be ≤1.5× vanilla baseline)
python3 scripts/probes/verify_phantom_d887.py rom/working/penta_dragon_dx_FIXED.gb

# Orange sprite flicker (PyBoy, 120 frames, must be 0%)
python3 scripts/diagnostics/verify_sprite_flicker.py
```

## Live palette editing session

```bash
scripts/palette_session.sh start
```

This currently boots the legacy debug workflow:
1. mGBA-qt with `penta_dragon_dx_teleport.gb` and `live_palettes.lua`
2. A Python HTTP server at localhost:8077 serving the color-picker UI
3. A browser tab pointed at the UI

Stop with `scripts/palette_session.sh stop`.

Use `FIXED.gb` for release validation. The palette browser remains useful for
live color tuning, but its boss-teleport request has no release-safe in-ROM
consumer yet.

---

## Architecture

```
scripts/
├── build_v301_gdma.py           # Base production ROM builder
├── build_v301_teleport.py       # Teleport ROM builder (extends gdma)
├── build_v302_title_fix.py       # v3.01 stream RC builder
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
