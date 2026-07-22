# Changelog

This project records source-level changes only. Copyrighted ROM images and
emulator save/state files are never release artifacts in this repository.

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
