# Transition palette blanking (#55 and #83)

## Symptoms
- #83: entering the Stage 1 secret area flashes garbled font tiles for
  ~16 frames before the STAGE ?? card (JP and EN builds alike: the garbage is
  the card font streaming into VRAM, not translated text).
- #55: for ~1 s after a stage appears, the wall columns are flat yellow and
  sprites are white before the stage colours land.

## Root cause (shared)
The original hides both load phases with the DMG palette registers alone
(BGP/OBP), which CGB mode ignores:
- Secret entry `00:1494` sets FFE4, then `169C` sets BGP/OBP = FF and streams
  the card font/map while the dungeon map (old attributes) is still displayed:
  garbage frames 1228-1243 on main.
- Stage start runs the native fade-in `00:0F7D` (BGP 00->40->90->E4). The DX
  palette sequencer is gated on `BGP == E4` (`0D:6BA4`), so during the fade
  BG1-BG7 still hold the previous deck (BG6 = flat yellow on the walls) and
  OBJ0-7 are white; only BG0 comes from the map-flip arm (`0D:740F`). Main:
  yellow frames 496-541, colours complete at ~548.

## Fix (stage `transition-palette-blanking`, `scripts/diagnostics/build_transition_palette_blanking.py`)
Gameplay-only call sites into a bank-$30 body via a 15-byte trampoline
in unreferenced fixed-bank fill `00F0-00FE`, plus one wait fix. The
attract-shared VBlank ISR at `0D:7430-746D` is not modified.
- `00:0F8B` (fade-in frame waits): sample at a 1-frame grain until the map
  is presented, install BG1-BG7 and OBJ0-7 from the stage deck once (the
  whole remaining transfer stays unpaced in VBlank so the last row cannot
  tear), then finish leftover frames with one native `CALL 4068`. This cuts
  the stale yellow from ~46 frames to 1 and keeps Cameo publication on the
  parent 1.2069 ratio. The remaining frame is inherent: the flip runs in the
  attract-shared ISR to LY 151-152, so no gameplay-only code can update
  CRAM before that first presented frame. The `stage_card_stability` /
  `stage1_entry_transition_integrity` gates allow exactly that one frame
  (approved 2026-11-09).
- `00:1494`: set FFE4 (displaced) and black out all 16 CGB palettes, matching
  the original's all-black BGP/OBP frames.
- `00:159F` (`CALL 75C7`, secret-only path): replay the bank-1 card routine as
  a return chain (492B, 0A16, 109E, 7653), perform the card map flip (`75D8`)
  and the card map copy (`75DE CALL 4B52`) while CRAM is still black, then from
  the top of the next frame restore BG0-BG7 (finished before the card glyph
  rows) and OBJ0-7, and resume stock code at `1:75E2`.
- `14:7F1D` (DX window-enable VBlank wait, r373): after DI accept any vblank line (LY >= $90)
  instead of exactly LY == $90. With the exact-edge test a timer IRQ straddling the
  edge every frame can starve the wait forever (found when the boss-handoff
  replay hung on the BOSS 01 card under shifted gameplay timing). Same size
  and cycles; never executed in attract. The 6-byte change is owned by this
  stage; `verify_low_health_flicker`, `arena_bank20_r455` and
  `verify_stage1_captured_menu` authenticate bank 20 after
  `reconstruct_parent` reverts those bytes (narrow lineage carve-out,
  approved 2026-11-09).

Mid-frame CRAM writes are 4-byte bursts on a mode-3 -> HBlank edge (or inside
VBlank).

## Evidence
- Stage start: stale yellow/white cut from ~46 frames to 1; the first
  presented post-flip frame may still hold leftover palettes, then the
  deck is complete.
- Secret entry: frames 1228-1245 black (the first 6 lines of 1228 still show
  the previous room while the paced blackout finishes), then STAGE ?? appears
  complete in one frame; secret-area colours unchanged.
- Attract: hook sites `00F0`, `0F8B`, `1494`, `159F`, `14:7F00` are never
  executed by the attract demo or title.

## Residual (not changed here)
The card fade-out (frames ~1388-1410) still shows card glyphs and a strip of
the secret map on white for ~20 frames (BG0 is whitened by the existing card
fade-out; other palettes are not). That code also runs in attract.
