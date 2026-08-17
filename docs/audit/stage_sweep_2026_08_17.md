# Stage playthrough sweep — 2026-08-17

OG-versus-DX visual regression sweep across all seven dungeon stages:
identical scripted boot route per side (title → level select → stage), 1200
play frames, screenshot every 60 frames, two-row contact sheets. Tooling:
`scripts/diagnostics/capture_stage_side_by_side.py` +
`probe_stage_side_by_side.lua`. Artifacts: `tmp/stage-sweep/` (gitignored),
manifest with ROM hashes per run.

**Baseline note:** DX side is the Aug-12 checkpoint
(`832dd43b`, `fef1739`'s candidate preserved in the deterministic-suite
tested-rom), because the sweep's first run found the CURRENT
`rom/working/penta_dragon_dx_FIXED.gb` (md5 `9c738aac`, built 2026-08-14
23:37 mid-Ted-iteration) **cold-boot broken in the dungeon**: game logic
runs (D880=02, mainline active) but the screen stays white with a garbled
band, frozen at room 5 — the classic colorize-init-never-fired class. The
same probe, same route, back-to-back against OG and the Aug-12 ROM both play
normally, isolating the ROM as the cause. Reported to the Ted lane
(intercom msg 5333); whoever promotes the next candidate must rebuild
FIXED.gb from a known builder state and launch-gate it.

## Verdicts (OG top row vs Aug-12 DX bottom row, 20 aligned panels each)

| stage | verdict | notes |
|---|---|---|
| 1 | CLEAN | rooms r03→r07 in lockstep; lavender floor, red pickups, colored enemies |
| 2 | CLEAN | cyan water-cave palette; spikes/rock band/enemies all track |
| 3 | CLEAN | sheet-scale "dark band" was the brick wall correctly blue-gray at full size; ghosts magenta; pickup classes visible (green/red) |
| 4 | CLEAN | cyan channels + blue-gray stonework; late-panel drift only |
| 5 | CLEAN | lava-yellow floor confirms the FFBA=4 molten override live |
| 6 | CLEAN | green chamber; rooms track perfectly |
| 7 | CLEAN | orange floor + ornate band + shrubs; 1-panel start offset (cold-start), aligned by f120 |

No white screens, no attribute bleed, no missing materials, no detached
artifacts observed in 280 panels. Late-run positional drift between rows is
the known ~6% dungeon speed difference, not a route divergence, and does not
affect palette review.

## Cutscene/menu OG comparison (added same day, PyBoy — no emulator slot)

- **Opening cutscene**: 33 OG panels captured with the same
  `inventory_opening_cutscene.py` schedule as the matrix's DX artifacts and
  tile-map-diffed per panel. Every difference is typewriter/scroll
  capture-phase skew (2-frame offset; mixed directions across panels —
  panel 14 DX-ahead by 31 cells, panels 13/17 DX-behind by 4–5; panel 11's
  49/49 bidirectional delta is the scrolling text tail with identical
  story_state both sides). **No glyph or content regression.** The one
  deliberate deviation: DX renders the text scroll black-on-white vs the
  original's white-on-black (region-palette choice; operator-taste item).
- **Ending sequence**: 86 OG panels via `inventory_final_cutscene.py`
  direct-entry, surveyed against the matrix's route-B ending inventory
  (157 panels). DX plays the full sequence colored (dragon art, dialogue,
  red credits) with no missing content; routes differ so this is
  survey-level, backed by the passing ending-inventory gates.
- **Menus**: matrix menu gate receipts + visual montage — colorized
  (MEDICAL overlay, red HP/accents), no artifacts. Palette polish remains
  an operator-stream item.

## Follow-ups

1. **Current FIXED.gb regression** — blocked on the Ted lane promoting a
   clean rebuild; re-run stage 1 against it after promotion.
2. Boss-arena OG/DX side-by-sides for the 8 non-Ted bosses
   (`capture_boss_side_by_side.py --target N`) — pending emulator-slot
   window after the Ted determinism battery.
3. Menus/cutscenes are outside this sweep's route; the existing matrix gates
   (menu_hud_and_combo, opening/ending inventories) cover them.
