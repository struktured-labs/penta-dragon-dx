# Changelog

This project records source-level changes only. Copyrighted ROM images and
emulator save/state files are never release artifacts in this repository.

## [v3.01-stream-rc2] - 2026-07-22

### Fixed

- Keep title-screen text on palette 0 instead of inheriting the dungeon font's
  red palette, and refresh the intended white-to-blue-gray palette safely at
  the start of each title VBlank.
- Clear the six visible item-menu window attribute rows in both hardware
  window maps when the menu opens, removing the red palette bleed from the HP
  bar, `MEDICAL` separator, and full-health `F` marker.
- Remove the unstable `SELECT+START` teleport and IRQ stack redirect that could
  freeze gameplay. Scene-aware palettes, lava overrides, and level-select
  setup remain enabled.
- Make the gameplay palette probe wait for a real dungeon scene rather than
  accepting the earlier all-palette-0 stage splash as gameplay.

### Verified

- Combined cold-boot mGBA release gate: exact title palette bytes, zero
  contaminated title attributes, and zero contaminated menu HUD attributes.
- Live `SELECT+START` regression through frame 1300: gameplay continued, the
  scene and boss indices stayed unchanged, and shadow OAM kept advancing.
- Title integration/color, gameplay background palette, miniboss object
  palette, and boot/menu-transition probes.
- Repaired output MD5: `bd2bd354dbf5393fbc8d37cee79595cc`
  (informational only; the ROM itself is not committed).

## [v3.01-stream-rc1] - 2026-07-22

### Fixed

- Render the exact title footer `DX V3.01 STRUK LABS` independently of the
  current Git tag or detached-head state.
- Use the title screen's signed VRAM tile-addressing mode correctly. The
  native `3`, `0`, and `1` glyphs are reused, while a one-block GDMA transfer
  installs the period and restores the displaced native `9` after the title.
- Move footer glyph data out of the live palette/colorizer routines it had
  overwritten, with explicit collision and free-space assertions in the
  builder.
- Restore reliable title-menu input through the proven joypad sampler and
  keep the title-safe tile-only inline colorizer path.
- Restore the correct level-select WRAM target and remove the duplicate sound
  engine call from the VBlank wrapper.
- Preserve cold-boot title palette timing so the title no longer appears
  completely white.

### Verified

- Exact footer tilemap and period glyph in live mGBA memory.
- Title integration and title-color probes through 600 frames.
- Gameplay background palettes, miniboss object palettes, scrolling attribute
  stability, boot/menu transitions, and menu input in PyBoy and mGBA.
- Repaired output MD5: `2809fe9005b17441c83078d921128685`
  (informational only; the ROM itself is not committed).

### Known issues

- The in-game menu HUD has red pixels on the HP bar, `MEDICAL` separator text,
  and the full-health `F` marker. This is captured for the next palette pass.
