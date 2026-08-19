# Penta Dragon DX

An in-progress Game Boy Color conversion of *Penta Dragon* (Japan).

Penta Dragon DX adds scene-aware color to the original game while preserving
its movement, music, maps, cutscenes, title demo, and boss fights. The project
is approaching its first public release; the remaining work is mostly visual
palette tuning with a live audience.

[![Seven-stage palette overview](artifacts/stage-collage/penta-dragon-dx-stages-current.png)](artifacts/stage-collage/index.html)

## Current status

**v3.01 stream candidate — emulator-qualified; palette vote and hardware pass
pending.**

- Title footer: `DX V3.01 STRUK LABS`
- Current candidate: **78/78 deterministic emulator gates**, SHA-256
  `c3f7cd1cf0df1136132d147107fdc3ea8ec40d3d20d5603c9124c57830843cbc`
- Stage 1, pickups, rotating hazards, title reel, bosses, and story scenes are
  colorized.
- Qualified: Ted's arena colorization and flicker containment. Stream-day
  review will choose between its stabilized whip/orb pose and the original's
  harsher pseudo-transparency cadence.
- Speed checks cover all seven stages and nine bosses. Matched-work timing puts
  Ted 1.94% slower; three stage routes remain about 3% slower, and Crystal
  Dragon about 3.9% slower. Six other arena loops are faster than the original,
  while their deterministic semantic-animation checks still pass. Every
  exception is visible in the top-level release ledger.
- Audience palette selection and the reservation-backed MiSTer pass are still
  required before release.

The ROM is intentionally not stored in this repository.

## Gameplay

<table>
  <tr>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage1.png" alt="Stage 1 rotating spike room" width="256"><br><sub>Stage 1 — rotating hazard and pickups</sub></td>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage4.png" alt="Stage 4 cyan floor and blue-gray masonry" width="256"><br><sub>Stage 4 — cyan floor and stonework</sub></td>
    <td align="center"><img src="artifacts/stage-collage/panels-current/stage6.png" alt="Stage 6 green chamber" width="256"><br><sub>Stage 6 — green chamber</sub></td>
  </tr>
</table>

The [full stage gallery](artifacts/stage-collage/index.html) shows all seven
stages and the Stage 4/6 palette comparisons.

## Shalamar animation reference

These five captures show Shalamar's major animation poses. The current release
candidate has since passed the all-boss geometry and material checks; exact
color choices remain adjustable during the palette stream.

<table>
  <tr>
    <td align="center"><img src="artifacts/shalamar-clips/shalamar-1.gif" alt="Shalamar animation clip 1" width="256"><br><sub>Idle fire</sub></td>
    <td align="center"><img src="artifacts/shalamar-clips/shalamar-2.gif" alt="Shalamar animation clip 2" width="256"><br><sub>Horizontal movement</sub></td>
    <td align="center"><img src="artifacts/shalamar-clips/shalamar-3.gif" alt="Shalamar animation clip 3" width="256"><br><sub>Vertical movement</sub></td>
  </tr>
  <tr>
    <td align="center"><img src="artifacts/shalamar-clips/shalamar-4.gif" alt="Shalamar animation clip 4" width="256"><br><sub>Orbit pattern</sub></td>
    <td align="center"><img src="artifacts/shalamar-clips/shalamar-5.gif" alt="Shalamar animation clip 5" width="256"><br><sub>Strafing</sub></td>
    <td></td>
  </tr>
</table>

## What is colorized

- Seven dungeon stages with distinct material palettes
- Sara Witch, Sara Dragon, enemies, projectiles, and pickups
- Rotating and thrusting spike hazards
- The 38-character title-screen spotlight reel
- Nine boss arenas and the miniboss roster
- Opening, pre-final, ending, credits, and epilogue scenes
- Title screen, stage cards, menus, HUD, death screen, and GAME OVER

Colors are defined in YAML rather than buried in hand-edited ROM bytes. The
main files are:

- `palettes/penta_palettes_v097.yaml` — actual CGB colors
- `palettes/monster_palette_map.yaml` — monster families
- `palettes/bg_tile_categories.yaml` — floors, hazards, pickups, and materials

## Build and play

You need your own supported Japanese ROM at `rom/Penta Dragon (J).gb`.
Its MD5 must be `df43e0adfdc74b2829c7e95e91c71a28`.

```bash
python3 scripts/build_v302_title_fix.py
scripts/launch_mgba.sh rom/working/penta_dragon_dx_FIXED.gb
```

The launcher is deliberate: it prevents multiple mGBA processes from piling
up and uses the working display configuration for headed testing.

## Tune palettes live

```bash
scripts/palette_session.sh start
```

This opens the guarded mGBA session and browser color picker. Its scene deck
jumps between stages, bosses, characters, and story art so colors can be
compared quickly during a stream.

Live changes are emulator-side CRAM overrides: they are allowed to use mGBA
states and palette-RAM writes, and they do not add a palette editor or teleport
to the release ROM. **Save to YAML** records an approved choice; rebuilding the
ROM is the independent proof that the same colors persist in the shipped patch.

```bash
scripts/palette_session.sh status
scripts/palette_session.sh stop
```

See the [livestream runbook](docs/stream_runbook.md) for the audience-vote
order and post-stream release steps.

## Verification

The release suite builds the ROM twice, requires byte-identical output, and
runs every emulator gate serially:

```bash
python3 scripts/diagnostics/run_deterministic_suite.py \
  --expanded-ted \
  --menu-icon-colors
```

The current candidate cleared **78/78** gates, including cold game start,
Stage 1 terrain and pickups, later-stage movement soaks, low-health flicker,
title-demo actors, all nine bosses, all seven stage comparisons, menus, and
story scenes. The receipt also binds two byte-identical 512 KiB builds to the
tested source and ROM hash, includes a phase-shifted 0.00% timing null, and
reports accepted deviations at the top level rather than hiding them inside
passing gates.

- [Latest hash-bound receipt](docs/release/verification/latest.json)
- [Release and packaging rules](docs/release/README.md)
- [Technical documentation index](docs/INDEX.md)
- [Changelog](CHANGELOG.md)

## Distribution

This repository contains source code, palette data, verification tools, and a
ROM-free IPS patch. It does not contain the original or modified game ROM,
save files, or emulator states.

*Penta Dragon* is owned by its original rights holders. Penta Dragon DX is an
unofficial fan project.
