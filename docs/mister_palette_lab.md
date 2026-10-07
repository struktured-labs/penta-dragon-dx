# Rivalmage palette lab — experimental first version

October 7 update (#19/#39): the bridge also accepts the emulator-qualified
retest ROM `6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`
via `--source PATH`. Its primary rows are unchanged, and its complete normalized
layout is independently pinned. Settled Stage 1/2 ownership checks apply to this
layout and palette-only edits; unsupported contexts retain rejection behavior.
Its browser labels identify OBJ0 as Sara's weapon shots and OBJ3 as enemy bullets
and crows, reflecting the projectile separation fix. Stable API/YAML keys are
retained. This is offline compatibility, not hardware Apply/Resume acceptance;
the default source and running services are unchanged. See
[validation and limits](audit/palette_retest_20261007.md).

Offline compatibility update: the bridge explicitly accepts experimental
late-return build `46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb`
for primary-row editing (#19). All15 rows match the126dd parent, and actual-ROM
tests constrain each edit to its row/checksum and matching active state row.
This does not change the default ROM, qualify live Apply/Resume, or declare the
experimental ROM release-ready. Running services are not automatically updated.

Run on Blackmage:

```sh
python3 scripts/mister_palette_bridge.py
```

Open <http://127.0.0.1:8078>. Rivalmage must already be running the exact
selected source as `Penta-Dragon-DX-<first12 SHA256 digits>.gbc` in GBC
(the original default uses `Penta-Dragon-DX-b93ebc46ed4a.gbc`).
Do not change games manually while
the controller is running. The SSH hostname is fixed to `rivalmage`; this
does not use misterclaw discovery or Redmage.

Choose a primary palette and click **Apply & Resume**. The controller backs
up any existing slot-4 file, saves a fresh checkpoint, patches only the
selected primary ROM palette and global checksum, converts matching active
palette rows in a copy of the checkpoint, uploads a uniquely named candidate,
verifies the uploaded ROM, savestate and MGL launcher hashes, then reloads
GBC and restores slot 4. A hash mismatch prevents reload. It saves again
to check palette readback.
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
- On the exact `46eb95a0…` and `6c4a9654…` layouts (including palette-only edits),
  settled ordinary Stages 1 and 2 have checked fixed-slot ownership maps. Equal primary
  rows remain independently editable there; a coincidentally equal private BG7
  row is not changed. This requires the complete primary palette installation,
  no menu/boss/jet/projectile override, and no pending palette-load phase.
  In Stage 2, BG4 owns both the scenery copy in BG0 and its normal pickup slot;
  an edit updates both. The Stage-1 Dungeon row is inactive there and cannot
  recolor those slots merely by having equal colors. Later stages remain pending.
  This is offline-tested, not yet hardware-qualified or enabled in a running server.
- Elsewhere, equal primary rows in the same BG/OBJ group are refused (#39).
  Undo the edit that made them identical or return to a supported context.
  Older layouts reject ambiguity before checkpointing. These two layouts
  can require a checkpoint to resolve ownership; unresolved aliases still fail
  before upload/reload. Receipts identify which ownership method was used.
  No-op quantized colors and invalid OBJ transparency changes also fail in
  this preflight. Checking whether a unique row is currently active still
  requires a fresh checkpoint and may reject afterward.
  Multiple active copies of one uniquely defined primary row remain supported.
- Supported initial ROMs are exact pins, not arbitrary same-layout files:
  original r536 SHA-256
  `b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`.
  The row-guard `e709869c85ed…`, Sara-atomic `4f5a67b8a9af…`, and experimental
  Ted-menu `4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903`
  and combined star `d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5`
  pins are also supported via `--source PATH`. Later session candidates derive
  only from the controller's palette edits. Unknown initial hashes are rejected.
- The experimental Ted-menu and combined star candidates are1MiB MBC5.
  The star build also routes the five-point pickup through BG5; editing BG5
  therefore changes that pickup as well as its other documented uses.
  Exact-pin support does not promote either build or change the default source.
  Offline tests cover all15
  primary rows, global checksum, unchanged expansion/private overrides, and
  unchanged non-palette savestate bytes. Its hardware Apply/Resume remains
  unverified; support is not deployment or release approval. Default source is
  unchanged. Do not point the editor at it while another ROM is running.
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
