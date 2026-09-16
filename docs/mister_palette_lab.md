# Rivalmage palette lab — experimental first version

Run on Blackmage:

```sh
python3 scripts/mister_palette_bridge.py
```

Open <http://127.0.0.1:8078>. Rivalmage must already be running
`Penta-Dragon-DX-b93ebc46ed4a.gbc` in GBC. Do not change games manually while
the controller is running. The SSH hostname is fixed to `rivalmage`; this
does not use misterclaw discovery or Redmage.

Choose a primary palette and click **Apply & Resume**. The controller backs
up any existing slot-4 file, saves a fresh checkpoint, patches only the
selected primary ROM palette and global checksum, converts matching active
palette rows in a copy of the checkpoint, uploads a uniquely named candidate,
reloads GBC, and restores slot 4. It saves again to check palette readback.
**Undo & Resume** returns to the prior ROM and pre-edit checkpoint, not to
the position reached after the edit. Slot 4 is reserved by this workflow;
slots 1–3 are not written.

The server is loopback-only and single-threaded; POST requests require a
per-process token. An exclusive local lock prevents two controller instances.
Artifacts and old slot files remain under `tmp/mister-palette-session/`.
Remote candidate files are retained for recovery. Release ROMs and the
project palette YAML are never overwritten. No ROM instructions or in-game
hooks are added. Existing battery saves are not migrated into candidate
namespaces; the checkpoint carries cartridge RAM for resumption.

## Current boundaries

- Primary BG0–BG6 and OBJ0–OBJ7 only. BG7, title aliases, hazard-specific,
  boss, story and other override tables are not yet supported.
- A palette must be active and exactly match its primary ROM row. Otherwise
  the operation refuses before uploading/reloading. A scene override may
  subsequently replace the colors; readback catches immediate replacement.
- OBJ transparent color zero cannot change. RGB picks quantize to BGR555.
- Fixed r536 initial ROM SHA-256:
  `b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`.
  Later candidates derive only from the controller's palette edits.
- State conversion recognizes the observed 181040-byte Gameboy state with
  header format `0xB0CA`. Palette registers occupy offsets 96–223. CPU and
  other memory bytes are preserved verbatim in the converted state.
- File hashes and core name are checked, but the active ROM identity is not
  independently exposed by this controller. Manual GBC ROM changes require
  ending the session and returning to the original pinned ROM first.
- Restarting the server begins a new session on the original ROM; in-memory
  Undo history is not reconstructed. Receipts retain recovery filenames via
  the candidate MGL files. A failed operation never implies successful play.

## Hardware evidence

The first reversible BG4 trial saved a native Rivalmage checkpoint, uploaded
a recolored ROM plus palette-adjusted state, reloaded/restored, and captured
a new native checkpoint. BG4 matched the new bytes `ff7f1f7caf190000`.
The original ROM/checkpoint was subsequently restored. Evidence lives under
`tmp/mister-palette-session/edit-20260914-225729-b9763f/` and
`tmp/mister-palette-session/hardware-after-edit/`.

This establishes palette persistence across one hardware reload, not complete
visual/state equivalence or release readiness. The separately reported
Game Over/restart corruption is not fixed by this feature.

Next: visual gameplay confirmation, broader context-aware palette source
maps, export to the existing YAML editor, and optional debounced file edits.

Descriptive browser labels retain the original BG/OBJ identifiers and explain
shared uses based on `palettes/bg_tile_categories.yaml` and the primary rows
in `palettes/penta_palettes_v097.yaml`. Names describe primary gameplay uses,
not every scene override. To restart only the UI after one verified edit,
use `--resume-edit tmp/mister-palette-session/edit-<timestamp>-<id>`; this
preserves that edit and its Undo target without reloading the game. The
controller refuses unsupported/multi-edit recovery rather than guessing.
