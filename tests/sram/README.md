# Test SRAM fixtures

Battery-save (.sav) files used to put the ROM into specific states for
end-to-end tests. Unlike savestates (.ss0 — full RAM+CPU snapshot),
these are just battery-backed SRAM contents, so the game still runs
through its cold-boot pipeline.

## Files

- `levelselect_stage1.sav` (iter 156) — 8 KB SRAM with slot 0 populated
  at 0xBF00 with a stage-1 checkpoint (validity flag 0x01, FFBA=0,
  FFBD=1, HP=23) per `reverse_engineering/notes/gap_sram_checkpoint_layout.md`.
  Drops the GAME-START path into the level-select bleed-prone screen so
  the iter 2582e85 WRAM stub can be verified end-to-end. Used by
  `scripts/diagnostics/probe_levelselect2.lua` (iter 156-157).

## How to use

Copy the .sav next to the ROM you're testing as `<rom>.sav`. mGBA
will load it on boot:

```bash
cp tests/sram/levelselect_stage1.sav rom/working/penta_dragon_dx_teleport.gb.sav
# or in a temp dir to avoid clobbering production .sav:
cp rom/working/penta_dragon_dx_teleport.gb tmp/test.gb
cp tests/sram/levelselect_stage1.sav tmp/test.gb.sav
xvfb-run -a mgba-qt tmp/test.gb --script scripts/diagnostics/probe_levelselect2.lua
```
