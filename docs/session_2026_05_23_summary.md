# Session Summary — 2026-05-23 (user AFK overnight)

User reported on MiSTer hardware: white splotches on title screen,
Sara's colors changing when miniboss appears, slowness, scroll flicker.
"BETTER VERIFICATION" — emphasized that verifying before claiming a
fix is essential.

This session built verification infrastructure, found 4 real bugs,
documented the game architecture extensively.

## User-reported issues — all resolved or characterized

| Issue | Status | Evidence |
|---|---|---|
| Sara colors change near miniboss | FIXED | OBJ CRAM probe shows pal 1/pal 2 unchanged after FFBF=1 force |
| Title screen splotches | FIXED | Pure title (no inputs) at f400 in mGBA: full YANOMAN+menu visible; MiSTer screenshot confirms |
| SELECT menu splotches | FIXED | Side-by-side captures vs v3.00: identical HUD strip |
| Scroll flicker | CHARACTERIZED | Not a v3.01 regression — both v3.00 and v3.01 have ~28-34 uninit attrs in non-displayed tilemap from double-buffering |
| Slowness | LIKELY FIXED | Removed FF99 protocol + cold-boot zero = ~5K T saved on first frame, ~125T saved per frame ongoing |

## Bugs identified and fixed

### 1. palette_loader OCPS stride: slot×2 → slot×8
In `bg_experiment.py:create_palette_loader`. CGB OBJ palettes are 8
bytes apart, not 2. Boss palette was landing on OBJ pal 1 byte 4
(corrupting Sara D) instead of pal 6.

### 2. Cold-boot zero of WRAM bank 2
~5K T-cycles on first VBlank pushed palette_loader into LCD mode 3
where CRAM writes are dropped. Bytes stuck at 0x7FFF (white). Removed
entirely (attr_comp+GDMA aren't called, so zero served no purpose).

### 3. FF99 protocol + DF03 init
~125T per VBlank of overhead caused additional palette write drops.
Removed. Colorize handler now byte-for-byte identical to v3.00 at
ROM 0x36E00-0x36E40.

### 4. bg_table missing hazard entries
v3.01 inherited the simpler `_bg_table` from build_v300_inline_hook.py
source, but deployed v3.00 FIXED.gb had pal 5 entries for tiles
0x2A-0x2E, 0x3A-0x3D (hazards/title text) and 0x47, 0x57 (spikes).
Restored.

## Verification infrastructure built

- `scripts/visual_diff_harness.py` — captures continuous frames from
  target + baseline at identical timestamps; generates 3-panel side-by-side
  diff images for 4 phases (title splash, title menu, stage load, scroll)
- `scripts/regression_animation_diff.py` — multi-frame regression with
  RMS flicker + white-pixel-fraction analysis
- `scripts/verify_v301_production.py` — fast functional smoke test
- mGBA Lua probes: OBJ/BG CRAM dumps, OAM tile IDs, VRAM tilemap+attr
  dumps, LCDC bit 3 transitions, tilemap write tracing, FFBF=1 force test

## Game architecture documented (8 new docs)

- `docs/v301_resolved_issues.md` — current production status + verification
- `docs/scroll_flicker_analysis.md` — double-buffered tilemap root cause
- `docs/inline_tile_attr_copy.md` — 0x42A7 mechanism end-to-end
- `docs/game_state_machine.md` — D880/FFC1/FFBA/FFBF/FFBD unified
- `docs/boss_arena_routines.md` (updated) — all 9 arenas with init positions
- `docs/bank_switched_call_pattern.md` — RST 28h thunk system
- `docs/sound_engine.md` — Timer ISR chain, bank-switching, audio
- `docs/obj_colorizer.md` — shadow_main + tile_based_colorizer

`docs/INDEX.md` updated to surface all new docs.

## Commits in this session (chronological)

```
c921076  Fix Sara color-change-near-mini-boss: palette_loader OCPS stride bug
db37a0b  v3.01: remove cold-boot zero — was causing OBJ palette corruption
888870a  v3.01: bg_sweep back inside FFC1 gate — fixes title animation timing
420f898  v3.01: restore missing bg_table entries (hazards/title text pal 5)
b822388  v3.01: title splotches FIXED — colorize handler now matches v3.00
46f83b7  Document v3.01 user-issue resolutions with verification evidence
4d39d64  Document scroll flicker root cause (double-buffered tilemap)
8ef2527  Document inline tile+attr copy at 0x42A7 end-to-end
25d2d88  Document each arena's init position + first data pointer
d139673  Document bank-switched CALL pattern (RST 28h thunk system)
fda3a0c  Document game state machine end-to-end
e327ed5  Document sound engine entry chain and Timer ISR bank-switching
04f4500  INDEX: surface 2026-05-23 architecture docs
11ae4e8  Document OBJ colorizer (shadow_main + tile_based_colorizer)
```

## What was NOT changed (deliberately, despite temptation)

- Scroll flicker dual-tilemap sweep — would require either +3K T/frame
  cost or +5 bytes of code in bg_sweep with state-machine added.
  Pre-existing v3.00 behavior; risk of regressing recently-stabilized
  CRAM write timing.
- shadow_main optimization (LUT vs branching) — ~3K T potential savings
  but risk of palette logic regression.
- attr_comp + GDMA re-enabling — proved unreliable on hardware in
  earlier sessions; production stays at v3.00-equivalent functional behavior.

## Hardware status (MiSTer)

ROM `penta_dragon_dx_v301.gb` (md5 `48649460f5d6833cfdc0dca3e95b6bda`)
deployed to both `.gb` and `.gbc` filenames on MiSTer. Title screen
visually verified clean.

Ready for user to test gameplay on real hardware.
