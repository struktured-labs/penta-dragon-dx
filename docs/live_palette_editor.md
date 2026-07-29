# Live Palette Editor (mGBA)

Tune CGB palette colors in real time while the game runs in mGBA.

## How it works

```
    [browser]                [Python server]              [mGBA + Lua]
  http://localhost:8077  →  live_palettes.txt       →   CGB CRAM writes
       (sliders)              (text file)                (~0.5s latency)
```

1. The Python server (`scripts/live_palette_editor.py`) hosts a browser UI
   with color pickers for all 29 builder palettes: 8 BG, 8 primary OBJ, 8
   miniboss/boss overrides, 2 jet forms, and 3 powerup projectiles.
2. When you pick a color, the server writes only the edited base or guarded
   special palettes to `rom/working/live_palettes.txt`. Boss, jet, and powerup
   overrides apply only while their exact `FFBF`, `FFD0`, or `FFC0` state is
   active, leaving unrelated CRAM alone.
3. The Lua script (`scripts/lua/live_palettes.lua`) running inside mGBA
   polls the file every 30 frames (~0.5s).
4. On change detected, Lua decodes the BGR555 values and writes them to
   CGB BCPS/BCPD (BG palette) or OCPS/OCPD (OBJ palette).

The game continues running. You see the color change in the running
emulator within half a second of picking it in the browser.

The **Stream Scene Deck** loads 42 mGBA states: the title; 12 story/ending
states; Stages 2–7; all nine stage/final boss arenas; both Sara forms; ordinary
enemy families; both minibosses; stable Spiral and Shield contexts; the jet
stage; and item menu. Stage 2–7 states are generated from the ROM's original
save-present level-select path and cached by ROM checksum under
`tmp/palette_session/`.

Those six mGBA captures are intentionally sequential. Parallel offscreen Qt
contexts can crash one emulator process even when each isolated capture is
valid; sequential generation takes only a few seconds and removes that
host-display race.

The story states cover the intro's first text, book, Sara, and dragon-eye
panels; pre-final Penta Dragon and Sara panels; and post-final dragon, Lisa,
and Sara panels. Three ending-tail states add the credits, END page, and
epilogue. The intro generator confirms the title's default first option with A
only. It never sends DOWN, because DOWN selects the actual GAME START option.

Every art state carries the stock committed-panel identity
`D880/DCE8/DCEA/DCF0/DD07`. Final-story states are also resumed for 60 clean
frames in a fresh mGBA process on the untouched release ROM. The release ROM
already maps the top eight artwork rows to the corresponding BG1–BG7 palette
while retaining BG0 for the separator, dialogue border, and text. Lua
reasserts that same position-aware layout after a research-state load; it does
not invent a layout that is absent from production.

Credits, END, and epilogue are direct-written pages whose portrait bytes can be
stale, so they do not use the story-art identity. Each state instead requires
the exact stock `D880/D889/DCE2/FFF9` ending-phase guard, `FFC1=0`, and
`FFE4=1`. Their production full-screen layouts use BG1, BG2, and BG3,
respectively. Lua reasserts those same 20×18 layouts after state loading. A
wrong or stale state receives no reassertion.

Boss states begin from a freshly generated Stage 1 state. The generator edits
only a temporary copy of mGBA's serialized CPU/memory state to invoke the
original boss dispatcher, then runs and recaptures each arena for 240 frames
on the untouched `FIXED.gb`. The browser itself only requests whitelisted
state files; the retired SELECT+START ROM teleport and raw state-byte holds
are not present.

## Setup

One-time:
```bash
pip install pyyaml  # if not already installed
```

## Usage

The launcher uses the verified XWayland/NVIDIA mGBA command, starts the editor
on loopback only, and tracks its own PIDs:

```bash
scripts/palette_session.sh start
```

It defaults to:

```bash
DISPLAY=:0 QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia \
  mgba-qt rom/working/penta_dragon_dx_FIXED.gb \
  --script scripts/lua/live_palettes.lua
```

Then open:

```
http://localhost:8077
```

Stop only the processes owned by this session:

```bash
scripts/palette_session.sh stop
```

The stop command does not kill unrelated mGBA windows.
Starting again first stops only the prior owned session before regenerating
ROM-matched states. Startup exits nonzero and stops the editor if the verified
XWayland/xcb mGBA process does not survive, instead of opening a browser onto a
dead emulator session.

## Saving your tuned colors

In the browser, click **Save to YAML**. It updates the color arrays in
`palettes/penta_palettes_v097.yaml` while preserving comments, ordering, and
the rest of the file. Before a changed save, the editor preserves the previous
YAML under `tmp/palette_session/backups/` as a hash-named
`*.presave_<md5>.backup.yaml`; unchanged saves create no extra copy. Rebuild
the current release candidate to bake the selected colors in:

```bash
python3 scripts/build_v302_title_fix.py
```

The ROM now has your tuned colors permanently.

The builder keeps BG7 equal to BG0 only during the title's boot-attribute
window, then restores the independently tuned YAML BG7 through a phased CRAM
service that handles one palette per VBlank. Each palette is written as two
LCD-mode-safe four-byte halves, preventing partial old/new CRAM hybrids.
`verify_palette_build_roundtrip.py` checks that path
with deliberately changed BG0, BG7, Sara Witch, both jet forms,
Gargoyle/Boss3, and all three powerup values in an isolated build. Before a
changed default `FIXED.gb` is written, the builder also creates
`penta_dragon_dx_FIXED.prebuild_<md5>.backup.gb` from the previous ROM. An
identical rebuild does not create another copy.

## Format reference

CGB palettes are stored as BGR555 (5 bits each for blue, green, red).
The text file uses 4-char hex strings:

```
BG0:0=7FFF,1=7E94,2=3D4A,3=0000
OBJ2:0=0000,1=2EBE,2=511F,3=0842
BOSS1@6:0=0000,1=601F,2=400F,3=0000
JET2:0=0000,1=7C1F,2=5817,3=3010
POWER2:0=0000,1=03FF,2=02BF,3=019F
```

`BG<n>` = BG palette `n` (0-7). `OBJ<n>` = OBJ palette `n` (0-7).
`BOSS<flag>@<slot>` is guarded by `FFBF`; `JET<slot>` by `FFD0=1`;
`POWER<flag>` targets OBJ0 only while `FFC0` matches.
`<idx>=<hex>` = color index `idx` (0-3) set to 4-char BGR555 hex.

Lines starting with `#` are ignored. The Lua script reads only lines
matching the patterns above.

## What's tunable

| Palette | Default name | Used by |
|---|---|---|
| BG 0 | Dungeon | Floor + most BG tiles |
| BG 1 | BG1 | Items (chests, potions) |
| BG 2 | BG2 | (decorative) |
| BG 3 | BG3 | (decorative) |
| BG 4 | BG4 | (decorative) |
| BG 5 | BG5 | (decorative) |
| BG 6 | BG6 | Walls (slate gray) |
| BG 7 | BG7 | (mystery/special) |
| OBJ 0 | EnemyProjectile | Enemy projectiles + effects |
| OBJ 1 | SaraDragon | Sara in Dragon form |
| OBJ 2 | SaraWitch | Sara in Witch form |
| OBJ 3 | SaraProjectileAndCrow | Sara projectiles + Crow enemies |
| OBJ 4 | Hornets | Hornet enemies |
| OBJ 5 | OrcGround | Orc/ground enemies |
| OBJ 6 | Humanoid | Runtime range `0x60–0x6F` (Gargoyle override when miniboss=1) |
| OBJ 7 | Catfish | Runtime range `0x70–0x7F` (Spider override when miniboss=2) |

The special sections add all eight `boss_palettes` entries, both
`SaraDragonJet`/`SaraWitchJet` alternates, and Spiral/Shield/Turbo projectile
entries. Gargoyle, Spider, Jet, Spiral, and Shield use natural curated states.
No natural `FFC0=3` Turbo state exists in the checked-in library, so Turbo
remains directly tunable and is guard-tested diagnostically without adding a
browser control that mutates game state.

The title-idle actor reel uses `monster_palette_map.yaml`; ordinary gameplay
uses the game's dynamic packed tile ranges. They intentionally share CRAM
colors but not the same tile-to-palette dispatch table.

## Automated stream gate

```bash
python3 scripts/diagnostics/verify_live_palette_session.py \
  rom/working/penta_dragon_dx_FIXED.gb
```

The gate starts the loopback editor and headless mGBA, generates 12 fresh
story/ending states, Stage 2–7, and nine boss-arena states, verifies selective
browser edits in actual BG/OBJ CRAM, checks comment-preserving YAML persistence
on a temporary copy, stress-tests 64 concurrent HTTP edits, proves that clicking
the same scene twice publishes two distinct mGBA requests, and loads/renders all
42 scene buttons. A dedicated guarded-special audit proves the Gargoyle, jet,
Spiral, Shield, and diagnostic Turbo values reach the intended OBJ CRAM slots
only under their matching state bytes. It also proves a changed save preserves
the exact prior YAML and an unchanged save creates no redundant backup. For
each artwork button it verifies the complete stock panel discriminator, 160
artwork cells on the intended BG palette, and 200 separator/dialogue cells on
BG0. It also requires the three ending-tail states to pass their complete phase
guards and map all 360 visible cells to BG1, BG2, and BG3 respectively.

The bridge smoke test captures its rendered PNG before publishing completion
and waits for the file to flush. The same gate is part of
`verify_release_candidate.py`'s 30-gate isolated release matrix.

## Troubleshooting

- **Colors don't update**: Verify mGBA is running with the Lua script and check
  `rom/working/live_palettes_lua.log`.
- **Scene button does nothing**: Run the automated stream gate above. It
  validates checked-in curated states plus the ROM-matched generated
  stage/boss state caches.
- **RGB conversion**: The conversion is BGR555 ↔ RGB888, rounded to the nearest
  5-bit value per channel. All 32,768 valid CGB words round-trip exactly;
  arbitrary 24-bit picker colors are quantized to the nearest representable
  CGB color.
- **mGBA crashed**: Do not switch to the legacy teleport ROM. Run the automated
  stream gate and keep `FIXED.gb` as the session ROM.
