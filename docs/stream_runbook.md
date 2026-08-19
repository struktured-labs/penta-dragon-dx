# Penta Dragon DX livestream palette runbook

This is the release-safe path for the Twitch color-picking stream. It uses the
exact production ROM in mGBA, curated ROM-matched states, and the browser
editor. Live tuning is external tooling: the browser/Lua bridge may load
curated emulator states and write mGBA's CGB palette RAM without adding those
controls to the ROM. It does not enable the retired SELECT+START teleport.

## Before going live

1. Confirm that no old owned session is running:

   ```bash
   scripts/palette_session.sh status
   ```

2. Run the stream workflow gate against the candidate:

   ```bash
   STREAM_ROM="tmp/menu-icons-candidate-r5/penta-dragon-dx-menu-icons-r5.gb"
   python3 scripts/diagnostics/verify_live_palette_session.py \
     "$STREAM_ROM"
   ```

   Prove that the current YAML also rebuilds that exact expanded candidate,
   without creating an approval record:

   ```bash
   STREAM_ROM="tmp/menu-icons-candidate-r5/penta-dragon-dx-menu-icons-r5.gb"
   python3 scripts/record_palette_approval.py \
     --rom "$STREAM_ROM" \
     --expanded-ted \
     --menu-icon-colors \
     --verify-only
   ```

3. Start the headed mGBA/editor pair:

   ```bash
   scripts/palette_session.sh start \
     tmp/menu-icons-candidate-r5/penta-dragon-dx-menu-icons-r5.gb
   ```

   The launcher uses the required XWayland/NVIDIA `xcb` path, verifies that
   both owned processes survive startup, opens `http://localhost:8077`, and
   refreshes all ROM-matched stage, boss, and story states when needed.

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

Edits reach mGBA in about half a second. Boss bodies reuse global BG palette
indices, so changing one boss can affect another that shares that BG row.
Revisit every affected boss button before locking a shared color. Story
artwork colors only the top artwork region; separator, border, and dialogue
must remain neutral.

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
  --expanded-ted \
  --menu-icon-colors \
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
STREAM_ROM="$STREAM_SUITE/build/candidate-a.gb"

uv run penta-colorize build-patch \
  --original "rom/Penta Dragon (J).gb" \
  --modified "$STREAM_ROM" \
  --out "$STREAM_SUITE/Penta_Dragon_DX_v3.01.ips"
```

Only after that proof, record the audience decision:

```bash
STREAM_SUITE="tmp/palette-stream-final"
STREAM_ROM="$STREAM_SUITE/build/candidate-a.gb"

python3 scripts/record_palette_approval.py \
  --rom "$STREAM_ROM" \
  --expanded-ted \
  --menu-icon-colors \
  --output "$STREAM_SUITE/palette-approval.json" \
  --confirm "AUDIENCE APPROVED" \
  --notes "Final colors selected during the Twitch stream"
```

The recorder independently rebuilds the same expanded profile in repo-local
temporary storage and refuses approval unless the saved YAML reproduces the
exact suite ROM byte-for-byte.

Finally, acquire the shared MiSTer reservation and run the physical checkpoint
sweep documented in `README.md`. The final ROM-free archive can be built only
when the hardware manifest, emulator matrix, IPS, and palette approval all
match that same ROM. `scripts/build_release_bundle.py` derives the expanded
gate roster from the authoritative matrix definition and rejects a 256 KiB or
menu-less ROM.

## Recovery

- If mGBA or the editor exits, `scripts/palette_session.sh start` first stops
  only the prior owned PIDs, then restarts a clean session.
- If a saved palette set needs to be abandoned, preserve the current YAML and
  restore the intended hash-named pre-save backup before rebuilding.
- Never treat a browser preview, emulator state, `.sav`, `.ss0`, or ROM as a
  release artifact. Only the guarded IPS/readme/checksum ZIP is distributed.
