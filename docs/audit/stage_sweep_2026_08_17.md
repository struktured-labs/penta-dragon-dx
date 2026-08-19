# Stage playthrough sweep — 2026-08-17

## Qualified-r9c rerun — 2026-08-18

The complete seven-stage sweep was rerun against the current source-built
candidate, `tmp/source-native-route-relocated-cadence0-r9c.gb` (SHA-256
`e37e90c5573415ab7295d72ac0a2d230d666ed9d6322d2be1445a316841abf4e`).
The builder replay at `tmp/source-native-route-relocated-cadence0-r9d-replay.gb`
is byte-identical, so these receipts describe the reproducible source output
rather than the older August 12 checkpoint below.

- Paired visual sweep:
  `tmp/source-native-route-relocated-cadence0-r9c-stage-sweep-r1/manifest.json`.
  All seven OG/DX pairs completed 1,200 play frames with 20 aligned captures
  per side: 280 screenshots total. Visual review found no white screen, black
  void, overlaid wall, pickup trail, or detached terrain class.
- Long semantic/display soak:
  `tmp/source-native-route-relocated-cadence0-r9c-later-soak-12000-r2/`.
  Stages 2–7 each completed 12,000 play frames across rooms 01/03/05/07.
  Every map selected for display matched its semantic attributes; all stage
  BG0 identities and required pickup/material/lava slots passed. Totals:
  72,000 play frames, 807 display-handoff scans, 1,192 pickup samples, 10,371
  Stage-4 material samples, and zero mismatches.
- Immutable-WRAM ownership is now checked in the owning CGB WRAM bank. The
  probe also defers samples while native OAM DMA makes the CPU bus unreadable;
  the old unbanked audit interpreted bank 2/3 attribute work and `$FF` DMA
  reads as mutations. With both conditions fixed, all six 12,000-frame runs
  report zero changes to the bank-1 D900/DA00 runtime pages.

The original sweep record is retained below as historical evidence.

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
the historical Aug-12 ~6% dungeon speed difference, not a route divergence,
and does not affect this palette review. The current r5 input-identical receipt
reduces the remaining slow routes to roughly 3%.

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

## Boss animation side-by-sides (added same day)

30-second OG/DX animation captures (`capture_boss_side_by_side.py`,
450+450 frames each, phase-unsynchronized) for shalamar, riff, cameo,
troop, faze, angela, penta_dragon — sheets and mp4s in `tmp/boss-sxs/`.
**All seven PASS**: pose/behavior classes track OG (including cameo's
vanish-reappear phases and penta's screen-edge wing clipping, both present
in OG), materials per contract, projectiles/debris colored by item palette
(the "green specks" watch item resolved as native floor debris visible as
gray dots in OG), no bleed or garbage classes. Ted is covered by its own
v8 60-second receipt (containment 0/3600). Crystal Dragon rejects the
animation capture with every available OG state (its portal cycle exits
the scene on the OG side); coverage stands on its dedicated gates —
crystal_dragon_ghost, the cached-atomic camera-wrap contract, geometry,
and the material gallery — the deepest per-boss gate stack in the matrix.

**Boss visual review verdict: 9/9 covered, 0 regressions.**

## Follow-ups

1. **Current FIXED.gb regression** — blocked on the Ted lane promoting a
   clean rebuild; re-run stage 1 against it after promotion.
2. Boss-arena OG/DX side-by-sides for the 8 non-Ted bosses
   (`capture_boss_side_by_side.py --target N`) — pending emulator-slot
   window after the Ted determinism battery.
3. Menus/cutscenes are outside this sweep's route; the existing matrix gates
   (menu_hud_and_combo, opening/ending inventories) cover them.
