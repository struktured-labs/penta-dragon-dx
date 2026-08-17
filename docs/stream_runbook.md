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
   python3 scripts/diagnostics/verify_live_palette_session.py \
     rom/working/penta_dragon_dx_FIXED.gb
   ```

3. Start the headed mGBA/editor pair:

   ```bash
   scripts/palette_session.sh start
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
3. Gargoyle/Spider, then all nine boss arenas.
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
python3 scripts/build_v302_title_fix.py

uv run penta-colorize build-patch \
  --original "rom/Penta Dragon (J).gb" \
  --modified rom/working/penta_dragon_dx_FIXED.gb \
  --out rom/penta_dragon_dx.ips

python3 scripts/diagnostics/run_deterministic_suite.py
```

Keep the full-matrix manifest from the suite's `/tmp` output. The committed
receipt is written only after two byte-identical builds and the full release
matrix passes (the gate roster grows with the work; 74 gates as of
2026-08-16).
Only after that proof, record the audience decision:

```bash
python3 scripts/record_palette_approval.py \
  --output /path/to/palette-approval.json \
  --confirm "AUDIENCE APPROVED" \
  --notes "Final colors selected during the Twitch stream"
```

The recorder rebuilds in a temporary directory and refuses approval unless
the saved YAML reproduces the exact release ROM byte-for-byte.

Finally, acquire the shared MiSTer reservation and run the physical checkpoint
sweep documented in `README.md`. The final ROM-free archive can be built only
when the hardware manifest and palette approval both match that same ROM.

## Recovery

- If mGBA or the editor exits, `scripts/palette_session.sh start` first stops
  only the prior owned PIDs, then restarts a clean session.
- If a saved palette set needs to be abandoned, preserve the current YAML and
  restore the intended hash-named pre-save backup before rebuilding.
- Never treat a browser preview, emulator state, `.sav`, `.ss0`, or ROM as a
  release artifact. Only the guarded IPS/readme/checksum ZIP is distributed.
