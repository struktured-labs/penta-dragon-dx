# Stream Palette Cheat Sheet

One-page notes for a live palette session on blackmage. The game stays running; colors show up in mGBA in about half a second.

## Launch (on blackmage, at the keyboard)

A normal mGBA window is fine for you. From the repo checkout that has current main:

```bash
cd ~/projects/penta-dragon-dx-issues   # or your usual worktree
scripts/palette_session.sh start
```

Then open [http://localhost:8077](http://localhost:8077).

To stop only this session (not other mGBA windows):

```bash
scripts/palette_session.sh stop
```

Need the UI on another machine on the tailnet? Keep the editor on loopback and tunnel in:

```bash
ssh -L 8077:127.0.0.1:8077 blackmage
```

Or start with `PENTA_PALETTE_BIND=100.120.23.124` and open `http://100.120.23.124:8077`. Default bind stays loopback.

## Pick colors

- Background, sprites, bosses, jet forms, and power-up shots each have their own pickers.
- **Stage 1 Rotating Spike** is the weathered-bronze BG7 row (body, rings, connectors, caps, and teeth). It applies only while Stage 1 is up (`FFD0=0`). Leave index 1 as the floor blue and index 3 as the floor shadow so the teeth still blend with the dungeon floor.
- Use the **Stream Scene Deck** to jump to title, story, stages, bosses, and the Catfish / moth / hazards room (spike + item).

## Save, reset, rebuild

- **Save to YAML** writes `palettes/penta_palettes_v097.yaml` (a backup lands under `tmp/palette_session/backups/` only if something actually changed).
- **Reload from YAML** drops unsaved picker edits and restores the file on disk.
- Browser changes are live in the emulator only until you save and rebuild. The official release builder is SHA-pinned, so a saved scheme becomes a real ROM through a source-chain rebuild (the v10 bronze spike row is already baked that way). Don't use the legacy `build_v302_title_fix.py` path for a release ROM.

## Troubleshooting

- Colors don't change: confirm mGBA was started with `scripts/lua/live_palettes.lua`, then check `rom/working/live_palettes_lua.log`.
- Scene button does nothing: the deck caches states per ROM checksum under `tmp/palette_session/`. Starting the session again regenerates them.
- Always use the corrected mGBA library: `LD_LIBRARY_PATH=$PWD/tmp/mgba-cgb-latches-r454/build`. `scripts/palette_session.sh` is the supported launcher; don't start a raw `mgba-qt` window for this.

## MiSTer (rivalmage)

The experimental bridge on port 8078 is loopback-only and talks to rivalmage. Today's JP SHA is pinned for offline use. Don't start or stop hardware from a remote session unless you're at the desk and mean to.
