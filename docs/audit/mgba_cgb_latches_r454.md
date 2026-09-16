# r454 emulator-instrument correction (not a ROM revision)

The r453 ROM remains SHA-256
`15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b`.
Its Ted publisher writes `$98/$9C` to `$FF73` before programming GDMA.
The installed mGBA library drops that write, so the transfer goes to `$8000`
and the arena tilemaps remain empty. This is not a reason to remove the
blank-arena check or to change the release ROM.

## Independent contract and reproduction

[Pan Docs](https://github.com/gbdev/pandocs/blob/master/src/CGB_Registers.md#undocumented-registers)
specifies byte-wide read/write `$FF72–$FF74` in CGB mode. The local MiSTer
Game Boy core also implements these registers. mGBA source revision
`98ab243601e814895132302864c7d1b0fe1fef57` names these registers but lacks
their write cases and the `$FF74` read case.

`scripts/diagnostics/mgba_cgb_latches.patch` supplies only those four cases.
No timing, raster, ROM, or gate thresholds are changed by the patch.
`scripts/diagnostics/check_mgba_cgb_latches.c` directly checks all 256 byte
values in each register plus rejection of writes on DMG. It does not run a
ROM, CPU, or GUI. Installed library: 765/771 failures. Corrected library:
0/771 failures.

The isolated build is under `tmp/mgba-cgb-latches-r454/`, cloned locally from
`/home/struktured/projects/mgba`, at the revision above with the checked patch.
Build configuration: Release, BUILD_SHARED=ON, BUILD_STATIC=OFF,
BUILD_QT=OFF, BUILD_SDL=OFF, USE_LUA=ON, BUILD_TEST=ON; `cmake --build ... -j 8`.
System installations have not been overwritten.

Recorded hashes:

- Installed library: `df25d1ecfdd1bb3acab3be96e0c2c00848c475c51ecfb4354828fda334e355e4`
- Corrected library: `20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`
- Patch: `4215c63f228d66f253c5aa955823fa5735c2ac056aa581d7c418e77d018f8508`
- Patched io.c: `51c52aad1df84d4f42d2d421d9f89adea56c02589de1d011a0548afd259c44a3`

To use the isolated library, set `LD_LIBRARY_PATH` to the absolute
`tmp/mgba-cgb-latches-r454/build` path on the **checked-in verifier** command.
Do not invoke an emulator directly or override its single-flight guard.
The release runner now fingerprints both emulator executables and their
resolved shared libraries before and after a batch; a changed runtime also
invalidates resume. Old emulator results are not interchangeable with these.

## Observed result, not full release approval

- `tmp/r453-ted-entry-current19`: old library, `$FF73=00`, blank arena.
- `tmp/r453-ted-entry-current21`: corrected library, `$FF73=9C`, rendered Ted,
  settle frame 282 (existing maximum 315), same ROM bytes.
- `tmp/r453-corrected-emulator-current22/manifest.json`: Ted entry, stock Ted
  entry and cadence pass. Static integration still rejects five old-layout
  expectations; all-boss generation reaches a separate final-boss fixture
  timeout. This batch is not a release pass.

A complete matrix rerun under the corrected runtime remains required.
