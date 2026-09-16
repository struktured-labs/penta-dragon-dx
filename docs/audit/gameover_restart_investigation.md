# Post-Game-Over investigation — 2026-09-15

## Latest verification — 2026-09-16 UTC

Issues #7–#10 are emulator-verified; final human/hardware acceptance is separate.
The current
candidate is `tmp/spike-death-trial-05/candidate.gb`, SHA-256
`c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d`.
The completed `tmp/spike-death-trial-05-full-integration-02/manifest.json`
passed all 89 then-registered gates with unchanged ROM, source inputs, and
runtime identities. This is emulator evidence, not hardware approval.

The #9 coverage audit found that counting 60 scene-zero frames captured a
blank transition, not the score selector. Identical blank images must not
pass as evidence. The verifier now rejects blank card images and has an
explicit `--saved-game` route: set the native save-present flag only before
each start, then observe the real score selector and plain Stage 01 splash
over two complete death/restart cycles. The selector is captured after 100
scene-zero frames; screenshots were visually reviewed. Static score labels
are compared, while variable numeric scores are excluded.

Each run now copies the ROM to a fresh runtime directory, without consuming
or modifying adjacent user saves. Fresh-save timing exposed different Sara
animation frames at the settled gameplay checkpoint; gameplay now uses the
existing terrain oracle (exact saved background/colour/priority comparison
plus rendered pixel comparison outside native sprite bounds), as traversal
already did. This does not waive terrain loss or colour corruption.

- `tmp/spike-death-both-cards-04/receipt.json`: exact candidate passes,
  including 482 title-frame comparisons and 102 Game Over frames.
- `tmp/spike-death-both-cards-broken-parent-01/receipt.json`: exact e709
  parent fails on corrupted Game Over capture 1 (negative control).
- `tmp/spike-death-restart-roster-01/manifest.json`: all three selected
  restart gates pass; this is explicitly not the full matrix.
- Focused tests: 28 restart tests and seven terrain-oracle tests pass.
- The authoritative roster now includes `gameover_saved_spike_restart`
  in addition to both previous restart routes: 90 gates total. The fresh
  full run `tmp/spike-death-trial-05-full-integration-03/manifest.json`
  completed at `2026-09-16T01:07:42.929375+00:00`: **90/90 passed**, zero
  failures, full scope, status `emulator-pass`. ROM hashes, source inputs,
  and runtime identities remained intact. Its before/after source
  fingerprint matched the checkout at that run (later publication-tooling
  changes require a new receipt):
  `ac26f638c4fd145b42e56da24f823f0bb2da6868ec0726cc74eb0b46ac2451f1`.
  The isolated tested copy, source candidate, and independent original-ROM
  rebuild all have the exact c693eafb… SHA-256 above. Post-run process
  inspection reports no mGBA processes remaining.

Publication follow-up: `scripts/build_restart_candidate.py` now reconstructs
the same exact ROM through a separate source profile. The first publication
attempt reproduced it twice but was interrupted after an interpreter-alias
verification defect was found (#11); that interrupted run is not qualification.
The interruption exposed a supervisor cleanup defect (#12). Its exact owned
matrix/emulator processes were stopped and the empty slot was verified.
Both defects now have focused negative controls. Run -02 independently
reproduced the repaired ROM twice and verified Python aliases, then was
interrupted to address the full unit sweep's historical-builder failure (#13).
Its exception cleanup stopped the owned matrix, and a subsequent process check
confirmed no mGBA process remained. Neither interrupted run is qualification.

The r315 prototype now reconstructs its exact archived 3af4b5bd… candidate;
the later LCD-off helper variant used by r324/r328/r329 is preserved separately.
The current restart candidate rebuilt from original source remains exact c693…,
so this archival correction does not change the repaired game.

Final publication qualification completed at `2026-09-16T11:28:16.241232+00:00`
under `tmp/restart-publication-suite-20260916-03/`: **90/90 serial gates passed**
and two independent original-cartridge source builds produced exact c693….
The full unit sweep passed **1,195 tests** in 379.692 seconds. The source
fingerprint is
`0cb070141e8e753d0ad9b5a435e32c5266c010d2973d27d45834166397ecead9`;
the completed matrix manifest SHA-256 is
`656edb0c7f9fc35dd5d8d87e6d8ceaac60a3c7f83edd2ceff60279f3bd9ac09a`.
The supervisor revalidated both source constructions, the full nested matrix
and exception ledger, then wrote `docs/release/verification/latest.json`.
The post-run process check found no mGBA processes. This supersedes the
earlier source fingerprints for publication, without claiming a hardware pass.

Death is still accelerated by HP=0 after hazard-area movement; this does
not claim a movement-only collision replay. Rivalmage deployment has not
occurred: its mandatory reservation ID/checker are absent. The original
89-gate receipt predates these harness changes and is historical evidence,
not a current-source qualification receipt.

### Fresh original-cartridge reconstruction

The following source-only build chain completed successfully on 2026-09-16
UTC, without reading a retained candidate as the starting point:

```sh
.venv/bin/python scripts/build_r536_candidate.py --out-dir tmp/gameover-original-source-20260916-01
.venv/bin/python scripts/diagnostics/build_gameover_row_guard.py tmp/gameover-original-source-20260916-01/candidate.gb --output tmp/gameover-original-rowguard-20260916-01
.venv/bin/python scripts/diagnostics/build_spike_death_trial.py tmp/gameover-original-rowguard-20260916-01/candidate.gb --output tmp/gameover-original-fixed-20260916-01
cmp tmp/gameover-original-fixed-20260916-01/candidate.gb tmp/spike-death-trial-05/candidate.gb
```

The r536 builder authenticated the original cartridge, performed the traced
double construction of its r534 parent, and replayed its checked overlays.
The two subsequent builders checked exact parent identities and patch
preimages. Their outputs were respectively b93ebc46…, e709869c…, and
c693eafb…. The final SHA-256 matches the candidate above and `cmp` exited
zero. Receipts are retained in each fresh output directory. This establishes
source reproducibility, not hardware approval or a published release.

## Human reproduction in local mGBA-Qt (supersedes non-reproduction)

The operator reproduced the failure on the deployed e709869c85ed ROM using
ordinary movement into rotating spike bars. The headed process was confirmed
to map the corrected `mgba-cgb-latches-r454` library. Window captures in
`/mnt/data/tmp/penta-spike-demo-20260915/` show:

- frames 8–9: spike contact;
- frames 10–11: Game Over lettering interrupted by white blocks;
- frames 13–14: grayscale returned title with missing letter segments;
- frames 20–24: both Stage 01 cards, with/without scores, similarly damaged;
- frame 38: restarted gameplay with mostly black terrain, gray walls/items,
  and a still-colored Sara.

An attached Lua console saved `tmp/spike-demo-failing.ss0` without resetting
the game. Its BG0 palette is all zero; BG1–7 are grayscale. A 300-frame
read-only replay (`tmp/spike-loaded-debug-01/`) preserves the failure:
D880=$02, cached scene DF0D=$17, FF91=$00; the joypad wrapper runs, but
there are no DF0D, FF91, or BG palette-data writes. FF91 gates the DX
scene prelude. A subsequent movement trace sees bank13:$7D08 disarm FF91
for scene $0A; the exact writer in the human run was not captured.
The first diagnostic FF91:=1 intervention stalled while watching the same
address. The timed-out process was confirmed gone before another launch.
Repeating without that watchpoint (`tmp/spike-loaded-rearm-02/`) restores
scene-cache updates, palette writes and colored terrain. This memory
intervention is causal evidence, **not a passing ROM test or a fix**.

The automated HP-zero test is not equivalent to this demonstrated collision
path. Its passing result must not be used to dismiss this confirmed emulator
failure. No new ROM has been deployed.

## Hazard regression and experimental successor

The new `gameover_spike_restart` integration gate walks through the hazard
area before accelerating death with HP=0. It reproduces the white-block
Game Over on e709 (`tmp/spike-hazard-death-01/receipt.json`). This is not a
movement-only collision test; attempts to complete that route remain
inconclusive. The release roster now has 89 gates; the old 88-gate result
does not cover this regression.

Three contributing failures have been isolated:

1. Hazard bank1 map attributes survive into Game Over. In particular, $0F
   selects graphics bank1 for native text. Native death writes bank0 maps
   but does not retire those bank1 attributes.
2. A zero FF91 disables the scene prelude and leaves the death scene cached
   even after gameplay restarts, preventing palette restoration.
3. The title palette repair incorrectly assumes returned titles have
   FFE4=0. Captured returned-title and stage-card states retain FFE4=1, so
   BG0/BG7 remain grayscale. Scene1 identifies this returned title without
   changing the native flag or removing scene0's epilogue dispatch.

`scripts/diagnostics/build_spike_death_trial.py` builds an exact-parent
experimental successor. It clears both attribute maps and OAM while the
LCD is safely disabled at death entry, rearms the prelude, and diverts only
the original nonzero-FFE4 branch through a physical-scene discriminator.
Scene1 re-enters the title palette repair; scene0 retains its original
epilogue. The complete cold-title instruction stream and timing are unchanged.
The trial's immutable artifact is `tmp/spike-death-trial-04/candidate.gb`,
SHA-256
`c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d`.

Two hazard-area death/restart cycles pass, including 482 returned-title
frame comparisons, 102 Game Over frames, Stage01 card colors, and restarted
terrain (`tmp/spike-death-trial-test-05/receipt.json`). The independent
three-checkpoint traversal route also passes two cycles
(`tmp/spike-death-trial-traverse-01/receipt.json`). The stage-card assertion
rejects the preceding partial trial (`tmp/spike-death-trial-test-03/`).
There are 24 passing targeted oracle unit tests.
The predecessor passed the separate title visual-receipt verifier for the
cold/returned footer, banner and 240 demo-miniboss samples with zero palette
mismatches (`tmp/spike-death-trial-title-01/receipt.json`). Trial 4 also
passes the full cold-title showcase in
`tmp/spike-death-trial-04-title-showcase.report`: all title scenes are sampled,
with zero unsafe attributes and zero bad/blank CRAM samples. The repaired Game
Over, stage card and restarted gameplay captures were visually inspected on
the predecessor and must be repeated on Trial 4.

This is **not release-qualified**: broader title/story/boss timing, the
bank13-only death hook and retired-code-space ownership need qualification.
No full matrix or new hardware pass has been completed, and no deployment
has been changed. The human failing savestate is preserved for investigation.

## Hardware rejection after deployment

The user tested the deployed e709869c85ed candidate on Rivalmage's GBC core
and reports that Game Over is still corrupted and the returned title lacks
colors, while gameplay after restart is intact. This supersedes any readiness
inference from the 88/88 emulator pass. The fix is incomplete on hardware.
Read-only checks after this report confirm GBC and the deployed file's full
SHA-256 e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b.
That file hash is not an independent measurement of the core's loaded bytes.
Do not promote this candidate as stream-ready. Next investigation must capture
the failing transitions and test hardware-sensitive palette publication timing.

## New frame-sequence regression

The `gameover_restart` integration gate now enables `--sequence` alongside
`--traverse`. It checks 482 returned-title frame pairs (ages 60–300 across
two restarts) against the corresponding cold-title logo/footer regions and
102 native Game Over frames (ages 10–60 across two deaths) against the
canonical RGB hash. Missing captures fail closed. Five oracle unit tests
include transient corruption followed by recovery and missing-frame failures.

`tmp/gameover-transition-sequence-02/receipt.json` passed on e709869c85ed
using the corrected CGB-latch mGBA-Qt runtime. This does **not** reproduce
the latest hardware rejection. The optional `--natural-damage` experiment
in `tmp/gameover-natural-sequence-01/receipt.json` failed to reach death
within 24,000 frames; it is not a successful regression or a ROM failure.
It remains diagnostic-only, not enabled in the release matrix.

Negative control: `tmp/gameover-sequence-baseline-negative-02/receipt.json`
rejects the old b93ebc46ed4a ROM. Independently running the new sequence
oracle against those actual emulator captures rejects returned-title frame
60 (`sequence-title-0-0060.png` versus `sequence-title-1-0060.png`).

These verifier changes invalidate the old suite source fingerprint; the
historical 88/88 receipt is not current-tree qualification.

## Historical pre-deployment result

At the earlier source revision, the row-writer guard passed the **88/88 emulator matrix**, including
two complete Game Over/title/restart cycles with three terrain checkpoints
each. Fresh manifest: `tmp/gameover-row-guard-full-integration-qualified-01/manifest.json`.
ROM, source, and emulator runtime identities remained intact; the read-only
full-manifest verifier passed. Subsequent deployment was rejected by the
user as described above; this result does not establish hardware readiness.

The earlier 69-pass/4-fail/15-blocked result below used the wrong libmgba.
See [the runtime investigation](ted_runtime_regression_20260915.md) for the
corrected-runtime full run, sandbox/socket resume, and baseline negative
control. Under the corrected runtime the old ROM still fails returned-title
rendering, whereas the exact row-guard candidate passes.

Exact baseline SHA-256:
`b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`.

The baseline completes two native Game Over → title → new-game cycles,
but fails the returned-title footer image comparison. Its Game Over captures
match the existing canonical image. Its restarted Stage-1 image region,
character data and packed room data match their pre-death checkpoints.
This does not reproduce or dismiss the reported missing-level hardware bug.

The optional probe write watchpoint identifies bank20:$4331 overwriting
title attribute $9A45 with $0F after bank25's title painter wrote $06.
That selects hazard graphics bank1 for a title version glyph. Cold title has
FFB7=0/FFC1=0; returned title retains FFB7=2/FFC1=1.

## Negative controls

- `tmp/gameover-baseline-recheck-01`: fresh baseline still fails footer only;
  route completes `ok 2 2 2`.
- `tmp/gameover-title-guard-test-01` through `-03`: writer-level scene guards
  fail to settle on returned title. Restoring VBK and explicitly selecting
  WRAM bank1 for the predicate did not resolve that failure. The underlying
  reason is not established; do not treat either as the proven cause.
- `tmp/gameover-title-guard-test-04`: clearing FFC1 at title paint completes
  both cycles, but the original footer corruption remains.
- `tmp/gameover-title-guard-test-05`: clearing both FFC1 and FFB7 fails to
  settle on title. The retained builder reproduces this rejected experiment.

## Corrected observation and passing fix

The above title-settling failures used a flawed probe: `emu:read8(D880)`
observes whichever SVBK bank the compiler currently owns, not necessarily
native scene state in bank1. The probe now observes physical WRAM and writes
the HP stimulus to physical bank1 too, without changing the game's SVBK.

- `tmp/gameover-physical-scene-baseline-01`: baseline still fails the footer.
- `tmp/gameover-physical-scene-test-05`: both full cycles pass, including
  canonical Game Over images, returned-title footer, and restarted level data.
- Passing candidate SHA-256:
  `0d7793a840af545a95837b699e9be5f9d433e45d6bea9a8a99c91dee26024cd2`.

The fix restores cold-title FFC1=0 and FFB7=0 inside the existing LCD-off,
scene1-only title painter. It changes only bank25 title code and the global
checksum. Hazard code, palette tables and gameplay timing code are untouched.
The older writer-level trials have not been requalified and are not selected.
The title reset still requires wider transition/feature regression checks.

## Full-suite preservation result and narrower trial

`tmp/gameover-fixed-full-integration-01` completed all 88 gate outcomes: 48
passed, 40 failed or blocked. Many new failures are exact-profile rejections
(menu LUT, bank25 protocol identity, publisher and arena observer selection).
However, `title_idle_reel` also missed the Gargoyle demo entirely. The generic
title-painter reset is therefore not accepted as feature-preserving.

Further native tracing (`tmp/gameover-native-return-stack-01`) shows Game Over
returns through bank1:$4ACB: CALL $007E; CALL $16FD; JP $015F. The scene write
at fixed:$0087 is called from $4ACE; fixed:$39D3 later publishes scene1.

`build_gameover_exit_reset_trial.py` moves the reset to that native exit using
a bank25 bridge, leaving general title code untouched. Candidate
`8dd292fbfec8e108efc87a25ec4a141c256907baade0247520989d77bcef0178`
completes both routes but fails rendering: the second Game Over is red with
stale sprites. Evidence is in `tmp/gameover-exit-reset-test-01`. Do not deploy.
Resetting the flags before native title initialization is not equivalent to
resetting them in the later title painter. Next work must preserve that timing
while limiting the retirement to actual Game Over returns, and must inspect
the mapper/stack ABI of any exit trampoline.

Exact-hash observer recognition for the first trial was added to existing
lists but is not release approval. Bank25 ownership support is still pending;
no failed runtime assertion was removed or waived.

## Selected row-writer guard after probe correction

Re-testing original row trial02 with physical-WRAM observations overturns its
earlier false timeout rejection:

- `tmp/gameover-row-guard-physical-02`: two full cycles PASS, including both
  Game Over images, title/footer, restarted level pixels and room/CHR data.
- `tmp/gameover-row-guard-attract-02.summary.json`: PASS; scene timings match
  baseline exactly (Stage1 f6401, Gargoyle f8612, returned title f8866).
  Gargoyle has 24 samples/338 sprites and zero palette6 mismatches.
- `tmp/gameover-row-guard-menu-01`: two menu runs PASS, all pages canonical.
- Source builder: `scripts/diagnostics/build_gameover_row_guard.py`.
- Fresh rebuilt candidate: `tmp/gameover-row-guard-candidate/candidate.gb`,
  SHA `e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b`.

This guard leaves native state flags and all title/attract code untouched.
Both semantic row entries reject scene1 through their original VBK0 cleanup
and mapper bridge. The accepted branch executes the displaced original code.
Exact-profile lists now recognize this candidate instead of the rejected
title-reset candidate. Inherited static checks authenticate the complete
reversible delta; runtime tests still execute the real patched ROM.

The legacy standalone spike static checker fails identically on baseline and
successor. This is not used as passing evidence. The dedicated profile's
publisher, semantic-row identity and bank20 source reconstruction checks pass.

The regression probe now retains full native savestates for banked VRAM
inspection, with an opt-in write watchpoint. Unit negative controls cover
the version-footer pixel corruption as well as missing levels/lost colour.
Unit passes are not evidence that the ROM defect is fixed.

## Completed full-matrix comparison and supplemental death coverage

`tmp/gameover-row-guard-full-integration-01/manifest.json` records all 88
outcomes for the exact selected candidate: 69 passed, 4 failed, 15 blocked.
The baseline matrix at `tmp/scene-bg5-integration-20260915-092230/matrix`
had 68 passed, 5 failed, 15 blocked. Comparing gate names and statuses shows
only one change: `gameover_restart` changes from failed to passed. Every
previously passing gate remains passing, including speed/movement, hazard
and menu regressions, stage galleries, and title/attract coverage.

The four remaining failures (`boss_arenas`, `ted_entry`, `death_gameover`,
`live_palette_deck`) encounter the same preexisting Ted state-generation
failure. The failed screenshot is genuinely mostly white with a small sprite,
not just a valid image rejected by a file-size threshold. No assertion was
weakened and the full-matrix result remains failed.

The death verifier itself exercises five stock death-path cases, none of
which is Ted. To distinguish its generation dependency from rendering:

- `tmp/gameover-row-guard-death-selected-01`: Shalamar and Cameo PASS using
  the exact-candidate states already generated by the matrix.
- `tmp/gameover-row-guard-death-extra-states-01`: freshly generated exact-ROM
  Troop, Faze and Penta Dragon states, all PASS.
- `tmp/gameover-row-guard-death-extra-01`: those three death cases PASS.

Together these supplemental runs cover all five cases without inventory mode
or relaxed checks: complete native art publication, coherent palettes,
meaningful coloured artwork, white fade and canonical GAME OVER rendering.
They do not retroactively turn the failed full-matrix gate green.

The reproduced returned-title corruption is fixed locally. The user's
missing-level symptom was not reproduced by the local initial-room route;
hardware confirmation remains required before claiming that symptom fixed
or declaring the candidate stream-ready. The candidate has not been deployed.

## Extended movement diagnostic (not passing evidence)

The restart verifier now has an optional `--traverse` diagnostic that adds
600 frames of up/fire input per run and three extra checkpoint comparisons.
The default two-cycle route remains unchanged. Its first run is retained at
`tmp/gameover-row-guard-traverse-01` and is FAILED: mGBA exited with signal 11
after writing `ok 2 2 2`. A subsequent read-only process check found no mGBA
processes running. This exit is not waived.

The captures show coloured level geometry after both restarts, but all three
checkpoints remain in room01. End camera Y is04 before death and08 after
both restarts, so frame-age-aligned screenshots are not equivalent viewports.
These observations neither prove traversal into another room nor satisfy the
strict context/image comparisons. Future route coverage needs room/camera
alignment and actual progression, not relaxed image checks. The full matrix
above predates these diagnostic-only probe/verifier changes.

The second traversal revision stops at physical game camera coordinates
0668,05AC,03A4 in room01, releases input and settles for16 frames at each.
`tmp/gameover-row-guard-traverse-02` and the unpatched control
`tmp/gameover-baseline-traverse-02` both complete two cycles with clean
emulator exits. All six post-restart checkpoints in each ROM match their
own cold-run context, CHR and room data exactly. This extends coverage down
the room to the existing north-wall checkpoint, not into another room.

The candidate still fails the strict screenshot comparison because moving
sprites differ. The unpatched control also has moving-sprite differences at
five of six checkpoints, in addition to its reproducible title corruption.
These observations justify investigating a sprite-aware terrain oracle, not
waiving the image check. Both extended receipts remain failed; no new ROM
changes or deployment were made during this diagnostic revision.

## Palette-editor compatibility

The hardware palette-session receipt
`tmp/mister-palette-session/edit-20260915-075134-6ffea6/receipt.json`
identifies the old base b93ebc46... and its BG5-only edit ec97c39c.... It is
not evidence that the Game Over fix has run on hardware, nor does it identify
the state at the original missing-level incident.

The editor previously hard-coded only the old base. It now accepts an explicit
`--source` selecting either exact supported hash, including e709869c.... The
default remains unchanged. Each base uses its own hash-qualified hardware
stem; resumed edit receipts must name that selected base, preventing an old
palette session from silently replacing the fixed ROM. This does not deploy
the ROM or update a running server.

Eight palette-bridge unit tests pass. A local byte-level check on the exact
fixed candidate exercised all15 editable rows: only the chosen palette and
global checksum changed, every row-guard patch stayed intact, and a matching
active state palette row was updated. No hardware calls were made. Hardware
save/reload/resume verification with the successor remains outstanding.

## Hardware availability check

A read-only SSH check on Rivalmage reports hostname `rivalmage` and active
core `SNES`, not GBC. No input, reload or deployment was performed. The two
relevant existing GBC slot4 files exactly match the local palette-session
checkpoint (03258597...) and confirmation (b08ea10f...) already inspected;
they are not new missing-level failure captures. Hardware verification now
requires the user's go-ahead to interrupt SNES and switch back to GBC, or a
recording/save state from the actual failure. The prior general offer of
MiSTer access is not treated as permission to interrupt this changed session.

## Sprite-aware extended regression

`restart_terrain.py` reads the documented mGBA v3 state layout, verifies PNG
chunk CRCs and reconstructs every background pixel's15-bit colour and priority
within the existing gameplay ROI from tilemap, attributes, both graphics
banks, flips, signed tile addressing and CRAM. It compares terrain even under
sprites. Native screenshots are also compared outside the union of both
states' OAM sprite rectangles, with at least half the ROI required unmasked.
LCD-off and overlapping-window checkpoints fail closed. This is not a test
of sprite timing equivalence or scanline rendering hazards.

Seven negative/control tests cover missing graphics, lost palettes, wrong
graphics bank, priority changes, sprite-only movement, LCD disable and window
overlap. All15 existing restart tests still pass. A fresh extended emulator
run `tmp/gameover-row-guard-traverse-03` passes both complete restart cycles
and all six room/camera-matched traversal checkpoints. Earlier failed receipts
remain unchanged. Later receipts also bind the terrain oracle's source hash.
