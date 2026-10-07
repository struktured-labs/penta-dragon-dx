# October 7: palette bridge compatibility with the retest build

Related: #19 (current-build rejection), #39 (palette ownership), #57 (projectile
roles). No game code, live server, hardware, save slot, or deployed ROM changed.

Before the fix, constructing Bridge with the merged exact retest ROM raised
`Starting ROM does not match an exact supported pin`. Its SHA-256 is
`6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228`.
All15 primary rows equal the supported46eb predecessor. The Stage2 selector
bytes at bank13:7BAC are unchanged (`200030001800c5d5e5`).

The bridge now explicitly permits this starting pin. Whole-ROM layout identity,
after normalizing only the15 primary rows and global checksum, is
`53e25cf01602fe9a4b9546d61845e1a9d17a581f2b2ad104734d92c280de5327`.
The existing settled Stage1/2 context and complete-palette-installation checks
remain mandatory for fixed-slot ownership. Arbitrary code changes do not gain
that path. Initial palette-modified ROMs remain rejected; palette descendants
are created only within the existing session workflow.

For this layout, OBJ0's label describes Sara's weapon shots and OBJ3's label
describes enemy bullets/crows. Legacy layouts retain their prior descriptions.
The historical API/YAML identifiers are unchanged, and descriptions disclose
them. Labels continue to follow the layout after a palette-only edit.

## Evidence

- Six new actual-ROM tests cover exact/unknown starting identity, all15 edit
  byte scopes/checksum, sequential alias edits in both stages, private BG7
  isolation,20 invalid-context mutations, four code/header mutations, labels,
  and simulated Apply/readback/Undo for both stages. Real device subprocesses
  are forbidden. A hash-checked local test fixture can be supplied with
  `PENTA_TEST_STREAM_ROM`; otherwise the fixture is built from original source.
  Both modes passed:1.32s with the authenticated fixture and64.17s rebuilding
  from original source, with no skips in either current-candidate run.
- Existing bridge suite:15 passed, four historical-ROM tests skipped because
  their optional scratch fixtures are absent from the isolated worktree. They
  are not counted as passes. The new exact-current-ROM tests are not skipped.
- Read-only inspection of retained exact-ROM mGBA states from the qualified
  `inline-rearm-full-suite-03` confirms the complete primary installation and
  all context guards. CRC/title/format/size were checked before copying WRAM,
  HRAM and CRAM into synthetic parser-test containers (not runnable MiSTer
  checkpoints and never deployed):
  - Stage1 hazard state SHA-256:
    `53248f68f2db6b7cf75caa16930f24763bb5a70e12a7eea3626987ca0824ab19`.
    BG0..6 own offsets96..144; OBJ0..7 own160..216.
  - Stage2 state SHA-256:
    `16dc8bda1840a2f9fefb0ebd07905380c72e941c97aac28c7533bd0b71f759fe`.
    BG4 owns96 and128; Dungeon/BG0 is inactive. Other slots retain their owners.

The game's97-gate receipt remains unchanged: this follow-up changes the
standalone palette bridge, its docs and tests, not the bound ROM build/replay
inputs. Revalidation of that receipt does not confer hardware acceptance on
this new bridge code. Live Apply/Resume and later-scene ownership remain open.
