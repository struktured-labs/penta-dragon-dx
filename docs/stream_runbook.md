# Penta Dragon DX livestream palette runbook

This is the release-safe path for the Twitch color-picking stream. It uses the
exact production ROM in mGBA, curated ROM-matched states, and the browser
editor. Live tuning is external tooling: the browser/Lua bridge may load
curated emulator states and write mGBA's CGB palette RAM without adding those
controls to the ROM. It does not enable the retired SELECT+START teleport.

## September 27 regression work — experimental source build

The later recorded-playthrough bugs remain under investigation. The historical
r536 qualification below does not certify the newer experimental builds or
resolve those reports. Do not deploy an experimental ROM based on this page.

To reconstruct the current combined experimental fixes from original ROM and
palette sources, choose a fresh ignored output directory:

```bash
uv run --with pyyaml python scripts/build_stream_regression_candidate.py \
  --presentation --output tmp/stream-presentation-local
```

The expected result is SHA-256
`d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5`.
The build checks exact intermediate identities and records loaded project
Python source hashes. It uses no archived candidate ROM as an input. Omitting
`--presentation` preserves the earlier source07 construction. Neither mode
runs acceptance tests, deploys, changes the default ROM, or grants readiness.
See [the regression audit](audit/recorded_stream_regressions_20260927.md) for
tested scope and unresolved reports, including persistent yellow trails.

## Historical pinned r536 profile

Tonight's qualified gameplay build is r536, SHA-256
`b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`.
The convenient local copy is
`tmp/stream-tonight/Penta Dragon DX v3.01.gbc`; it is byte-identical to both
independent source builds retained under
`tmp/r536-restored-suite-current721/build/`.

The fresh deterministic receipt is
`docs/release/verification/latest.json`, and its complete 87-gate matrix is
`tmp/r536-restored-suite-current721/matrix/manifest.json`. Use those
exact paths together. Do not substitute an older ROM merely because its
filename is familiar.

The normal gameplay-stream entrypoint is `scripts/launch_mgba.sh CANDIDATE`.
It requires an explicit ROM, records its SHA-256, and keeps the headed emulator
under the project single-flight wrapper. Use
`scripts/palette_session.sh start CANDIDATE` only when the browser palette
editor is actually needed.

A live color preview does not alter the ROM. If YAML is saved during a palette
session, rebuild and qualify the resulting r536 identity before treating those
colors as part of the patch. Ted's stabilized whip/orb animation remains a
documented taste choice under item 6 of `release/known_deviations.md`; it is not
a gameplay-stream blocker.

## Before going live

1. Confirm that no emulator already owns the single-flight slot:

   ```bash
   scripts/check_emulator_processes.sh --require-none
   ```

2. Revalidate the fresh receipt and its exact complete matrix without starting
   another emulator:

   ```bash
   env LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
     TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
     python3 scripts/diagnostics/verify_suite_receipt.py \
       --receipt docs/release/verification/latest.json

   env LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
     TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
     python3 scripts/diagnostics/verify_live_regression.py \
       "tmp/stream-tonight/Penta Dragon DX v3.01.gbc" \
       --verify-manifest \
       tmp/r536-restored-suite-current721/matrix/manifest.json
   ```

3. Start the guarded gameplay build:

   ```bash
   scripts/launch_mgba.sh \
     "tmp/stream-tonight/Penta Dragon DX v3.01.gbc"
   ```

   For an audience palette-tuning stream instead, start the editor pair with:

   ```bash
   scripts/palette_session.sh start \
     "tmp/stream-tonight/Penta Dragon DX v3.01.gbc"
   ```

   That launcher also opens `http://localhost:8077` and refreshes the
   ROM-matched stage, boss, and story states when needed.

4. Capture the mGBA window in OBS. Keep the browser editor available to the
   host; show it on stream only if desired.

## Title controls to explain on stream

- **OPENING START is the first/default option.** Confirming it plays the story
  intro.
- Press **DOWN** to move to **GAME START**, then confirm to play.
- SELECT+START has no teleport function in the production ROM.

## Suggested audience-vote order

The 42-button Stream Scene Deck is arranged to make comparison quick:

1. Title/idle reel, then Sara Witch/Dragon and common Stage 1 actors.
2. Stages 2–7, with special attention to the Stage 5 and 7 lava scenes.
3. Gargoyle/Spider, then all nine boss arenas. For Ted, explicitly compare
   the stabilized DX whip/orb pose with the original's roughly 10 Hz
   pseudo-transparency phase and record the audience verdict.
4. OPENING book/Sara/dragon-eye art.
5. Pre-final Penta/Sara; post-final dragon/Lisa/Sara; credits, END, epilogue.
6. Spiral, Shield, jet forms, and item menu.

Edits reach mGBA in about half a second. Boss bodies use global BG palette
rows, so a **global** BG edit on one boss also changes every other boss that
shares that row. Use the per-arena panel below to tune one boss without
touching the others. Story artwork colors only the top artwork region;
separator, border, and dialogue must remain neutral.

## Per-arena boss colors (`arena_bg_palettes`)

The editor's **Boss Arena BG Palettes (per arena)** panel lists all nine
arenas. Each one shows the BG rows its tile table actually produces, derived
from `scripts/arena_tables_data.py`, and names the other arenas that share each
global row:

| Row | Arenas using it |
|---|---|
| BG0 | every arena (backdrop / unmapped cells) |
| BG1 | Cameo, Ted (shell), Penta Dragon |
| BG2 | Riff, Ted (tendrils), Faze, Angela |
| BG4 | Shalamar, Crystal Dragon |
| BG5 | Ted (gold scales) |
| BG6 | Ted (floor tiles) |
| BG7 | Ted (floor tiles), Troop (whole body) |

No arena uses BG3.

- To edit one boss, load its scene button, expand that arena, and pick
  colors. The first edit to a row copies the current global row, so only the
  color you changed differs. The row is then marked **ARENA OVERRIDE**.
- The Lua bridge applies an arena row only while `D880` equals that arena's
  scene id: `$0C` Shalamar, `$0D` Riff, `$0E` Crystal Dragon, `$0F` Cameo,
  `$10` Ted, `$11` Troop, `$12` Faze, `$13` Angela, `$14` Penta Dragon.
  Everywhere else, including the death screen (`$17`) and the post-boss
  reload (`$16`), the global rows stay in effect. Inside the arena, an arena
  row wins over a global edit of the same row.
- The **global** button on a row, or **Revert all … rows to global**, drops the
  override and immediately re-asserts the global row in CRAM.
- **Save to YAML** writes the global rows exactly as before. It also writes
  the editor-managed block `arena_bg_palettes.<Boss>.BG<n>`, with the same
  hash-named pre-save backup. If no arena overrides exist and the YAML has no
  such block, the saved YAML is byte-identical to what the old editor wrote.
  Missing arenas or rows always fall back to `bg_palettes`.
- **Reset live colors from YAML** reloads saved arena rows too, and discards
  unsaved ones.

**Until the builder compiles `arena_bg_palettes`, per-arena rows are only a
live preview.** The current stream candidate does not contain them. A rebuild
from a YAML that has only arena overrides produces the same ROM, so
`record_palette_approval.py --verify-only` would pass without those colors
being in the patch. Record which boss got which arena row, and do not treat
arena rows as approved until a builder with `arena_bg_palettes` support has
rebuilt and requalified the ROM. Global-row picks follow the normal flow
below.

### Running the session from a worktree

`palette_session.sh` now derives its project directory from its own
location, and exports it to `live_palettes.lua` as `PENTA_PROJECT_DIR`.
Running `scripts/palette_session.sh` inside a git worktree therefore uses
that worktree's editor, YAML, backups, `tmp/palette_session` states, and PID
files. The historical checkout path keeps working unchanged. Pass the ROM as
an absolute path when it lives in another checkout. `status` and `stop`
only see sessions started from the same checkout, but the global
single-flight lock still refuses a second emulator. Set
`PENTA_PALETTE_NO_BROWSER=1` to skip opening the browser tab.

An on-screen live change proves the tuning bridge only; it does not alter the
ROM file. **Save to YAML** followed by a fresh build proves that the chosen
colors survive reset and are part of the eventual patch.

Use **Reset live colors from YAML** to abandon unsaved experiments. Use
**Save to YAML** only after the audience has chosen a set. A changed save
creates a hash-named pre-save backup under `tmp/palette_session/backups`;
an unchanged save does nothing.

## After the audience locks the colors

Stop the owned session:

```bash
scripts/palette_session.sh stop
```

Then build and prove the exact audience-tuned candidate in this order:

```bash
STREAM_SUITE="tmp/palette-stream-final"

python3 scripts/diagnostics/run_deterministic_suite.py \
  --r536-source \
  --output "$STREAM_SUITE" \
  --receipt "$STREAM_SUITE/deterministic-receipt.json"
```

This is the only production rebuild path for the current release line. It
builds the 512 KiB image twice with native Ted sparse geometry, the exact
native pose table, and the item-menu publisher. It then runs the complete
applicable matrix. The receipt is written only after both builds are
byte-identical and every gate passes; all output stays under the repository's
`tmp/` tree.

Use the suite's proven build—not a pre-stream ROM or an independently rebuilt
copy—for the patch and approval:

```bash
STREAM_SUITE="tmp/palette-stream-final"
STREAM_ROM="$STREAM_SUITE/build/source-a/candidate.gb"

uv run penta-colorize build-patch \
  --original "rom/Penta Dragon (J).gb" \
  --modified "$STREAM_ROM" \
  --out "$STREAM_SUITE/Penta_Dragon_DX_v3.01.ips"
```

Only after that proof, record the audience decision:

```bash
STREAM_SUITE="tmp/palette-stream-final"
STREAM_ROM="$STREAM_SUITE/build/source-a/candidate.gb"

python3 scripts/record_palette_approval.py \
  --r536-source \
  --rom "$STREAM_ROM" \
  --source-output "$STREAM_SUITE/palette-source-proof" \
  --output "$STREAM_SUITE/palette-approval.json" \
  --confirm "AUDIENCE APPROVED" \
  --notes "Final colors selected during the Twitch stream"
```

The recorder independently rebuilds the same expanded profile in repo-local
temporary storage and refuses approval unless the saved YAML reproduces the
exact suite ROM byte-for-byte.

For a public release, the optional hardware and approval workflow remains
documented in `README.md`. It is separate from launching the qualified ROM for
a gameplay stream.

## Recovery

- If mGBA or the editor exits, `scripts/palette_session.sh start` first stops
  only the prior owned PIDs, then restarts a clean session.
- If a saved palette set needs to be abandoned, preserve the current YAML and
  restore the intended hash-named pre-save backup before rebuilding.
- Never treat a browser preview, emulator state, `.sav`, `.ss0`, or ROM as a
  release artifact. Only the guarded IPS/readme/checksum ZIP is distributed.
