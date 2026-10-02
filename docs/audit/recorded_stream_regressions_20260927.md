# Recorded playthrough regressions — 2026-09-27

Status: investigation in progress. Issue #23 has emulator-verified geometry and
BG0 source fixes; full scene palettes/return behavior and other reports remain open.
Objective: address all known bugs, not only the secret-area failure cluster.

## Menu inventory/health fixture uses physical bank1 (#41)

Changed `probe_menu_icon_palettes.lua` inventory initialization, cursor reset
and health assistance from CPU-mapped writes to physical WRAM bank1. Each write
records selected SVBK without changing it. Original probe retained at
`tmp/menu-icons-before-physical-assistance-01/`, SHA
6b06e71453af9b4130bfed6d31019ea18f55b321f3b58f087109655cd8968110.
New probe SHA2a4a95921e311e0f21f8295f61e5ea36b6c2fbabfd87e22064e8fd2e94c37e9e.

Actual Lua helper tests exercise all eight bank selections, health/save bytes
and every DCBD..DCDD inventory/cursor address; scratch banks2..7 remain intact.
The previous mapped-write negative control corrupts bank3. Ten tests pass.
Fresh guarded1510-frame reported4f5a menu replay passes all five page palette
checks:1251 assistance writes, all selected SVBK1. A separate serial replay of
the archived original probe matches every original report field and all five
PNG files byte-for-byte. Thus this route does not demonstrate a visible effect
from the old unsafe writes; the all-bank fixture tests cover that hazard.
Protect-page screenshot reviewed. Neither run changes the ROM or hardware.
Source/core/artifact bindings and counts are retained in
`tmp/menu-icons-physical-assistance-01/assistance-verification.json`; mapped
control in `tmp/menu-icons-mapped-control-01/`. Process check confirms no mGBA
remains. Wider mapped-write callers and #41 remain open.

## Fixed-fade relocation: reject occupied attract service (#45)

Read-only allocation review on authenticated ec8 parent rules out $10E7 as
replacement storage for the experimental $00CF..$00E0 routing. Although a
historical constant comment calls this a retired attract-delay service, current
`build_stage1_demo_attr_trampoline()` emits `3E01B70605C900`: A=1/NZ and B=5,
then RET. The actual parent contains those bytes. Fixed caller $3489 tests
DCFD, and its zero arm reaches $3494 `JP $10E7`. The source identifies this
as required dirty publication for moving semantic cells during attract play.
It is occupied code, not seven free bytes or an eighteen-byte cave.

Added an exact-parent allocation regression binding the emitted service and
caller predicate. This is static ownership evidence, not a fresh attract replay
or a solution to #45's placement/timing blockers. No candidate bytes changed.
The candidate's fixed bank also has no contiguous all-zero or all-FF run of
18 bytes; that scan alone is not a general allocation proof. Do not relocate
the fade guard based on stale comments or unobserved execution alone.

## Recorded menu context and corrected form identification for Sara tear (#6)

Rehashed the player's 7716.955-second recording: SHA
459facd00aed66b615cf93bb1873f20a2f203dfe3e7186786c63927b7b8da664.
Reviewed two diagnostic contact sheets under
`/mnt/data/tmp/penta-miniboss-recording-review-20260928-01/`:
`11m00-12m00.png` (one sample/3seconds, SHA
fedfdd768d3acfa1571a740a94349e9b80b90ee9772dce4f6a9a19da01b1a34b)
and `10m50-10m52.png` (10samples/second, SHA
8d73443da4d776cb33e0e1fd50f343d9472ab2e9582092d967d052d902f9a57b).
Both crop the recorded gameplay area1200x1080 at0,0 and scale240x216 for
review; these are lossy diagnostic overviews, not native-pixel acceptance.

The initial visual identification as a winged/alternate form was incorrect.
Compared the full gameplay crop at11m06 with authenticated exact46eb
`late-return-sara-geometry-fire-01/gameplay.frame0065.png`: its trace has FFBE=00
and tiles21,20,23,22 with horizontal-flip attributes22, showing the same
rear-facing Witch silhouette. Image SHA
e9c1f3bc0b871298de346c1ccb8fb599d480508de5d97a1b58fd2d039dbde2ac and complete
trace revalidated against the retained receipt. This is visual form recognition,
not an exact cross-capture pixel match or proof of the recording's RAM state.

Reviewed all60 successive recording frames from11m05–11m06 in a player crop
(150x150 at525,465, scaled100x100). Contact sheet
`11m05-sara-60frames.png`, SHA
c9fd78475087e55eee7dc2550526e667b598836bbf4bd1eb21b5ea940d34757e,
shows no obvious missing quadrant or split silhouette in that one-second
window; this does not disprove a subtler tear or a failure elsewhere. Firing
and repeated menus remain observed context, but an alternate-form reproduction
is not justified by these images. The specific torn frame still needs locating.
No ROM change, emulator launch or hardware access during this investigation.

## Palette Apply terminal failure receipts (#48)

Verified the prior exception handler retained an uploaded/pending receipt after
a terminal restore failure. Apply now records failure phase (load, confirmation
checkpoint, or palette readback), exception type and message, while preserving
Undo history and re-raising the original error. A secondary receipt-write error
is attached to the original exception rather than hiding it.

Offline fake-device transactions exercise all three failures in both Stage1 and
Stage2, including successful Undo afterward. Success and pre-reload rejection
controls remain. Combined palette suite: 73 tests plus 72 subtests pass in
4.53 seconds. An in-memory negative control restoring the old exception handler
fails both Stage1/Stage2 readback receipt assertions (2 expected failures).
No emulator, hardware, live editor or ROM changes. This fixes durable editor
failure reporting, not the recorded gameplay corruption; hardware qualification
and the wider game regression work remain open.

Follow-up: injected a disk-full error specifically while writing the terminal
failure receipt. The original load exception survives by object identity with
the disk error attached as a note; history remains available and Undo restores
the original identity. The on-disk receipt correctly remains pending in this
unwritable-storage case, not falsely claimed updated. Combined suite now passes
74 tests plus72 subtests (4.37s). This completes #48's offline reporting scope;
it does not close the separate gameplay or hardware issues.

## Stage-2 palette ownership and shared scenery copy (#39)

Extended the exact46eb-layout editor to settled ordinary Stage2 (D880/FFB7=03,
FFBA=1; same active/no-boss/menu/jet/projectile-override and completed-phase
requirements). Bank13:7BAC contains20, selecting primary $6820/BG4 for BG0.
BG4 therefore owns state offsets96 and128; primary Dungeon owns no active slot.
The entire expected primary installation is checked before ownership is used.
Other scenes still use the previous conservative ambiguity handling.

Tests cover BG4→BG1 identical colors followed by a distinct BG4 edit: both
scenery/pickup copies change, BG1 remains unchanged. Inactive Dungeon cannot
steal equal BG4 rows. Ten context mutations reject ambiguous edits. The retained
Stage2 entry state SHA34682d1ae62dfa598d81c0036bf9d7383ae4cec60ccaf6769a17463bc40aa2e2
is authenticated against its receipt and exact ROM CRC; its actual memory/CRAM
confirms the mapping after translation into a synthetic MiSTer test container.
No synthetic checkpoint is deployed or claimed hardware-compatible.

Full fake-device Apply/Resume/Undo scenarios now run in both stages, including
scene changes, damaged launcher uploads and palette-readback failures. Combined
palette suite:69 tests plus72 subtests pass. No ROM code changes, emulator
launches, live editor restart, hardware access or deployment. Wider scene maps
and actual device qualification remain open.

## Owned-palette Apply/Resume/Undo transaction coverage (#39)

`tests/test_palette_owned_transactions.py` now runs the actual checkpoint,
Apply, upload-hash verification, load, readback and Undo methods against an
in-memory fake device. Real subprocess/device access is forbidden. It models
stable savestate reads with incrementing save headers and exact per-ROM slot4
files, rather than replacing checkpoint/load with unconditional success.

Two Stage1 BG0 edits first alias BG1 and then separate BG0 again; BG1 remains
unchanged. Two Undos restore the previous aliased state and original palettes.
The second-edit variants enter an unsupported boss context, truncate the MGL
upload, or return an incorrect palette after restore. Unsupported context and
bad upload perform no second reload and preserve prior history. Failed readback
retains the failure receipt and both Undo entries for recovery. Receipts identify
fixed-slot ownership. All4 transaction scenarios pass; no device or live editor
was contacted. This is workflow simulation, not hardware qualification.

## Stage-1 palette editor fixed-slot ownership (#39)

Implemented scene-aware ownership for ordinary settled Stage1 on exact46eb and
its palette-only descendants. Authentication normalizes only the15 primary rows
and global checksum, then requires full-ROM layout hash
`3521f83aaf36fdf9a5f82fdefd603e7b289fa9a58fa46447c17d441209cf83c2`.
State requires physical D880=02, DF4C=0, canonical FFB7=02, FFBA=0, FFC1=1,
FFBF/FFD0/FFE4/FFC0=0, and all15 active primary rows equal their ROM sources.
That resolves ownership by slot, not row-byte equality. BG7 remains private.

All15 sequential alias/edit tests pass; each second edit leaves the equal peer
and all non-target state bytes unchanged. The previous content-matching control
recolors an equal private BG7 row, while the fixed-slot path preserves it.
Nonpalette code mutations and10 scene/transition/override mutations reject the
new ownership path; unresolved aliases still refuse before upload/reload.
48 tests plus72 subtests pass. Initial source allowlist/default is unchanged.
Receipts now disclose the selected ownership method.

Layout was read from local Gameboy_MiSTer commit
`a8136879695ed0b159f71d64f452cf8a0811c1fc`, gb_savestates.vhd SHA
`1c0f7782413defbc5a0cf4434a906cdf78dc73a318fb7f79057bdc9cc0ff04bc`,
gb.v SHA `76004fb44b704ee3f36c50bd5f3c2fccdcda82599974c8bc9aa266508da39909`:
WRAM begins520, HRAM49832; ordinary gameplay primary sources are fixed slot
rows in the pinned ROM palette loader. Retained native46eb secret-return frames
4800/5000/6000 have the complete expected layout. Tests authenticate the full
native-state stream and translate its memory/CRAM into a **synthetic** MiSTer
container for parser/edit checks, not a bootable or hardware-tested checkpoint.
The retained Gargoyle route has no eligible frames, correctly excluding bosses.

No live editor restart, MiSTer access or deployment. Other scene ownership and
device Apply/Resume qualification remain open; do not close #39 globally.

## Sara walking position-coherence coverage (#6)

The pose checker rejected mixed tile generations but accepted four correct
tiles with a quadrant shifted one pixel horizontally or vertically. Both
deliberate mutations returned PASS before correction. Added an independent
2x2 slot-origin check to `verify_sara_pose.py` and negative controls; existing
mixed-pose, absent-frame, missing-pixel and frozen-animation checks remain.
This is a checker correction, not a claim to reproduce the player's new tear.

Fresh exact46eb rapid-turn/fire720 `late-return-sara-geometry-fire-01` passes:
716 walking observations,4 absent,8 pose permutations,131655 opaque pixels,
no split geometry or pixel differences. All720 native PNGs and the complete
gameplay TSV match the earlier same-ROM/probe replay byte-for-byte. Frame360
visually inspected;16 unit tests plus5 subtests pass. Runtime/probe/ROM/source
identities are in the new receipt. Replay/evaluation wall time3.34 seconds;
no emulator remains after completion.

Read-only examination of the retained2400-frame Gargoyle streams also finds
no split fully visible walking geometry: reported4f5a1904 coherent/471 inactive/
25 not-fully-visible; current46eb1798/577/25 respectively. Thus this check still
does not distinguish the reported hardware tear. Dragon/nonwalking forms,
scanline ownership and the exact recorded failure remain unresolved. No ROM or
hardware change and no closure of #6.

## Restart saved-game fixture physical-bank safety (#41)

Changed the restart probe's DCFD save-present fixture from mapped CPU writes to
physical bank1 writes; the existing physical HP-zero stimulus now uses the same
counted helper. No ROM change. Actual Lua helper tests exercise all eight SVBK
selections and retain the previous mapped-write scratch-corruption control.
The driver records per-bank assistance counts and archives its probe/verifier
sources with new runs. Earlier sources were preserved in
`tmp/restart-source-before-physical-save-01`; historical receipts remain bound
to those exact sources rather than the modified files.

Fresh exact46eb `late-return-physical-save-restart-01` completes4114 frames,
two accelerated deaths/restarts, both stage-card variants,482 title-frame pairs
and102 Game Over frames. All122 assistance writes (120 save flag,2 health)
occurred with masked SVBK1. Therefore this run does not reproduce an actual
wrong-bank setup write or demonstrate a visible improvement. Every retained PNG
matches `late-return-gameover-restart-01` byte-for-byte. The second returned
stage-selector capture was visually inspected. Focused suite:41 tests and2
subtests pass. Process check finds no remaining emulator; hardware untouched.
Other legacy assistance consumers still need review; #41 remains open.

## Natural-damage Game Over color and restart comparison (#18)

Fresh guarded `late-return-natural-restart-01` on exact46eb completes two
movement-driven deaths and cold-title/new-game returns in6812 frames. No HP
writes, save-present fixture, scene repair or palette writes; ordinary B pulses
dismiss the native low-health inventory. Route uses1600 Up frames then Up/Down
oscillation. It reaches scene0B before death: **not** an isolated rotating-spike
reproduction. Game Over entries occur at2761 and5774. All482 returned-title
frame pairs,102 complete Game Over images and restarted terrain checks pass.

Fresh same-protocol reported4f5a `reported-natural-restart-01` completes6774
frames and passes the legacy restart oracle too. That oracle accepts either
reviewed gray or purple palette, so its green verdict alone does not prove #18
fixed. The requirement-specific comparison checks every102 Game Over images:
current output must preserve all original pixels except the reviewed gray accent
becoming purple, and reported-gray-as-candidate must fail. Regression coverage in
`tests/test_natural_gameover_color.py` rehashes both ROMs, all artifacts and bound
sources and reruns both oracles. No cross-build timing or audio equivalence claim.

Visually inspected both Game Over captures and current second restarted stage.
Core executable SHA1d93c92ffdc4974d21628a69221da2f65c32b28fd6f500d08cdbe7efba391950,
library SHA20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf.
Post-run process check: no mGBA emulators. Hardware untouched; issue18 remains
open for device confirmation. This expands offline coverage, not a new ROM fix.

## Fixed-ROM allocation observer read control (#45)

The initial one-shot diagnostic `fixed-fade-read-positive-01` (2 frames) and
longer `fixed-fade-read-positive-02` (180 frames) both finished successfully but
logged no read. Their sampled CPU PC is 0104, after the diagnostic LD/HALT;
these are inconclusive controls, not evidence of absent reads. Retained unchanged.

A separate nonplayable diagnostic keeps the entry jump and replaces startup at
0150 with `LD A,(00CF); JR -5`. Exact ROM
`2ab49f3d4638756f2d155148b6c518a67b59af2b48491068c48479bf5335691c`,
`fixed-fade-read-loop-positive-01`, completes two guarded frames and logs 4452
CPU reads of 00CF at PC0153, spaced 56 native cycles apart. Watched bytes CF..E0
are unchanged from the exact ec8 parent. Source/hash-bound regression tests check
the allowed mutation, reject an unknown parent, and require those actual reads.
No emulator processes remain after the run.

This validates the read observer once installed. It does not establish startup
coverage, global allocation safety, or gameplay correctness. The proposed fixed
ROM allocation still needs whole-game ownership proof or relocation. No playable
ROM, running game, deployment, or hardware was changed; issue45 remains open.

## Current Shalamar one-frame Select delivery and observer neutrality (#34)

Fresh exact46eb/own Shalamar state `late-return-select-short{721,722}-{on,off}-01`:
four guarded1080-frame captures, no game-memory writes during replay, only third
entry shortened to one frame. All three rendered menu cycles PASS in each run.
At721 raw04 and edge04 arrive in the same frame; at722 raw04, release00 at723,
edge04 at727 with both raw/held00. The latter demonstrates post-release buffered
delivery rather than merely selecting a phase where the gameplay poll catches
the held button. Native resumed frame900 visually inspected.

For each phase, same-ROM/state observer-on/off full video, states, input timeline,
PCM, WAV and metadata hashes match, all files rehashed; restored epoch PASS and
1080 native frames each. Twelve delivery/model tests PASS, retaining historical
missed-press controls and adding exact-ROM/state/source bindings plus release/
delivery assertions. This is observer neutrality, not original-relative audio
equivalence or all-phase/all-arena ownership qualification. The original-stock
comparison remains the retained separate-fixture evidence, not a fresh stock run
or a cycle-equivalent comparison. No ROM changes, deployment or hardware access;
issue34 remains open for wider phases/lifecycle/arena qualification.

## Side-by-side assistance now preserves selected scratch banks (#41)

`probe_stage_side_by_side.lua` still wrote DCFD save flag every frame and DCBB
health after selection through the banked CPU window. Replaced only those two
assistance stores with physical bank1 writes, independent of SVBK, and added
total/masked-SVBK counters to the trace and driver manifest. SRAM level select,
inputs, read-only checks and image cadence unchanged; no cursor/resource refill.
Counter parsing fails for missing/inconsistent counts. Actual Lua helper tests
cover all eight selections and demonstrate the previous mapped-write failure.
All8 physical-assistance tests PASS.

Fresh guarded original/current46eb Stage1 patrol720, screenshots every120,
`late-return-side-by-side-physical-01`, completes with6 images per ROM. Current
build2436 writes:2368 at SVBK1,68 at SVBK3; all now target physical bank1. Original
DMG2327 writes read maskedFF70=7 (unsupported DMG register, not bank7 selection).
Do not interpret this as proof of visible damage in the old captures. Contact
sheet inspected, including black transition panels; frames are not position-
aligned. Stage1 semantic audit explicitly says not-applicable, not a palette
correctness PASS. No native audio captured. Post-run process check finds no mGBA.

This corrects another active harness consumer, not the ROM or hardware. Other
legacy diagnostic mapped writes remain to audit; #41 stays open. Historical
source-bound receipts are retained, not rebound to the modified probe.

## Palette bridge accepts exact46eb without discarding current fixes (#19)

New actual-ROM test first reproduced unsupported-pin rejection for current
source-built46eb. Added explicit `LATE_RETURN_PIN` only; default source and running
service unchanged. All15 primary rows are identical to authenticated126dd.
Offline tests populate every primary active row in a synthetic MiSTer-layout
state and exercise all15 edits, checking only intended ROM row/checksum and
corresponding state row change. Unknown one-byte variant still rejected;
all19 bridge tests PASS (5.28s), with subprocess/device access forbidden during
the new test. No hardware checkpoint, server restart, upload or game change.

This fixes exact-build editor compatibility, not scene-aware alias ownership,
live Apply/Resume, transition backups or experimental-ROM release qualification.
The diagnostic6cf9/7916 builds remain unsupported. Issue19 stays open pending
live workflow acceptance; experimental46eb's other open gates remain explicit.

## Current Sara walking/firing regression PASS; combat proxy does not reproduce report (#6)

Fresh guarded exact46eb ordinary-input `late-return-sara-walking-01` and
`late-return-sara-firing-01`:720 samples each, turn periods45 and17 respectively.
Both PASS:716 walking-pose frames,4 no-visible-Sara observations retained,
eight observed tile quartets, zero mixed/incomplete poses or raster failures,
zero unsupported raster samples. Walking checks131312 opaque pixels; firing
131655. Replay wall times3.35s and3.39s. Reinspection reproduces every result and
all720 PNG hashes per run. Firing frame360 visually inspected. Existing15 pose
tests PASS, including observed mixed-pose, missing/duplicate-tile, frozen-pose,
missing-sample and raster-negative controls. No sound acceptance in this probe.

Reused native Gargoyle captures (not new emulator runs): runtime-art pixel check
on current46eb finds zero differences in322571 pixels/1798 checked frames,
577 outside-active and25 no-opaque frames retained. Reported4f5a also gives zero
differences in328888 pixels/1904 checked frames,471 outside-active and25 no-opaque.
Consequently that particular combat proxy does not distinguish the player tear;
do not use it to claim the report fixed. Runtime-art agreement also cannot prove
that the art itself is the intended pose or establish scanline-time ownership.
Retained receipts `late-return-gargoyle-sara-pixels-01` and
`reported-gargoyle-sara-pixels-01`. Issue6 remains open for report-specific
coverage/hardware validation. No ROM or hardware changes.

The #45 dispatch review confirmed shared bank20:428F→4700 routing also owns menus:
a global bypass is not a scoped timing fix. The rejected card ablation remains
diagnostic only; no new fade patch was made during this regression check.

## Card-entry ablation rejected as a general fix: secret-route timing drifts (#45)

Explicit late-parent mode builds exact7916d5152ff628fab1b95753bd89fb1c65f850c791d7475480a06b55e28083de
from46eb, changing only75F0's target and checksum. Fresh cold3600 state generation
`late-card-route-entry-01` and own-state6000 `late-card-route-exit-01` both exit0;
restored capture epoch PASS, no state retargeting. Original disclosed position,
inventory and health assistance retained. Native frame4800 visually inspected:
Stage1 renders, but this does not establish timing parity.

Cold entry telemetry first diverges at2650 (Y1852 versus1854),710 differing rows.
Restored route has3852 differing telemetry rows. Return4679 versus4666; resume4734
versus4722. Incomplete-map frames4679..4683 remain completely white; first visible
4699. Thus the hidden-map property survives but the original timing does not.
Full native audio guard FAILs both silence checks:13023567 different stereo sample
frames, first0, last13167007, max39514, RMS ratio1.004271318. The independently
generated pre-states already differ, so this is not an isolated post-return APU
measurement. No alignment, trimming or retargeting used to conceal the mismatch.

Retain the successful cold Gargoyle ablation as causal evidence only. Do not
adopt its shared-card restoration: later-stage/native entry routing is necessary
to preserve this route. Next fix must retain that behavior while addressing the
stage-zero dispatch overhead. New regression retains this failed trial; current
46eb candidate and production build remain unchanged, all broader work open.

## Card-entry ablation removes the complete cold Gargoyle PCM difference (#45)

Diagnostic builder `build_card_route_ablation.py` takes exact988b and restores
only75F0's jump to4289 (previously00CF), plus global checksum. Fixed final-fade
dispatch and all fade bodies remain untouched. Exact output6cf95d403a53d8d9d55e1c7ccfc53e4d299aace1ab4561721779d9ca3435282b.
No production integration; the unqualified fixed-ROM allocation remains.

Fresh guarded cold2400 `card-route-ablation-gargoyle-01` exits0 with the same
spawn/health assistance, patrol/menu inputs and native tap. Full untrimmed video,
input timeline, PCM and WAV hashes match ec8 exactly. This removes all2514 PCM
differences seen in988b on this route, without video changes. Evidence regression
rebuilds the diagnostic ROM, restricts byte differences to checksum/card target,
rejects a different parent and rehashes complete primary streams; Gargoyle tests
14/14 pass. This is a causal ablation, not a release fix: secret-return rendering,
later-stage timing and placement safety are not qualified by this cold trial.
Next: test the restored card entry with the late-return upload on secret return
before adopting it. No hardware changes or readiness claim.

## Fixed-route audio trace: unchanged commands, shifted instruction timing (#45)

Revalidated fresh cold2400 `fastpath-gargoyle-sound-on-01` (ec8) and
`fixed-route-gargoyle-sound-on-01` (988b), both exit0. Rehashed every primary
capture artifact against its receipt and its own same-ROM uninstrumented patrol:
full video, states, timeline, PCM, WAV and metadata are byte-identical on/off.
The restored-epoch FAIL remains visible: these are assisted cold routes, not
restored-state qualification. No hardware touched.

Both traces contain3561 timer entries and5819 sound-port writes; ordered
kind/value sequences match exactly. Changed cycle timestamps:76 timer entries,
133 port writes, confined to frames559..629, deltas -40..+24 cycles. The shared
75F0 entry at frame558 has identical cycle78732124; following native0F33 entry
is88 cycles later in988b. Later0F7A entry at frame601 is16 cycles earlier.
This supports investigating fade dispatch/instruction timing rather than altered
sound command bytes. It does not prove which write causes the retained2514 PCM
differences, establish audible impact, or qualify a fix. No delay compensation,
threshold relaxation, ROM edit or issue closure. The evidence regression checks
observer neutrality, full command ordering, and the measured timing window.

## Current Gargoyle geometry PASS; new cold-route audio difference localized (#21/#45)

Fresh2400-frame `late-return-gargoyle-patrol-01` on exact46eb completes0 using
the established disclosed spawn/health assistance, patrol and menu inputs.
Geometry: zero split frames,1578 coherent fully-visible frames,166 not fully
visible frames retained. Native1560 PNG visually inspected: intact purple boss.
Full native video and input timeline are byte-identical to repaired126dd patrol;
all capture files rehashed. Retained reported4f5a control still has18 splits.

Unlike video, full PCM differs from126dd:2514 stereo sample frames, first1255668,
last1380738, maximum difference5376. The unchanged narrow audio comparator FAILs
same_digital_silence_intervals: one of22 intervals ends at1255669 rather than
1255668 (one sample/131072Hz ≈7.6microseconds). Other five guards pass, RMS ratio
0.9999999324. Full differences retained in `late-return-gargoyle-audio-pair-01`.
No trimming, retiming or threshold relaxation; audible impact is not established.

Fresh intermediate cold replays `fastpath-gargoyle-patrol-01` (ec8) and
`fixed-route-gargoyle-patrol-01` (988b) use identical inputs/probe. Rehashed full
PCM:126dd=ec8, ec8≠988b,988b=46eb. Full video/timeline identical across all four.
Thus this observed difference enters at fixed-route construction, not the final
late-window upload. This narrows the next instruction/timer investigation; it
does not establish the exact instruction or a perceptual regression. All cold
captures explicitly FAIL the restored-state epoch check and are not restored
audio acceptance. Tests retain positive geometry, broken controls, PCM failure,
and intermediate localization. No ROM change, hardware action or issue closure.

## Exact source-defined no-bleed profile bound to46eb; fresh full route PASS (#24)

Compared source-built d744 and46eb: their entire256-byte Stage1 LUT is identical
(SHA25666b0876cbe0a4a64885655a60d9fa56ca8479c51514e3d60fe4d9a45be15de82),
and their four star CHR tiles are identical. Differences from the YAML baseline
are exactly the authored12 tooth entries7→15 and4 star entries0→5. The existing
oracle omitted46eb from these exact-pin profiles. Added only this source-built
pin, leaving the independent YAML-plus-authored-transform expectation intact.
New test failed before the binding and passes afterward; all256 one-cell
mutations and an unknown-ROM mutation still fail the semantic comparison.
The four source-construction tests also PASS. No ROM bytes changed.

Fresh `late-return-stage1-no-bleed-profile-01` exits0: full7200-frame vertical-box
route, all17 runtime checks, exact static LUT checks, zero semantic-pickup errors
and zero detached pickup-color pixels across7113 raster captures. All7120 native
play/raster PNG files were compared byte-for-byte against the preceding
physical-assistance run: identical. Final7200 PNG visually inspected. This is
not a full native PCM comparison or hardware proof. The earlier two failed
receipts remain immutable and a regression test retains that distinction.
Five no-bleed tests pass, including fresh evidence/source hashes and all PNGs.
Verifier SHA2560a0b0b12c82bf51135dfc78daff3740ee5ab02341510651aa730052d378c1c89;
probe SHA2561a7aac8d57e935344c44a514f6214f68e362221a37054d98e0534bdff19a7c5c.
No MiSTer action, issue closure, or full-release readiness claim.

## Stage1 no-bleed health assistance corrected; semantic profile failure retained (#41/#24)

Fresh46eb7200-frame vertical-box run `late-return-stage1-no-bleed-01` failed
three static ROM/YAML semantic-table checks, despite all17 runtime checks
passing. Inspection also found the known #41 pattern in this probe: its
continuous health refill used mapped CPU DCBB, not physical bank1. Extended
the existing issue before changing the probe. Health now uses the same
physical-WRAM helper contract as the corrected stage-speed probe, with total
writes and sampled SVBK counts in probe.txt/receipt.json. No game ROM changed.

Fresh `late-return-stage1-no-bleed-physical-01` completes the same full route:
7326 health writes, of which7008 occurred with SVBK1,312 with SVBK3 and6 with
SVBK7. These318 scratch-bank-selected callbacks now write physical bank1.
Actual prior-run scratch damage is not established by these new counts.
All17 runtime checks again pass: zero semantic-pickup errors, zero detached
pickup-color pixels in7113 raster captures, safe attribute bits, and intact
final Stage1 gameplay. Native final7200 screenshot visually inspected.
Both runs remain FAIL on the same three static table checks; no threshold,
expected palette table, historical receipt or test outcome was rewritten.

Five assistance tests pass, including actual Lua execution with all eight bank
selections and the previous mapped-write negative control. The fresh-receipt
test keeps the static failure explicit. Next: authenticate the inherited
tooth/star table profile against its construction, rather than learning the
expected table from the tested ROM or treating runtime PASS as overall PASS.
The existing expected-profile function recognizes the original d744 star
candidate but not46eb. This is a candidate/profile binding gap to investigate,
not yet a waiver. No hardware interaction or readiness claim.

## Fixed-route reference reader: 034364 is consumed as data on the tested route (#45)

Added opt-in `ENTRY_FADE_REFERENCE_READERS=1` to the diagnostic probe, watching
data reads and execution separately at the thirteen unresolved byte-shaped
reference sites. It filters and records the software bank shadow FF99; it does
not assert global physical-bank coverage. No memory writes were introduced.
Exact ec8 parent cold1800 run `fade-reference-readers-cold-01` exits0 and logs88
reads of file034364, all at fixed PC0E0F with bank shadow0D and HL4365, and no
execution events. Pinned bytes at0E0E are `2A F5` (LD A,(HL+); PUSH AF).
The bytes `C4 D3 00` at034364 therefore occur as data consumption here, not a
CALL NZ,00D3 instruction. The other twelve sites were not observed; neither
their role nor alternative uses of034364 are cleared by absence on this route.

Restored the exact own frame600 state into fresh120-frame on/off runs
`fade-reference-readers-{on,off}-01`, both exit0 with valid native capture epochs.
Seven positive read events reproduce at relative37,51,65,78,91,104,117.
Rehashed all full primary capture files: native video, states, PCM/WAV, timeline
and metadata are identical between observer-on/off, without trimming or masking.
This establishes bounded observer neutrality, not general audio acceptance or
global allocation safety. `tests/test_fade_reference_readers.py` PASS (0.025s
verification); the test retains allocation/release=false. Probe source hash is
352b1a77454e0b36163a32b72b18d6b1c013bf2705f7d5a0f57a42f3a1da3efd.
No ROM patch, deployment or issue closure. Remaining allocation work must resolve
other readers/computed entries or use independently established owned space.

## Gold star collection and inventory menu return on 46eb (#22)

Fresh serial local runs `late-return-star-{live,collect,menu,resume}-01` all
exit 0 on source-built ROM SHA-256
`46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb`.
Cold entry uses the disclosed one-time position assist (1192,624); subsequent
120/360/180-frame collection/menu/resume runs use only controller input and
exact-ROM states, with no observer memory writes. Frame1500 screenshot was
visually inspected: the star is yellow/gold. Its entire 16x16 pickup region
matches the retained fixed reference and differs from the known-broken reference;
three interior samples are RGB255,255,0. Inventory changes from empty to DCD1=15
and survives paused and resumed scene02 states. The new
`tests/test_late_return_star_route.py` passes, rechecking ROM hashes, state CRCs,
state-chain hashes, probe bindings, inventory and rendered pickup pixels.

Follow-up `late-return-star-uncollected-{menu,resume}-01` restores the same
own-ROM live star state, opens the menu for360frames, then closes it for180frames
using six-frame Select pulses. Both runs exit0 with no observer memory writes.
All180 close-replay screenshots have a byte-identical RGB16x16 star region to
the pre-menu screenshot, including the first still-paused frame; frames2..180
are unpaused scene02. Inventory stays empty throughout. Terminal screenshot
visually inspected. The regression test now has two passing cases and checks
every captured close-replay frame, exact state/ROM bindings, and the retained
known-broken star region. Verification took0.204s (not emulator runtime).

This verifies collection, retained inventory, and uncollected star color on this
menu route, not an unassisted teleport route, audio fidelity, or hardware
acceptance. Issue #22 remains open. No ROM edits or hardware actions.

## Reviewed doorway alignment and occlusion restored on46eb (#14/#45)

Fresh cold `late-return-doorway-01` uses the existing disclosed position/resource
assist and unchanged Down-input recipe. At1216, exact46eb now reaches world
1240/1356 and camera0c08, matching the authenticated original-cartridge reference
`ceiling-stock-doorway-03`. Sara's four OAM quadrants have priority set and all256
pixels of the reviewed16x16 black overhang remain black. The unchanged doorway
oracle PASSes. Native screenshot inspected; surrounding doorway/background is
nonblank. Prior126dd still fails alignment at y1352; that historical rejection
is retained rather than changing the reference or accepting a shifted mask.

Fresh `late-return-floor-01` patrol retains clear priority for all four Sara
quadrants on every frame1201..1800, with the expected runtime helper present.
This checks the floor-priority tradeoff, not a full pixel-level floor-bleed gate.
Two tests authenticate the46eb result, preserve the original broken control's
192 exposed pixels, retain the old alignment rejection, and check all600 floor
observations. Exact reported overhang/collision route and broad layering/audio
coverage remain separate; no all-overhang or collision-fix claim. No deployment.

## Latest Stage2 Continue and timeout controls (#28/#45)

Fresh exact46eb stage entries generated serially in `late-return-stage-states-01`
report expected scene/stage and unsafe_attr0 for Stages2..7. This is assisted
entry coverage, not level completion. The Stage2 state has exact ROM CRC/header.
Three new6000-frame runs `late-return-stage2-continue-{a,neutral,start}-01`
use the existing disclosed one-credit/HP1 stimulus followed by Up movement to
native death. All reach death2352 and prompt-relative input2414. A produces a
native input edge and resumes2470, remaining in active Stage2 through6000.
Neutral and Start produce no A edge, observe481 prompt polls, and time out to
title3314. All three input/timeout oracles PASS; reported broken candidate A
still FAILS. Two new tests rerun these checks with exact ROM/state bindings.

Final A-route PNG was inspected: Stage2 terrain and Sara are present and colored.
This is a visual spot check, not a full terrain/CHR or audio equivalence gate.
No whole-session reproduction, hardware validation, deployment or issue closure.

## Low-health Shalamar menu regression on46eb (#27/#45)

The new standard boss checkpoint starts with HP240, unlike the prior low-health
case. Following its ordinary menu replay with600 no-input damage-exposure frames
(`late-return-shalamar-damage-01`) leaves HP238..239 and raw scene0C throughout;
that run does not cover the sound alias. Do not count it as low-health evidence.

Used the existing explicit one-time physical-bank1 HP stimulus, `ENTRY_ONCE_HP=109`,
in `late-return-shalamar-lowhealth-entry-01`. No scene/palette/cursor/graphics
writes. Own-ROM frame1 records HP109 and raw/canonical0C; game execution reaches
raw0B by frame10. Its frame1 state then seeds the controller-only1080-frame
`late-return-shalamar-lowhealth-menus-01`, with no further memory assistance.
All three standard Select cycles PASS endpoint/cadence/map-readiness checks.
Raw0B spans exactly frames7..1080 (1074 frames); canonical0C and authored C600
palette policy hold throughout. Native restore epoch PASS,2370048 sample frames
captured; all raw hashes rechecked. Replay/verification wall4.061/1.185 seconds.
Final native PNG inspected: cyan Shalamar and patterned background intact.

Two regression tests authenticate the explicit fixture and exact46eb capture,
rerun the three-cycle and all-frame palette checks, and reject a wrong palette
on an aliased frame even when canonical scene remains0C. This is assisted-entry,
controller-only menu coverage, not an ordinary full-route, acoustic-equivalence
or hardware claim. Allocation/global qualification remain open; no deployment.

## Fresh Ted/Shalamar standard menu routes on46eb (#27/#32/#36/#45)

Authenticated Ted bank17 as byte-identical to126dd (SHA256
6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7), then added
only46eb to the generator's exact relocated-latch recognition. It is not added
to the fixture-retarget allowlist. A mutation test rejects changed latch code.
Fresh stock-dispatcher-assisted checkpoints in `late-return-boss-states-01`
pass Shalamar entry at100 and Ted at302. Ted then receives600 frames of left
input in `late-return-ted-escape-01`, without observer game-memory writes.

`late-return-{ted,shalamar}-menus-01` each capture1080 frames with Select at
120/240/420/540/720/840 held6 frames. Both PASS all three existing endpoint,
fade-cadence and map-readiness cycles. Native capture epochs PASS; full raw
hashes are checked by the new evidence test. Replay/verification wall seconds:
Ted4.977/1.226, Shalamar4.191/1.238. Final native PNGs were inspected: bosses
and patterned backgrounds remain intact. Audio was captured but these checks
do not establish acoustic equivalence or hardware behavior.

Neither route enters the sound-alias interval (zero alias frames); this does
not replace the prior low-health Shalamar regression. Two evidence tests rerun
both new oracles and retain rejection of the broken historical Ted control.
The three Ted profile/evidence tests also PASS. Fixed-region allocation and
other remaining qualification are unchanged. No deployment or issue closure.

## Source-reproducible late-return candidate and fresh restart checks (#18/#45)

The main regression builder now offers explicit `--experimental-late-return-fade`
after all existing chain flags. Default builds are unchanged. It reconstructs
the initial-map fastpath, fixed stage routing and final late-window restore from
the original cartridge/palette sources, checking every intermediate SHA. Fresh
`tmp/stream-late-return-source-01/candidate.gb` equals the retained46eb trial
byte-for-byte (SHA25646eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb).
No retained candidate is a construction input. The manifest explicitly retains
`release_qualified:false`, `allocation_review_complete:false`, the unresolved
fixed-region ownership and414 differing audio sample frames. Four construction
tests check opt-in dependencies, wrong-parent rejection, exact chain and source
bindings. This is offline experimental integration, not release promotion.

Fresh guarded emulator runs `late-return-gameover-restart-01` and
`late-return-hazard-restart-01` both PASS. Each uses the native save-present
fixture and checks two Game Over/title/new-game cycles, both stage-card variants,
restarted terrain,482 title-frame pairs and102 Game Over frames. The first uses
HP=0 once per life; the second walks through the hazard area before the same
accelerated death stimulus. Neither is an unassisted natural-death claim.
The new evidence test rehashes captures and reruns the existing rendering and
sequence oracles. Broader routes, code allocation, residual audio investigation
and hardware validation remain incomplete. No deployment or issue closure.

## Bounded fixed-region runtime observation (#45)

Added opt-in `ENTRY_FIXED_FADE_ALLOCATION` read watchpoints and execution
breakpoints for each byte 00CF..00E0; callbacks do not read those watched bytes.
Fresh ec8 assisted cold3600 `fixed-fade-allocation-on-01` and its own-state6000
`fixed-fade-allocation-return-on-01` record zero accesses. Both terminate with
status0. The fresh return `off-01` replay uses the exact same source state,
ROM/core/probe/runner/tap and matches the full raw PCM, video, serialized state,
input timeline, WAV and metadata hashes, freshly rehashed. Restore epochs PASS.
Cold prefix has no full native capture: no full cold observer-neutrality claim.

A separate240-frame positive control from46eb's own4560 state detects eight
instruction entries: CF/D1/D2/D5 at relative69, D8/DA/DB/DE at109. This validates
execution detection, not a data-read positive control. Two evidence tests retain
the negative observations, positive execution control and full return neutrality.
No state retargeting, ROM modification, release integration or hardware action.
The static references and unexercised routes remain unresolved; zero accesses
on this assisted route do not establish that the region is globally unused.

## Fixed-route placement review: direct-reference census remains insufficient (#45)

Rechecked exact ec8 parent before release integration. The proposed fixed-ROM
00CF..00E0 region retains original nonzero bytes after the LCD-enable RET;
it is not established padding. A full-ROM byte-shaped scan of absolute branches,
BC/DE/HL immediate loads and absolute A loads/stores finds 15 mentions:
008A1F, 008C58, 01918A, 02C2DF, 02C60F, 02CCD9, 02D4D7, 02D55B,
02D763, 034364, 036264, 040364, 042264, 080364, 082264.
No fixed-bank JR-shaped reference enters this region.

008A1F and 008C58 are verified numeric initializers: `LD HL,00E0` followed
by stores of L/H to DD87/DD88, not reads from 00E0. Their arena entry points
match the documented bank-2 Cameo/final-boss setup routines. The other 13
mentions are **not cleared** by this census. Several have table/tile-like
contexts; appearance alone is not reachability or allocation proof. The
034364 context repeats at 040364 and 080364; duplication is not independent
evidence that it is unreachable code. Comparing 32-byte contexts against the
original ROM (SHA256 2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30)
locates all except 042264 in native bytes, so they cannot simply be dismissed
as new patch artifacts.

Added a pinned regression census to `test_fixed_fade_route_trial.py` which
also retains the explicit unqualified allocation/release flags. This is a
static investigation, not an emulator acceptance test. Next allocation work
must resolve the remaining data/control references and computed readers, or
replace this placement with independently established code space. No ROM,
historical receipt, hardware state, or release qualification was changed.

## Residual audio investigation retains full sound-register ordering (#45)

The trigger-only observer did not explain the residual PCM, so added opt-in
`ENTRY_SOUND_ALL_REGISTERS` under `ENTRY_SOUND_TIMING`, retaining every write to
FF10..FF3F, including wave RAM and unused ports. Fresh own4680-state120-frame
`final-fade-all-audio-{control-,}on-01` runs and corresponding `off-01` runs
match full raw PCM/video/states/input/WAV/metadata within each same-ROM pair.
All hashes and exact ROM/state/probe/runner/tap bindings are checked by two tests.

Both control and46eb issue497 sound-register writes with identical port/value
sequence. Four cycle differences exceed32 master cycles, all FF18 valueF7:
relative23:+11856,26:-28440,28:+1496 and28:+56. Smaller phase offsets remain in
the complete TSVs; no values, frames or PCM samples are excluded from acceptance.
This locates timing differences in channel2 frequency updates after the fade,
not a missing/replaced register value. It is not yet proof that those four writes
alone explain the414 residual full-route sample frames. Full audio originals and
their differences remain unchanged. No new ROM change or hardware action.

## Final restore dynamically stays in VBlank and preserves all colors (#45)

Fresh120-frame replays from46eb's own4680 state, `final-fade-cram-on-01` and
`final-fade-cram-off-01`, verify actual palette writes with the existing CRAM
watchpoint observer. All320 palette writes avoid blocked mode3. The new final
routine emits exactly64 FF69 writes, palette indices0..63, all mode1 atLY150,
151 or152 in relativeframe21. First/last write cycles1166219130/1166221146.
Every emitted byte equals the physical bank7:DF00 backup in the source state;
the following captured state's actual BG CRAM also equals that backup.

The same-ROM/state observer-on/off pair is byte-identical in full PCM, video,
serialized states, input timeline, WAV and metadata; all raw hashes rechecked.
Both restore epochs PASS. `check_final_fade_cram.py` implements the narrow
trace contract. Two tests retain the actual upload/neutrality and reject mode3,
wrong bank/index/value, missing writes and wrong resulting CRAM mutations.
This establishes write safety on this replay, not every arrival phase or a
full-game palette qualification. The static late-window bound remains separate.
Fixed-ROM allocation review and414 residual audio sample frames remain pending;
no release integration, deployment, hardware action or issue closure.

## Bounded final late-window restore repairs handoff on assisted route (#45)

`build_final_fade_late_window_trial.py` changes only the final E4 restore call
and a new bank20 FF-cave body on988b. Candidate SHA256
46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb.
The routine disables interrupts before samplingLY; accepts144..150, otherwise
uses the unchanged safe-window fallback. All64 backed-up bytes are written in
order usingLDH(C),A. Static instruction-budget test counts1140 normal-speed CPU
T-cycles from LY read through final CRAM write, below the minimum1368 remaining
after the end ofLY150. No wait counts, other shades or native card code change.
This is a static bound, not yet an exhaustive dynamic CRAM-write safety campaign.
The parent's fixed00CF allocation remains unqualified. Not release-integrated.

Fresh assisted cold3600 `final-fade-late-window-entry-01` matches all telemetry
and38 PNGs of native-fade control. Own-state6000 `final-fade-late-window-exit-01`
has PASS restore epoch and ALL6000 gameplay telemetry rows equal to control.
Return4666, active gameplay4722 now match control. In the100-frame return window,
incomplete map4666..4670 remains fullywhite and firstvisible4687 is complete.

Full native audio `final-fade-late-window-audio-pair-01` passes activity, level,
silent-block, digital-silence-interval, clipping and discontinuity guards.
Not waveform identical:414 sample frames differ, indices10316126..10316539;
maximum difference1632, RMSratio0.999999983. All later samples match exactly.
WAV SHA8768a874a2b0d09711c1e5db77acfc51850e1ae4bc83b1528dd2c7800e12ae11.
Four tests preserve exact patch, static budget, raw hashes, complete telemetry,
map visibility, residual audio differences and rejection of the prior988b audio.
Next: dynamic boundary/write checks and allocation review before integration;
also investigate the remaining short audio discrepancy. No hardware/deployment
or all-game readiness claim. Issue45 remains open.

## Measured fade-window arrival misses current acquisition range (#45)

Opt-in read-only `ENTRY_RETURN_FADE_WINDOW` observes exact988b bank20 addresses.
Fresh own4680-state120-frame `fixed-fade-window-on-01` and `-off-01` match in
full native PCM/video/states/input/WAV/metadata; all raw hashes freshly verified.
Shade40/90/E4 calls reach5BF8 at relative5/13/21, alwaysLY150. The acquisition
returns at relative6/14/22, LY144. Final entry1166218912 does not acquire until
1166353832. This directly verifies the previously hypothesized missed window.

Final uncompact upload reaches RET5BF7 at1166357376/LY147,3544 master cycles
after acquisition. The same RET breakpoint repeats at1166362448 and1166363120
after interrupts, bothLY0; these are retained, not counted as extra uploads.
Simply accepting lateLY150 for this3544-cycle body is unsafe: fewer than four
scanlines may remain. Any late-window alternative needs a complete worst-case
write budget including detection, bank changes and interrupt masking, and must
preserve all colors/ordinary waits. No change to ROM/window limits yet. Existing
source-bound receipts remain unchanged; new probe hash lives in new receipts.

## Fade exit, not the seven settle calls, owns the extra frame (#45)

Fresh own4680-state120-frame replays `fixed-fade-completion-control-01` and
`fixed-fade-completion-trial-01` use existing fade/build observers. Both match
their respective retained same-ROM observer-off replay in full PCM, video,
serialized states, input timeline, WAV and metadata; raw hashes freshly checked.
The native fade returns to15DD at cycle1166218944, relativeframe21/LY150.
The988b trial returns at1166363648, relativeframe22/LY0:144704 master cycles
later. Both then call16DD exactly seven times. The first settle starts at
1166219064/1166363768, so the delay already exists before the settle sequence.
Two evidence tests preserve observer neutrality and these exact exit/call facts.

Source review: shared CRAM-window acquisition5BF8 only acceptsLY142..143 and
waits for144; arriving during VBlank is rejected until the next frame. This is
a plausible contributor, not yet a measured entry-phase cause. Do not blindly
widen its bounds: the upload must fit before visible mode, including interrupt
and mapper costs. Next measure arrival at that window and the final upload exit
to determine whether a safely bounded late-VBlank path is possible. No ROM
change or hardware action in this step; full audio failure remains open.

## Shorter return uploads do not remove late completion (#45)

Tested one mechanism on988b: reuse the compact straight-line return CRAM uploader
without changing shade values, wait counts, entry addresses, or native card code.
Scratch builder `build_fixed_fade_compact_trial.py`; candidate
f653ed03f2cc3274b4dc53eb286b6b5d00ff095d093edc8427fd14aa09daa280.
Inherits the parent's unqualified allocation; not integrated or deployed.
Existing instruction-model tests verify all64 bytes of each shade against the
original uploader for32 palettes and show reduced upload cycles.

Fresh `fixed-fade-compact-entry-01`3600 matches every control telemetry row and
all38 PNGs. Own-state `fixed-fade-compact-exit-01`6000 restores cleanly, returns
on4666, hides incomplete map4666..4670 and first displays complete map4687.
However active gameplay still resumes4723 instead of control4722. Full native
audio `fixed-fade-compact-audio-pair-01` still FAILS digital-silence intervals;
first differing sample remains10316126.2789785 sample frames differ; remaining
level/clipping/discontinuity/silent-block guards pass. WAV SHA
56fb6f8f7fd75fb653db3f2142bbc1e85cb1d3886f98d7e0b9820113205dbf92.
Two new tests retain exact patch scope, raw hashes and failed resume/audio result.
This falsifies shortening upload length alone as sufficient to restore the
handoff. Do not extend this failed variant to a broad campaign; inspect the
wait/publication boundary before another timing patch. Rivalmage untouched.

## Remaining fixed-route mismatch localizes to fade completion (#45)

Reanalysis of full native captures places first PCM difference10316126 in
timeline row4700 (emulator frame8299). Native/control and988b trial return to
scene02 on4666, but activeFFC1=1/menuFFE4=0 resumes4722 versus4723.
The first gameplay telemetry mismatch is4702: worldY1484 versus1486. BGP
steps occur on matching frames4686/4694/4702, while trial OBP writes appear one
frame later than control at each step. These are measured correlations, not
proof that a single palette write causes every later difference.

Fresh120-frame sound-timing/command probes from each build's own4680 state:
`fixed-fade-late-control-01` and `fixed-fade-late-sound-01`. Corresponding
`-off-01` runs are byte-identical in full PCM, video, states, input timeline,
WAV and metadata; all four restore epochs PASS. Three evidence tests rehash
these files and preserve the late resume and command timing findings.
Later command26 is accepted in both, at relative53 versus55,188432 master
cycles apart. The remaining failure is not simply a lost command. Early sound
register events differ by small instruction-phase offsets; a timer delivery
difference over1000 cycles first appears at relative23 (control interrupted12E0,
trial7478). Next examine native fade exit versus CRAM publication completion
and subsequent settle calls, without shortening wait counts or masking audio.
No ROM edits, hardware actions, or readiness claim in this investigation.

## Late fixed-bank fade routing removes return-frame slip, audio still fails (#45)

Experimental `build_fixed_fade_route_trial.py` leaves the native loader and all
card waits intact, routing only the two final fade calls. Candidate SHA256
988b3e07bcfd884c01f7355704a48530502cab157d01d33f2767417ffd9921b7.
It uses18 original random bytes at00CF..00E0 after the00C8 LCD-enable RET.
This is an UNQUALIFIED allocation hypothesis, not an established free-space
contract. A raw scan found instruction-shaped mentions in banked data and
operand bytes; absence of a verified call is not proof of no indirect reader.
Independent allocation review is required before integration. In particular,
75F3 is a live SRAM-slot pointer table, not tail padding; it remains unchanged.

Fresh assisted cold3600 `fixed-fade-route-entry-01` matches every telemetry row
and all38 retained PNGs of the native-fade control. Its own unretargeted3600 state
feeds `fixed-fade-route-exit-01`,6000 frames with native PCM/video/states and a
PASS restored epoch. Return begins4666, matching control rather than the cloned
loader's4667. All incomplete map frames4666..4670 are entirely white; first
nonwhite4687 has a complete map in the checked100-frame return window.
The retained4800 screenshot was inspected: terrain is visible; this is not
all-palette or all-scene approval. Setup position/inventory and replay health
assistance remain declared; no physical hardware used.

Full unmodified audio comparison `fixed-fade-route-audio-pair-01` still FAILS
digital-silence-interval equality. First differing sample10316126, versus9803918
for the cloned-loader trial;2786787 sample frames differ. Full-route silent-block,
clipping, discontinuity and two-percent level guards pass (RMSratio1.0058456468).
WAV SHA4424519e0d992c32b3ee647c536acb70685b68084e2030a8cdae9d5746437771.
Do not call this audio acceptance or trim the later mismatch. Three tests preserve
patch scope, entry parity, raw artifact hashes, return visibility and audio FAIL.
Next: locate the later divergence within the fade/settle sequence, and separately
complete allocation review. No integration, deployment or issue closure.

## Fresh Shalamar native capture starts after restore (#43, related #27)

The boss-menu runner now uses the existing CPU startup barrier in native-capture
mode: Qt restores the exact-ROM state before the Lua-ready marker releases CPU
execution. Non-native launch behavior is unchanged. The runner rejects invalid
restore epochs or capture counts other than the requested 1080 frames; three
unit tests include invalid epochs despite otherwise complete capture files.

Fresh runs `tmp/shalamar-gated-native-menu-02` and `-03` used candidate
126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b and its own
`return-fade16-shalamar-entry-01/boss0_shalamar.ss0`. Run03 was invoked with
`ENTRY_NATIVE_START_DELAY_US=10000`; run02 used the default startup delay.
Both passed three Select menu cycles at120/240/420/540/721/840, with no game-memory
writes. Both retained1080 native frames and2370048 stereo samples, with no samples
or video emitted before the single successful restore. Raw PCM, video, full
serialized state stream, input timeline, metadata and WAV match byte-for-byte;
no trimming, alignment or normalization. Native PCM SHA256:
62cb8716d378eecc0bc5c1c9304ddf229d662c00a8f63054bd77524014e1f060.

`tests/test_shalamar_native_startup_evidence.py` freshly rehashes both captures
and source/ROM/state/tap bindings and compares runtime identities and full streams.
Its evidence test passes. Raw AV lives in
`/mnt/data/tmp/penta-shalamar-gated-native-menu-{02,03}-av`.
This establishes startup-delay invariance for this exact replay, not general
observer neutrality, native-game audio fidelity, or hardware acceptance. Issues43
and27 remain open. No ROM modification, deployment or Rivalmage interaction.

## Corrected Shalamar residency gate retains corrupted-palette rejection (#47)

After filing47 and verifying native behavior, `check_boss_menu_fades.py` now
records raw scene, canonical scene, model and authored Shalamar C600 policy for
every frame. Only demonstrated Shalamar raw0B/canonical0C may count as resident;
unknown/missing model or canonical identity cannot qualify an alias. Other boss
aliases are not generalized from this evidence. Changed canonical ownership or
unexplained raw scenes fail. On CGB, Shalamar's authored256-byte BG policy is
required on EVERY checked frame, including ordinary0C, not only alias0B. This
prevents canonical identity from concealing the original dungeon-table regression.
RGB palette intent and full scanline publication remain outside this check.

Tests include native stock alias acceptance, current126dd alias acceptance,
and rejection of retained broken d744 frame999 with the actual dungeon table.
Mutations cover wrong canonical owner, unknown scene/model, wrong policy both
with and without alias, and unsupported other-boss alias. Surrounding menu,
roundtrip and native-counterexample suite:56 tests plus4 subtests PASS in41.36s.

Reanalysis (NOT a fresh emulator run) of all1080 retained126dd Shalamar frames
now PASSes residency, graphics-table policy and all3 endpoint/cadence/map cycles.
All129 alias frames952..1080 remain listed and checked. Historical FAIL receipts
are unchanged and tested as historical; new report
`tmp/shalamar-alias-qualified-reanalysis-01.json` SHA
3481b03973c31d730fcbbcd564e77c323227e8210c8eebdea4a107c362f9e7cf;
checker SHAe583a19bb46b5f9477652249a19cd3fe993f09ee7fa1610664c8b4f7d933caf2.
This resolves the verified harness defect47, not full Shalamar issue27 or game
readiness. No ROM changes, audio qualification, deployment or hardware action.

## Native Shalamar counterexample to raw scene residency (#47, related#27)

Fresh original-ROM2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30
own Shalamar dispatcher state, three ordinary Select cycles at120/240/420/540/
721/840, completes1080 frames and PASSes existing checker in
`shalamar-native-residency-01`. HP remains158, raw/canonical0C throughout; this
does not reach the relevant alias and is not sufficient counter-evidence.
Continued from its own frame1080 with neutral input6000 frames and no game-memory
writes in `shalamar-native-lowhealth-01`. RawD880 changes0C->0B at1537/HP109,
remaining0B for4464 frames. All51 retained states keep canonicalFFB7=0C;
38 sampled alias states are rejected by existing `scene_route_failures`.
Trace SHA85c52b570ab6e7c16157f9f8df8a8f6e0fdd491e9a12fcae98036e9dd35b02a8.
The older `shalamar-stock-button4-01` ends with invalid603 state; it was not
used as complete evidence. Fresh captures have complete receipts.

Filed distinct harness issue47 before implementation. This establishes that
raw0B alone does not prove leaving the arena. It does NOT clear palette corruption:
retained d744 alias installed a dungeon C600 table while canonical0C persisted.
A corrected gate must retain every alias frame and independently validate the
expected graphics policy, wrong canonical exits and unexplained raw scenes.
Added native counterexample test; existing acceptance/checker and historical
failed receipts unchanged this turn. No ROM patch, deployment or audio claim.

## Sara runtime pixels during retained miniboss combat (#6)

After unsuccessful#45 timing variants, expanded the previously missing Sara
raster check to retained combat captures, without launching an emulator or
changing ROMs. New `check_sara_runtime_pixels.py` decodes actual captured VRAM,
OAM and OBJ palettes, including bank selection/flips and OAM-index overlap.
It keys Stage1 on canonicalFFB7=02/activeFFC1=1 rather than rawD880=02: most
combat frames use temporary0A. It explicitly retains absent/non-gameplay and
unsupported8x16/priority cases. It checks opaque rendered content, not coherent
pose generation or complete scanline-time state; differences would need further
investigation, not automatic attribution to tearing.

Reused captures were re-bound to original receipts/ROM hashes, with raw video
and states rehashed. `gargoyle-latest-patrol-01` is665a33b6 (NOT current release),
2400 frames:1798 checked,25 no opaque Sara pixels,577 outside activeStage1;
322571 pixels, zero differences.1736 checked frames have rawscene0A.
`gargoyle-reported-long-menu-01` is reported4f5a67b8,4080 frames:3584 checked,
25 absent,471 outside;637840 pixels, zero differences.3498 checked frames use0A.
Both original replays declare miniboss spawn assistance. New report directories
`sara-miniboss-runtime-pixels-01`/`sara-miniboss-runtime-pixels-menu-01` preserve
all classification counts and input hashes; checker SHA
b617288f151486512cfac9aed98598c1b62148ed3ec44f0be4311bd3c100a3ed.

Three tests include deliberate missing-pixel detection, runtime bank1/flipped
art, and explicit unsupported/absent categories. No reported tear reproduced,
no sprite timing workaround justified, no hardware or audio acceptance added.
Issue6 stays open; use a visibly failing route or recorded affected frame to
choose the next fix, rather than treating late DMA alone as the symptom.

## Native-chain failure is still inside the100 waits (#45)

Fresh own trial05 frame4440+240 `return-chain-wait-trace-01` uses the existing
loader observer, no ROM changes. Native0F47 begins1135264816, completes its
0F64 tail1137428720. Native4068 starts1137428776 (32 cycles BEFORE control,
not local04's32 cycles after); B100,99,98,97 occur at frames56,57,58,60.
All100 counters are present. Native control reaches B97 at59. Custom5C22 is
already frame190 versus native final fade189. Thus unchanged late music is
not hiding a recovered native wait followed by a new custom-fade delay.
The third native wait still loses a frame despite removing the mapper between
callees and using original wait code. This trace has not received a new
observer-off qualification; earlier on/off evidence is not silently extended.

Source placement review: fixed/bank1 contain no all-FF/all-zero span of8 bytes
except live bank1:50C4 collision fallthrough. Fixed00C1..C7 remains only7 bytes;
LCD enable starts00C8, Select wrapper RET00C0 is live. No duplicate fixed-bank
LCD-enable routine was found to safely reclaim00C8. Do not overwrite adjacent
code to fit a dispatcher. Existing four-register epilogue sharing could save
only one byte of the Select wrapper, insufficient for a9-byte stage dispatcher,
and would require separate input timing qualification. No such rewrite made.
Other open issues were rechecked: bridge#44 is already offline-fixed pending
deployment, Shalamar#27 retains an explicit overall-failed replay. Neither is
newly closed or presented as hardware-verified. Added counter-trace regression.

## Native return-chain experiment also retains late handoff (#45)

Added reviewed-stack `native_chain` primitive: synthetic RET continuations keep
native routines in bank1 until a final callback restores bank20. Instruction
model tests verify AF/HL, bank and balanced stack across both native returns for
all16 flag nibbles; this is not cycle equivalence. Explicit builder option
`--native-card-chain` preloads B=100 (native0F47 preserves BC), runs native0F47
then native4068 with no intervening bank20 callback, and retains original100
mode waits. It moves LD B,64 before the fade and adds a continuation word:
these differences are disclosed, not claimed as native timing parity.

Trial05 SHA62ed16109187ea84b7cade8e2c36fcb128d4ffa020cf49ce750f720d605117b3;
builder1ae80089ec575e0f8e22afc1e1a5564a471bd9d35e8a2a7b823d3b79d55242b1;
primitive8f4630ca971058c841f6de1eef84d0eeed06e83bb291f0c92f70e56bb5a6f10a.
Fresh cold3600 `return-native-chain-entry-01` trace and all PNGs match trial03.
Own3600 state909a51980316d5c4ac6692cc756e8c5aca3c57c63f2f7a0fa9dd4ec78e0f0fb9
feeds4800-frame `return-native-chain-exit-prefix-01`, with native capture and
sound-command observer. Epoch passes; this is explicitly a return prefix, not
full6000 audio acceptance or observer-neutrality qualification.

FAIL intended improvement: music request1161391592 and accept1161408856 are
exactly unchanged from03/04. Dungeon first frame4667; mismatching map4667..4671
fullywhite; first visible4687. No frame recovery from keeping these original
callees together. Retain trial05 without integration or a larger campaign.
Reconsider interception before initial native fade and its synchronization,
not another wait-count adjustment. All local emulators stopped; Rivalmage untouched.

## Poll instruction trace explains the first lost wait (#45)

Fresh `return-poll-phase-control-01`/`return-poll-phase-trial-01` capture the same
own-state4440+240 replay, observing only cycles1137842700..1137860300 at native
407E and trial04 63ED mode-poll instructions and fixed IRQ boundaries. No ROM
change. Control reads STAT C1 before VBlank IRQ; interrupted stack PC4088 is
the AND03 instruction, AF C160. After VBlank and STAT handlers return, it still
uses that saved mode1 value, decrements to zero and returns through408D at
1137860152 despite live STAT already C2. Trial interrupts at63FA (JR NZ), AF
FF60, from its earlier mode0 read. It consequently branches back to63F5 and
polls the new frame, missing this wait completion. This directly explains the
first divergent iteration; it does not establish a general repair or justify
reducing the100 waits. Preserve native polling phase when selecting the next
orchestration change rather than padding a particular replay into agreement.

Both new complete primary captures are byte-identical to the respective prior
`return-wait-counter-*-off-01` captures (reused controls, rehashed raw PCM,
video, state, input timeline and metadata; same exact ROM and own state).
Existing full-route audio failures remain. Added one evidence test for saved
AF/return-PC and branch behavior. No hardware action; no emulator left running.

## First divergent card wait isolated; observer neutrality verified (#45)

Fresh own-state4440+240 captures `return-wait-counter-control-01` and
`return-wait-counter-trial-01` add B and STAT to the loader trace plus the existing
IRQ cost observer. Exact ROMs remain d7ea4f6b (native control) and24b78374
(failed local-wait trial04); no ROM change. Probe SHA
f11d9bdc547553d7f96d672230574125dd187df0753b9826a6a662c47cefbf50.
Both loops show B descending100..1 at SP DFE7, with102 breakpoint rows:
raw row count is not the iteration count. First-entry cycle differences for
B=100,99,98,97 are32,32,-40,129968. The third wait (B98 to97) first diverges
substantially: control B97 at frame59/cycle1137860216/LY9 versus trial frame60/
1137990184/LY151. Frame59 VBlank returns at1137859408(control) and1137859400
(trial); subsequent STAT returns at1137860080/1137860072. These nearly identical
IRQ boundaries suggest a polling/instruction-phase difference, not an extra
loop iteration or a substantially longer trial IRQ. Exact interrupted PC and
the mode-test instruction are the next missing observations; cause not yet proven.

Fresh same-ROM/state `return-wait-counter-control-off-01` and
`return-wait-counter-trial-off-01` match their respective observer-on captures
byte-for-byte across all240 primary video/state/input timeline frames and native
PCM (including WAV), verified by hashes. Restored epochs pass. This validates
these bounded observations, not full-route audio fidelity: the6000-frame audio
failure remains open. Two evidence tests rehash capture files and preserve the
100-counter sequence and first large divergence. Rivalmage untouched; process
check confirms no local mGBA remains running.

## Card wait locality experiment does not recover the lost frame (#45)

Added optional read-only `ENTRY_RETURN_LOADER_TIMING` to distinguish card fade,
100-wait entry and downstream loader calls. Own-state240 probes
`return-loader-control-01`/`return-loader-trial-01` begin at exit4560;
`return-card-wait-control-01`/`return-card-wait-trial-01` at4440. The latter show
native0F47 completes at1137428688 control versus1137428720 trial03, only32
master cycles apart. Subsequent100-wait entry is1137428808/LY152 control versus
1137430472/LY0 trial03. Custom return-card fade starts a frame late, before
the later map loader; the delay is not introduced solely by music emission.
These timing probes have not received new same-source on/off qualification.

Tested a specific causal hypothesis: eliminate the bank transitions between
initial card fade and100 waits. Explicit `--local-card-waits` copies the native
instruction sequences into bank20 with relocated CALLs, retaining the four-tick
shade waits, fixed RST08 service, all100 mode waits and native comparison loops.
No shortened delay, palette change or input retiming. Variant04 SHA
24b78374dc8dc55f24778b2688ac7d60e47b953881a0394f484e34559859a729.
Default02 and direct-sound03 remain reproducible. Native source preimages and
unchanged wait bodies/counts are tested before building.

Fresh3600 `return-local-wait-entry-01` matches prior entry trace/images. Own
state SHA f3a2ec78dbf434df633ee15664beb941d8b14f5aa1144aa5cb845c006507717b feeds
fresh6000 `return-local-wait-exit-01`. It FAILS the intended timing improvement:
music request remains exactly1161391592, accept1161408856; dungeon4667,
incomplete map4667..4671 still fullywhite, complete visible4687. Full audio
`return-local-wait-audio-pair-01` still FAILS silence interval/block equality,
3031848 differing sample frames beginning9803918; WAV SHA
0887a5312caffc178b72950c7167a845700a182f595ff32de8675d3bf6b1f849.

Own4440+240 `return-card-local-wait-trace-01` confirms local wait entry is now
1137428840/LY152, only32 cycles after control, but card fade still begins at
frame190 versus189. Thus removing the scanline wrap alone is insufficient;
do not claim that the bank-switch gap alone caused the lost frame. The optional
`ENTRY_RETURN_LOCAL_WAIT_TIMING` sites are explicit trial04 labels63C1/63E6,
not universal bank20 addresses. Preserve this failed experiment without release
integration. Revisit the native wait's interrupt/polling phase before another
patch; do not compensate by reducing the wait count or retiming the replay.
Two new evidence tests preserve this falsification. Rivalmage remains untouched.

## Direct native sound request restores ordering, not total return timing (#45)

Added explicit `--direct-sound-request` to the private-return builder. Default
still reproduces9c7e. Variant03 replaces the unnecessary native-bank thunk for
fixed RST38 with the original `PUSH AF; LD A,13; RST38; POP AF; LDH A,(FFB7);
LD (D880),A` sequence. No interrupt mask, earlier request or altered music command.
Exact variant SHA73ee08d7b5ad4f2af16a0e5c297856150908af76a0d2543ec0865ffcafcfb770.

Fresh3600 `return-direct-sound-entry-01` retains the prior complete entry trace
and all captured PNGs. Own frame3600 state SHA
bc2b7d21c54722c2d07c209cdf9cc5e616ed3ca792ed3a3d4c9efdd1a878a6be feeds fresh6000
`return-direct-sound-exit-01`, with sound-command observer and guarded native
capture. Epoch PASS, all6000 frames retained. Request13 now at1161391592
(640 master cycles earlier than far-call trial), accepted1161408856 in scene02,
not scene18. The request-to-scene publication order is restored for this replay.
No claim of observer neutrality for this new full6000 run; the preceding bounded
on/off checks remain bound to their own exact ROMs and states.

Return remains dungeon4667, incomplete-map frames4667..4671 fullywhite, first
visible complete map4687.100-frame visibility check has no exposed incomplete
map. Full untrimmed audio `return-direct-sound-audio-pair-01` still FAILS silence
interval/block equality: first difference9803918,3031865 differing sample frames,
RMSratio1.0043764855. Clipping/discontinuity guards pass. WAV SHA
547d65bbfc4175e57206f096acd9f7db05141ea55e4bf5d0cc614e243487d439.

This is a partial ordering improvement, not a fix for the larger late-loader
arrival: stage music remains requested roughly one frame later than control.
Three new evidence tests retain corrected ordering against the failed far-call
control, map visibility and full audio rejection; the builder test verifies the
original fixed RST sequence and unchanged default output. Next measure private
card completion versus native loader entry to locate the preceding delay. No
release integration, deployment, issue closure or Rivalmage action.

## Sound divergence narrowed to late stage-music handoff (#45)

Fresh own-state240 probes from each ROM's exit-frame4320:
`return-sound-control-01` (d7ea) and `return-sound-trial-01` (9c7e).
Both have357 timer events and identical sound-command requests/acceptances.
First timer-cycle mismatch is event214/frame144: trial56 master cycles earlier;
the subsequent channel triggers mostly differ by8 cycles. Untrimmed short PCM
comparison `return-sound-short-audio-01` passes the existing dropout/silence/
level/clipping/discontinuity guard, despite82772 differing sample frames, first
323694. This short PASS does not supersede the retained full6000 FAIL.

Full6000 silence intervals agree for the first18 intervals. The nineteenth
starts10180407 in both, ends10239690 control versus10241167 trial:1477 samples
(about11.27ms) later. The count is21 control versus20 trial; later gameplay
also diverges, so this is not a globally constant shift to be aligned away.

Fresh own-state240 probes from exit-frame4560, `return-handoff-control-01` and
`return-handoff-trial-01`, narrow the meaningful mismatch: command13 is requested
at cycle1161249864/frame105 control versus1161392232/frame106 trial (142368
master cycles later). It is accepted1161305584 in scene02 control versus
1161393288 in scene18 trial (87704 cycles later). The command is delivered,
not missing, but the experimental loader's sound request/scene publication
handoff is delayed and reordered relative to the timer interrupt. This does
not yet prove which preceding wait or call causes the delay.

Observer-neutrality checks completed on trial's early240 and BOTH late240
replays: `return-sound-trial-off-01`, `return-handoff-control-off-01`, and
`return-handoff-trial-off-01`. Each exact same-ROM/same-state on/off pair has
byte-identical full native PCM, states, video, input timeline and telemetry.
All restored capture epochs PASS. No claim for untested longer observer runs.
Three evidence tests preserve this neutrality, the late command and the full
failure. No ROM change this step. Next: compare the end-of-card native wait
and cloned loader call overhead; in particular the clone unnecessarily makes
native RST38 a far call, allowing an interrupt before the following scene store.
Do not trim PCM or loosen gates to erase the delayed handoff. Rivalmage untouched.

## Private return orchestration: entry restored, return hidden, audio still FAIL (#45)

Implemented experimental `build_return_only_fade_trial.py` using the six-byte
fixed callback and bank20:$6314 private loader/card/fade orchestration. Native
15DA CALL0F7A and bank1:75F0 JP0F33 are restored; compact CGB fade bodies remain
unchanged. Only1498/149B enters the new orchestration. Exact parent ec8be288;
current trial02 SHA256
`9c7e4f94a5dcb898faac58c9f9af66a416fa92be6b6843b1468549d3f61788ea`.
Not integrated into the source release builder, deployed or release-qualified.

Important correction:1498 is NOT exit-exclusive. Fresh cold2700 trial01
`return-only-fade-entry-01` hits it at2426 in scene02/stage00 on secret entry.
The unguarded clone f6176ff643f397f918dfc92a1c66bf939a73ff4493f44c4eff5e4f79146a9fb1
therefore fails entry parity (three retained PNGs differ). Preserve it as a
negative control. Trial02 checks destination stage after native169C and resumes
native146C/bank1 for nonzero stages. This retains the previous stage00 scope.

Fresh2700 `return-only-fade-entry-02`: all2700 telemetry rows and31 PNGs equal
`secret-fade-native-timing-01`;15DD ends at exactly cycle372828952/frame2652.
Not instruction-cycle identical:0F33 starts40 master cycles later and0F7A eight
later than control. Fresh3600 observer-off `return-only-fade-entry-03` also has
the entire trace and every retained PNG equal to the native-fade control entry.
No broad observer-neutrality or all-scene timing claim.

Own frame3600 state SHA fdfb3c32c6d5370f0471c8962e30b55c0a8805d097e9758d14d37ba4c8d7e1da
feeds fresh6000 `return-only-fade-exit-01`, using the guarded native tap and a
PASS restored epoch. Boss534, return tosecret2533, destinationstage0 at4463,
card4481, dungeon4667 (control4666). Native map mismatches4667..4671 are all
fullywhite; firstnonwhite4687 has complete map. No exposed incomplete map in
the100-frame checked window. Inspected native entry2700 and returned4800 PNGs;
returned Stage1 terrain is visible and colored. Cold setup position/inventory
assistance and replay health assistance remain declared in receipts.

Full, untrimmed native audio `return-only-fade-audio-pair-01` versus d7ea control
still FAILS silent-block and digital-silence-interval equality. First difference
is now sample9803918, not0: pre-return PCM matches.3037073 sample frames differ
through13167007, RMSratio1.0076808062; clipping and maximum-discontinuity guards
pass. Candidate WAV SHA a8f9c914937646bdfed1fbc3e80c8cf9c5183520f3ff0debc736c3c42d8d6dfb.
Do not relabel this partial improvement as audio acceptance. Tests preserve
patch scope, the failed unguarded variant, entry matches AND timing differences,
hidden map initialization, eventual visible output, and full audio failure.
Next narrow investigation: transition-time sound/timer behavior now that the
pre-return gameplay/audio history is matched. Rivalmage untouched; issue open.

## Six-byte return callback resolves the immediate size obstacle (#45)

The eight-byte standalone callback rejected below is unnecessary: existing
fixed $099D is `CALL $0061; POP AF; RET`. A six-byte callback at $00C1 can
therefore use `PUSH AF; LD A,20; JP $099D`. This fits the seven-byte padding
without changing $00C8 or the input service ending at $00C0. No ROM has been
patched yet; absence of computed/data references into the padding still needs
review before integration.

Added `scripts/diagnostics/return_bank_call.py` with that callback and a native
call thunk. Three PUSH AF instructions reserve target/callback words and save
original flags; saved HL is restored after writing the synthetic stack. The
existing epilogue restores AF after the bank switch. This avoids losing flags
to LD HL,SP+n or clobbering native output A during the callback. It also avoids
new persistent WRAM allocations. FF99 and DC09 follow the selected bank.

`tests/test_return_bank_call.py`: three tests pass, covering all 16 flag-nibble
combinations for bank1/bank13 calls, native AF/HL input preservation, changed
native AF/HL outputs surviving return, balanced stack, byte preimages in exact
ec8be288, and rejection of altered mapper/epilogue/padding bytes. This is a
bounded instruction model, NOT emulator execution, cycle acceptance, audio
acceptance, or a verified game fix. Each native call has an extra callback
return word: stack-inspecting callees and interrupt/bank behavior still require
explicit review. Next step is return-only orchestration using this primitive,
restoring original shared fade hooks and testing cold entry before full return.

## Return-only relocation: reject occupied and executable padding (#45)

Rechecked the actual ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b
image before allocating a callback trampoline. The historical description of
bank1:$7C91 as an unused cached-Ted tail does not apply to this candidate:
its nine bytes are `3E10210040E5C36100`, the live bank16 trampoline. Bank1:$6FE4
contains `FA80D8FE10C29542C3917C`, selecting that trampoline for Ted. Neither
location is available. The candidate's bank20:$7C91 is also populated, so a
mirrored bank-switch continuation cannot be placed there either.

The only eight-byte zero span in bank1 below $6000 is $50C4..$50CB. It is
executable fallthrough, not unused space: `CALL $50DF; LD ($DB3E),A` immediately
precedes it and `CALL $50DF` immediately follows it. Replacing it with a
callback would corrupt collision processing; adding a branch around a callback
would also change that existing path's timing. No allocation made there.

Fixed-bank $00C1..$00C7 contains seven zeros after the existing service's RET,
with live LCD-enable initialization beginning at $00C8. This is not enough for
the proposed eight-byte AF-preserving callback (`PUSH AF; LD A,bank; CALL $0061;
POP AF; RET`); do not let its return fall through into $00C8. Zero-span searches
are placement leads only, not proof that code/data references are absent.

This eliminates the retired-cave placement proposal without modifying a ROM or
running another timing trial. Next design work must establish a genuinely owned
callback/continuation region or relocate an existing owner with ABI and timing
preserved; shortening the already-failed shared dispatcher is not a fix.
Issue remains open. Rivalmage and all prior raw evidence remain untouched.

## Shortened native fallback does not resolve phase regression (#45)

Read-only bank-call review ruled out treating118B as free space: it contains
an existing bank24 helper. Generic0847 calls selected-bank6C80 and switches
again using returned A; it is not an arbitrary-address transparent far call.
No allocation was made in those locations or in sparse WRAM.

Bounded alternate `build_native_fade_dispatch_trial.py` patches only bank20's
existing non-menu branch and an authenticated FF cave at5D00. Menu fallthrough
bytes remain unchanged. For stage!=0 and callers15DD/15A2, it reaches the existing
native fade/card fallback more directly. Experimental32f85ef6b4d0799c852a749ac55f99df9d44c57ef713f1ec9c6ba1a7b417e41f.
Fresh cold2700 `native-fade-dispatch-entry-01` completes but FAILS the intended
timing restoration:15DA entry now matches native cycle367096768, yet0F7A costs
1104 cycles vs48 native (previous1216);15DD still returns2649 vs2652 native.
Card0F33 starts361315152 vs native361313392. Reducing dispatch alone does not
remove the banked-wrapper cost or fix native wait phase. Keep this failed variant;
do not integrate or launch broader qualification. Two tests preserve patch scope
and the measured failure. Return-only interception remains the needed design.

## Secret-return caller ownership traced before hook relocation (#45)

Restored ec8's own exit frame4320 in `secret-return-callers-02` for600 frames;
controller A pulses and health assistance retained, no state retarget. At161,
1482 runs scene09/stage07;1498 CALL169C is reached with bank0D/SPDFED, then
149B JP146C with bank01/SPDFED and stage00. Shared1473 CALL1594 follows;
75F0 card tail has SPDFE9 and shared15DA fade call has SPDFEB. This confirms
a distinct exit branch before the shared loader, but not a safe placement for
a banked trampoline. Banks0/1 contain no24-byte all-FF cave; do not overwrite
zero-filled data or assume a new bank can call bank1 routines transparently.

First trace `secret-return-callers-01` placed two breakpoints on operand bytes
1499/149C and saw no hits there. Corrected to instruction starts1498/149B,
preserving old trial. Both complete600-frame traces are byte-identical. Extended
`test_secret_entry_fade_timing.py` checks bank, stack and destination-stage
ownership. No ROM patch or readiness claim from this diagnostic evidence.

## Secret-entry native fallback timing directly measured (#45)

Read-only `ENTRY_SECRET_FADE_TIMING` observes fixed15DA/0F7A/15DD/15E2 and
bank1 card tail75F0/0F33 only in2400..2700. Fresh2700 cold captures
`secret-fade-native-timing-01` (d7ea control) and
`secret-fade-fastpath-timing-01` (ec8) retain their respective observer-off
trace prefixes and all shared captured PNGs byte-for-byte. No PCM-neutrality
claim, since these timing runs did not capture audio.

Both enter75F0 at cycle361313360, frame2570. Native0F33 begins361313392 in
control versus361315272 in ec8:1880 extra master cycles and LY152->0.
Later15DA->0F7A dispatch costs48 control versus1216 ec8. Both use native0F7A
with scene09/stage07 and return stackDFEB, but return15DD is frame2652/LY151
control versus2649/LY0 ec8. Thus native fallback is NOT timing-transparent:
the added dispatch changes the phase-sensitive native wait behavior by3 frames.
`tests/test_secret_entry_fade_timing.py` preserves this evidence and observer
comparison; one test passes without labeling the observed behavior acceptable.

Next implementation must move custom fade interception off unrelated card and
scene-entry call paths, rather than adding a timing delay or retiming test inputs.
Preserve the scoped secret-return CGB fade and correct initial-map copy. Shared
75F0 and15DA hooks currently affect stage07; a replacement needs caller/bank/stack
ownership review before patching. No ROM change in this diagnostic step.

## Original-fade fastpath control also exposes pre-return phase divergence (#45)

Added explicit diagnostic-only `--native-fade-control` to the fastpath builder:
exact916ebb parent only, output
`d7ea4f6bbb1e63a29ac5aba42e8c260bb6d246dd9207d65e6d8326bba7382004`.
Default remains exact126dd; neither parent is broadly accepted. Native15DA/75F0
fade calls remain unchanged in this control, and the optimized map gate matches
ec8be288. Historical receipts were not rewritten after the builder change.

Fresh own cold3600 `initial-map-native-control-entry-01` and restored6000
`initial-map-native-control-exit-01` completed. Both control and ec8 enter
scene09 at2608, but their entry traces differ (worldY444 rows, C4 488 rows,
mode/bonus/room3 rows each); only30 of38 retained PNGs match. Therefore this
control also does NOT establish equivalent gameplay/audio history at restore.
Control boss starts534 vs527; dungeon return4666 vs4679. Full unaligned audio
`initial-map-native-control-audio-pair-01` FAIL: silence intervals/blocks differ;
level/clipping/max-step checks pass, RMSratio1.0003457797.13023564 differing sample
frames, beginning0. No trimming/retiming; all differences retained. Control WAV
SHA03a4556c5b427ace70c5b34fb9e4863f925dbb201aa03200a654d117e7493c41.

Source inspection identifies an additional path to trace: return-fade hook15DA
is dispatched even for nonzero stage and then falls back to native fade. Secret
scene initialization therefore pays dispatch overhead despite not owning the
new CGB fade. Exact causal timing still needs tracing; do not infer an audio fix
from this source finding. No ROM integration, hardware action, or issue closure.

## Fast-path trial full return: hidden initialization, audio gate FAIL (#14/#45)

Fresh ec8be288 cold3600 `initial-map-fastpath-entry-01` and own-state6000
`initial-map-fastpath-exit-01` completed with the guarded native tap and valid
restored capture epoch. Setup uses dense inventory, position and health assistance;
exit retains health assistance. Secret boss scene0A begins527, returns09 at2548,
stage0 at4481, card18 at4499, dungeon02 at4679. These are NOT timing-equivalent
to126dd (dungeon4801); entry routes already differ before the restored checkpoint.

All five incomplete-map frames4679..4683 are fully white in the untouched native
video. Map complete4684; first nonwhite frame4699 has a complete map. The next65
dungeon frames have no visible incomplete-map publication. This is a bounded
native-output check, not every transition's acceptance.

Full unaligned audio comparison `initial-map-fastpath-audio-pair-01` versus126dd
FAIL: silence intervals/blocks differ, max sample step19232 versus18624,
RMS ratio0.9972459692,13129132 differing sample frames starting at0. Both contain
13167008 stereo samples. Candidate WAV SHA256
`d134e9869e91323b1b85d3af92b6fd2c63c33779ad61c7bb001a13d6fb3328d8`.
The changed route/initial audio phase prevents attributing this failure solely
to transition audio; do not trim, retime, waive, or claim audio fidelity. Two new
`test_initial_map_fastpath_return.py` checks rehash raw evidence and preserve both
hidden map initialization and the audio rejection. No integration/deployment.
Next qualification needs an appropriate independently generated parent route
with matching gameplay/audio history, not a cross-ROM state retarget.

## Doorway timing isolated; experimental common-path repair (#14/#45)

Fresh1216-frame chain bisection: `doorway-bisect-chunks-01` (2b797) reaches
Y1356, while `doorway-bisect-initial-map-01` (916ebb) reaches1352. Both enter
scene02 at599 and first loop637; total loop observations133 versus132. The
initial-map gate, not subsequent fade changes, is the first divergent step.
Read-only `ENTRY_MAP_GATE_TIMING` measures fixed13CD..13D2 at frames1000 onward:
common active1/CE0 calls cost600 master cycles in parent,656 after the prefix.
Interrupt-stretched parent calls are retained, not filtered into timing parity.
Observer runs `doorway-gate-parent-01` and `doorway-gate-initial-map-01` each
match their own observer-off trace, loop log, and final PNG exactly (no audio claim).

New `build_initial_map_fastpath_trial.py` preserves the original CE0 instruction
path and moves the inactive check to the synthetic-skip branch only. Inactive
still returns bank1/Z to demand the real initial copy. No new RAM or palette
changes. Exact experimental ROM
`ec8be28897810fac01a8918a0403900780015bf6703531f0f82ae259f209f21b`, from126dd.
Fresh `doorway-gate-fastpath-01` passes unchanged reviewed doorway gate, zero
exposed pixels, position1356; complete1216-row trace, loop log, and final PNG are
byte-identical to2b797 under identical inputs, without alignment or retiming.
Three tests cover branch layout, patch scope/pin, and failed126dd control.
Still experimental: full secret-return fade/map/audio replay and broader
regression validation MUST precede integration or deployment. No hardware touched.

## Current doorway replay fails position alignment (#14)

Fresh `return-fade16-doorway-01` on126dd uses the historical cold1216 recipe:
position1240/1344 at1201, Down through1212, health assistance. It ends at
1240/1352, camera0808, not the reviewed1240/1356 camera0C08. The unchanged
doorway verifier rejects it; native image inspected, Sara remains visible.
This is NOT proof of occlusion failure at the reviewed footprint or acceptance.
Fresh `return-fade16-doorway-parent-01` on665a with the SAME current probe,
runner and settings reaches1356 and passes. Thus a candidate-chain timing or
movement difference remains, not merely drift from the historical harness.
Cause and first changing build are not yet isolated. Do not retime acceptance
or relabel this attempt PASS. Both runs exited0; their receipts preserve inputs,
assistance, probe and runtime bindings. No ROM changes or hardware actions.

Separate `return-fade16-floor-01` cold1800 patrol checks frames1201..1800:
zero Sara behind-BG priority flags and zero installed-helper mismatches across
600 rows. This narrow floor guard does not replace doorway/collision/audio
qualification. `tests/test_return_fade_doorway_evidence.py` preserves the failed
alignment and passing parent/floor controls. Next: isolate the first candidate
chain step changing the same-input doorway position before changing gameplay.

## Current Ted checkpoint and repeated menus (#32/#36)

Candidate `126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b`
was missing from the generator's relocated-Ted-latch recognition. Added only its
exact hash, not approval for Penta generation or historical state retargeting.
Ted bank17 is byte-identical to d744, SHA256
`6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7`;
fixed-bank differences excluding checksums are only 15DB/15DC (return-fade call).
No ROM bytes changed in this step.

Fresh `tmp/return-fade16-ted-entry-01` passed the checkpoint gate (settled294,
saved300); inspected native image shows Ted and patterned arena, not blank white.
Its own state was replayed Left600 in `return-fade16-ted-escape-01`, then
`return-fade16-ted-menus-01`: all1080 frames and all three menu cycles PASS.
Escape/menu replay used controller input only, no memory writes; entry generation
is assisted, so this does not qualify natural progression, audio, or hardware.
`tests/test_return_fade_ted_profile.py` authenticates the latch ABI, rejects an
unknown mutation, rechecks the current menu evidence and retains the old
`ted-menu-broken-roundtrips-gated-01` failure as a negative control. Issues stay open.

## Reproducible current candidate from cartridge sources (#45)

Added explicit `--return-fade` to `scripts/build_stream_regression_candidate.py`.
It requires all predecessor experiment flags, authenticates each of five
additional intermediate ROM hashes and leaves defaults unchanged. Fresh
`tmp/return-fade16-source-01` builds from the original cartridge and palette
sources without retained candidate ROM inputs, yielding exact
`126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b`.
The receipt hashes transitive Python sources and records release_qualified=false.
Reproduction command (choose a fresh output directory):

```sh
uv run --with pillow --with pyyaml python scripts/build_stream_regression_candidate.py \
  --output tmp/return-fade16-source-01 --presentation --arena-alias \
  --arena-completion-safe --secret-sound-alias --return-fade
```

This closes the source-construction gap, not remaining gameplay/audio/hardware
qualification. Tests cover exact reconstruction, unknown-parent rejection,
required flags before output writes and fresh transitive source bindings.
No deployment, default-ROM change, commit or release tag.

## Current Shalamar repeated-menu/low-health check (#27/#34)

Fresh exact126dd0b7 dispatcher checkpoint `return-fade16-shalamar-entry-01`
settles101/saves113. Controller-only1080-frame replay
`return-fade16-shalamar-phase721-01` completes all three menu cycles and passes
each endpoint/cadence/map check, but overall raw scene-residency remains FAIL:
D880 becomes0B at952 through1080. This is the same129-frame low-health sound
alias interval as parent916ebb `current-map-shalamar-phase721-01`, not a newly
observed arena departure. FFB7 stays0C and every aliased frame retains the
authored Shalamar C600 palette policy, unlike the retained broken d744 control.
All1080 PNGs equal the parent; final native screenshot inspected, cyan boss
and patterned arena intact. Two classification tests pass while explicitly
requiring the overall replay FAIL to remain visible. Entry is assisted, menu
replay has no memory assistance; no full-route/audio/hardware acceptance.
No ROM modification or deployment; read-only process check clean after run.

## Current handheld-enemy palette isolation (#25)

Exact126dd0b7 entry3600 screenshot inspected: gray/olive handheld actor
visible in scene09. Fresh own-state `return-fade16-handheld-menu-01` and
`return-fade16-handheld-resume-01` each complete180frames with Select6 and
no observer memory writes; menu flags1 then0, scene09 retained, OBJ3 remains
000018634e2e8410. Retained same-ROM entry1200 and exit6000 scene02 states
both have original primary OBJ3 00001f0017000f00 matching ROM36858, not the
handheld override. Four handheld tests pass, including existing old-red
control and exact patch boundaries. Initial route setup was assisted; menu
continuations were not. Native screenshot after resume inspected, but actor
has moved offscreen there; no claim of whole-sprite pixel equality. This
establishes bounded routing/menu retention, not user art approval, natural
full-route or hardware acceptance. No new ROM edit or deployment.

## Current Gargoyle patrol/menu regression (#21)

Fresh `return-fade16-gargoyle-patrol-01`, exact126dd0b7, cold2400frames:
native spawn assistance and DCBB health refill, patrol after1200, Select at
1350/1470. No inventory/cursor overwrite. Completed0; geometry oracle reports
zero split frames,1578 coherent fully visible frames,166 not fully visible.
Native1560 PNG inspected: intact purple Gargoyle over patterned corridor.
Rehashing complete raw video, PCM, WAV and timeline verifies byte identity
with retained repaired665a33b6 `gargoyle-latest-patrol-01`, not the reported
broken4f5a build. All2400 frames and5272352 stereo samples are retained.
Cold captures still fail the restored-epoch validator by design; this is
bounded cold-route equality, not restored-audio/hardware qualification.
Geometry tests retain reported18-split negative control and censored frames.
No ROM edit, deployment or hardware change; red-bleed trigger #20 remains
unreproduced by this route and is not declared fixed.

## Direct title LCD-exit timing (#35)

Input follow-up: fresh `title-input-{parent,guard}-01`210-frame runs use a
bounded read-only probe at native3B26/3B37/3B3F during frames190..195.
Both accept A at194 with A02, carry set (F10), FF93=01, FF94=01 and identical
stack/scene transitions. The -53448-cycle difference is already present at
native selection return3B26, before LCD-off. FFD4 is91 versus90; earlier
neutral loop returns have different raster phases too. This rules out a
missed A edge or different selected entry in this replay, not an upstream
timing effect. Each new run matches its previous same-ROM LCD-observer run's
entire210 screenshots, decoded machine states, inputs and telemetry. Two
direct timing tests pass. Native audio was not recaptured and no ROM patch
was made; avoid inventing a delay merely to equalize file lengths.

Fresh210-frame cold runs `title-lcd-exit-parent-01` (106c2e01) and
`title-lcd-exit-guard-01` (8ff1c98d) complete0 with identical input logs and no
memory assistance. The existing LCD write observer records nine FF40 writes
in each, same frame/PC/old/new sequence. Cycle deltas are
0,0,0,+4032,+4032,-53448,-53448,-53448,-53448. At frame194, PC53CF,
the title-exit LCD-off write is at cycle27544582/LY101 for parent versus
27491134/LY38 for guard. Thus the earlier PCM-length difference corresponds
to a direct game LCD-exit timing difference, not just a capture count anomaly.
The pinned core GBVideoWriteLCDC resets its frame-event schedule on LCD-off;
the next task is upstream title-loop/input scheduling, not PCM padding.
The new direct-trace regression test passes. This diagnostic does not prove
why the slower helper leads to earlier exit, audio equivalence, hardware
correctness, or current-candidate full qualification. No ROM changes.

## Current cold-title palette access (#35)

Fresh serial 600-frame runs `return-fade16-title-cram-01` and
`return-fade16-title-control-01` use exact126dd0b7, explicit audio settings,
normal probe boot inputs and no memory assistance. Both complete0. All2984
observed CRAM writes pass the unchanged access checker, with zero blocked
writes. Native title frame180 was visually inspected: blue background, yellow
title and colored menu are present. Inputs and all600 telemetry rows match
observer-on/off; all11 PNGs and all11 decoded71680-byte machine states match.
Full savestate files differ only in one gbAx extension with type0x101 and
length8: the pinned core names this EXTDATA_META_TIME. This is not full-file
identity; raw files are retained. New `test_return_fade_title_cram.py` passes
and rejects a mode3/LCD-on mutation. No native PCM was captured here; prior
title timing/audio concern remains unqualified. No hardware changes.

## Current-candidate palette editor support (#19)

The bridge now accepts exact candidate
`126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b`
when explicitly selected; its default source is unchanged. A new actual-ROM
test first failed with the unsupported-pin error, then passed after adding
that exact pin. All 15 primary rows equal authenticated star parent d744124d.
Each edit is checked with all primary rows populated in a synthetic MiSTer
state: only the selected active row, ROM primary row and checksum may change.
The complete bridge suite passes 18 tests (2.696 seconds); a one-byte unknown
variant is still rejected. No SSH, deployment, server restart or emulator run
was performed. This is not live Apply/Resume qualification, nor a solution for
scene-override ownership (#39) or palette backups during transitions.

## Combined-entry fade trial: actual return still fails (#45)

Trial16 star route (#22): `return-fade16-star-live-01` cold1500 uses only the
existing one-time position assist1192,624. Native PNG inspected; star crop
72,80..88,96 exactly matches reviewed d744 gold fixture and differs from broken
gray fixture. Three center pixels are255,255,0. Whole scene differs from old
d744 (bbox40,0..104,122), so no whole-screen equivalence claimed.
Own-state native Down20 collection120 frames yields inventory DCD1=0F
(zero-based offset20 from DCBD; corrected from the erroneous slot19 note);
Select6 opens menu at360 and closes at180, retaining that inventory.
First resume trial `return-fade16-star-resume-01` exited-11 despite final capture;
retained as FAILED. Read-only process check found no remaining emulator;
same-input fresh `resume-02` completed0. Crash cause unverified, not hidden.
New route test verifies exact ROM/state chain, RGB/broken control, inventory,
and paused/resumed flags. No audio or full teleport-route/hardware claim.

Trial16 Stage2 Continue validation (#28): fresh exact-ROM assisted entry states
for Stages2..7 generated serially in `return-fade16-stage-states-01`, each entry
metadata reports expected scene/stage and unsafe_attr0. This is entry coverage,
not stage-completion evidence. Stage2 state CRC/header was checked against
126dd0b7 before replay. Three6000-frame prompt-relative Up-approach runs
`return-fade16-stage2-continue-{a,neutral,start}-01` PASS: death2352; A edge
observed and resume2470; neutral/Start show no A edge and time out to title3314.
All start input2414. Stimulus includes one credit and HP1 then native movement
damage, so this is not reproduction of the player's entire corrupted history.
New regression test verifies exact state/ROM binding, reruns the oracle and
retains reported-build A failure as negative control. No hardware changes.

Trial16 restart regression expansion (#18 and prior restart reports): both
`return-fade16-restart-sequence-01` (hazard-area movement, HP0 acceleration,
saved-game selector fixture) and `return-fade16-restart-natural-01`
(movement-driven native damage, B dismisses low-health inventory) PASS the
existing two-cycle Game Over/title/new-game oracle. Each checks482 same-age
title frame pairs and102 consecutive settled Game Over frames. Hazard route
also compares score-selector and stage-card captures before/after both cycles.
Game Over/title PNGs visually inspected. Both test exact126dd0b7 candidate,
probe0422fcd3, verifierf79a61bc, sequencee856eda9. Regression test rehashes
all captured artifacts and reruns the existing geometry/color/sequence oracles.
This is local emulator rendering/transition evidence, not hardware acceptance
or an audio test of the restart routes. No deployment or closure.

Trial16 qualification expanded locally. Exact6000 assisted repeat
`return-fade-audio-enabled-exit-16-repeat` matches every full native capture
hash plus inputs/telemetry. Fresh own4680 short240 observer/control pair
`return-fade-sound-trial-{16,control-16}` likewise matches all primary hashes
and inputs. All512 private fade writes occur mode1 LY144..147; full640-write
trace retained. No continuous health assistance pair
`return-fade-nohealth-exit-{16,parent-01}` reaches card4807/dungeon5001 with
HP55 and has all6000 telemetry rows identical. It starts from assisted setup
states, so is not unassisted cold gameplay. Its full PCM guard
`return-fade-nohealth-pair-16` PASS, RMS0.9998851644,13773 different samples
retained (11052125..11165476). Inspected native RGB remains white during load.
Four card-only regression tests now rehash repeat/observer captures, assert
palette timing, and recompute both audio gates. Still not global release or
hardware qualification; other known bugs remain in scope.

Card-only compact trial16 passes the unchanged full-route PCM guard.
Trial15's largest21326 sample jump is atsample13023144, replayframe5935,
scene02 active gameplay, about19seconds after resume (parent maximum18624
at13020272/frame5934). It is not a contemporaneous palette-upload spike.
To isolate phases, `build_return_card_compact_trial.py` pins trial14, copies
four compact card upload routines into verified-FF bank20:5083..5518, and
redirects only its four deadline-card calls. Original return uploads and
window routine remain byte-identical; no new RAM state.
Candidate SHA `126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b`.
Fresh cold3600 telemetry matches parent; own6000 assisted native capture
`return-fade-audio-enabled-exit-16` enters dungeon4801 and sampled native RGB
keeps loading white. Unchanged guard `return-fade-audio-enabled-pair-16` PASS:
silence intervals/blocks match, RMS ratio1.00004951078, no added clipping or
larger discontinuity. Whole752304 differing sample frames remain recorded,
first10595915,last11499605; this is not waveform/perceptual equivalence.
Regression test rehashes WAVs and reruns full guard, requiring trial15 to fail
and trial16 to pass. Further scope/raster/repeat qualification remains; no
hardware deployment or issue closure.

Trial15 composes the compact upload bodies with trial14's unchanged deadline
schedule. Builder now accepts both exact parents and records the actual parent
hash, preserving prior trial12 bytes. Candidate SHA
`de9f55bacefa10e55c65d6346ef504a18813925d2ff1aebf0efe10db30c5ec93`.
Fresh explicit-audio cold3600 telemetry matches parent; own6000 capture
`return-fade-audio-enabled-exit-15` enters dungeon4801 and differs in one
telemetry row. Native RGB collage inspected: white initialization retained.
Full unchanged audio guard `return-fade-audio-enabled-pair-15` now matches all
silence intervals/blocks but FAILS maximum sample discontinuity:21326 vs18624.
RMS ratio0.99988795098,2313200 differing sample frames, first10632696 through
13167007. Thus smaller masked work does not alone qualify audio; retain the
new failure instead of selecting only the improved silence metric. No changes
to guard thresholds, no retiming/normalization, and no deployment.

Harness audio default fixed under #43: `run_secret_entry_probe.py` now defaults
ENTRY_AUDIO_ENABLED=1 for cold and restored runs alike and always records
audio_options. Explicit opt-out remains visible in environment/receipt.
Four mocked launcher tests pass, including exact audio arguments without a
native tap. Fresh default cold3600 `return-fade-default-audio-entry-14` has
the complete71680-byte serialized state and telemetry identical to the prior
explicit-audio trial14 control. New runner SHA:
`52f4f4f36657ec83de7b6af3923f344cf70e67a929d057a09ffa88abcfae8264`.
Old receipts stay bound to the old runner; no historical evidence rewritten.
Read-only comparison of short parent/trial14 sound traces finds122 identical
ordered register/value events: cycle deltas97x0,11x8,5x-8,3x16,3x1232,
1x3064,1x-24,1x24. Largest delay is FF23 atrelative149; three delayed events
at165 are FF23/FF19/FF1E. This supports investigating interrupt scheduling,
not a missing/changed sound command. It does not qualify full-route audio.

Audio startup confound (#43/#45) now separated from fade timing. Repeating
trial14 cold3600 with prior implicit audio settings produced identical gameplay
telemetry but different saved capacitor fields A8..AF and sample buffer. Local
core serialize.h identifies those fields; audio.c applies masterVolume before
updating them. Do not attribute that sample-zero difference to ROM execution.
Attempted cold native-start-gate runs `return-fade-audio-entry-14` and
`return-fade-audio-entry-parent-01` both failed74: gate requires restored state.
Read-only process check found no surviving emulator. Failed artifacts retained.
Fresh `return-fade-audio-enabled-entry-{14,parent-01}` explicitly set
ENTRY_AUDIO_ENABLED=1 without a cold restore gate. Their complete APU48..B3 and
buffer1D8..27F agree, capacitors901a7119901a7119; gameplay telemetry also agrees.
Fresh own-state6000 gated restores `return-fade-audio-enabled-exit-{14,parent-01}`
now have identical PCM prefix through sample10485476. Full unchanged guard
`return-fade-audio-enabled-pair-14` still FAILS silence timing, with745710
differing sample frames, first10485477, last11499605, RMS ratio1.00005414375.
All full-route silent blocks match. No trimming, state editing, retargeting or
gate relaxation. The remaining fade audio discrepancy is real in this matched
startup comparison; original failed evidence remains intact.

Trial14 short safety trace: fresh240-frame own4680 sound/CRAM replay and
observer-off control (`return-fade-sound-trial-14`,
`return-fade-sound-trial-control-14`) match every full native capture hash and
input log. Source state SHAe5c9a535a3decb9d55337dcca26c9a041a8d20f7a8f7d8a64d663a7fdab8d2a4.
All512 private fade writes (bank14 hexadecimal) occur mode1 atLY144..147.
The full640-write trace also retains128 later bank0D OBJ updates, with92 mode1,
32 mode2 and4 mode0; no mode3 observed. Do not mislabel those as fade writes.
Music13 request/read/accept all remain relativeframe120, each exactly8cycles
later than parent; no additional request-to-accept delay. This replaces
trial10's148656-cycle request/178968-cycle acceptance delay in this replay.
The full-route silence-boundary failure is still present; command timing is
not acoustic equivalence. Three trial14 regression tests now include these
hash-recomputed observer/safety checks. Hardware remains untouched.

Deadline trial14 improves the measured timing. Builder
`scripts/diagnostics/build_return_card_deadline_trial.py` pins trial10, redirects
only its scoped card body to verified empty cave5C20, includes backup in the
first interval, acquires each upload after two ticks, then waits until four
ticks before BGP update/reset. Existing safe-window/map code is unchanged.
Candidate SHA `8ac7fbe3b290f4743280961541fb81746046e89bbdabde6f2b914e73fd60888c`.
Fresh cold3600 telemetry exactly equals map parent. Own6000 assisted replay
`return-cgb-fade-exit-14` enters dungeon4801 and resumes4858, matching parent
instead of prior4802/4859. Only one full telemetry row differs (4848).
Native RGB collage inspected: initialization stays white; the first18 dungeon
CRAM snapshots are white whereas the known-broken map parent fails that check.
Card CRAM90/40/00 publishes4772/4776/4780; BGP changes4773/4777/4781,
matching parent's BGP cadence. Return CRAM40/90/E4 publishes4821/4830/4838.
Full untrimmed PCM guard still FAILS: silence interval starts10486615 instead
of10486614, both end10535734. The former2684-sample extension is gone and all
full-route silent blocks match. RMS ratio1.0000532466, zero added clipping.
There are748457 differing sample frames beginning at0; no masking or trimming.
Source-state APU differences and exact interrupt timing still need investigation;
safe-window instruction reuse alone is not a full raster/audio qualification.
Not deployed; issue remains open.

Fresh read-only240-frame window trace `tmp/return-card-window-trial-10` reuses
trial10's own4680 state (SHA360b2e17e8ec1bc90aca0b532349ab4b8561c03a891a72acc045d005c9df7a34).
All native state/video/PCM/timeline hashes and input logs exactly match retained
`return-fade-sound-trial-control-10`. Nine window acquisitions are observed.
Final card map00 acquisition enters relative100 atLY2, cycle1177319664, and
returns relative101 atLY144, cycle1177449224:129560 cycles spent acquiring the
write window. Earlier card90/40 acquisitions similarly cost131448/129880.
Full-state inspection shows BGP00 at4781 in both map parent and trial10, but
trial10 CRAM white publication at4782; dungeon entry then4802 vs parent4801.
This localizes the delay before initialization; it does not justify unsafe
late-VBlank writes or blindly reducing all fade intervals. Next candidate
must arrange safe palette publication within the native card cadence.

Timer-origin trial13 also **does not remove the extra frame**. The pinned
trial10 private card entry now resets FFD4 before palette-backup acquisition
instead of after it; all later intervals and upload routines remain unchanged.
Builder: `scripts/diagnostics/build_return_card_timer_trial.py`. Candidate SHA:
`1ae1456b4aed771d0e54aec35daec7281dc6e5898a1a7b0fdeb2136a3c4f39d2`.
Fresh cold3600 telemetry is byte-identical to the map parent. Own-state assisted
6000-frame return (`tmp/return-cgb-fade-exit-13`) still enters dungeon at4802,
versus parent4801. Inspected sampled native RGB keeps initialization white.
Full untouched PCM guard (`tmp/return-cgb-fade-audio-pair-13`) FAILS both
silence-timing checks; RMS ratio1.002268, no added clipping, first differing
sample10460436. Thus counting backup acquisition within the first interval
does not suffice. Do not promote this experiment or infer hardware readiness.
Next investigation must localize the remaining wait rather than shorten fade
intervals blindly. Rivalmage was not touched.

Compact-writer trial12 is implemented but **does not fix the remaining delay**.
Builder `build_return_palette_compact_trial.py` pins trial10 and replaces only
the four straight-line upload bodies, retaining their entry addresses, wait
sites and post-RET padding. White bytes use cached B/C constants; consecutive
saved colors reuse HL with incrementing reads. Candidate:
`588454dfe430120581790e2efaef0691dfcd451272397141ef66020cb58a6be5`.
Pure instruction-model tests compare all64 output bytes against an independent
mapping formula over32 seeded decks/all4 shades and show lower upload cycles.
They do not establish interrupt/raster safety.

Fresh cold3600 telemetry matches parent. Fresh own6000 assisted return retains
stage/card4603/4620, dungeon4802 and active4859, still one frame late. Inspected
native RGB retains the white initialization/no-map-flash result. Full audio
guard in `tmp/return-cgb-fade-audio-pair-12` still FAILS on silence timing and
silent blocks; RMS ratio1.0018099349621885. Transition silence now ends10538404
instead of trial10's10538418 (only14 samples earlier), still later than parent
10535734. Other silence intervals change and are retained. First PCM difference
is again sample0, so startup audio equivalence remains unqualified. This rules
out shortening the four upload bodies alone as an adequate latency/audio fix.
No hardware action, deployment, or full acceptance claim.

Identity-write trial11 is a **negative experiment**. New pinned builder
`build_return_card_identity_trial.py` changes only the first private card E4
map call (physical516C3) to existing native wait5682, plus checksum. Candidate
`ab899c87ac3dda6d56dbc19ced52a9830ea6ed051e1c20990396465c02482c51`
keeps the intended final frame wait while eliminating an unchanged deck write.
Fresh cold3600 telemetry matches parent; fresh own6000 assisted return telemetry
is byte-identical to trial10. Full native audio guard still FAILS in
`tmp/return-cgb-fade-audio-pair-11`; the extended silence remains exactly
10486614..10538418. RMS ratio1.0028592249046122; silent blocks/intervals fail,
level/clipping/maximum-step guards pass. No timing/silence improvement supports
adopting this experiment as a fix.

Unlike trial10, trial11's first PCM difference is sample0. The own3600 serialized
source states differ at APU-region A8..AF; APU48..A7, IO310..33F and clock198..19F
compare equal. The cause of those initial APU bytes is not established; do not
attribute all waveform differences to removal of the later write or conceal
the startup difference by trimming. Full PCM/differences remain retained.
Two tests verify patch scope and preserve the unchanged latency/silence failure.
No hardware action or deployment.

Audio scheduling follow-up: four fresh240-frame own4680 replays complete0,
without memory assistance: `return-fade-sound-parent-01`, its `parent-control-01`,
`return-fade-sound-trial-10`, and its `trial-control-10` (same prefix). Each
instrumented run matches its own control's complete native state/video/PCM/input
hashes. Existing SOUND_TIMING/SOUND_COMMANDS/CRAM_TIMING observers were used;
no probe source change. The music command13 request at15BC occurs relative120,
cycle1180228592 in parent, versus121/cycle1180377248 in trial:148656 cycles
later. Acceptance occurs120/1180245232 versus122/1180424200:178968 cycles later.
Thus both the request and subsequent service contribute to the delay; the
incremental service delay is30312 cycles. This is not a dropped/rejected command.
There are358 timer entries in each window, but maximum inter-entry gap grows
121488→126640 cycles. First differing APU port write is FF1E=87 at relative86,
cycle1175434666 parent versus1175434658 trial; the first PCM difference is not
itself evidence of a missing sound command. Full window has122/121 traced APU
events, kept visible rather than forced into sequence equivalence. Next fix
must preserve transition request timing and interrupt service together.
Two audio evidence tests pass, including observer neutrality and exact command
latencies; full audio FAIL remains. No hardware actions or deployment.

Trial10 full native audio guard **FAILS**. Reused complete source-bound WAVs
from parent `return-initial-map-exit-01` and `return-cgb-fade-exit-10`, each
13,167,008 stereo sample frames at131072Hz. Unchanged
`verify_native_audio_pair.py` produced `tmp/return-cgb-fade-audio-pair-10`,
retaining every sample difference without trimming, retiming or normalization.
RMS ratio1.002859900176142, zero clipping in both, and maximum sample step
17310 candidate versus18624 parent pass their narrow guards. Silent-block
and digital-silence timing fail. First difference is sample10460436 (native
timeline row4766, one-based capture frame4767);2,622,052 sample frames differ.
The shared silence start10486614 ends10535734 in parent but10538418 in trial:
2684 extra samples, approximately20.48ms. An additional low-RMS block1607 is
also retained. This is not a claim of heard popping, and level/clipping PASS
does not override the full FAIL. Exact PCM equality before that point narrows
the onset to the card fade period, not a mismatched startup audio phase.
Cause within that period remains to be traced; no waveform alignment was used.
Added a ROM/WAV-hash-bound test that recomputes the full comparison and retains
the failure. It passes as an evidence test, not audio qualification. No new
emulator launch or hardware action was needed for this offline measurement.

Trial10 corrects trial09's initial-card fallback. Static callers of75C7 are
159F and bank1:4143; the retained cold480 stack contains return4146. The new
tail hook previously sent4146 to the unrelated credits fallback742A rather
than native0F33. Dispatch now recognizes4146 and takes native_card. Candidate:
`f938ae85785b4bc30133dad1c39e5f45ee0bcbea249d94f160132970ce22be29`.
Fresh `return-cgb-fade-own-entry-10` completes3600 with every telemetry row
equal to parent. Only after that comparison passed, fresh own6000 assisted
`return-cgb-fade-exit-10` completed. Stage0/card remain4603/4620; dungeon
now starts4802 vs parent4801. Card BGP90/40/00 is4773/4777/4781, CGB changes
4774/4778/4782. White is retained across asset loading and dungeon entry;
the native RGB collage `tmp/return-cgb-fade-images-10/transition.png` shows
no initial colored-map flash. Return BGP40/90/E4 is4821/4830/4838, with
CGB publication4822/4831/4839. Activity4859 remains one frame late versus
parent4858. Full6000 telemetry differs in431 rows, first4801. This is not
speed/audio acceptance; native PCM retained, broader routes still unqualified.
New tests preserve cold3600 equivalence and compare the initial white-map
invariant against the failing parent, while retaining the one-frame delay.
All16 evidence tests pass. No hardware actions/deployment.

Card-tail trial09 (`73a68c346f5890db77eb62a6b3ec498e79082c9df0847d632893016cac6b1c66`)
adds a bank1:75F0 tail hook through the existing20-bank wrapper. Stage0,
scene18 and ancestor1476 guard its private backup/fade-out. Return15DD with
ancestor147C reuses that backup rather than copying white CRAM. It allocates
no persistent RAM latch. Card steps experimentally use three FFD4 ticks plus
safe-window publication; this is not native timing equivalence. Unrun trial08
is retained: builder tests caught a misplaced native-wait label affecting
non-card variants. It was corrected before trial09; old variant hashes pass.

Fresh trial09 cold3600 completed0 but **fails timing**:2353 telemetry rows
differ from parent, first583, and checkpoint Y856 versus860. The fresh own6000
assisted return also completed0, with a differently phased route: stage0 at4724,
card18 at4742, dungeon02 at4934. Native RGB shows no colored-map flash during
the inspected dungeon white phase; CRAM is all white4934..4954. Fade shades
40/90/E4 occur4954/4962/4970, CRAM follows4955/4963/4971, activity4991.
These absolute frames cannot establish speed parity against the parent after
the cold route already diverged. The palette becomes white on the earlier
card at4914 and stays white across asset loading, demonstrating the intended
visual mechanism. Screenshot collage: `tmp/return-cgb-fade-images-09/transition.png`.
The source/stack scope is not yet sufficient to qualify cold behavior; inspect
its fallback and initial-stage path before another variant. No broad testing,
audio qualification or deployment follows. A new hash-bound evidence test
retains both the white phase and the cold failure; all14 fade tests pass.

Earlier fade ownership resolved from immutable parent native stacks:
frames4768/4773/4777 are scene18/stage0, with BGP E4/90/40 and SP DFE1.
Their stack contains saved AF, wait return0F5D, native saved BC/HL, then
caller15A2. Fixed159F calls bank1:75C7. That card routine initializes the
card, sets scene18, calls0F47 at75E8, holds100 waits at75EB/75ED, then
**tail-jumps75F0→0F33**. The latter uses E4/90/40/00 and returns directly
to15A2, before dungeon asset loading at15AF/15B2/15B5 and scene assignment
15BF. This is the specific earlier path missing CGB palette mapping; it is
not a15D7 setup invocation. Prior generic CALL0F33 searches missed the
relevant tail jump. A scoped card-tail hook must preserve other stages,
native four-tick fade cadence, and the live palette needed by the subsequent
fade-in. If the live palette is saved before whitening here, the fade-in
must not overwrite that backup with the now-white live CRAM. Intervening
backup ownership still needs proof. No new ROM patch was made from this
read-only attribution. Added a parent-ROM/native-state-hash-bound stack and
instruction regression test; all13 fade tests pass, not release acceptance.

Fused-setup trial07 (`4c30a79db223c687a6f027747248946352328b58ea173dcc3574193061624c1f`)
unrolls backup reads eight at a time and tail-transfers into the existing white
writer before releasing the acquired window. There is no stack access with
SVBK7 selected; the white writer restores bank1 before popping the saved port.
Fresh cold3600 telemetry remains byte-identical to parent. Fresh own6000
assisted return (`return-cgb-fade-exit-07`) shows BGP40/90/E4 at4821/4830/4838,
matching parent, but corresponding CRAM publication remains one frame later.
Activity resumes4859 versus parent4858: one extra frame remains. White now
appears4806, but the colored map at4805 still shows in the inspected native
collage `tmp/return-cgb-fade-images-07/transition.png`. This is not a full fix.

Fresh120-frame own4800 `return-cgb-fade-window-07` and uninstrumented control
complete0 without memory assistance. All native video/state/PCM/input-timeline
hashes match. All320 helper CRAM writes are mode1. Initial whitening starts
LY150 and ends LY0 while still mode1 at the VBlank tail; there is little margin,
and this run does not qualify other entry phases. Saved64-byte backup equals
the original live palette exactly, and the final64 writes restore it exactly.
The paired evidence test retains those facts and the boundary warning; all12
fade tests pass. Audio fidelity and earlier card/setup exposure remain open.
No deployment or hardware action.

Scheduled-write trial06 now changes only four scoped wait counts (plus ROM
checksum) from trial05: seven ordinary waits followed by the existing window
acquisition/publication are intended to occupy eight frames, instead of eight
ordinary waits plus another acquisition. This does not skip the CRAM safety
window or touch the shared native fade. Candidate SHA-256:
`e3d342b56000badcd28aa8a8aedb41a2c2c6dc4189ee30548f10cf7832e1b773`.
Fresh own cold3600 `return-cgb-fade-own-entry-06` telemetry is byte-identical
to916ebb's cold prefix. Fresh own6000 assisted `return-cgb-fade-exit-06`
retains stage/card/dungeon transitions4603/4620/4801. Activity now resumes4860,
four frames earlier than trial05, but still two frames later than parent4858.
BGP40/90/E4 occurs4822/4831/4839; CRAM follows4823/4832/4840. The initial
colored map at4805 remains visible before white4807. Native RGB collage
`tmp/return-cgb-fade-images-06/transition.png` was inspected. Full6000-row
telemetry differs from parent in534 rows, first4806; no retiming or exclusions.
Both emulator runs completed0; native6000-frame PCM is retained but not yet
audio-qualified. This is a measured timing improvement, not a successful
return fix or release candidate. The remaining initial backup/white acquisition
and earlier card/setup exposure still need correction. Two new structural and
hash-bound replay tests retain both the improvement and failure; all11 fade
tests pass. No hardware action or deployment.

Window-cost follow-up: fresh120-frame own4800 replays
`return-cgb-fade-window-05` and `return-cgb-fade-window-control-05`
complete without memory assistance. Full native video/state/PCM/input-timeline
hashes match. The unchanged probe's bank20 critical-site breakpoints observe
window5B22 and return5B39; the former is also the polling-loop head, so
acquisition cost uses the first visit after each preceding return, retaining
all intermediate polling rows. Six acquisitions start at LY113/5/149/149/152/149
and take27464/126600/135408/135456/132488/135448 core cycles respectively.
All return atLY144. Thus four fade steps enter during VBlank but still wait
for the following frame. A blanket mode1 fast path is unsafe: the LY152
entry has insufficient remaining window for the full deck. The five observed
64-byte writes take2520/2520/2712/2904/3264 cycles from first to last port
write, all in mode1 (LY144 through146/147). These spans exclude surrounding
setup/restore and must not be used as a complete budget. The backup's second
acquisition starts in visible line5, also requiring its own window.

Next implementation needs to schedule publication earlier within the native
wait sequence or reduce/bound the complete transaction, not merely remove
the late-window check. Added a full-file-hash-bound observer-neutrality and
wait-cost evidence test; all9 fade tests pass. No new ROM change, deployment,
or audio-fidelity acceptance follows from this diagnostic.

Candidate `tmp/return-cgb-fade-trial-05/candidate.gb`, SHA-256
`e7811f61995b30dc6070bc5ab886f01dcb06179c22bde0d5ad7af820ff7f6035`,
preserves native setup15D7 and combines backup/white publication at the
scoped fade entry. Cold2700 telemetry matches the916ebb parent and native
fade exit has the same cycle, despite1120 additional entry cycles. All3600
cold-prefix telemetry rows also agree. Neither result qualifies a return.

The completed own-state6000-frame `return-cgb-fade-exit-05` capture reaches
stage0 at4603, card18 at4620 and dungeon02 at4801, matching the parent.
It uses explicit health assistance and pulsed A, not an unassisted playthrough.
Native RGB inspection (`tmp/return-cgb-fade-images-05/transition.png`) shows
partial colored strips at4801, a colored map at4805, then white and a
progressive return of the colors. BG CRAM first becomes all white at4807;
it stays white through4825. The earlier colored exposure remains unfixed.
Native BGP40/90/E4 changes at4825/4834/4843; corresponding CGB palette
publication follows at4826/4835/4844. Activity resumes4864 versus parent's
4858: **six frames later**. Full6000-row telemetry differs in600 rows,
first at4806. No trimming or retiming was used to turn this into a pass.

The window acquisition in the experimental palette routines remains a
latency suspect; this capture does not isolate each wait's cost. The next
fix must cover the earlier card fade-out/setup exposure and publish within
the native schedule, rather than add another broad qualification run for
this failed narrow case. Native PCM is retained but audio fidelity is
unqualified. No hardware changes or deployment were made.

Added a receipt/ROM/native-state-hash-bound regression evidence test retaining
both the initial flash and six-frame delay. All8 fade tests pass; explicitly,
that means the counterexample is preserved, **not that this ROM passes**.

## Current initialization-map candidate: Shalamar cross-check (#27/#34/#45)

Publication follow-up filed as checker issue #46. Fresh60-frame own580 replay
`shalamar-map-publication-window-01` and control both complete without memory
assistance; full PCM/video/states/input hashes agree. All60 native RGB frames
equal the original menu replay581..640. The flagged relative18/original598
holds the complete source from17/597 while the next source changes. Selected
9C00 remains that complete pose through23; FF40 flips8B→83 at relative23/LY8,
and serialized24's selected9800 exactly matches its new source. This explains
the old terminal map mismatch without declaring full raster/speed correctness.
The optional full-copier trace has only `entry_observed` rows for unsupported
caller028D and no paired begin/end events; it is excluded from attribution.

After filing #46, updated `return_map_readiness`: intermediate fade frames
still require exact live-source agreement. Only first E4 may retain the
immediately preceding90 frame's independently complete pose. All current-source
differences remain in the output with accepted-generation/reference-frame
fields. Corrupted current map, corrupted prior map, missing prior state and
wrong/intermediate fade states are explicit rejected mutations. Historical
verification.json is untouched. Fresh inspection gives three menu-cycle PASS
results but overall FAIL remains due raw-scene alias, a separate unresolved
route-oracle contract. No ROM fix/readiness/audio-fidelity claim or deployment.

Fresh own-ROM dispatcher checkpoint `current-map-shalamar-entry-01` reaches
Shalamar on916ebb (settle101, saved113). The1080-frame controller-only
`current-map-shalamar-phase721-01` completes all three menu round trips with
third Select at721. The strict verdict remains FAIL: raw scene0B appears
952..1080 and cycle2 has eight source/selected-map mismatches at598.
All129 low-health frames retain canonical FFB7=0C and the exact Shalamar
C600 policy (blank00/01/FF neutral, other253 IDs BG4), unlike the old d744
wrong-dungeon-table counterexample. This is a renderer-policy gain, not full
arena/audio acceptance or a reason to discard the existing FAIL.

Fresh parent2b797 checkpoint `map-parent-shalamar-entry-01` (settle/saved100)
and same scheduled1080-frame menu replay `map-parent-shalamar-phase721-01`
pass the unchanged three-cycle gate. Entry states have different phases;
this is a regression signal, not proof the Stage1-only copy helper directly
executes in Shalamar. Its fixed13C0 caller still requires FFBA0/D8802.
At the trial's flagged598, the displayed24x24 map exactly equals frame597's
source; the current source differs by8 IDs and changes further at599/600.
Native frame598 was inspected and shows the boss/scenery rather than the
scrambled initial-map symptom. A completed-generation/publication trace is
needed to distinguish a stale visible pose from an oracle sampling an in-flight
next pose; no threshold or scene-route gate was relaxed. New evidence test
retains both the129-frame policy result and the unresolved map failure.

An earlier120-frame d744 own960 replay `shalamar-scene-exit-window-01`
reproduced the already documented native low-health scene assignment at
bank1:4F71 (watch callback4F74), not a new Select defect. It adds no new fix
claim and was not used to qualify the current ROM. No hardware actions.

## Experimental live-palette CGB return fade (#45)

Interrupt-window follow-up: fresh240-frame exact-own-state replays
`return-card-irq-window-01` and `return-card-helper-window-01` both finish0,
without memory assistance. Both match the complete uninstrumented
`return-card-palette-control-01` native PCM/video/states/input hashes.
No observer source change was needed. The helper trace has239 entries at
bank0D:6F23; every entry is inside a fixed06DC→06DF interrupt-hook span.
LCD modes are199 mode1,19 mode3,13 mode2,8 mode0. The first mode3 entry is
relative frame113, LY2, cycle1179145632. Thus the existing prelude is not an
unconditionally safe CRAM publication site, despite its VBlank name. A naive
whole-deck ISR writer would encounter blocked palette access. Any deferred
writer must prove its actual acquisition/publication timing and retain missed
windows; spinning in the ISR would also risk timer/audio latency. This rejects
the proposed unconditional prelude route, not all possible interrupt designs.
The expanded evidence test verifies full observer neutrality and correlates
banked sites with fixed interrupt spans. No ROM patch or hardware deployment.

Lifecycle follow-up (same immutable240-frame916ebb capture): the native BGP
fade-out already changes E4→90→40→00 on active scene18 at relative93/97/101.
Scene02 appears at121; FFC1 only becomes0 at123. Fade-in advances40/90/E4
at141/150/158 while inactive; activity resumes178, and the palette loader
starts OBJ phases182..189 followed by BG phases190..197. All64 BG-CRAM bytes
remain unchanged through189, so the missing mapping covers both fade-out and
fade-in, not just inactive dungeon setup. The expanded receipt-bound test
retains the exact lifecycle as a failure, not a readiness assertion.

Read-only disassembly of the exact916ebb bytes confirms two relevant guards:
bank0D:76E5 returns Z when FFC1=0, causing6F29 to skip the ordinary palette
service;6BA4 also returns unless BGP=E4. The independent inactive scene path
7129→7DF4 subtracts15 and rejects scene02 (unsigned ED>=06), while scene18
is handled earlier at712E. Therefore neither simply removing the BGP guard
nor adding an inactive-only service covers this lifecycle. Next implementation
must own the active Stage1 card fade-out as well as inactive dungeon fade-in,
preserve the live palette deck, and fit the existing interrupt timing budget.
This static-path finding is not a runtime claim about all ISR invocations;
no new candidate, emulator launch, or hardware action in this follow-up.

Existing-retirement-hook check: on916ebb, the own4680 checkpoint restores
before the card-to-dungeon transition. Fresh240-frame
`return-card-palette-window-01` records64 OBJ-CRAM writes at182..189 and64
BG-CRAM writes at190..197. All64 BG palette bytes remain unchanged through
the first189 serialized states, including scene18→02 and the earlier fade.
An initial claim of zero BG writes across the whole240-frame window was wrong;
the new test caught it and the full trace corrects it here. Palette reloading
happens after setup/fade, not during the exposed interval.
The existing bank31:7540 card blanker is not producing its expected
BG0 writes in this window. Merely extending its eight-byte blank is therefore
not a supported fix for this route. Pair `return-card-palette-control-01`
matches complete PCM/video/states/input timeline hashes, so the write observer
does not introduce this result. Added a receipt-bound regression evidence test.
No new ROM variant in this step; revised approach must cover the actual return
fade/setup lifecycle rather than assume normal cold-card retirement runs here.

Fresh2700-frame parent/trial04 cold breakpoint traces isolate the first shift:
both enter fixed16DD at frame2609, cycle366922392. The unchanged native0F7A
entry is parent cycle367298032, trial367300136: +2104 cycles from interception
and fallback before the fade. Native15E2 resumes at parent2650/trial2652.
The sampled C1A0 source bytes at fade entry match. This narrows the first
divergence to the generic setup/fade wrapper calls; it is not evidence that
the early map producer itself slowed down on this secret entry. The traces
have no primary PCM capture, so this is instruction/phase evidence, not
observer acoustic neutrality. Do not compensate by shortening native waits.
The next design needs a scene-specific hook already on the Stage1 return
path, avoiding new mapper round trips on secret entry and other transitions.
Six fade-trial structural/evidence tests now pass, retaining the timing failure.

Timing follow-up: scoped trial03 (2d58ae4c...) leaves native0F7A bytes
untouched and calls a private equivalent eight-wait loop only from15DA.
Isolated trial04 (d9dc5d0700f9bd553aaf05ad35a0f221c64841db590157910f334b2964d06e85)
also leaves the old menu entry and taken0A menu path intact, redirecting only
the existing non-menu branch. Both complete their own3600 cold routes, but
both still diverge from916ebb telemetry at frame2651 and endY864 rather than
Y860. Therefore the shared fade/menu dispatcher overhead hypothesis alone
does not explain the timing shift. The remaining generic15D7 setup hook still
executes on non-Stage1 transitions before falling back, and must be examined.
Neither variant is timing-qualified; no long replay campaign launched for04.
The tests retain this counterexample rather than treating unchanged code
bytes as proof of runtime parity. No hardware touched.

`build_return_cgb_fade_trial.py` layers on916ebb. It routes the15D7 setup
call and0F8F palette-fetch/write through the existing bank20 wrapper, backs up
live BG CRAM to the existing menu buffer SVBK7:DF00, applies white/40/90/E4
shade mapping, then restores the exact live deck. Native eight-wait loop bytes
remain intact, but the extra calls/window waits are **not timing-neutral**.
The0F7A caller stack is checked for15DD so cold boot does not use an uninitialized
backup. Other menu calls retain4700 dispatch. Trial01 was built but not run,
then superseded because it lacked this cold-caller guard; preserve it as rejected.

Trial02 SHA8187e912d82694a29b9b4b921b3e0f2960b4472616baebb3fe0a96af650d3889
completed its own cold3600 route and own-state6000 health-assisted exit.
It reaches dungeon at4691. Inspected native collage
`tmp/return-cgb-fade-images-02/transition.png` shows a white hold and progressive
return to color, with coherent maps. Initial partial strips and a fully colored
setup flash still precede the white hold. Cold checkpoint position differs from
the parent (Y872 versus860), so neither gameplay nor audio parity is established.
This is a visual experiment, not a release candidate.

Short own4680 replay `return-cgb-fade-window-02` and uninstrumented control
both complete120 frames. Full untouched PCM/video/states/input timelines match.
All320 writes from the new helper occur in mode1 (VBlank); its final64 bytes
exactly equal its saved live palette. `test_return_cgb_fade_trial.py` has three
passing tests covering exact patch scope/wait-loop preservation, caller/menu
fallbacks, complete observer neutrality, write timing, and backup restoration.
These do not establish original fade duration, no visible setup exposure, or
audio fidelity. Next work must remove the added timing cost and hide setup
before it becomes visible, not simply bless this slower experiment. No deployment.

## Initialization copy shortcut trial (#45)

Matched health-assisted parent control `return-initial-map-parent-exit-01`
now also completes6000 frames from its own3600 checkpoint. Comparing every
frame of the65-frame dungeon-entry window against the native C1A0 24x24 tile
source: parent has53 frames with selected-map mismatch; trial has4, followed
by61 consecutive exact map matches. This is a frame-boundary tile-ID measure,
not full-raster or palette acceptance. Both source and selected page are read
from each frame's own complete serialized state; no shifted state reuse.

Important tradeoff: native BGP transitions relative to dungeon entry are
parent0/20/28/36 versus trial0/20/29/37 (values00/40/90/E4). One trial fade
step lasts9 rather than8 frames. The tests explicitly retain this timing
difference, not label it parity. Fade and timing work remain required.
`tmp/return-initial-map-measurement-01.json` retains all65 measurements per ROM;
`test_return_initial_map_trial.py` independently recomputes them from exact
receipt-bound full states and rejects the broken parent on the map criterion.

Trial replay result: `return-initial-map-own-entry-01` completed an independent
3600-frame cold route; `return-initial-map-exit-01` restored its own3600 state
SHA8d39bf5572a84b14b0e15549579160ddb151683b3ee8821819856625ae3e4412
and completed6000 frames pulsed A, with explicit health assistance. It returns
to stage00 at4603, intro18 at4620, dungeon02 at4801. No state retargeting.
Inspected native frames4801/4805/4809/4817/4825/4833/4841/4865 in
`tmp/return-initial-map-images-01/transition.png`: initial4801 still has partial
strips, but4805 onward shows coherent dungeon geometry instead of the previous
sustained scrambled field. BGP still changes00/40/90/E4 without a visible CGB
fade. This is partial visual improvement only: setup hiding/fade, matched route
controls, complete frame acceptance, timing/audio, and hardware remain open.

Fresh `secret-return-build-01` completes120 frames without memory assistance;
its full PCM/video/state/timeline hashes match the previous return capture.
The first pre-fade16DD/5077 call has FFCE=01, DCFD=01. C1A0 contains newly
built map bytes at the subsequent4295 entry, but42ED follows only1280 cycles
later. Serialized FFE4 remains01 during the fade and becomes00 later.
Native3485 therefore returns Z through its FFE4 check. Stage1's bank27:6C80
shortcut then uses FFCE=01 to synthesize copy-end registers and return NZ,
skipping the actual tile copy. Later address-only breakpoint rows may include
other physical banks while FF99 is a shadow; do not interpret those as native
bank1 calls without a physical-bank qualification.

`build_return_initial_map_trial.py` adds an eight-byte prefix to that helper:
FFC1=00 returns A=1 with Z set, routing through the existing real-copy fallback;
active gameplay retains the old FFCE logic. Returning bank1 (not A=0) is
essential to the mapper ABI. Candidate SHA
`916ebb1858c6b9e91491081d82e93d00d283180ef44323f1f29c37a033e48deb`,
at `tmp/return-initial-map-trial-01/candidate.gb`, is experimental, not deployed.
Two builder/ABI tests pass, including all256 FFC1 values and exact patch scope.
CGB fade mapping is still missing. An independent cold route is required;
parent savestates will not be retargeted to this candidate.

The updated optional observer is bound by fresh health replay03; three health
telemetry tests pass including full primary-output equality to its control.

## Map-plane inspection rules out a map-selection-only fix (#45)

Offline decoding of both map pages at relative6/8/24/40/80 from the exact
`secret-return-publication-01` capture is retained in
`tmp/return-map-inspection-01/maps.png`, generated by
`tmp/inspect_return_maps.py`. Each row shows native output, both CGB maps,
and both map pages decoded with bank0 tiles and grayscale (diagnostic views,
not modifications to primary video). Inspected result: at8/24/40, 9800 has
partial strips and 9C00 has the scrambled field. At80 both contain coherent
dungeon geometry. Selecting the other page alone cannot restore the dungeon.

Full 6144-byte tile-data regions in **both** VRAM banks are byte-identical
between8 and80. Both 1024-byte tile maps differ. BG CRAM is unchanged across
8/24/40 even though BGP advances00/40/E4. This narrows the work to map
construction/publication and missing CGB fade handling, rather than CHR
restoration. The added evidence test checks exact capture identity and these
whole-region comparisons. No ROM patch or emulator run was needed for this
inspection. The next causal check is why the pre-fade native setup does not
produce the valid map that later setup calls produce (including cache path).

## Return publication traced without changing primary output (#45)

`secret-return-publication-01` completed 120 frames on exact experimental
ROM2b797, restoring its own state80af2876 without memory assistance. Compared
with `secret-return-boundary-01`, all full native PCM, video, serialized states,
and input timeline hashes match. The optional write observer is neutral for
this replay; this is not acoustic fidelity qualification against stock.

The first FF40 change is relative frame7, LCDC83→8B, bank0D:7457
(callback PC7459), LY146, FFC1=00. Native white-in writes at fixed0F90
(callback PC0F92) occur at relative15/23/31/39, values00/40/90/E4.
Thus deferred publication selects the map before the native fade completes.
The trace's `pending` column is physical DF5C, a packed scroll-X payload,
**not** a Boolean pending latch. FFC4 owns publication flags. Suppressing all
publication while FFC1=00 is not yet justified: native setup also runs then.

`tests/test_secret_return_publication_evidence.py` retains exact identities,
complete primary-output equality, the write site, and the fade ordering.
It records a known-broken behavior, not a fixed-build acceptance criterion.
Fresh `checked-secret-health-replay-02` completed with the current probe;
the health telemetry test now binds that run rather than the older probe.
No ROM modification or deployment in this step. Issue45 remains open.

## Original-ROM return establishes intended blank/fade behavior (#45)

Fresh `stock-secret-return-visual-01` restores stock's own frame3600 checkpoint,
SHA4405befb9135752ddb2f5b29f5e8f9b61a89cc9832b3eed6f099decdac789050,
and runs6000 frames pulsed A with explicitly declared DCBB health refill.
This is a visual transition control, not matched combat/cadence qualification.
It completes the encounter and returns: stage00 at4649, intro18 at4666,
dungeon02 at4820. Native video4820..4839 is uniformly one color with BGP00;
4840 starts two-color fade,4848 three colors,4857 four. Inspected4848/4857
show coherent dungeon geometry, not the candidate's scrambled tile field.
`tmp/stock-return-fade-images-01` retains extracted views; originals unchanged.

Read-only source/stack inspection identifies fixed0F7A called at15DA, after
15D7 calls0A0E (BGP/OBP white). 0F7A writes the stock00/40/90/E4 fade while
preserving its eight-frame-per-step delay. The native routine is unchanged;
the candidate's CGB path exposes inappropriate graphics instead. Also note
candidate LCDC selects8B by original968, while the stock fade remains83 through
4858. This is a publication/visibility discrepancy to trace, not evidence that
skipping the native delay or simply advancing C600 will fix it.

`tests/test_secret_return_fade_evidence.py` binds ROMs and checks every specified
setup frame, requiring blank stock output and retaining the candidate's visible
counterexample. It is a regression-evidence test, not candidate acceptance.
No ROM modification, hardware action, or issue closure in this step.

## Visible scrambled-map return transition filed separately (#45)

Read-only inspection of the full native video, not just saved120-frame samples,
found a previously missed visible regression. `secret-exit-after-menu-fight-01`
frames956..967 show partial graphics (raw frame SHA256
a98274fa45b1100f6cb2d9b120555e548a646d6e72723e954e07adcc29c3d052);
968..1001 show the same scrambled tile map (raw frame SHA256
1a5ff2fe759ced8326295beffee501b4ab0edf9ca15f55b8a0e2567536a4268f).
Extracted963/968 images were visually inspected in
`tmp/secret-return-handoff-images-01`. Original capture remains unmodified.
This contradicts any broad interpretation of the clean1080/2400 samples.

Fresh120-frame `secret-return-boundary-01`, exact own frame0960 state SHA256
80af2876f2e7284a975395fb90e8e4574c66461c73d7dbe3633d468544739afa,
pulsed A/no memory assistance, shows PC4086..408B for relative8..39.
Serialized stack returns through406B/0F8E: native DMG fade0F7A calls the
eight-frame wait4068 at0F8B for each palette step. It is not waiting on
unfinished C600 construction: dungeon policy is already restored by966,
before the scrambled-map interval. CGB fade visibility/publication ordering
is the next hypothesis, not a verified root cause or justification to skip
the stock delay. No ROM changes yet; issue-first report:
https://github.com/struktured-labs/penta-dragon-dx/issues/45 .
This is distinct from persistent recorded trails and does not prove their cause.

## Actual secret return after explicitly closing the encounter menu (#26)

Read-only inspection of `secret-moving-pause-expiry-01/frame-2040.ss0` shows
FFE4=1, LCDC=AB, WY=60, minibossFFBF=0F: the checkpoint has an open item menu.
`secret-exit-close-menu-01` restores that exact checkpoint and supplies a
six-frame Select pulse followed by pulsed A for1800 frames, without memory
assistance. Menu is closed by the first captured native frame; miniboss15 at120
is absent at960. No Game Over occurs. This is a materially different input
route from the prior firing-only deaths, not a ROM fix.

`secret-exit-after-menu-fight-01` continues from its own frame1800 checkpoint
for2400 frames, pulsed A only, no memory writes. Stage07→00 at756, intro18 at774,
dungeon02 at963, low-health sound alias0B at1016. No Game Over/new-game restart
occurs. Source checkpoint history still includes declared earlier assistance;
do not call this a fully unassisted cold playthrough. Pause effect already
expired before this return, so active-pause-across-return remains uncovered.

Native-state scan shows canonical scene02 from963 onward, but C600 retains
the secret table for963..965 and installs expected dungeon table SHA256
90b7393e610c67b97cd32664fae294ec76d10fd9a25384e004320b76c4ad4cb4 at966.
The three-frame handoff gap is retained, not hidden as an immediate-policy pass.
Screenshots1080 and2400 inspected: intact blue/white scenery, no visible broad
yellow/red bands in those samples. Not continuous raster or recording parity.
`tests/test_secret_unassisted_return.py` checks both complete timelines, no
death, actual return milestones, closed menu/encounter end, and every canonical
scene/policy-table state963..2400 including the explicit gap. One test passes.
No ROM patch, deployment, hardware testing, or issue closure.

## Scrolling endpoint still dies in projectile collision (#26)

Fresh180-frame pair `secret-expiry-death-trace-01` / `secret-expiry-death-control-01`
restores2b797a own `secret-moving-pause-expiry-01/frame-2040.ss0`, SHA256
`4282da3a878f3a303bc3c654ff618a5df4eeebb65eab6ef41505857294adf08f`.
Pulsed A, no gameplay-memory writes. Full PCM/video/state/input timelines are
byte-identical with and without death watchpoints. At relative86, projectile
damage32(hex50decimal) changes health59→27(hex89→39decimal) at PC1032;
another damage32 call underflows and reaches4A44 via native collision5BD5.
Scene00 then17 at87/88 is Game Over, not the secret exit. Read-only comparison
with stock code confirms its subtract-and-jump-to-GameOver behavior; no exit
patch or damage suppression is justified. Endpoint screenshot was inspected.

`secret-exit-dodge-right-01` tries Right+pulsed A from that same checkpoint,
without memory assistance. It delays Game Over to639 but does not avoid it;
later Stage1 at1298 is a new game, not a secret return. No readiness claim.
The new regression assertion preserves damage-write/stack evidence and full
observer neutrality; all3 moving-return evidence tests pass. Further return
coverage needs a surviving encounter route, not another stationary scroll soak.

## Capture barrier prevents pre-initialization debugger execution (#43)

`secret-endpoint-startup-diagnostic-01` reproduced the endpoint failure with
unchanged guard semantics and added failure logging: restored=1, samples=32,
frames=0, interrupt_depth=0. The pinned core's thread loop dispatches
mDebuggerRun before servicing its pause request; debugger execution can call
core runLoop/step while the replay initialization barrier is still closed.

`native_av_tap.c` now gates those two CPU entry points with an atomic startup
flag, enabled only by the opt-in startup barrier and released after successful
restore/probe initialization. It does not discard audio, reset counters, retime
the machine, or relax the zero-frame/zero-sample assertion. Source SHA256
`c259aa6616f6dd8586ef7047ef15c56245ee13fc41ca0bc5837c133ead2ebb6d`;
compiled against the pinned core flags/headers into
`tmp/native-av-startup-cpu-gate-04.so`, SHA256
`9c85658b9fe1da74e11ae41ff86f08653b72a3acf623537b5dbc05d716d92b22`.
Old binaries and failed evidence remain unchanged.

Fresh `secret-endpoint-startup-fixed-01` succeeds for240 frames from the exact
previously failing state, with Left+pulsed A and no memory writes. Sara moves
104→24 in X: the earlier stationary route was not proof of an input hang.
`secret-endpoint-startup-fixed-delay-01` adds10ms startup delay; all primary
PCM/video/state/input-timeline files are byte-identical. Separately,
`secret-startup-fixed-neutrality-01` reproduces the established120-frame
`checked-secret-health-replay-01` control with full byte equality in those four
streams. Three retained-evidence tests pass, including the failing old capture.
This is scoped local tooling verification, not general audio qualification.

Using the fixed recorder, `secret-moving-pause-expiry-01` continues2400 frames
from the new left-movement endpoint with pulsed A and no memory assistance.
Native pause timer reaches0 at1224; scrolling subsequently reaches worldY8.
Game Over occurs2128, title2381; there is still no verified secret-to-Stage1
return. Do not describe this as fixing #26 or preserving combat parity.
No hardware/deployment changes. Final process check found no mGBA running.

## Moving secret-route attempt: no return, timer remains live (#26)

Fresh `secret-alias-chunk-moving-return-01` (2b797a) and
`secret-fast-moving-return-control-01` (665a) replay their independently
generated exact-ROM frame3600 states for2400 frames. Right plus pulsed A,
pause-item menu at100, and explicit one-time DCBB=118 assistance are recorded
in receipts. Both stay in stage07 throughout; from frame240 onward player
position remains104,792. This is neither a successful secret return nor a
reproduction of yellow trails on the main map. Frame2400 was visually inspected.

An initial inference that the pause timer froze was **incorrect**: scanning
all native states shows activation60 at161, then59 at202, decrementing every60
frames through23 at2362 in BOTH builds. The item-action text log has a partial,
unflushed tail ending2344 and must not substitute for terminal native state.
Stationary coordinates alone do not establish a hang. No ROM patch follows.

Two subsequent exact-ROM restores from the trial's frame2400 state
(`secret-alias-chunk-moving-neutral-01`, `secret-alias-chunk-moving-left-01`)
exited74 at the native capture startup guard. Both retain load_begin/load_end
with success1 but zero captured frames/samples and empty gameplay traces.
They are failures, not neutral/Left gameplay observations. No guard was relaxed;
read-only process checks confirmed no remaining emulator. Investigate under
#43 before using that endpoint for captured replays.

`tests/test_secret_moving_return_evidence.py` binds both ROMs, checks every
native state in the stationary interval for stage and the expected live timer,
and rejects treating either failed restore as a capture pass. Existing health
telemetry tests also passed (3). Hardware remains untouched; no readiness claim.

## Health telemetry incorporated into repository replay harness (#42)

Added repository `scripts/diagnostics/probe_secret_entry.lua` and
`run_secret_entry_probe.py`; corrected physical DCBB logging no longer exists
only in scratch. Lua preserves diagnostic behavior (corrected opening comment);
historical scratch files/captures remain untouched. Launcher requires explicit
ROM, validates exact state CRC/header/size, removes cross-ROM retargeting, binds
output/startup marker to repository scratch, propagates emulator exit75 without
retry, and records timeout as incomplete with a read-only process check.
Native capture falls back only to repository tmp, never system temporary space.

Fresh `checked-secret-health-replay-01` uses the new launcher, same exact own
state/ROM/input as `secret-alias-chunk-death-control-01`. All120 logged health
values equal corresponding serialized physicalDCBB bytes. Entire native PCM,
video, machine-state and input-timeline files match the scratch control exactly.
Probe/runner hashes are bound in the receipt. Three health tests pass, including
old broken-telemetry rejection and full observer neutrality. Three additional
mock-only runner tests verify mismatch rejection, output escape rejection, and
single-flight busy-status propagation; no emulator is launched by those tests.

Usage/assistance/runtime limitations are documented in
`docs/secret_replay_harness.md`. This verifies tooling issue42, not a player-facing
health or ROM fix. Hardware and experimental ROM qualification are unchanged.

## Stationary restarted Stage1 sound alias does not change tile colors (#24)

Read-only scan of the retained2b797a6000-frame native capture: restarted
Stage1 raw scene changes02→0A at5318 while canonicalFFB7 remains02.
All64 BG palette bytes remain identical from5001 through6000. Across every
frame5318..6000, comparing both full physical tile maps with5317, there are
zero attribute changes for cells whose tile IDs are unchanged. Thus this
specific stationary sound-alias transition does not reproduce #24.
This is not a scrolling route, secret-area return, or general stage-color
qualification. No ROM patch or issue closure follows from this negative test.

Read-only #42 status review confirms its runtime DCBB logging correction is
verified, but the fix remains in the ignored scratch probe. Its issue explicitly
requires incorporation into the checked-in reproducible harness before closure;
do not close it merely because retained corpus tests pass. That tooling task
remains distinct from player-facing Stage1 palette corruption.

## Secret projectile death retains reviewed Game Over colors (#18)

Reused authenticated native6000-frame2b797a capture
`secret-alias-chunk-lowhealth-return-01`, not another forced-death run. Raw17
spans259 frames1041..1299. Every settled frame1084..1299 (216 consecutive)
matches reviewed purple Game Over RGB SHA256
`d2f6b153ad3069aead0ca07fde2900b0e8d46f51ee8d728bb621e9621fd055ab`.
Against the separately hash-authenticated intact gray reference, all216 are
exact accent-only substitutions with unchanged glyph/background pixels.
The gray negative control is rejected. First43 scene frames1041..1083 do NOT
match the settled reference and remain explicitly listed as transitions;
they are not discarded or declared palette passes.

New `tests/test_secret_death_gameover_color.py` verifies the candidate pin,
video completeness against trace length, every raw17 frame, exact settled
geometry/color and retained transition interval. One test passes; missing
local artifacts produce a skip, not a claimed emulator pass. Frame1200 was
visually inspected previously; reviewed purple-accent lettering is intact.
This extends #18 coverage to a secret-area projectile death; it does not
qualify the trial's altered combat/audio or hardware appearance. No new ROM
change, hardware test, deployment or issue closure.

## Trial death traced to stock projectile volley, not overwritten templates (#26/#31)

Own-ROM restore from trial's frame0960 checkpoint
`4e3b65d66712027962fc8cbf0f709761dfd40de57e79171361b6a88ce7e9e74f`,
120 frames pulsed A, no memory writes. Optional scratch-probe trace start
parameters now permit death/projectile observation before1201; old defaults
unchanged. Captures `secret-alias-chunk-death-{watch,sources,control}-01`:
both instrumented variants exactly match uninstrumented full native PCM,
video, states and input timeline hashes. Restored epoch clean; normal exits.

At relative75, source bank20:5D8E supplies48 bytes exactly equal to original
cartridge bank0D:5D8E (authenticated stock SHA2f32570c...). All8 records are
active, damage0A each; types/directions0202,0206,0402,0406,0602,0606,0802,0806.
Live copy applies native origin offsets0C,0C→48,44, preserving other fields.
At78, six successive writes through native damage store endingPC1032 reduce
HP50→46→3C→32→28→1E→14; at79 another reduces14→0A, then the following
damage underflows to the native death path. Stack return5BD8 identifies the
projectile collision routine, whose bounds are B=3B..4D and C=43..55.
Earlier HP1A→5A at48 comes fromPC77E5, a distinct health increase, not part
of the damage burst. No unexplained direct copier write to HP was observed.

This particular death is not recurrence of overwritten-template issue31:
the entire source volley is authentic original data. Timing changes still
alter encounters and survival, so the trial is not promoted, and this does
not prove broader gameplay parity. Do not "fix" authentic projectiles by
removing their damage or adding invulnerability. Next separate original
combat behavior from renderer-induced timing differences. Hardware untouched.

## Pause-item route rejects alias chunk trial for promotion (#26)

Fresh `secret-alias-chunk-lowhealth-return-01` restores2b797a's own3600
checkpoint, sets HP118 once, fires pulsed A for6000 frames, and opens/selects
the pause item at relative100. No health refill/position/palette intervention
in this replay. Pause timer becomes60 at161. The player reaches raw17 Game
Over at1041 while still stage07; held A subsequently starts a new game,
reaching stage00 gameplay at1660. Final stage00 scenery is NOT a successful
secret-area return. Inspected1200 Game Over and1680 restarted scenery.

Control `secret-fast-lowhealth-return-control-01` repeats the same input through
1800 from665a's own matched checkpoint. Pause activates at161 here too, but
this control stays in secret raw0B/stage07 throughout, alive withHP48 at1800.
At960 old/new HP94/56; new HP changes80→20→10 at1038/1039/1040 before
Game Over. At720 worldY188/200; both reach8 later. This demonstrates materially
different combat/damage outcomes, not a proven new memory-corruption cause.
It rejects promotion based on the short audio improvement. Both native runs
complete normally; no hardware changes.

Added explicit sequence regression in `test_secret_alias_chunk_movement.py`:
pause activation, candidate death before any stage00 return, control survival,
and later restart are all retained. Two tests pass, including full map evidence.
Next inspect the changed damage/collision timing or keep665a as the working
baseline; do not hide this result behind the clean restarted endpoint or
reclassify the trial as a fixed return. Trial2b797a remains unqualified.

## Alias chunking: 480-frame movement keeps selected maps correct; audio FAIL (#26)

Fresh `secret-alias-chunk-movement-01`, exact2b797a candidate and its own
matched3600 checkpoint, HP118 once/Right480, completes with native capture.
Full frame-boundary inspection authenticates each state's ROM CRC and secret
stage/canonical context, checking both maps'24 published rows against the
existing tile-ID palette policy (not an independent art-direction oracle).

Across480 frames, d901 has474 frames with any-map mismatches,470 involving
the selected map. Prior665a has4 any-map mismatch frames and0 selected-map
failures. New2b797a has3 any-map mismatch frames and0 selected-map failures:
frame1 has32 cells,5 has28,13 has14, all hidden-map. These transient mismatches
remain recorded, not waived as universal correctness. Final screenshot inspected;
scene geometry/Sara visible. No continuous raster/CHR acceptance is implied.
`tests/test_secret_alias_chunk_movement.py` verifies all three full timelines,
retaining the known-broken control and hidden-map failures; passes in1.07s.

Full untrimmed audio compared with d901 remains FAIL in
`tmp/secret-alias-chunk-movement-audio-comparison-01`: RMS ratio1.00965470468,
941589 differing sample frames, first35733/last1053343. Level/silent-block/
clipping checks pass; exact silence intervals and maximum discontinuity fail.
Short neutral-replay improvement therefore does not qualify longer movement.
No threshold changes, PCM alignment, deployment or readiness claim. All480
native frames and1053344 samples retained. Emulator exited normally; final
process check found none running. Full return/recorded yellow trails unresolved.

## Alias-only chunking improves short audio guards, remains FAIL (#26)

`build_secret_alias_chunk_trial.py` preserves the healthy gate/copy code and
redirects only successful raw0B/canonical09-or0A alias branches to authenticated
empty bank38. That bank receives the chunked copier, trampoline, and an exact
copy of bank36's attribute policy. Candidate SHA256
`2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306`.
Fresh cold3600 `secret-alias-chunk-own-entry-01` checkpoint SHA256
`2df8775c8a44e22b8049a841cf5a6f68027ac21c4c1149a025926a27e9124e01`
matches665a machine state byte-for-byte after the32-byte ROM identity header
(and bytes8..15 also match). No retargeting. Two tests cover exhaustive routing
and the independently generated checkpoint; prior chunk-body tests still apply.

Fresh120-frame HP118/keys0 `secret-alias-chunk-neutral-timing-01` and control
without SOUND_TIMING both complete. Entire native PCM/video/states/input timeline
hashes match each other, validating timing-observer neutrality. Final image
inspected: intact secret-room scenery and Sara. This is not all-frame tile
qualification or the recorded long return route.

Compared to the original d901 control, the frame16 FF26 delay falls2288 to624
cycles. Full120-frame audio guard improves: RMS ratio1.0111280533739855;
level, silent blocks, clipping and maximum-step checks pass. Exact digital
silence intervals still differ: parent[190121,197859], candidate[190105,197830].
Result remains FAIL, with185270 differing samples and first35733. No trimming,
alignment or threshold changes. All differences retained in
`tmp/secret-alias-chunk-audio-comparison-01`.

Candidate now has the same3 sound-command events and HP118 throughout as d901,
ending worldY736 (665a ended732/HP108 with17events). WorldY still differs from
d901 on11 of120 frames. Improved audio level is therefore not solely attributable
to reduced interrupt latency; changed encounter timing matters. No promotion,
deployment, readiness or acoustic-fidelity claim. Longer low-health movement,
return transitions and unchanged healthy behavior still need qualification.

## Chunked staging trial changes healthy starting phase; not qualified (#26)

Added experimental `build_secret_chunk_yield_trial.py`, exact665a parent only.
It inserts48 additional interrupt windows after eight-tile staging groups:
restore SVBK1, EI/NOP/DI, restore SVBK6, then continue with LD A,[DE].
The old staging/DMA sequence remains byte-for-byte recoverable by removing
those windows; no tile-copy instructions or DMA loops are removed. Body grows
7358 to7886 bytes within authenticated free space before the entry trampoline.
Two tests verify instruction grouping, exact bank-switch sequence, preservation
of all old instructions, parent identity rejection, and patch boundaries.
These are code-structure tests, not interrupt-handler fidelity proof.

Trial `tmp/secret-chunk-yield-trial-01/candidate.gb`, SHA256
`c9e893b531b535f81128f1956f0795b279a3bed1767aa882a902ee477c6d5685`.
Fresh assisted cold3600 route `secret-chunk-yield-own-entry-01` completes;
its own checkpoint SHA256 is
`dbf175be79a2678e89a3cd2ec99db85aa206dee41de29d7dbd844798c167e7ca`.
Machine/register/APU state already differs from665a at3600, because this
variant also changes healthy09/0A copying. Fresh120-frame neutral/HP118
`secret-chunk-yield-neutral-timing-01` completes with native capture, but is
NOT a matched-start sound comparison and must not be promoted on its metrics.
Both runs exited normally; process check found no remaining emulator.

Next isolate chunking to the low-health alias path while preserving the
healthy path's exact code. Read-only allocation check finds bank37 occupied,
banks38/39 erased in the exact parent; allocation must still be authenticated
by the next builder. No release/source-default/device change. Preserve this
trial rather than overwriting it or retargeting an old checkpoint to it.

## Neutral replay locates first watched APU delay in timer entry (#26)

Fresh `secret-parent-neutral-timing-01` / `secret-fast-neutral-timing-01`
repeat the120-frame neutral-input controls below with existing SOUND_TIMING
instrumentation added. For each exact ROM, full native PCM, video, serialized
states and input timeline hashes equal its uninstrumented control. This is
full observer neutrality, not merely endpoint agreement.

Before relative frame77, both have115 timer entries and43 watched APU writes.
The complete watched kind/value sequence agrees in this diagnostic interval;
timer values/timestamps do not. First timer-entry divergence is frame8,
507213000 versus507214288 cycles. First watched APU timestamp divergence is
frame16 FF26=FF,508252986 versus508255274. Its preceding timer entry is
508248968 versus508251256: both entry and APU write differ by2288 cycles,
with the same4018-cycle entry-to-write duration. The next four channel writes
have the same2288-cycle delay. Candidate interrupted bank24 at returnPC52CB
(combined copier); parent interrupted bank1C at6DEA. Candidate TIMA isD3
versus parent'sD2. This locates the delay upstream of the sound routine, at
timer servicing during graphics work; it does not establish audible severity.

Across the pre77 interval paired timer deltas range-8928..7952 cycles and
watched APU deltas-5636..2384. Equal counts are not proof of equal deadlines,
and only the watched trigger/control registers were traced. The full120-frame
audio FAIL and later extra encounters remain visible and unresolved. Next
inspect the bank24 staging critical section at52CB rather than altering sound
commands or padding PCM. No new ROM change or hardware action.

## Neutral-input audio diagnostic still includes autoscroll/encounters (#26)

Fresh120-frame parentd901/candidate665a replays restore their respective
matched3600 checkpoints, set HP118 once, and deliver keys0 throughout.
Names `secret-parent-stationary-audio-01` and `secret-fast-stationary-audio-01`
describe the attempted experiment, NOT actual stationary gameplay: both rooms
autoscroll from worldY860 toward736/732. No subsequent memory assistance.
Native capture/startup epochs complete; both contain263328 stereo samples.

The unmodified full-audio guard fails: RMS ratio1.1478059007932295,
225308 differing sample frames, first35733, last263327. Level, silent-block,
digital-silence-interval and maximum-step checks fail; clipping check passes.
All samples and differences remain in `tmp/secret-stationary-audio-comparison-01`
and `/mnt/data/tmp/penta-secret-{parent,fast}-stationary-audio-01-av`.
No trimming, retiming, normalization, or relaxed thresholds.

Both sound logs begin with identical request/read/accept for1B at frames1/2.
Parent has only those3 events; candidate has17, beginning extra18/20 requests
at77 and later damage/health commands. WorldY first differs at26 (836/832;
26 differing frames overall), HP first differs78 (118/113;43 differing frames),
while scene fields agree throughout. Parent retains HP118; candidate reaches108.
Thus keys0 does not isolate music from encounters and the whole-route level
difference cannot alone identify an audio-engine fault. The first PCM mismatch
still precedes extra commands and the first observed position divergence;
that early interval remains a timing lead, not a qualified audio fix.

No ROM changes, device actions, or readiness claim. The shorter diagnostic
narrows the next investigation to early timer/APU timing rather than assuming
neutral input suppresses gameplay. Prior moving-route failures remain valid
unresolved evidence. Final process check found no mGBA processes.

## Existing BG0 repair verified at early menu entry (#23)

Fresh `secret-fixed-early-menu-held-01` restores665a's own frame2640 state
`3b4eb9abadea1281d7c8506a6af09635296f018c64e83993e58b14fa663ccb19`,
without retargeting. Same Select120/neutral120 schedule as the reported-ROM
control below; no replay memory writes. All240 native frames retain BG0
`ff7f947e4a3d0000`; window enables at33 and stays on. The broken control
violates BG0 on frames32..240 and enables its window at37. Inspected final
candidate image has intact blue/white scenery and MEDICAL menu, without the
control's green/red walls/pink fill. This validates the existing source repair
on this entry case; no new ROM patch was necessary.

`tests/test_secret_early_menu_palette_evidence.py` authenticates both ROMs,
their own restored states, complete native-state hashes, input schedule,
and every frame's BG0/window state. Known-broken control fails the palette
invariant; candidate passes. One corpus test plus five existing source-patch
unit tests pass. Corpus absence is an explicit skip, never a fresh-run PASS.

Candidate captured526688 samples versus control526656; menu acceptance also
differs by4 frames. These separately generated assisted checkpoints are NOT
phase-identical gameplay/audio controls. No sound-fidelity, recorded-onset,
full-secret-return, hardware, or release-readiness claim follows. Earlier audio
failures remain unresolved. Native candidate evidence is retained at
`/mnt/data/tmp/penta-secret-fixed-early-menu-held-01-av`. No device changes.

## Earlier entry replay: BG0 corruption precedes accepted menu (#23/#26)

Read-only inspection of `reported-secret-menu-scroll-entry-01` finds stage07
at frame2429, scene09 at2612. BG0 is still `ff7f947e4a3d0000` at2640,
but is `070607ff7f947eff` at2760 and every inspected120-frame checkpoint
through3360. Inspected2612/2640 pictures already have broken white/blue
geometry;2880 has green/red walls. Geometry and palette onset are distinct.

Two fresh240-frame replays restore this reported4f5a ROM's own2640 state
SHA256 `6b2732eda732a6b60b0c6231f4f05fea139821a29156bbc4e6f53f3ffca24421`:
`reported-secret-early-menu-01` supplies Select for6 frames;
`reported-secret-early-menu-held-01` supplies Select for120 frames, then
neutral. Both use probe4e364f65, native startup-gated capture, no replay
memory writes, and finish normally with240 native frames/526656 samples.
The source checkpoint's assisted route remains diagnostic, not native play.

Full native-state scans show the same BG0 change at relative frame32 in both
replays. Six-frame Select never enables the window; held Select enables it
at37, after corruption, and it remains enabled through240. The held replay's
final image visibly has the MEDICAL menu over green/red walls and pink fill.
Thus merely requesting an earlier menu does not reproduce the recording's
white/blue pre-close picture: actual menu acceptance must be distinguished
from requested input. No claim that menu causes this initial palette change,
that this is the exact recording state, or that the later recorded trails are
fixed. Native artifacts: `/mnt/data/tmp/penta-reported-secret-early-menu-01-av`
and `/mnt/data/tmp/penta-reported-secret-early-menu-held-01-av`.

The next investigation must explain the differing entry presentation/history
or verify the same entry on the relevant core; another long hold from the
already-corrupted menu state cannot establish the recorded onset. MiSTer was
untouched; read-only process check after both runs found no mGBA processes.

## Long MEDICAL hold delivered, but starting presentation differs (#26)

Fresh `reported-secret-long-medical-01` restores the reported4f5a ROM's own
menu-open frame3360 checkpoint755ecf5d49065b3216cb8dc45c7bb9b164bfb43d0a3a88eee258ed9939db23a4.
New opt-in scratch-probe `ENTRY_RESUME_MENU_AT=3960` supplies neutral input
until3960, Select for6 frames, then Up with pulsed A. No gameplay-memory
assistance during this replay; the checkpoint's prior route used documented
inventory/position/health assistance. Capture4200 frames, native audio/video
and states; normal exit, clean restored epoch, no emulator left running.

Window-enable bit is set on exactly frames1..3960, then clears. Position/HP
remain72,1176,255 throughout the hold. Native scrolling resumes, reaching
worldY936 at4200 withHP255. Inspected3960/4080/4200 images: fixture already
has green/red walls and pink backdrop before closing, unlike the recording's
mostly white/blue pre-close picture. Do not qualify this as the same recorded
onset or infer that menu duration is irrelevant on other starting states.

Read-only palette-session artifact check finds only September14/15 receipts,
both descendants of b93ebc46, not the September27 launched4f5a candidate.
Those artifacts do not establish an edited ROM in the recorded session.
The launch pin remains the available provenance; do not invent an active-ROM
identity from picture colors. The next reproduction needs a matching earlier
entry state/presentation, not another repeat from this already-corrupted one.

## Earlier recorded red-patch onset after long secret menu (#23/#26)

Reviewed new recording derivatives in
`/mnt/data/tmp/penta-secret-first-colors-20260928/`. Coarse fps-filter sheets
are search aids only: their output-clock labels are not exact source event
times. In particular the initial estimate1490.5s was superseded by unsampled
frames plus showinfo. The broad sheet named1440-1650 extends beyond its name
because output duration is applied after tiling; do not use its filename as
an exact time bound.

Unsampled seek1491s,60 source frames: menu visible at relative.038 and closed
at.054. Frame006 (.088) shows no red in the upper-left wall region; frame007
(.104) shows a red patch. Frame011 (.171) loses the red patch again. Thus
the observed color event is around24:51.104, well before the27:41.8 broad
yellow-band expansion. White/broken geometry predates this menu close.
This is the first red patch in this inspected window, not proof of the first
corruption anywhere in the recording or exact controller input timing.

At480x432 diagnostic scale, red-pixel threshold R>150,G<100,B<100 in
rectangle(0,0,200,150) finds red on frames007–010,015–018,023–026,031–034,
039–043,048–051,055–059. It is absent on intervening frames. The visible
patch therefore alternates during scrolling, rather than remaining continuously
red. Frames006/007/011 were individually inspected. Their SHA256 values:

- 006: d14c94c3dc9563d82ecde4974d094191b8e93a71a7dbd6265cde384816f0842b
- 007: 1aa972ccd263e32679ceca8e1f43ebbe5af9afac75a7a002831ab476b0304589
- 011: 0c2a1ea0142b53893bbca97eca31b195aff47164395cbd2962ca82f6ef56577e

Fresh `reported-secret-blink-review-01` reuses exact4f5a-owned checkpoint
ff06ed43, physicalHP118 once,120 Up frames, captures every frame plus native
audio/video/state. It completes normally. This is a different room/route
state, not reconstruction of the recording. Its first32 samples retain red
pixels in the left16-pixel wall strip throughout (225→314), rather than the
recorded on/off behavior. Raw scene changes09→0B at frame8. Do not describe
this short low-health trial as reproduction of the newly identified onset.
Next route should reproduce the long MEDICAL hold/close and the same scroll
direction/location; distinguish palette values from tile and attribute changes.
No ROM changes, deployment, or hardware actions this turn.

## Secret BG0 dedup trial: equivalent sampled colors, unmatched startup (#26)

`build_secret_bg0_dedup_trial.py` creates experimental7f073be481998f2d04b6e533f00ea058436760a27b97c941bce31d6643663015
from exact665a33b6, independently of the faster-clear trial. The existing
phase-qualified BG0 repair tail69CD redirects into13 padding bytes6D4E.
Only FFBA7 returns without republishing; other stages continue to7FE0.
Both paths preserve AF/stack. Two instruction/patch-boundary tests pass,
including all256 stage values and16 flag combinations. Existing shared
palette timing guards and the primary publisher are unchanged.

Own cold3600 checkpointa263d60fa92c4a31e321c4ad9cdcb30f19a0a29b933aa88203fc680eb2730dc7
already differs from the parent in APU/register phase and clocks. Therefore
the480-frame comparison is not a matched-start timing/audio acceptance test.
`secret-bg0-dedup-transition-01` captures48 accepted CRAM writes instead of56;
frame-end BG CRAM equals the parent on all480 frames, but all480 video frames
differ. No claim of improved user-visible corruption or original fidelity.
The same-ROM `secret-bg0-dedup-control-01` matches its observed run's entire
PCM/WAV/video/states/input. Captures complete normally and process check is
clean. No hardware or deployment action.

Keep this experimental branch unqualified. Two timing-oriented trials have
not established improvement of the recorded trails. Return to locating and
reproducing the recording's first corruption event rather than stacking
further speed optimizations onto an unmatched replay.

## Remaining secret palette delay includes redundant BG0 publication (#26)

Fresh `secret-fast-palette-writes-01` adds existing CRAM write observations
to the qualified480-frame palette-setup replay. ROM665a33b6, own checkpoint
e7eeb9b5, HP118 once and Right. Full PCM/WAV/video/states/input equal the
same-ROM unobserved `secret-fast-gated-audio-01`. No ROM modification.

All56 observed writes target BG CRAM in raw scene0B, with no LCD-on mode3
write. At frame7 the main palette service writes BG0's eight bytes
FF7F947E4A3D0000 at LY148/150. Later-stage BG0 repair writes the identical
index/value sequence again at LY1/3. This duplicate contributes to the
4448-cycle prelude delay; it is not a blocked write or evidence of the
recorded trails. OBJ3 remains000018634e2e8410 in all480 frame-end states,
so the handheld treatment does not disappear in this replay.

The next candidate should consider skipping the unnecessary secret-stage BG0
repair while preserving overrides needed by ordinary later stages. Do not
remove the shared safe-window writer: accepted CRAM writes are a property
of this run, not proof that its timing guard is unnecessary. Trace SHA256
cf157f7e881ca34461f5c5d08ccef6d75ac00909c745a6de64dc7f8971eae520.

## Faster scene-table clear trial remains unqualified (#26)

`secret-fast-palette-setup-cost-01` isolates12360 global cycles in the
256-byte C600 table clear6D43. Its full primary capture equals the prior
fast-alias control, including PCM. Frame7's separate delay instead includes
the71DB palette-writer calls; it is not another table clear.

After recording the plan on #26, added `build_scene_table_clear_trial.py`:
redirect only later-dungeon setup CALL5489 into14 verified padding bytes at
6D4E. Four stores per loop replace one, preserving256 writes and A/B/HL/flags;
old clear and its other callers remain unchanged. Instruction model measures
6180→3108 CPU cycles, including RET. Missing-store negative control differs.
Experimental ROM b799905b139756d9e10e3d382ebad2769ebef63088897ded884534de78acc9f1.

Its own cold3600 checkpoint SHA3d00cddd5776247f9b4b4b3741f9562e986ffbc90b8c6e88781ab32b0ba0c117
matches all serialized machine bytes after offset32 of the parent's own
checkpoint, including APU/timer/clocks. No cross-ROM state retargeting.
Fresh480-frame HP118/Right transition and same-ROM observer-off control have
identical PCM/WAV/video/states/input. Both complete normally. Transition
5484→548C shrinks12456→6312 global cycles, exactly6144 saved, but service
still ends in visible LY7 instead of14.

Do not promote this trial: against the fast-alias parent400/480 rendered
frames differ, although sampled world coordinates and scenes match. HP differs
on141 frames, first118 (106 parent vs111 trial). Full audio guard FAIL:
RMS ratio0.966976,898996 differing sample frames, first16585; silence intervals
also differ. No added clipping or larger maximum sample step. Full differences
retained in `tmp/scene-table-clear-audio-comparison-01`, without alignment or
trimming. The shorter loop alone is not proof of fidelity or a #26 fix.
No deployment/hardware actions; preserve trial for diagnosis.

## Secret VBlank spike narrowed to one scene-change setup (#26)

Fresh `secret-fast-prelude-cost-01`: exact 665a33b6 candidate, its own
e7eeb9b5 frame3600 checkpoint, 480 frames Right, physical DCBB=118 once.
The optional `ENTRY_PRELUDE_COST` probe adds bank13 prelude/scene-detector
boundaries to the existing VBlank helper trace. Full native PCM, WAV, video,
serialized states and input timeline equal `secret-fast-gated-audio-01`.
Restored capture starts with zero pre-restore samples/frames; run exits 0.

Scene detector6F90 runs480 times, but changed-scene branch6F98 runs only once,
at relative frame6. That frame's6FA2→6E83 setup tail takes13632 cycles,
LY152→13; it accounts for most of the16632-cycle6F68→6F6E service spike.
Thus repeated scene-change detection is not the explanation on this route.
Frame7 instead spends4448 cycles from6E83 to572C, a separate prelude path.
The next investigation should isolate these setup/palette paths, not assume
all delay comes from the combined map copier. No ROM timing change is justified
by this observation alone, and the retained audio comparison still fails.

Trace SHA256 c05b642c4b9ca40324fb1d40728a89b4a01a145df33148def667324672320a4a.
Six IRQ accounting tests pass in0.673s, including the new trace-bound
transition count/duration and full observer-neutrality check. No hardware or
deployment actions. Post-run process check found no mGBA processes.

## Palette transaction recovery and launcher verification (#39, #44)

Fresh offline bridge suite: 17 tests pass in 2.031 seconds. The simulated
device transaction covers successful Apply/Undo, upload hash mismatch,
corrupted launcher, reload failure, palette readback mismatch and Undo
failure. Tests forbid real subprocess/device access. Upload failures leave
ROM/stem/history unchanged and request no reload; post-upload failures retain
the previous checkpoint identity for Undo; failed Undo retains its history.
These are mocked workflow checks, not hardware or gameplay acceptance.

Found and filed #44 before implementation: Apply verified the ROM and state
but not the MGL launcher it then loaded. A simulated truncated MGL produced
a failing regression (no exception raised). Apply now verifies the launcher
hash alongside ROM/state before changing session identity or reloading.
The same test then passes. No live bridge restart, hardware call, deployment
or ROM edit occurred. #39 remains open for scene-aware ownership; #44 retains
offline-verified status pending deployment/acceptance.

## Palette Apply rejects ROM-only errors before checkpointing (#39)

Moved ROM-only edit validation into shared pure `validate_edit`, called both
by `Bridge.apply` before directory/checkpoint creation and by `patch` before
editing bytes. Ambiguous primary-row ownership, unchanged quantized colors,
OBJ transparency changes, bad color/index inputs and unsupported ROM layout
now reject without saving slot4, writing an edit directory, uploading or
reloading. Previously those semantic checks ran after `checkpoint()`.
The issue was updated before implementation.

All16 bridge tests pass. New six-case failure test forbids mkdir, checkpoint,
SSH, copy and load and asserts unchanged ROM/stem/history. Existing tests
retain successful byte-local edits, multiple copies of a unique active row,
sequential alias rejection, and exact supported candidate checks. This is an
offline workflow fix: active-row matching still requires a captured state,
and scene-aware disambiguation remains unimplemented. The bridge process was
not restarted and no hardware operation or ROM deployment occurred. #39 stays
open for the remaining workflow/scene-aware validation.

## Recorded-duration menu pause still does not reproduce red bleed (#20)

Fresh reported4f5a cold replay `gargoyle-reported-long-menu-01` changes only
the menu hold from120 to1740frames, using new optional
`ENTRY_MINIBOSS_MENU_HOLD` (default120 unchanged). Same spawn/health/patrol
assistance, Select1350 and3090. Probe0c036e5e…;4080frames captured normally.
The entire first1350 serialized states equal the corrected short-menu control.
LCDC confirms the window visible at1355..3090 inclusive:1736frames, roughly29s.
Native state SHA7c23b65c2b666bf2661e3007c1e2c6478e58795c677c570393a1df2f2efc0bfe.

All3506 boss-tagged states retain one BG CRAM image and no unexpected BG1
assignments under the same narrow plane check. Reviewed PNGs1440,3120,4080
show open menu, resumed combat, and later combat without apparent red scenery
bleed. Three evidence tests pass, including exact pre-stimulus equality,
observed window duration/closure, and the red-attribute negative control.
This rules out the longer hold as sufficient on this assisted corridor route,
not every menu interaction, populated inventory, room, damage or palette-edit
history. It is not a fix or full raster/audio qualification. All raw frames,
states and audio remain retained. No ROM changes or MiSTer actions; process
check after completion found no local mGBA processes.

## Full captured combat/menu palette sampling does not reproduce red bleed (#20)

Reused the authenticated native states from the corrected reported/latest
patrol captures below; no fresh emulator run or ROM edit. All1826 reported
and1744 latest Gargoyle-tagged samples retain one identical64-byte BG CRAM
image, including the scheduled menu interval. Across the LCDC-selected BG
plane's20x18 scroll-aligned cells, every BG1 assignment belongs to tile88,
89,98 or99, all designated BG1 by the existing YAML-derived `_bg_table`
policy. No unexpected red-palette assignment was found in these samples.

Two focused tests pin both raw state hashes, require the exact coverage counts,
and demonstrate that a deliberate red attribute on a non-red tile fails the
cell check. This is a negative reproduction, not proof #20 is fixed: the
window/sprites can cover those BG cells, partial edge tiles are not included,
and frame-end snapshots cannot rule out transient scanline-time corruption.
It also says nothing about OBJ palette errors or later encounter history.
Existing recording contact sheets240–360s and600–640s were inspected again;
they are sparse search aids, not a continuous onset test. The later sheet
shows a prolonged open menu, whereas this short replay closes it after120frames.
That duration difference remains an untested reproduction variable.
Issue #20 stays open; no hardware interaction or readiness claim.

## Corrected combat/menu replay retains the boss-tear repair (#21)

Fresh serial2400-frame cold captures compare reported4f5a67b8 and latest
experimental665a33b6 using the same current probe e76a34e1…:
`gargoyle-reported-patrol-corrected-01` and `gargoyle-latest-patrol-01`.
Native spawn is assisted after560; health alone is refilled through physical
WRAM. The former erroneous DCDD/DCDC resource writes are absent. Floor patrol
alternates directions after1200 and Select1350/1470 exercises the menu.
This is not unaided player traversal.

Reported build:1633 coherent boss frames,18 split frames,175 not fully visible.
Latest:1578 coherent,zero split,166 not fully visible. All2400 samples remain
in each capture, including those outside the boss contract. States hashes:
reported `63fc2863a842c884d3af5615037a2f68c0207565a2ecd237eacd8db443c99779`;
latest `a5251b015485073f7856e9b6dccd6218c148383731956b0913a9087b64bc8651`.
Reviewed native sample845: reported lower boss section is visibly displaced;
latest boss is coherent but at a different position. Do not label these images
an instruction-aligned or pixel-equivalent pair. Earlier guard repair remains
byte-present at2B91..2BDA in the latest ROM; the whole candidate differs in more
than that fix, so this comparison alone does not isolate causal attribution.

Nine geometry tests pass, retaining both the reported failure and latest pass.
Native capture completeness is distinct from restored-epoch qualification:
these are cold runs, so their restored-epoch checker reports FAIL (no restore);
neither is accepted as restored audio evidence. Existing audio-fidelity failure
and broader encounter/hardware qualification remain unresolved. No ROM edits,
deployment, issue closure or readiness claim; MiSTer untouched.

## Latest candidate retains walking/firing raster integrity (#6)

Exact experimental665a33b6 now has fresh cold-start, ordinary-input Stage1
walking/firing captures, without MiSTer interaction:

- `secret-fast-sara-turns-fire-01`:1200frames,45-frame turns,1196 walking
  samples,4 absent startup samples,218649 opaque pixels, zero failures;
  elapsed4.509s.
- `secret-fast-sara-turns-fire-17-01`:2400frames,17-frame turns,2396 walking
  samples,4 absent startup samples,439291 opaque pixels, zero failures;
  elapsed7.408s.

Each route visits eight directional pose quartets. No incomplete/mixed poses,
unsupported raster samples, or missing opaque pixels were reported. Inspected
the first run's sample600 PNG: complete Sara sprite amid Stage1 scenery and
enemies. Fifteen existing Sara tests pass, including missing-pixel and
mixed/partial-pose negative controls. These runs use verifier65972220…,
probe14e374fe…, core20fa5dda…; complete hashes and all per-frame image hashes
are in each receipt. The native-audio adapter was not attached to these
verifier runs, so they add no audio-fidelity qualification.

This extends earlier4731248a visual evidence to the current665a33b6 trial.
It does not reproduce the remaining player-reported MiSTer tear or close #6.
No new game-code fix is justified by these passing routes. The recorded
miniboss fight (#21) is the next useful rendered-failure target rather than
more stationary secret-area timing counters. Existing audio and palette
regressions remain unresolved; nothing was deployed.

## Late-DMA hypothesis does not reproduce missing Sara pixels (#6)

Follow-up captures `secret-stock-oam-lcd-01` and `secret-fast-oam-lcd-01`
add LCDC at the FF46 write. Both have480 writes with LCD enabled throughout:
stock133 and DX109 writes have LY<144. In the DX trace25 of those still report
STAT mode1, so LY alone overstates visible-mode DMA. Original visible-mode
starts range LY1–8; DX ranges0–71. This is not equivalent timing, nor evidence
that the original and DX sprites suffer the same effect.

More decisively, decoding Sara's four 8x8 sprites from each captured state's
actual VRAM and OBJ palette yields **zero missing opaque pixels in all480 DX
frames**. Sprite Y coordinates are80/88 (screen rows64–79). The narrow decoder
rejects priority/bank1/8x16 cases instead of silently claiming their coverage.
It checks only expected opaque content, not extraneous pixels, moving enemies,
bosses, or every possible within-frame state change. This diagnostic does not
reproduce the reported tear and is not a release gate.

An initial attempt using the old verifier's static ROM-art location mismatched
every frame; that art is not the captured VRAM content in this scene and is not
valid evidence of tearing. Use actual runtime art for this route. Full native
PCM/WAV/video/states/input still match each exact-ROM control; five accounting
and rendered-content tests pass. Do not introduce DMA skipping or waiting based
on the late-write count. Next obtain a visibly failing movement/combat route
and correlate its lost pixels with the published sprite data. Issue #6 remains
open. No ROM edits, deployment or hardware actions occurred.

## VBlank helper breakdown and late sprite-DMA observation (#6, #26)

Fresh exact665a33b6 own-state 480-frame replays:
`secret-fast-vblank-helpers-01`, `secret-fast-vblank-dma-01`, and
`secret-fast-vblank-dma-02`. All five full primary artifacts (PCM, WAV, video,
states, input timeline) equal `secret-fast-gated-audio-01` in every run.
Final probe SHA64cf808b91a77313b9a43f69cc70843ea96c602f617f822d0aa472a7d526b073.
No ROM patch, deployment, or hardware interaction.

All480 helper sequences contain every observed boundary. Mean cycles:
73FC→6F1D729.067; register saves96; CALL570E600; CALL6A60136;
palette scheduling6F26→6F3D453.417 (max5352); joypad/dispatch1696;
6F68→6F6E1200.917 (max16632); graphics/OAM6F6E→6F821873.5;
glyph helper224; register restores72. The16632-cycle service at frame6
crosses LY149→14; frame7 costs5056 and crosses152→4.
69 hook entries already have LY<144;206 more enter with LY>=144 and finish
with LY<144. These are observed line-register ranges, not a full LCD-enable
or mode-qualified deadline oracle.

The FF46 watchpoint records480 DMA starts,109 with LY<144. Independent
instruction boundaries corroborate late execution:103/480 FF80 entries and
110/480 FF8B boundaries have LY<144 (boundaries occur at different cycles).
This is a candidate mechanism for missing sprite pieces, not yet a rendered
reproduction of the player's Sara/boss tear. Do not skip or move DMA merely
to pass a timing counter: require complete sprite output, stable game cadence,
and audio qualification. Next check LCD enable and actual sprite scanlines,
then compare the original/parent behavior before selecting a DMA fix.
Three accounting tests pass and preserve the adverse109-start observation.

## IRQ accounting localizes added work to the VBlank hook (#26)

Fresh serial 480-frame captures `secret-stock-irq-cost-02` and
`secret-fast-irq-cost-02` use exact own-ROM states and the existing HP118/Right
diagnostic. ROMs remain original `2f32570c…` and experimental `665a33b6…`;
neither was patched or deployed. Probe SHA:
`1ccc6f752ceee42486e85e7d91ffc0f01d1a40c5dbd42fdff2f242e06b450689`.
Each full native PCM, WAV, video, serialized-state sequence and input timeline
equals its exact-ROM gated control. Two IRQ accounting tests pass.

Measured handler-body cycles (stock / DX): STAT is exactly 600 in all 480
intervals each; VBlank means 2711.633 / 10258.6 across 479 / 480 complete
intervals. The nested CALL0824 boundary at06DC→06DF costs exactly560 in stock
and mean7448.9 in DX (range6648–24832), across480 calls each. Thus the injected
VBlank hook explains much of the measured additional interrupt work; this is
not evidence that the native map expander needs optimizing. Timer means are
3168.324 / 3209.140 across715 / 716 complete intervals.

Stock starts mid-VBlank: its initial complete560-cycle hook lacks an outer
entry, and its final timer lacks an exit. Both remain visible. Hook intervals
are nested measurements, never added to their enclosing VBlank cost. Hardware
dispatch and RETI execution are outside the measured IRQ bodies. Encounters
still differ between stock and DX, so this is not a qualified speed comparison.

Read-only disassembly: DX0824 dispatches to bank13:73FC; the subsequent
6F1D pipeline includes sprite/palette helpers, native joypad polling and
additional graphics work. Bank25:6C80 can publish attributes via GDMA when
FFC4 indicates a pending map. These operations may be necessary; no redundant
work or cause of the recorded yellow trails is established yet. Next isolate
which hook helper accounts for the long calls and whether it crosses a render
deadline. Existing audio-fidelity failure remains open. MiSTer was untouched;
the final process check found no local mGBA process running.

## Map phase split rules out animation as dominant aggregate delta (#26)

Fresh `secret-stock-loop-phases-01`/`secret-fast-loop-phases-01` and then
`secret-stock-map-phases-01`/`secret-fast-map-phases-01` split fixed-bank caller
boundaries without modifying ROMs. All runs retain full480 frames and each
exact-ROM PCM/WAV/video/state/input timeline equals its unobserved gated control.
Final probe SHA352979d1dc1082ad35f3f82dccbef47e23cf4fbc2ce807d2ec54a3ba6cbbcf8a.

Across all132 stock/128 candidate complete periods, mean cycles stock/DX:
four495D calls14677.455/15760.375; DE9 work20378.242/21614.625;
E7C1768.364/1660.75. Map call overall367187.939/382844.75, split into:
entry→12D4 80409.697/87881.125;12D4→12DA63936.909/67682.063;
13xx expansion call12DA→12DD73022.545/75381.063;
12DD→12E0 including copier149452.909/150716.5;
commit12E0→return01F0 365.879/1184.

Every period is retained, with repeated event intervals charged once from their
first phase boundary. Cost is distributed, not concentrated in a duplicate
copier or the four animation calls. Read-only ROM disassembly confirms the
native439F setup entry is unchanged; DX1399 dispatches through bank24:7000,
7500,7380 to its7300 relocated metatile expander in the non-Stage1/non-Stage5
path. This source inspection alone does not establish which dynamic branch or
interrupt accounts for the differences. Existing different encounters remain a
confounder; no speed-parity or redundant-work defect claim is made.

Two accounting tests pass including full raw-capture neutrality and every-period
phase ordering/partition. No new ROM fix is justified by these aggregate numbers
alone. Next compare interrupt-inclusive versus exclusive cost and actual branch
workload in the native map resolution path; do not optimize unrelated animation
or pad the copier. Existing candidate audio FAIL remains. No MiSTer interaction;
all runs completed normally and final process check is clean.

## Full loop accounting locates remaining stock/DX cost outside copier (#26)

Fresh serial480 traces `secret-stock-loop-work-01` and
`secret-fast-loop-work-01` retain fixed-bank loop016C, map return01F0,
services0181/0184/0187 and tail018A, plus the complete copier boundaries.
Probe SHAe203f957b10d56139d49a77b12daacc30b6864f6a32a9eec65abe8dc3c01e42c.
Each exact-ROM full primary capture (PCM/WAV/video/states/input timeline) is
byte-identical to its qualified gated unobserved control. No ROM changes.

`tmp/secret-loop-work-accounting-01.json` retains every132 stock and128 DX
complete period, all constituent events, source hashes, and both partial edges.
Each period partitions exactly with no dropped cycles. Consecutive repeated
boundary hits occur in one stock and four DX periods; they are retained and
their elapsed time charged to the phase starting at the first boundary hit,
not removed or double-counted. Interrupt return is a possible explanation for
repeated hits, not yet a verified cause. The initial strict one-hit parser failed
on these repeats; no result was written until it accounted for them explicitly.

Mean currentCycle units (stock / DX): total504732.182 /520881.5;
copier149254.848 /150528.5; pre-map-return excluding copier254757.152 /271352;
map tail8017.03 /7016.75; service55BB25500.485 /24786.625;
object service66877.455 /66815.625; service4F5D293.212 /350; loop jump32 /32.
The largest aggregate delta is the pre-map-return non-copier region, not the
copier or object service. These are differing workloads, NOT speed-parity proof:
at the initial object boundary stock slots are00/00/26/2E/00 and DX
F9/26/20/27/27. Four495D animation calls, DE9/E7C work, and map preparation
remain combined inside that pre-map region. Inspect/split that region next;
padding the copier would target the wrong measured cost. The audio FAIL remains.

`tests/test_secret_loop_accounting.py` passes source-binding, all-period cycle
partition, partial-edge retention, repeated-event retention, and unequal-object
state checks. Final process check reports no mGBA processes. MiSTer untouched.

## Full copier boundary corrects stock/DX timing scope (#26)

Prior DX timing measured bank28:6C80 to bank1:42ED, excluding preparation and
post-copy work; stock timing measured42A7 to436D. These are not equivalent public
routine boundaries. Added optional scratch `ENTRY_FULL_COPY_TRACE`, observing
bank1:42A7 through the actual caller return with SP advanced by2. The restored
routes use the bank dispatcher's fixed-bank return12E0, not only direct CALL
sites. Probe SHA6929daf65843bd6b352c8d2654d202df7bcf7db3157e319465d887e2522bee1c.

Fresh serial480 runs `secret-stock-full-copy-02` and `secret-fast-full-copy-02`
retain134 and130 complete invocations respectively, no terminal pending call.
Each exact-ROM full PCM/WAV/video/state/input timeline matches its unobserved
startup-gated control. Original low-health132 calls average149295.636 cycles
(142344..178504); candidate128 calls average150541.875 (143880..174256).
First candidate low-health full call507135472..507286080 takes150608 cycles;
its older inner-helper measurement was145912: omitted setup4400 + tail296.
Stock first low-health full call takes144944, including32 cycles after its
previous pre-RET endpoint. All events and differing workloads remain retained.

This does NOT prove cross-ROM speed/audio parity: own-ROM starting states have
different encounter/audio phases, and the workloads diverge. It does establish
that comparing the older inner DX helper against whole stock copier overstated
the apparent speed difference. Do not add arbitrary delay to mimic the broken
parent. Next split non-copier loop time and native object/service workload using
these qualified complete-call boundaries.

Retained failed attempts `secret-stock-full-copy-01`/`secret-fast-full-copy-01`
produced empty traces because the observer omitted dispatcher return12E0; no
timing inference comes from them. `secret-stock-full-copy-callers-01` records
the actual return, motivating correction. Two regression tests validate full
boundaries/raw-file neutrality and reject the empty first attempt. No ROM edits
or MiSTer activity; all emulator runs completed and process check is clean.

## Candidate-side startup check excludes capture race as alias failure cause (#26/#43)

Fresh serial 480-frame runs `secret-parent-gated-audio-01` (d901357a) and
`secret-fast-gated-audio-01` (665a33b6) restore each ROM's own previously pinned
frame3600 state, with Right and one-time physical health118. Both use tap e3287ec6,
probe3ed843b4, the opt-in startup barrier, and 10000us startup delay. Both boundary
checks pass with zero pre-restore audio/video and 1053344 captured stereo samples.
For each ROM, full PCM/WAV/video/serialized-state/input-timeline bytes equal its
retained unbarriered audio capture. Thus the stock startup defect does not explain
the candidate/parent audio mismatch.

`tmp/secret-gated-audio-comparison-01/receipt.json` still fails unchanged guards:
RMS ratio1.0425446889401393, different silence intervals, larger maximum sample
step. First differing sample35733;984047 differing stereo sample frames. No
trimming, clock shifts, threshold relaxation, or game-loop padding. Four audio
evidence tests pass, explicitly retaining this failure. Audio is measured, not
claimed to have been listened to. #26 remains unresolved; this is not a new ROM
fix or release qualification. Next work belongs on runtime copier/game-loop
timing and matched native workload, not further startup-capture instrumentation.

## Opt-in startup barrier passes stock replay controls (#43)

The native AV adapter now supports `ENTRY_NATIVE_START_GATE`: a unique initially
absent marker path. Its reset callback pauses the core before its first CPU loop.
Qt restores the exact own-ROM state normally; the probe creates the marker only
after installing all callbacks/initial inputs. The outer Qt thread-continue then
releases the pause, requiring successful restoration and zero captured frames or
samples. No emulated cycles or PCM samples are removed. This is diagnostic-only,
opt-in, and requires a cooperating restored-state probe (not a cold-boot mode).

Source SHA `2139efd2f6714ac1c4f0e0a4a494c1f7c4c14a049d547df96b4f54db111f47a8`,
tap `tmp/native-av-startup-gate-02.so` SHA
`e3287ec62ba5039d813269c65ddee66c80b96755fc76cda3c03b2aaf0d7b022b`.
Probe SHA `3ed843b477c88756aa9cdebc6700fbf6b925539e05cdb42c2805a2648acfefb3`.
Fresh guarded stock 480-frame runs `secret-stock-startup-gated-on-01` and
`secret-stock-startup-gated-off-01`, both with 10000us host startup delay, capture
1053376 stereo samples with zero pre-restore samples. Full raw PCM, WAV, video,
serialized states, input/sample timeline, and metadata are byte-identical to one
another and the retained `secret-stock-copy-lifecycle-off-01` control. Actual
file hashes were recomputed, not merely copied from receipts. PCM SHA:
`2daf75e218c5cc0c381ef7944647f4abe397d09b60bc436c1daf62ead3bd1022`.

Fresh same-tap/probe negative `secret-stock-startup-ungated-negative-02` (60 frames,
10000us delay, barrier absent) again captures 512 pre-restore samples and fails
the boundary check. Earlier gated 60-frame/1000us run
`secret-stock-startup-gated-delay-01` matches its retained clean control in every
primary file. All launches were serial and completed normally; no MiSTer changes.

This resolves the demonstrated startup contamination in the cooperating stock
replay path. #43 stays open pending harness adoption and candidate-side checks;
it does not waive the separate candidate/parent audio mismatch or qualify a ROM.

## Restored-capture boundary rejection (#43)

Added `scripts/diagnostics/verify_native_capture_epoch.py`: requires exactly one
successful restoration and zero captured audio/video at both boundaries. Missing
lifecycle evidence, incomplete restoration, and contamination fail. The retained
`secret-stock-startup-short-01` control passes; `secret-stock-startup-delay-01`
fails with 512 pre-restore samples. No PCM was trimmed or regenerated. Four new
unit tests and three existing retained-evidence tests pass. Future native capture
finalizer receipts include the separate `restored_replay_epoch` result and its
lifecycle hash; file completeness remains explicitly distinct from acceptance.
Historical receipts are unchanged. This detects the startup defect, not fixes it;
#43 remains open, and no candidate fidelity or release claim follows. No emulator
or hardware was launched for this check.

## Startup race mechanism reproduced with explicit negative control (#43)

Pinned Qt `Window.cpp` starts the emulation thread at2292, loads pending state
at2295, and installs command-line scripts afterwards. Therefore capture can
contain pre-restore audio even when its first video frame is from the restored
state. Added an explicit diagnostic-only thread-start delay knob to the native
tap (default absent/no delay, bounded10000us); it neither edits ROM nor drops
samples. SourceSHA bf78be52cc84da8c853385b66f5cf4a32dfb98e778cd748eabfac4708b11dc82;
`tmp/native-av-startup-mutation-01.so` SHA747e8d81b12376d808788c6826903a178bf375f10b693fbf0cfb58edec833038.

`secret-stock-startup-delay-01` explicitly sets
`PENTA_NATIVE_AV_START_DELAY_US=1000` and runs60 frames. Lifecycle log proves
512 samples are already captured at load_begin, with no video frames; successful
restore retains that count. The unmutated short control has zero pre-load
samples. This reproduces the startup contamination mechanism, not necessarily
the exact scheduling of the old32-sample incident. All raw prelude samples remain
in the capture. The three-test suite now rejects this negative control's
zero-prelude assumption. Fix remains pending: state/script/capture initialization
must be ordered deterministically, or captures with pre-restore data explicitly
rejected; do not retroactively trim them into passing evidence. No game patch or
hardware changes. Guarded diagnostic exited0; final process check clean.

## Audio lifecycle tracing narrows, but does not resolve, #43

The old observed PCM has exactly32 leading silent samples followed by a
byte-identical copy of the unobserved PCM. This offset comparison is diagnostic
only; full-file neutrality still fails and no raw file was trimmed or changed.
Added loadState begin/end observation to `native_av_tap.c`, retaining every
sample and writing `native.lifecycle.tsv`. SourceSHA3023f862743eff4b1fa57692bb418725f4dd91a01cd04f3a5f4c59ccd8e65ae2;
compiled tap `tmp/native-av-lifecycle-01.so` SHA9c5fc0593f70785c0ba72a306bc3d70f73b4def7b2106e3cd66c7e8e73233a20.

Fresh480-frame `secret-stock-copy-lifecycle-{on,off,repeat}-01` all show one
successful load, frame0→3553, with zero audio/video samples before/during load.
All three now match full PCM, video, serialized states, and sample timelines
without offsets or exclusions (1053376 samples each). The old observed run's
extra block does not reproduce with this instrumentation. Therefore do not
assert breakpoints necessarily alter game audio, or that lifecycle logging
fixes the cause: startup/capture nondeterminism remains possible and the original
failed files remain authoritative evidence. The new two-test regression retains
both old failure and new full-file equality. All runs exit0; process check clean.
No ROM/hardware change, no audio release acceptance, #43 remains open.

## Stock copier measurement: audio observer neutrality fails (#26)

The DX copier observer cannot measure stock: the original ROM has no bank28,
and its bank1:42ED is inside the copier, not its return. Disassembly establishes
stock entry01:42A7 and final RET01:436D. Added an opt-in scratch observer using
these boundaries (`ENTRY_STOCK_COPY_TRACE`, probeSHAe7e5d11b701f13d3c146f2d2c79f8955eba1223071a47fc80c34c4b527c367c3).
No ROM edit. Fresh `secret-stock-copy-cadence-01` and exact repeat restore
stock's own frame3554 checkpoint, HP118 once, Right480 frames, with native AV.
134 complete copy intervals: two scene09,132 scene0B. Low-health durations
range142312–178472 currentCycle ticks, mean149263.6364. This is a diagnostic,
not a matched cross-ROM workload or performance qualification.

Crucially, full observer neutrality FAILS. Both observed repeats match each
other in PCM/video/states/timeline. Against fresh same-probe observer-off
`secret-stock-copy-unobserved-01`, all480 video frames and serialized states
match exactly, but PCM and sample timelines do not: observed1053408 versus
unobserved1053376 stereo samples. An earlier unobserved health-log capture also
has1053376 samples. Its timeline differs from observed starting at the first
frame by32 samples. No samples are trimmed, shifted or discarded to call this
equal. Added debugger breakpoints affecting audio delivery is a hypothesis,
not yet a diagnosed mechanism. These timings cannot be advertised as a fully
neutral audio measurement. Preserve complete native artifacts under matching
`/mnt/data/tmp/penta-*-av/` directories. All three runs exit0; no emulator is
left running. Failed candidate audio gates remain failed; nothing deployed.

## Latest secret-alias candidate: doorway and upward traversal (#14)

Fresh cold1216-frame `tmp/secret-alias-doorway-01` on exact665a33b6 passes the
unchanged stock-bound doorway oracle: world1240/1356, camera0C08, all four
priority bits set, zero exposed pixels in the reviewed256-pixel footprint.
Current probe15361266 uses health-only resource assistance; initial position
assistance remains explicit. Original stock reference was authenticated/reused.

New `stock-doorway-exit-up-01` and `secret-alias-doorway-exit-up-01` restore
each ROM's own doorway state and apply120 Up frames, with no memory assistance.
All120 frames have screenshots and states. Both traverse the same distinct
world-position sequence from1240/1356 to1240/1248, but37 frame-indexed positions
differ by up to4 pixels. Preserve this timing difference: neither matching
endpoints nor deduplicated positions establishes speed parity or general
collision equivalence. Terminal stock/DX screenshots were inspected; neither
establishes the separate ordinary-floor no-bleed guard. Complete unaligned
position sequences, differences and bindings are retained in
`tmp/doorway-up-comparison-01.json`. Existing doorway negative control remains
available; no acceptance thresholds changed. Runs exited0, final process check
found none running. No ROM patch, deployment, hardware action or issue closure.

## Continue result survives corrected Stage2 checkpoint (#28/#41)

Fresh serial6000-frame runs restore the physical-assistance checkpoint
`secret-alias-stage2-physical-entry-01/stage2.ss0` into its exact665a33b6 ROM.
`secret-alias-stage2-physical-continue-a-01` observes native death2352, A input
start2414, native A edge,10 Continue polls, resume2470, no title transition.
`secret-alias-stage2-physical-continue-neutral-01` instead observes481 polls,
no A edge/resume, and title3314. Both complete with their intended oracle result.
Their full trace.tsv hashes match the respective earlier runs exactly:
A `d44229f590f7a95df0fe3ea9176ab8c813b98b42aecff603b4bb8ae050afb9e7`;
neutral `b3f2437b2a27c333b550c182c09a9c11d9b30d540e95ac376e2494c7a63b6d0e`.
Thus the repaired Continue outcome on this route did not depend on the fixture's
stray bank3 write. This does not prove that byte harmless on other routes.

The A endpoint screenshot was inspected. The regression test now covers these
two fresh cases plus the four retained controls, including the failing reported
ROM (one test, six subcases, all expected results). Native death follows assisted
health1 and Up movement; the precise collision/death cause is not asserted.
This is not the recorded secret-return corruption history, full audio, or
hardware qualification. No ROM/deployment change or issue closure. Final process
check reports no emulators running.

## Stage checkpoint assistance no longer writes graphics scratch bank (#41)

Extended the existing issue before editing. `probe_stage_integrity.lua` now
writes DCBB/DCFD assistance through physical WRAM bank1, independently of SVBK,
and reports the bank selections seen at those writes. The shared Lua-helper
test executes both speed and checkpoint implementations across selections0..7,
preserves scratch sentinels, and demonstrates failure of the old mapped-write
control. All three tests in `test_stage_speed_physical_assistance.py` pass.

Fresh guarded Stage2 generation on exact665a33b6 candidate completes atframe718:
`tmp/secret-alias-stage2-physical-entry-01`. ProbeSHA
`65ecb67f5f8d88c2d721cc0d6c6099148b382ce9633a157a49a93002872c4a89`;
stateSHA `8e5d630a5eb0af1112600986eaff69016f46fb895aab31d03355816d534f6a23`.
Of268 assistance writes,267 see SVBK1 and one sees SVBK3. Comparing the complete
decoded state against the prior same-ROM Stage2 checkpoint gives exactly one
changed byte: serialized80BB (physical bank3 D C B B offset) wasF0 and isnowFF.
Thus the original generator really did overwrite graphics scratch on this route;
the repaired run preserves it. All other serialized bytes, including game state
and clocks, match. The Stage2 screenshot was inspected. This establishes a
harness repair, not a player-visible ROM fix or qualification of the candidate.
No ROM/hardware/deployment changes; #41 stays open for broader harness review.

## Low-health black-background change is an old palette-source failure (#23/#26)

Follow-up `tmp/reported-secret-lowhealth-cram-01` restores the same reported-ROM
checkpoint as the controls below, runs their first60 frames with one-time HP118,
and enables the existing CRAM-write observer. At frame9, bank0D shared copier
PCs71E6/71E8/71EA/71EC first write correct BG0 `ff7f947e4a3d0000` during
VBlank. A second BG0 publication attempts the known erroneous source
`070607ff7f947eff`: its final two writes (7E/FF) arrive in LCD-on mode3 at
cycles507266638/507266670, so the previously published black color3 remains.
This explains the prior pink→black observation without a new palette policy.
The bad source matches the already diagnosed FFBA7 table overrun at68C5 and
the existing #23 source-table repair; it is not a newly established yellow-band
cause and does not justify another ROM patch.

Observer frame60 PNG equals the unobserved control byte-for-byte
(`8ec0ddfd6fa2067bf47e26db9136ded8c2d3a42b527501b952f33c802c708da9`).
The decoded serialized state also matches byte-for-byte; PNG savestate container
hashes differ. This is endpoint neutrality only, not full video/PCM neutrality.
The short run exited0; process check then found no emulators. No hardware action.

## Reported ROM: fresh populated-menu scrolling / low-health control (#26)

`tmp/reported-secret-menu-scroll-entry-01` freshly cold-boots reported ROM
4f5a67b8 for 3600 frames using current probe15361266. Unlike the older dense
fixture, resource assistance writes only physical DCBB health, not DCDD/DCDC.
Inventory is explicitly seeded at1180 and position assisted once at2401; this
is not an ordinary-input reproduction of the recording. Own-ROM frame3600
SHA `ff06ed43cd8a0a2a844242f8fb580da719eb31eeb6bd0e53a5194267ea440cf5`
is restored without identity retargeting for both 480-frame controls.

`reported-secret-menu-scroll-healthy-01` and `...-lowhealth-01` hold Up,
open/close MEDICAL with Select at120/240 (six frames each), and continue moving.
The latter changes physical DCBB once to118. Both complete normally; sampled
menu is open150–240 and closed270 onward; both move x72,y992→612. Healthy
scene remains09; low-health scene becomes0B at saved frame8. Palette comparison
shows only BG0 color3 changing from serialized FF7E to0000, between samples8
and30, before the menu opens. OBJ palettes and tile-pattern bytes stay constant
through each run. Map contents change with scrolling; attribute buffers change
with menu state. Low-health sampled endpoint is black versus healthy pink
background, with the existing broken secret geometry in both; both endpoint
PNGs were inspected. Neither demonstrates the recorded yellow-band expansion.

Full saved-state hashes/regions are in
`tmp/reported-secret-menu-scroll-comparison-02.json`; frame8 is explicitly
unpaired, not shifted against the other run. The initial comparison01 is retained
but its cross-run zip summary is superseded by frame-keyed comparison02. This
control rules out menu-close plus this particular Up/low-health route as a
sufficient reproduction; it does not rule out other positions, items or palette
edit history. All three emulator runs exited0, and the subsequent read-only
process check found none running. No ROM patch, hardware action, audio pass,
or issue closure follows from this negative reproduction.

## Recorded yellow-band expansion localized before secret return (#26)

Read-only recording review; no ROM, emulator, or hardware changes. The previous
turn only acknowledged gameplay and made no bug-fix progress. This review narrows
the next reproduction target rather than claiming the experimental copier repair
matches the player's failure.

Source remains `/mnt/data/Videos/2026-09-27 20-40-28.mkv`. New diagnostic crops
are in `/mnt/data/tmp/penta-miniboss-red-review-02/`. The 1645–1665 second sheet
samples at 2 Hz; the 1661–1663 sheet samples at 20 Hz. Both were inspected.
Scattered red/cyan wall patches already exist at the start, so this is NOT the
first corruption onset. The conspicuous persistent yellow/red wall bands expand
near 1661.8 seconds (27:41.8), still in the secret area. The MEDICAL menu was
visible around 1657.5–1659.0 and is closed during this expansion. Earlier menu
use is not exonerated; a return-transition-only cause cannot explain these bands.

`onset-native-1661_6.png` retains all 30 decoded source frames in a half-second
window, without an fps sampling filter (source reports 60/1 fps). Labels are
relative to seek 1661.6. Frame label .188 still has the predominantly white/blue
wall; .204 shows a narrow red/yellow strip at its right edge; .221 shows the
broad red/yellow column, persisting in subsequent frames. These are OBS recording
timestamps and scaled diagnostic crops, not emulator cycle or VRAM observations.
They do not distinguish palette writes, attribute publication, tile changes, or
capture tearing. Next reproduction should include secret-area scrolling after
closing the populated menu and inspect tile IDs, bank-1 attributes, and palette
RAM together. A palette-only hypothesis would be falsified by changed tile or
attribute data accounting for the affected columns with palette RAM unchanged.

SHA-256 bindings:
- `onset-1645.png`: `616ce307bce9c9edca7870be41dc357267a4890a139dc6146191135b3b970f88`
- `onset-1661.png`: `9c0e10e85f5cdf3d26c18645c92ccb7372610498151f87e529f4c29dcbca24a1`
- `onset-native-1661_6.png`: `353a9cf68b5420f389725c6dc8fcbe331b013b7425590bb5d5e0607cec7b604d`

The separate 600–640 second miniboss sheet was inspected at 1 Hz: menu open
through much of the fight, no obvious red wall bleed in those samples. That is
not a full-frame negative result and does not resolve #20. #20 and #26 stay open;
no audio, hardware, or release qualification is added.

## Secret alias experiment is reproducible from source (#26)

`scripts/build_stream_regression_candidate.py` now accepts explicit
`--presentation --arena-alias --arena-completion-safe --secret-sound-alias`.
The new last flag defaults OFF, requires the completion-safe chain, and is marked
experimental/audio-unqualified in CLI help and build receipt. Default construction
and deployment selection are unchanged.

Fresh `tmp/secret-sound-alias-fast-source-01` reconstructs the exact665a33b6 ROM
from original cartridge and palette source, with no retained candidate input.
The final overlay and transitive Python helper hashes are recorded. Source tests
check the pin, source identities, explicit dependencies, default-off behavior,
and retained failed-audio warning; release_qualified remainsfalse. This makes the
visual repair reproducible; it does not promote it or resolve audio acceptance.
Older control source receipts are preserved. New control folders are
`arena-completion-safe-source-02`, `arena-alias-source-03`, and
`stream-presentation-source-04` for the updated builder identity.

## Continue movement replay rejects actual streamed build (#28)

Fresh `reported-stage2-continue-up-a-01` uses the same probe/input policy as the
latest candidate and its own CRC/header-matched Stage2 entry. Actual streamed ROM
SHA4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5,
state SHA4112b5c1480552041153df6aec07eb355494f59491d96f537e06cb7a54f8267f.
It reaches death1216 and receives A pulses1278 onward, but448 native Continue polls
show no A edge; no resume, title2125. Oracle correctly FAILS, with all6000 frames
retained. Encounters/death times differ across the separately generated entries;
this proves the missed-input symptom, not performance equivalence.

Fresh `secret-sound-alias-fast-stage2-up-start-01` is the third current665a33b6
control: death2352, no A edge, no resume, full countdown, title3314. Together with
current A/neutral results this preserves original A-only Continue semantics.
`test_stage2_movement_continue.py` re-evaluates all four actual traces and authenticates
each entry's ROM CRC/header; all four subcases pass expected outcome assertions,
including the old build's failure. Issue28 remains open for full recorded route,
audio/hardware acceptance. No ROM edit or deployment in this qualification step.

## Stage2 movement-to-death Continue pair passes on latest experiment (#28)

Added explicit opt-in `--approach-up` to the checked-in Continue runner, restricted
to Stage2 prompt-relative mode. After the existing disclosed health/credit stimulus,
hold physical Up from1202 until the first native death scene; stop movement then
and never resume it after Continue. Oracle validates that entire schedule, including
movement release on death and after resumption. Default stationary cases unchanged.

Fresh6000-frame pair on665a33b6, using its own Stage2 entry above:
`secret-sound-alias-fast-stage2-up-a-01` reaches death2352, begins A pulses2414,
observes a native A edge, consumes credit and resumes2470; active Stage2 persists
through6000, no title. Terminal gameplay screenshot inspected.
`secret-sound-alias-fast-stage2-up-neutral-01` reaches the same death2352, counts
down fully, never resumes or observes A, and returns to title3314. Both pass.
Probe SHA `fec273d24fbede41e16118293ce464821c890d000f4d662cf119564899177049`.
18 builder/oracle tests pass, including four wrong-movement schedule mutations.

This is a genuine movement-triggered native death with assisted initial health,
credit and level-select entry, NOT unaided progression or the recorded corrupted
secret-return history. Does not qualify audio/hardware or close28. Stationary
2400/6000 failures remain preserved; no scene or controller-register forcing was
introduced. The candidate ROM itself did not change during these tests.

## Latest Stage2 Continue trial lacks a death trigger (#28)

Fresh own-ROM Stage2 entry for665a33b6 uses the existing guarded native level-select
generator, saved at frame718, scene03/stage01. State SHA
`b3d3941ba58f29fc25397d87e34d1a2de652d81f18d33e57eb12a7f001a285cf`, under
`secret-sound-alias-fast-stage2-entry-01`. Both fixed2400-frame and prompt-relative
6000-frame A trials terminate normally but the oracle rejects them with
`death not reached; not a Continue test`. Full artifacts remain in
`secret-sound-alias-fast-stage2-continue-a-01` and
`secret-sound-alias-fast-stage2-continue-prompt-a-01`.

Health DCBB really changes to01 at1201 and stays01 through6000. No native Continue
poll occurs. The terminal screenshot remains active Stage2, not a Continue screen.
Disassembly explains a missing prerequisite in the fixture assumption: native
bank1:41F1 tests DCDF nonzero, then decrements it and DCE0; only when the latter
reaches zero does4200 decrement DCBB and potentially dispatch death4A44. Merely
setting DCBB=1 is not a guaranteed death stimulus without pending damage. This is
not evidence that the input repair regressed. Previous d744 pass remains qualified
only for its own captured encounter state. Next use an actual collision route or
explicitly disclose/validate a native pending-damage fixture; do not force scene
or Continue input registers and call it a natural reproduction.

## Corrected secret diagnostic health column (#42)

Filed issue42 before changing the scratch probe: trace `hp` previously read DCDC,
not actual health DCBB. Updated only that read to physical WRAM1 offset1CBB; old
captured probes/traces remain unchanged. New probe SHA
`15361266cfe09e625f031c55f74dd72630b1dca3d0ddb4bf8bf98261f9055590`.
Fresh480-frame `secret-sound-alias-stock-health-log-01` records118 initially and108
at the end; all17 sampled health values match serialized physical DCBB. The old
trace fails the same check. Complete native PCM/video/states/input timeline remain
byte-identical to `secret-sound-alias-stock-lowhealth-01`.
Two tests in `test_secret_health_telemetry.py` cover actual saved-state readings and
whole-capture neutrality. This is a diagnostic correction, not a game bug fix or
audio acceptance. The ROM is unchanged. Generalizing the scratch replay into a
checked-in reproducible harness remains separate work; issue42 stays open for that.

## Fresh stock low-health secret control reaches the same position (#26)

Stock ROM SHA2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30
was cold-booted using the same declared health/inventory/entry-position assistance
and inputs (`secret-sound-alias-stock-own-entry-01`). It reaches x72/y860 in secret
stage07 at frame3554 rather than candidate frame3600. A fresh cold run ending3554
(`secret-sound-alias-stock-position-01`) captures that position without altering
the checkpoint. State SHA0a000d355f47ffdb26be734b1e31f93f048533258ae606d088ac8bca55eaaf51.
No cross-ROM state identity changes. This is an assisted route, not unaided play.

`secret-sound-alias-stock-lowhealth-01` restores that exact stock state and performs
480 frames Right with one physical DCBB=118 write, no subsequent refill. It records
133 original loop entries, versus126 broken-parent and129 patched entries. First
stock loops are frames2,6,10,14,18 at x72,76,80,84,88; terminal position104/860.
Native PCM/video/states are retained under
`/mnt/data/tmp/penta-secret-sound-alias-stock-lowhealth-01-av/`.

The stock sound-command trace does NOT share the candidate's initial command1B
request; its first request is18 at frame217. Matching player position therefore
does not establish matched encounter state or audio phase. Do not interpret
129/133 as a qualified slowdown measurement, or compare these PCM files as an
equivalent-route acceptance pair. This establishes a usable stock scene control,
and disproves assuming the patched129 loops necessarily exceed original speed.
Next compare object/service workload and scene-local loop cadence; all existing
audio failures remain retained. Also note the scratch probe's legacy `hp` column
reads DCDC, not DCBB: health claims must use physical savestate DCBB instead.

## Low-health copier is faster than broken parent; stock speed still unqualified (#26)

Fresh480-frame `secret-sound-alias-parent-cadence-01` and
`secret-sound-alias-fast-cadence-01` record original loop016C and copier entry6C80
through return42ED. Every complete PCM/video/state/input timeline matches its
unobserved same-ROM audio run. Read-only analysis: `tmp/compare_secret_cadence.py`.

Parent completes126 observed loop entries; candidate129. The first healthy copy
is exactly identical: cycles506566848..506708488 (141640). The first low-health
copy starts at507139872 in BOTH: parent ends507299016 (159144 cycles), candidate
ends507285784 (145912 cycles), a13232-cycle reduction before later encounters
diverge. First differing loop boundary is frame14 versus13 at the same x84/y860.
All recorded low-health copies: parent124, mean157954.58/max194680; candidate128,
mean145675.69/max169560. These later aggregate workloads are not necessarily
identical. The finite window censors surrounding loops/copies; entry and completed
copy counts are not interchangeable.

This supports a real speed difference introduced by switching the low-health
path back to the combined copier, not observer slowdown. It is faster than the
known-broken parent, but original-game speed has NOT been qualified here. Do not
add an arbitrary delay to reproduce broken-parent audio, or waive the failed
audio gate. Next obtain a stock low-health secret-scene cadence/audio control
through its own native route; no cross-ROM state retargeting.

## Sound-event trace is neutral; runtime cadence diverges (#26)

Fresh480-frame `secret-sound-alias-fast-events-01` and
`secret-sound-alias-parent-events-01` add existing sound-request/read/accept/reject
breakpoints and timer/APU-trigger watches. For EACH exact ROM, the complete native
PCM, video, serialized-state and input timeline hashes match its unobserved audio
run. The instrumentation is neutral over these captures, not merely screenshots.

The first differing observed APU trigger timestamp is FF14 at frame14:
parent508064434 versus candidate508064442 cycles, same value86. The first three
command events match exactly; the next command20 request arrives at frame74 in
parent versus73 in candidate (516484480 versus516233240 cycles). All20 paired
command event/type/caller tuples match, but candidate has27 events: seven extra
terminal events are UNPAIRED, so this is not a matched encounter/full-route proof.
First differing trigger event/value tuple is index41 at frame73. These findings
locate runtime divergence after the matched checkpoint; they do not establish
acoustic fidelity or justify dropping silence/level failures.

The candidate has714 consecutive secret-context timer intervals, max112864 cycles,
no interval above the unchanged141312-cycle guard. Trace SHA
`e2030094e7a3fd57b9f4bdab335f18549885fff90dd5068d1cb1305ed9ec93f2`.
`tests/test_secret_alias_event_evidence.py` retains neutrality, unequal event counts,
and earlier candidate request timing. Next inspect copier/game-loop cadence before
altering audio code: no missing-command defect has been established here.

## Secret alias fallback preserves healthy paths; audio remains unqualified (#26)

New experimental builder `scripts/diagnostics/build_secret_sound_alias_fast_trial.py`
moves alias handling after the original raw09/0A classification. Only the original
JR NZ destination changes in the old gate; healthy09/0A and non-stage07 instruction
paths retain their original addresses and instructions. Exhaustive routing tests
pass. Candidate `tmp/secret-sound-alias-fast-trial-01/candidate.gb`, SHA
`665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7`.

Fresh assisted cold4200-frame route `secret-sound-alias-fast-own-entry-01` now
has frame3600 APU, sound I/O, audio buffer, master/global cycles and timer bytes
identical to the parent's own checkpoint. No state retargeting or editing.
The same480-frame Right/one-time-health118 native AV replay completed in
`secret-sound-alias-fast-audio-01`. Both maps rows0..23 have32 offscreen projected
mismatches at frame1, then zero at every saved30-frame sample through480; the
parent retained88 at samples30..480. This is sampled, not full-raster coverage.

Untrimmed native audio still FAILS (`secret-sound-alias-fast-audio-comparison-01`):
first differing sample35733 rather than7, RMS ratio1.04254468894; level, silence
interval and maximum discontinuity guards fail. Silent-block and clipping guards
pass. Healthy-path preservation removes the initial-state confound, but does not
qualify low-health audio. Keep both failed variants and all samples. No deployment,
promotion or issue closure. Next investigation is the low-health copier's runtime
effect on sound/encounter timing after the common initial audio prefix.

## Audio replay deterministic; cross-ROM starting sound states differ (#26)

Recovered `tmp/secret-sound-alias-audio-repeat-01/receipt.json`: exit0,
480 frames and1053344 stereo sample frames. Read-only process check found no
running mGBA. The repeat's complete PCM, video, serialized states, metadata and
timeline are byte-identical to `secret-sound-alias-audio-01`; capture randomness
does not explain this pair's failure.

Inspected the original own-ROM frame3600 checkpoints against the pinned core's
`include/mgba/internal/gb/serialize.h`. Before replay or one-time health assistance,
APU channel state already differs. Sound I/O differences are FF18, FF21, FF22,
FF23 and FF26. In particular FF26 is86 in the parent versus8E in the candidate:
the candidate's noise channel is already active and the parent's is not. The
candidate global cycle counter is8 cycles ahead. Thus this is not an equivalent
starting sound state, and shifting PCM by a constant would not establish it.
Read-only diagnostic: `tmp/inspect_secret_audio_start.py`.

`test_secret_alias_audio_evidence.py` now checks the actual full repeat and pinned
initial checkpoints in addition to retaining the failed untrimmed comparison.
This establishes a comparison confound, NOT sound fidelity or that every later
silence difference is harmless. No acceptance threshold or ROM changed. Next
audio qualification needs native sound-event/dropout evidence from matched
encounters, not cross-ROM savestate editing or acceptance-time alignment.

## Native audio comparison FAIL retained for secret alias candidate (#26)

Compiled the checked-in native AV tap against the pinned core's actual header
paths/compile definitions. Binary `tmp/secret-alias-native-av-tap-01.so`, SHA
`337c75dfaa448939c5089ef60ad78fb854ce46b883eaaf7a35669b258590f2d7`.
The single-flight launcher still owns the emulator; tap capture is not a launch
bypass. Fresh480-frame own-ROM low-health Right runs:
`tmp/secret-sound-alias-audio-01` and `tmp/secret-sound-alias-parent-audio-01`.
Explicit unmuted/full-volume options and capture hashes are in their receipts.
Large artifacts are `/mnt/data/tmp/penta-secret-sound-alias-audio-01-av/`
and `/mnt/data/tmp/penta-secret-sound-alias-parent-audio-01-av/`.

Both files validate complete:480 video/state frames,1053344 stereo PCM16 sample
frames at131072Hz. WAV wrappers preserve PCM unchanged. The untrimmed comparison
at `tmp/secret-sound-alias-audio-comparison-01` FAILS, retaining every sample
difference. RMS ratio0.991306 and zero clipping pass their narrow guards, but
digital-silence intervals, silent blocks, and maximum sample step fail.
Parent/candidate maximum steps15366/15388. Parent silence intervals:
[368026,375733),[758001,765813),[934777,942463); candidate:
[195676,203517),[374017,381640),[940687,948341).

1049762 sample frames differ, first at7. The separate own-ROM checkpoints have
not established equal starting audio phase or encounter histories. Therefore
this is a failed acceptance comparison, not proof that the gate patch introduced
an acoustic defect. No trimming, alignment, resampling, normalization or threshold
relaxation was used. The clips have NOT been listened to; no perceptual claim.
`test_secret_alias_audio_evidence.py` rechecks the actual complete PCM and keeps
all three failures explicit. No promotion, deployment or closure is justified.

## Low-health secret copier retains bounded interrupt spacing (#26)

Added canonical FFB7/stage FFBA columns to the existing optional scratch timer
observer. Updated `check_secret_timer_spacing.py` to include raw0A/0B only when
explicitly tagged canonical09/stage07; raw09 behavior is unchanged. Otherwise
the old raw09-only check would omit the low-health portion being qualified.
The existing1.5 nominal-period delay threshold is unchanged. Tests include an
artificial late alias interval that must fail, other-stage boundary handling,
and retained real delayed-interrupt/menu negative controls.

Fresh480-frame own-ROM low-health Right continuations:
`tmp/secret-sound-alias-timing-01` (877ed751) and
`tmp/secret-sound-alias-parent-timing-01` (d901357a). Both contain714 consecutive
timer intervals, no boundary intervals, no late intervals, ending on native
sound0B. Maximum observed cycles: candidate110312, parent118696; nominal94208.
First/last intervals remain censored. This supports bounded interrupt servicing
in this sample, not identical speed, native PCM fidelity, full-route or hardware
acceptance. All17 candidate sampled PNGs match its preceding uninstrumented
replay; that is not a full A/V observer-neutrality claim.

Observer SHA `ce944121013863bd52629856a1c602a6f88d4ae07cb0700d266acc98ffc0e981`.
Trace hashes and exact maxima are asserted by the tests. Six timer tests plus
eight alias tests pass; no emulator remains. No ROM edit or deployment this step.

## Low-health secret exit retains correct attributes and restores dungeon policy (#26)

Fresh600-frame paired continuations from each ROM's own frame8040 checkpoint:
`tmp/secret-sound-alias-lowhealth-exit-01` (877ed751) and
`tmp/secret-sound-alias-parent-lowhealth-exit-01` (d901357a). One physical
DCBB=118 intervention, pulsed A, no subsequent health refill or rendering writes.
Checkpoint history retains declared cold-route position/inventory/health assistance;
this is not a fully unassisted playthrough. Both receipts complete normally.

Ten active-secret samples1/10/20/.../90: candidate zero policy mismatches;
parent0/0 followed by16 at every sample20..90. All saved evidence retained.
Candidate native sound changes09->0B at6; stage07->00 at96, intro18 at114,
dungeon02 at298 and low-health sound0B again at359. At600, both runs are active
Stage1 with canonical02, HP118, menu0 and a nonzero pause timer (41/42).
Both restore the same256-byte dungeon C600 table, SHA
`90b7393e610c67b97cd32664fae294ec76d10fd9a25384e004320b76c4ad4cb4`.
Candidate endpoint picture inspected: intact blue/white dungeon scenery.

Thus the demonstrated improvement is secret-area attribute publication BEFORE
exit. Both builds can complete this exit; do not call return completion a repaired
parent failure. No recording-cause, identical cadence, full raster/audio, or
hardware claim. Eight focused tests now include this actual paired evidence.
No new ROM changes, deployment or issue closure; emulator process check is clean.

## Secret alias fix: low-health miniboss and assisted return checks (#26)

Exact877ed751, own frame4200 checkpoint,480frames Right with one physical
DCBB=118 health intervention: `tmp/secret-sound-alias-miniboss-lowhealth-01`.
All17 saved samples have zero tile-signature policy mismatches across1536cells.
Samples30..480 keep raw sound0B/canonical09/stage07/miniboss15/menu0. Health
falls118 to78: no health refill, invulnerability or rendering writes during
this replay. Terminal picture inspected: purple/white scenery, gold miniboss,
colored pickups; no obvious persistent bands. This is not a complete fight,
pixel-equivalent combat trace, sprite-tear gate or acoustic qualification.

Fresh12000-frame cold route `tmp/secret-sound-alias-return-01` uses the existing
explicit position, health-refill and dense-inventory assistance. Native pause
item activates at7261 (timer60), persists across secret exit: stage00 at8137,
intro at8155, dungeon02 at8340 with timer45. The run reaches a stage00 miniboss
at11026 and ends12000. Inspected8400 and12000 pictures show intact geometry
without the recorded widespread yellow/red bands. This is a HEALTHY assisted
return, not proof of low-health exit or the recording's exact input history.
Transition times differ from the parent; no speed-equivalence assertion.

Seven focused tests pass, retaining all sampled miniboss cells and explicit
assistance/return/pause assertions. Normal process exit confirmed; no emulator
left running. No hardware, source-chain promotion, issue closure or deployment.
Remaining qualification includes low-health exit, timing/audio and wider routes;
the actual recorded persistent-trail cause is still not proven.

## Dense secret-alias replay localizes the remaining transient offscreen (#26)

Fresh own-ROM120-frame replays, identical Right input and one health118 write:
`tmp/secret-sound-alias-dense-01` (877ed751) and
`tmp/secret-sound-alias-parent-dense-01` (d901357a). Captured every frame,
not only every30. Both complete normally with the retained probe f07da29a.
No other emulator or hardware activity; no ROM changes in this step.

`tmp/analyze_secret_alias_frames.py` retains all120 frames, state hashes and
every mismatched cell in each run's `alias-map-analysis.json`. It projects cells
using the final LCDC/SCX/SCY/WX/WY state; this is explicitly NOT a mid-scanline
raster oracle. Candidate: only frame30 has mismatches (44), and all are outside
that projection. Parent:110 frames11..120 have40–44 projected-visible mismatches.
The parent mismatches persist on both maps, rather than a single update boundary.

Candidate screenshots29/30/31 and parent30 inspected directly. Candidate keeps
the sampled pickups' colored appearance through the boundary; parent shows
neutral/white pickup details. No widespread recorded yellow/red bands appear.
The candidate's wrong offscreen cells and parent failures remain in raw evidence;
none were discarded to claim whole-plane or raster perfection. All five shared
PNG samples1/30/60/90/120 match each build's earlier sparse replay byte-for-byte.
That is a limited sampling consistency check, not full A/V observer neutrality.

Five focused tests pass, now retaining dense coverage, state bindings, the
offscreen transient, the failing parent, and sampled PNG consistency. No release,
hardware, full-fight or audio qualification. Next coverage: low-health secret
miniboss and return transition on the exact patched ROM.

## Secret low-health copier routing defect isolated and patched experimentally (#26)

Correction to the preceding LUT-only investigation: unchanged C600 does NOT
establish correct attributes. Both-map rows0..23 policy inspection found32
transient mismatches at frame1 in the parent healthy/low-health pair, then
healthy0 versus low-health88 at every30-frame sample30..480. Native sound0B
causes bank28:4000 to bypass the secret copier: it accepts only raw09/0A.
Evidence was posted to issue26 before implementing the fix:
https://github.com/struktured-labs/penta-dragon-dx/issues/26#issuecomment-5873598862

`build_secret_sound_alias_trial.py` changes only that bounded gate and checksum.
It retains stage07 and raw09/0A routing; only raw0B consults canonical FFB7.
The sound fields themselves are untouched. Exact d901357a parent produces
`877ed7510cd59d79117d160f70493cf4ecff0b1ca822697a3834d119de104f7f` under
`tmp/secret-sound-alias-trial-01`. This is not promoted into the source chain.

Generated a fresh own-ROM checkpoint by the same assisted cold-entry route:
`tmp/secret-sound-alias-own-entry-01`,4200frames. Then repeated480frames Right
from its frame3600, with one physical DCBB=118 intervention, under
`tmp/secret-sound-alias-lowhealth-01`. No cross-ROM savestate reuse.
All17 saved samples retained: mismatch counts are frame1=0, frame30=44,
then0 at EVERY30-frame sample60..480; parent stays88 at30..480. The frame30
transient is not excluded or claimed fixed. Sampled frames30..480 retain native
sound0B/canonical09/menu0. Endpoint screenshot inspected; no persistent bands.
Different own-ROM startup phases mean no pixel/cadence-equivalence claim.

Four tests pass: executable gate truth table over all raw/canonical byte pairs,
other-stage exclusion, bounded patch/hash checks, and actual parent/candidate
sampled attribute evidence with the failing parent retained. Full raster timing,
transient publication, performance/audio, scene exit, and hardware remain open.
This proves a bounded publication improvement, not the recorded trails' cause.

Also retained the new secret miniboss parent controls
`arena-secret-miniboss-lowhealth-01`/`arena-secret-miniboss-healthy-01`,480frames
from own frame4200. Low health reaches automatic MEDICAL by480; these are not
a matched full-fight comparison or proof of miniboss palette correctness.
Do not close #26 or extend its fix claim to these controls. No MiSTer changes.

## Secret-area low-health alias: bounded non-reproducing control (#26)

Tested a missing condition in the healthy assisted secret-return routes. Exact
d901357a source-build ROM, its own saved frame3600 from
`tmp/arena-completion-safe-late-pause-return-01`, 480 frames holding Right.
State SHA `3c6c1c0e7f6c68e1bd0dfb71d60f7653a9990430ad132e403c3f06d097b992ca`.
No state retargeting. New retained runs:
`tmp/arena-secret-healthy-control-01` (no memory writes) and
`tmp/arena-secret-lowhealth-01` (one physical-bank1 DCBB health write to118
at the first frame callback). No scene, palette, cursor, cache, or graphics
writes. Both diagnostic receipts report normal completion; original checkpoint
was generated with position/resource/inventory assistance, not ordinary progress.

Native code inspection confirms bank1:5050 sets DD06=1 below128 health, and
4F6E publishes sound scene0B whenever DD06 is nonzero. In the low-health run,
sample30 has raw scene0B, canonical FFB7=09, cache DF0D=0B, HP118. The healthy
control retains raw/cache09. At480, health is106 versus243. Nevertheless C600's
full256-byte lookup table matches between runs at inspected samples1/30/120/480
(SHA `b3757dbb934881df967b2c4d8a335745f73470327fd580b83ee0f61fbf2a1878`).
Both endpoint screenshots were inspected: intact purple/white right-hand wall,
no widespread recorded yellow/red bands. Actor arrangement differs, so this is
not pixel equality or timing qualification. No audio or hardware claim.

Probe copy SHA `f07da29a799860985835fe0387dda963f7cfaebce5cddaec3e715d1d67363146`;
the added scratch option records its single health intervention in the receipt.
This rejects a simple Shalamar-like C600 replacement explanation for this
secret09 window only. Secret miniboss0A and other histories remain untested by
this pair. Do not broaden the arena resolver or close #26 on this evidence.

## Completion-safe Shalamar fix is reproducible through the source builder (#27)

Added explicit `--arena-completion-safe` to
`scripts/build_stream_regression_candidate.py`, requiring both `--presentation`
and `--arena-alias`. This extends the experimental chain with the direct-scene
resolver while retaining bank16/31 legacy completion. Defaults and the old
explicit alias-only chain are unchanged; no automatic promotion or deployment.

Fresh construction from original cartridge and palette sources:

```sh
uv run --with pillow --with pyyaml python scripts/build_stream_regression_candidate.py \
  --presentation --arena-alias --arena-completion-safe \
  --output tmp/arena-completion-safe-source-01
```

Output SHA-256 is exactly
`d901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a`,
matching the earlier bounded emulator-tested trial. The construction receipt
records all loaded project Python source hashes, stage parent/output hashes,
and `release_qualified=false`; it uses no retained candidate ROM as input.
This is source reproducibility, not a new emulator run or complete validation.
In particular, route-match failures and unresolved recorded yellow/red trails
remain outstanding. The old receipts and failed experiments remain intact.

Fresh presentation-only control `tmp/stream-presentation-source-03` still
produces d744124d. Source tests now use fresh receipts for the changed builder
identity rather than rewriting historical receipts. New tests reject missing
explicit prerequisites, authenticate the d901 output and transitive sources,
and require the old and new alias chains to remain distinct. The fresh old-chain
control `tmp/arena-alias-source-02` reproduces 585f5830 unchanged. Focused source,
installer, and retained native-restart checks: 22 tests pass. No hardware touched.

## Native spawn selection explains the observed extra type bytes (#27)

Completed the pending parent run; both fresh guarded 1800-frame receipts remain
FAIL on route matching, not release qualifications:
`tmp/arena-stage1-spawn-trace-01` and
`tmp/arena-parent-stage1-spawn-trace-01`. Candidate d901357a still has 422
measured loops, parent d744124d has 431, and stock has 429.

At the native `$2317` spawn store, all nine candidate and four parent events
(including one loading event each) agree with the captured native selection
table. Both repeated replays agree. The five choices are decimal
`[4,25,16,42,8]`. Candidate loops 45 and 255 select `$2A`: captured FFD1=44,
ROM[$0D85+44]=93, 93 modulo 5=3, choice[3]=42. Parent selects `$10` at all
four observed spawns. This rules out an unexplained slot write as the source
of these particular `$2A` appearances; it does not prove all object behavior
correct or establish the first cause of the different encounter histories.

Live candidate bytes confirm timer vector `$0050` jumps to `$06B3`, whose
`$06C4` calls `$0D79`; that helper increments/wraps FFD1. The selector at
`$0D5D` also advances that index. Thus selection is timer-sensitive, but an
interrupt between selection and the observed store remains possible. Sampled
index agreement is a consistency check, not a complete RNG execution trace.
No RNG freezing, enemy removal, gate relaxation, or ROM patch was performed.
Stop treating aggregate loop difference as isolated renderer overhead; further
performance claims require accounting for the differing native workloads.

Probe SHA-256:
`5931f1161529c1782e25782fda7a90119523b8605597490cf76395d8ae1ac994`.
`tests/test_native_spawn_evidence.py` checks both replays against exact candidate
and parent hashes, the native timer bytes, and every captured selection. Flipping
each captured type byte makes the consistency check fail (negative control).
This is diagnostic evidence, not validation of the user's visible Shalamar
symptom. Issue #27 remains open; MiSTer and the player's game were untouched.

## Object workload differs; aggregate loop deficit is not isolated rendering cost (#27)

Fresh service-boundary traces locate most mean excess in the native2222 service:
parent63716 versus candidate76626 CPU cycles. The preceding55BB service averages
22974/24289; map-caller-to55BB8309/8054;4F5D303/262. The entire2222..27F3 ROM
range is byte-identical between d744 and d901357a. Native2222 walks five8-byte
object records startingDC85; this identifies measured records, not their art names.

Added physical-bank1 slot-type reads at the existing optional trace boundaries.
Fresh repeated guarded receipts: `tmp/arena-parent-stage1-object-trace-01` and
`tmp/arena-stage1-object-trace-01`. Full logs and per-period analyses retained.
Over all complete periods, parent430 averages1.281 nonzero slots; candidate421
averages2.658. Type2A appears in376 candidate periods and ZERO parent periods.
Most common tuples: parent[0,0,0,16,0]214 times; candidate[0,0,16,16,42]107 times.
Decimal16/42 are native type bytes10/2A, not claimed monster names. Terminal
partial periods remain explicitly censored in interval analysis; full raw traces
and1800-frame gate outputs remain intact. Both original gate verdicts stay FAIL.

This changes the interpretation:422 versus431 iterations is a real observation,
but not a workload-matched measurement proving extra rendering CPU cost. It must
not motivate deleting colorization or changing native object behavior to gain a
passing ratio. Native spawn code calls0D5D, a table selector advancingFFD1;
the cause of the different object histories still needs tracing before attributing
it to RNG startup phase, gameplay timing, or an actual gameplay regression.
The earlier simple mapper/lookup-cost hypotheses remain rejected, not fixed.

Probe SHAa9d1ea42a0c38eee092161d6bcde734c52346f7708dcaecbaca4c3575c125b20.
Cycle-accounting tests now verify raw-slot coverage and the observed mismatch,
alongside exact native code equality, without changing acceptance policy.
No ROM, hardware, or deployment changes; all known-bug work remains active.

## Cycle tracing locates the difference after map-return boundary (#27)

Optional existing loop/copy traces now include currentCycle, LY, DIV, TIMA,
IF and IE. Copy tracing adds3497 completion and12E0 caller-return boundaries.
No ROM changes. Fresh repeated1800-frame receipts:
`tmp/arena-stage1-tail-trace-01` (d901357a422 loops) and
`tmp/arena-parent-stage1-tail-trace-01` (d744431 loops).
Both still FAIL route coverage. Full attribute traces match their prior runs.
The earlier cycle-only runs are retained separately under
`arena-stage1-cycle-trace-01` and `arena-parent-stage1-cycle-trace-01`.

All complete consecutive-anchor periods are retained:421 candidate/430 parent.
The start before the first anchor and end after the last anchor are explicitly
censored, not silently folded into complete-period timings. Each period is
partitioned without gaps; raw TSVs and complete per-period JSON remain available.
Same-core, same-CGB-mode mean CPU-cycle diagnostics (not acceptance averages):

| Interval | d744 parent | d901357a |
| --- | ---: | ---: |
| Loop anchor to copy entry |355629|355699|
| Copy entry to copy-done |51147|50413|
| Copy-done to first12E0 hit |77913|77670|
| First to last12E0 hit |5662|5857|
| Last12E0 hit to next loop |96632|110500|

Thus most mean excess falls AFTER the last caller-return boundary, not in
copying/compiling. Compiler-entry to3497 averages125310 parent/123557 candidate.
Repeated12E0 breakpoint hits are retained; they are not claimed to be distinct
completed calls. This localizes the next observation to sprite/gameplay services
and interrupt/wait work after12E0, before016C. It does not prove a timer cause.
The four calls after map handling at0181/0184/0187/018A are useful next boundaries.
Both longer intervals and the two candidate seven-frame gaps remain in evidence.

Probe SHA2910bbeef1fdedcc17604480cd6077039860cbccb5c83f92b96ab8b0740bfb86;
diagnostic analyzer `tmp/analyze_stage_cycle_trace.py` SHA
86acdf1127bb0615d776da09896947589dca79917cc72919fa319b365542a849.
Accounting regression verifies every complete period partitions exactly and
neither failed gate nor slow intervals are dropped. No hardware touched.

## Alias-only miss optimization rejected on measured Stage1 throughput (#27)

Experimental82d09c7e8bd42df760cf40cfce86669efaf44e6f1398ace15b485711f6cd3c5f
adds CP0B/JR NZ after the unchanged scene-cache hit prefix. Non-alias misses
skip the mapper resolver; raw0B still takes the existing FFB7-aware resolver.
The bank20 mapper rendezvous moves from6F9A to6F9E, with its return adjusted.
Builder: `scripts/diagnostics/build_arena_alias_only_miss_trial.py` (SHA
f57ecd6acec4e42f8f773e79344723027c03f5e39befff54841dfc41fe4f9dc6).
Four source/layout/classification tests pass, including all raw/canonical scene
pairs and exact preservation of completion/runtime source ranges. Those tests
are not emulator qualification of the relocated alias path.

Fresh sequential repeated1800-frame patrol with corrected physical assistance:
`tmp/arena-alias-only-stage1-speed-01/manifest.json` gives stock429/candidate418,
versus d901357a's422. Route coverage also fails. Thus the smaller normal-miss
path worsens measured throughput in this window; REJECTED FOR PROMOTION.
No expanded qualification, source-chain change, deployment, or hardware action.
Do not pick this build on instruction counts alone. The evidence continues to
point toward startup/interrupt/map-completion phase interactions; their exact
mechanism remains unproven. A cycle/phase observation at actual gameplay/map
boundaries is more useful next than another speculative micro-optimization.

## Stage-speed assistance no longer writes into selected graphics banks (#41)

Filed #41 before changing the harness. Its frame callback wrote DCFD=01 and
DCBB=FF through mapped CPU addresses even when CGB graphics work selected a
different WRAM bank. The helper now writes physical WRAM offsets1CFD/1CBB and
records the FF70 low bits at each write. Lua execution tests exercise the actual
helper across selections0..7, preserve bank2/3 sentinels, and demonstrate that
the old mapped write fails that scratch-preservation invariant.

Fresh sequential repeated Stage1 replay:
`tmp/arena-stage1-physical-assistance-01/manifest.json`, exact d901357a ROM.
Candidate records4733 assisted writes:4579 with FF70 low bits1,150 with bits3,
and4 with bits7. DMG FF70 readsFF; its low bits7 must NOT be interpreted as
physical bank7. The150 bank3 observations confirm the unsafe context exists.
Correcting writes does not recover throughput here: stock429/DX422 and the
full DX attr-events SHA remains e3856e06147114efd5608ab387cc115166c5a3dac43ad5a650b4db3160fb7db7.
Overall FAIL remains on route coverage, with deterministic repeats. This fixes
a harness defect but does not establish it caused the player's corruption or
the measured slowdown. Probe SHA06681638e5ba97a09fc335a76a955fed729ebbd7bc0e36f449e073fdd8fc626e.
No ROM or hardware changed; issue remains open for wider harness validation.

Prior to that correction, the retained one-frame sync-delay diagnostic at
`tmp/arena-stage1-sync-delay1-01` gave stock428/DX422, still route FAIL. One
measurement-start shift alone did not eliminate the candidate deficit. Do not
choose a favorable start offset as an acceptance workaround.

## Detector reversion and bank-qualified tracing reject a simple cost explanation (#27)

Diagnostic76368800 restores only d744's112-byte scene detector into d901357a,
deliberately removing the scene-cache alias fix. Its fresh repeated patrol
(`tmp/arena-detector-cost-speed-01`) falls to407 loops against stock429, rather
than recovering d744's431. It fails throughput and route gates. This is not a
candidate for deployment; the diagnostic builder/receipt are retained in tmp/.

Unqualified CPU-address traces initially reported470 hits at6F98 and6F9F.
Register samples showed those were other ROM banks, so the existing optional
probe now also emits an exhaustive FF99-shadow histogram per address. FF99 is
explicitly a mapper shadow, not an assertion of physical bank identity.
Fresh `tmp/arena-detector-bank-trace-01` reports1610 detector-entry hits with
FF99=0D and ZERO miss-path hits with that shadow. All470 apparent miss hits
belong to shadows1A/1E (235 each). The measured detector path is therefore the
byte-identical cache-hit prefix, not the new alias mapper work. This rejects
attributing the observed deficit to alias-resolution cost during this window;
startup/raster timing and completion interactions still need investigation.

Probe SHA5330d157dca6eceebf21c14cc1d034ab65926be11b8284aa65c53a44676a9afd.
The instrumented repeat still has422 loops and an identical full attr-events
trace to the prior same-ROM run, with the route failure retained. This is narrow
observer consistency, not full video/audio neutrality. Three cost-evidence tests
and four observer tests pass. No production ROM or hardware changed.

## Stage1 resolver-cost hypothesis falsified in the patrol window (#27)

Four fresh sequential 1800-frame patrol comparisons retain the performance
failure. Three diagnostic ROMs individually replace one bank13 CALL DBDF with
the original raw D880 read: dispatcher e43495f1, copy-gate 088b64fa, and semantic
3b3d89c4. These deliberately lose some arena-alias protection and MUST NOT be
deployed. Each still produces 422 loops versus stock429; all repeat traces are
deterministic and the full DX attr-events trace equals d901357a's existing trace
(SHA256 e3856e06147114efd5608ab387cc115166c5a3dac43ad5a650b4db3160fb7db7).
Their receipts are under `tmp/arena-{dispatcher,copy-gate,semantic}-cost-speed-01`.

The unchanged d901357a diagnostic trace at
`tmp/arena-completion-stage1-path-trace-01` counts zero DABB, DB80, DBA6, and DBDF
entries, but235 DBDC completion entries. Thus the three extra resolver calls
cannot explain this replay's throughput loss: they do not execute in the
measurement window. This does not establish their cost in other scenes, nor
prove boot-prefix neutrality. All four overall verdicts remain FAIL on route
coverage. No acceptance gates or production builder were changed. Next isolate
the earlier alias chain from the completion/guard changes, rather than weakening
arena protection. Diagnostic builder is `tmp/build_dispatcher_cost_control.py`;
its first dispatcher receipt predates adding the site selector (historical
builder hash, not a current-source binding).

The subsequent exact585f5830 pre-completion parent comparison at
`tmp/arena-fastpath-parent-stage1-speed-01` produces415 loops (stock429), worse
than d901357a's422. Consequently the safe completion change improves this
window by7 loops; the earlier alias chain already carries the deficit relative
to d744's431. Next bisect the scene-detector/graphics-owner/fastpath chain and
its boot timing. This is a measured localization, not proof of one instruction's
cause. The parent also fails route coverage. Two local evidence tests pass,
retaining the individual negative results and zero-call trace. No hardware or
release changes were made.

## Stage1 performance failure retained; combined-helper observer repaired (#27/#40)

The corrected-cursor stage-speed probe ran1800-frame loop-patrol on d901357a
and d744. Stock:429 loops, d744:431, d901357a:422. Thus the trial is1.63% below
stock and2.09% below its presentation parent in this window. Both DX runs fail
the overall gate on exact route coverage; do not promote a throughput sub-pass.
Artifacts: `tmp/arena-completion-safe-stage1-speed-01/receipt.json/manifest.json`
(output option was inadvertently named receipt.json but is a directory), and
`tmp/arena-completion-parent-stage1-speed-01/manifest.json`.

Both also initially failed central OBJ telemetry: old observer watches separate
11A2/1188 helpers, while combined doorway/flash code calls DB40. Filed #40 before
changing observer. It now authenticates the whole helper and caller bytes,
observes DB40 entry, DB5C flash/priority boundary, and DA45 output. Entries and
outputs are counted separately without weakening the missing-telemetry check.
Initial observer edit hit Lua's200-local limit and timed out before a receipt;
preserved `arena-completion-safe-stage1-speed-02`. Consolidating counters into a
table fixes compilation; a Lua5.4 syntax-only test now guards this failure.

Fresh `arena-completion-safe-stage1-speed-03` captures12213 entries and12213
outputs; throughput422, emitter12231, tile/palette counts and complete attr-events
trace match pre-observer-change evidence. This is narrow observer consistency,
not full video/audio neutrality. Overall verdict still FAIL on route mismatch,
as required. Four observer tests and eight assistance tests pass. Source-layout
checks authenticate the actual combined helper. #40 remains open pending further
negative-control validation; Stage1 performance cost needs attention under #27.
No ROM modifications/deployment, and no emulator remains.

## Healthy Shalamar throughput comparison (#27; #37 probe correction)

The boss-speed probe still wrote DCDC/DCDD=FF, the #37 inventory corruption.
Removed those two writes before fresh measurements. Deliberate DCBB health,
D888 and DD06 arena-hold assistance remains; this is NOT natural low-health
performance coverage. A retained stock checkpoint had cursor255, so it was
not reused: fresh stock entry is `tmp/arena-completion-speed-og-state-01`.

Fresh1800-frame anchor-synchronized measurements, repeated twice per ROM:

| Build | loop hits | maximum gap | bank-parked frames |
| --- | ---: | ---: | ---: |
| Stock | 337 | 6 | 0 |
| d744 presentation parent | 337 | 8 | 85 |
| d901357a completion trial | 336 | 8 | 68 |

All1800 frames remain in the denominator; raw/filtered anchor counts agree and
each repeated trace matches. Candidate ratio336/337=0.99703264 (0.2967% fewer
iterations) passes the unchanged2% gate without exemptions. Do not call it
cycle-identical: one iteration and the parked-frame distribution differ.
Artifacts: `arena-completion-safe-shalamar-speed-01/receipt.json` and
`arena-completion-parent-shalamar-speed-01/receipt.json` under tmp/.
Probe SHA45407d6aec53efe7303d5bdbae06d6026c8d4f5993802a4ecc032a0d282a6873;
verifier SHA702653cbf3780b475132c8750217273ae6e9baea35c5a02b29849d90477482f9.
Runs used the previously bound Qt/libmgba and single-flight wrapper.

Thirteen completion-trial tests and eight native-item-assistance tests pass,
including a slowdown negative control. Other-stage and low-health performance,
audio, remaining visual issues, and hardware remain outstanding. No deployment.

## Legacy nonzero completion executed with explicit pending-flag injection (#27)

The retained stationary diagnostic `arena-completion-safe-pending-injection-01`
completed180frames with `injected=false`: it did not reach a map completion and
is explicitly noncoverage. A separate ordinary-Right movement variant,
`tmp/arena-completion-safe-pending-walk-injection-01`, restored the exact d901357a
post-repair state and injected FFE1=1 once at DBDC after checking the legacy
trampoline/tail and native Stage1/SVBK1. This is fault-injection coverage, not
normal input-only proof of how pending palette work arises.

Frame6 trace: DBDC→DBDF→4000→4042→DBEE→3497. FFE1 is1 through4000 and0 at4042;
the original pending-palette branch clears its flag and returns through DBEE.
The mapper changes directly in the legacy tail, so FF99 remains01 while bank21
code executes; the probe checks the mapped entry byte instead of treating that
shadow as physical-bank proof. The trace follows the statically decoded branch.
Frame180 was inspected: intact lavender Stage1 architecture, active player,
HP253, scene02/menu0, no stranded completion. Twelve focused tests pass.
Both completion branches now have targeted execution evidence. This does not
qualify arbitrary injected states, audio, performance, all scenes or hardware.
Scripts/identities are retained in the diagnostic receipt and named
`tmp/run_completion_pending_walk.py` / `tmp/probe_completion_pending_walk.lua`.
No ROM changes or deployment; no emulator remains after the run.

## Legacy repair executed with explicit fault injection (#27)

`tmp/arena-completion-safe-repair-injection-01` restores d901357a's exact-ROM
Stage1 frame9000 and deliberately injects D880=0B plus stale DADE..DAE0=C2B9DA
once at the native3492 callsite, requiring SVBK1 and canonical FFB7=02.
The source state comes from the assisted secret route. This is a diagnostic
fault test, NOT evidence that normal play generates the stale code.
Runner/probe hashes and emulator identities are bound in completion.json;
the scripts are `tmp/run_completion_repair.py` and `tmp/probe_completion_repair.lua`.

Execution trace: frame1 bank31:6F00 and6F55, frame2:6D4D, frame4 DBDC→DBDF→3497.
Snapshots2..180 contain the restored C41300 gateway, legacy conditional tail
behind JPDBDF, and relocated guard. FFE1=0 throughout, so this demonstrates
the zero branch only; the nonzero bank21 completion branch remains untested.
The frame180 image was inspected and shows intact lavender Stage1 geometry.
The native scene is back to02 by frame10; no health/gameplay fix claim follows
from injecting the low-health sound-scene byte. Eleven focused tests pass.
Process check confirms no emulator remains. No ROM change or deployment.

## Completion-preserving resolver: Ted coverage, not legacy execution (#27/#32)

Candidate d901357a has a fresh Ted checkpoint in
`tmp/arena-completion-safe-ted-state-01` (entry302, settled292). Before generation,
bank17 was verified byte-identical to recognized d744, SHA256
`6aa4f5f8105b300176429bfe69b7dce4688720f915982e3a6243202acc9ce8d7`;
bank21 also matched. The exact candidate was added only to
`relocated_ted_latches`, not to the cold-Penta/fixture inheritance set. This
changes the generator's source identity: older manifests binding that file
remain historical evidence and must not be asserted current without rebuilding.

The own-ROM600-frame Left escape (`arena-completion-safe-ted-escape-01`) and
1080-frame three-menu replay (`arena-completion-safe-ted-menus-01`) have no
game-memory writes. All three strict menu cycles PASS, replay wall5.5264s;
final scene10, HP232, menu0. Final image inspected: intact orange/red Ted on
lavender arena. No low-health alias frames occurred.

Crucially, all1080 runtime snapshots retain bank13's direct resolver and
JP3497 trampoline. Ted gameplay therefore does NOT establish execution of the
bank16 legacy completion path. Source investigation identifies bank31 as the
scene0B stale-gateway repair installer, gated on SVBK1, canonical Stage1 and an
exact obsolete gateway preimage; ordinary current-runtime play need not execute
it. Next qualification must target those actual preconditions and keep deliberate
fault injection distinct from ordinary gameplay. Ten focused tests pass,
including explicit checks that Ted coverage does not imply legacy installation
or cold-Penta fixture approval. Audio/timing/full-scene qualification remain open.

## Completion-preserving resolver: secret return and native restart (#26/#27)

Exact d901357a trial completed a fresh12000-frame cold route in
`tmp/arena-completion-safe-late-pause-return-01`. Inventory/position/health
assistance is explicitly retained in its receipt; it is not a reconstruction
of the recorded stream. Pause item activates at7261 (timer60), Stage1 returns
at8334 (timer46), and timer eventually reaches0. The parent585 route returned
at8436; these timings are not equivalent and do not prove preserved gameplay
cadence. Sampled secret frames3480/7080/7440 have no tile-policy attribute
mismatches. Frame9000 was visually inspected: lavender walls/floor, intact
architecture, no observed widespread yellow trails.

At7080/7440/9000 DF0D remains0A despite native scene09/09/02. The installed
direct resolver survives and does not use this stale cache. All sampled runtime
tails remain bank13's layout: this route does NOT prove bank16/bank31 legacy
completion execution or self-heal behavior. #26 remains unreproduced/open.

`tmp/arena-completion-safe-natural-restart-01` additionally passes movement-driven
native-damage death/game-over/title/Stage1 restart twice (`ok 2 2 2`), including
saved-game stage cards, terrain,482 title-frame pairs and102 game-over frames.
Eight tests in `test_arena_completion_safe_trial.py` pass after rechecking raw
captures with the existing validators. No hardware changes; process check after
the runs reports no remaining mGBA process. Audio/performance and legacy installer
coverage remain outstanding; the candidate is experimental and unpromoted.

## Completion-preserving resolver: fresh narrow emulator evidence (#27)

The d901357a trial below now has its own fresh Shalamar state in
`tmp/arena-completion-safe-shalamar-state-01` (entry frame100) and a complete
1080-frame three-menu replay in `tmp/arena-completion-safe-shalamar-phase721-01`.
All three strict cycles PASS; replay wall time4.6415s. Actual captured runtime
DBDC..DBFC matches the intended trampoline/resolver/guard layout at frames1
and1080. This replay has zero low-health alias frames, so it is not the alias
symptom proof.

Two exact-own-ROM, no-memory-write idle continuations (2400 then6000frames)
reach native low health. The dense180-frame replay from the second continuation's
frame2160 is `tmp/arena-completion-safe-shalamar-onset-01`. Raw D880 switches
to0B at frame119; all62 alias frames119..180 remain active gameplay (menu0),
canonical FFB7=0C, with the correct Shalamar C600 table. The inspected frame120
shows a consistently cyan boss on the lavender arena. The retained d744 broken
control frame999 has raw0B/canonical0C but the wrong dungeon table. Six tests
now pass, including these state-level observations and the broken control.

These runs use the same single-flight guard and Qt/libmgba identities captured
in completion.json; no hardware was touched. Long idle capture eventually
reaches the native medical menu, and those menu samples are not counted as
active alias-fight coverage. Legacy/self-heal transitions, performance and audio
remain unqualified; this is not full #27 closure or release readiness.

## Completion-preserving direct resolver layout (#27; initial static evidence)

Fresh trial `tmp/arena-completion-safe-trial-01/candidate.gb`, SHA-256
`d901357a105036469b8debbff138fb63e87afb3a0cfbe5a24eeaafa91353910a`,
is built by `scripts/diagnostics/build_arena_completion_safe_trial.py` from
the exact 585f5830 parent. It is NOT promoted or emulator-qualified.

Read-only disassembly found a third semantic-runtime installer at bank31:7196
and its guard source at bank31:71E3. Like bank16, it owns the conditional
completion tail, not bank13's direct JP3497. All three installers now retain
their own completion behavior behind a DBDC trampoline. Bank13's resolver
occupies DBDF..DBF1; the last RET is installed with the guard fragment.
The guard is compacted and moved to DBF3; both fixed-bank callers and all three
guard sources move together. Bank16/31 continue native raw scene reads; this
does not yet establish an all-scene alias fix. The conditional guard's cycle
cost and trampoline cost differ from the parent and need measured qualification.

Five static tests pass (legacy tail preservation for both installers, resolver
fragment boundary, guard sources/callers, shared stack-restoring return, exact
parent rejection). These are layout checks, not proof of visible correctness,
speed, audio, or transition safety. No emulator or hardware was launched while
the user's latest status says they are playing. Next: qualify this layout on
its own fresh-ROM Shalamar replay, then exercise legacy/self-heal transitions.

## Direct scene resolver trial retained, not accepted (#27)

`build_arena_direct_scene_trial.py` replaces bank13's three global cache reads
with a19-byte WRAM resolver. It reads native D880; only raw0B with FFB7 in0C..14
uses canonical arena identity. All other inputs return raw scene, independent
of DF0D. Exhaustive65,536-pair emitted-instruction tests pass, including the
new stale-cache counterexamples. It shares identical pure-return tails and
reclaims bank13 DBDF's redundant JP3497 with adjacent padding. Bank16's
distinct runtime tail was NOT overwritten; its graphics reads revert to raw.

Candidate`578028889c93ba6b810bc9002d0efa7c0bcc606b03f4ef87556f30a94b8a9e8d`
in`tmp/arena-direct-scene-trial-01` enters Shalamar109. Fresh own-ROM1080-frame
phase721 replay has cycle verdicts PASS/FAIL/PASS, remaining map-readiness
failure; no alias frames, final HP173/menu0. Installed19-byte resolver matches
exactly. This replay is NOT evidence of fixing the low-health symptom.

Promotion blocker found during caller review: changing bank1 JPDBDF directly
to JP3497 preserves bank13 completion but can bypass bank16's conditional
completion tail if that legacy runtime is installed. Thus byte-preserving the
legacy tail is NOT behavior preservation. Candidate rejected for promotion;
not added to source chain. Builder commentary now warns of this limitation;
original build receipt is retained unchanged (its older builder hash remains
historical, not current-source proof). Need a completion-preserving placement
or relocation strategy before further qualification. No hardware/deployment,
oracle relaxation or issue closure.

## Secret-return freshness counterexample constrains alias fix (#26/#27)

Fresh585f5830 route `arena-alias-late-pause-return-01` completes12000 frames
with the same explicit dense inventory, initial position and ongoing health
assistance as retained d744 control. Native pause-item effect spans return at
8436 (timer44). Secret samples3480/7080/7440 match the authored1536-cell palette
policy; inspected return9000 looks intact. This is not a reproduction or fix
verdict for the recorded yellow trails.

Important counterexample: DF0D=0A at7080/7440 while D880=FFB7=09, and remains0A
at9000 while D880=FFB7=02. The retained d744 control has the same stale cache.
Thus global cache freshness is FALSE. This does not itself prove wrong visible
output (09/0A both take a neutral shared-dispatch route), but invalidates the
general ownership assumption behind the six-read graphics-owner overlay.
Do not promote585f5830 on its Shalamar/menu PASS alone. Two regression tests
retain the stale-cache counterexample alongside successful sampled palettes.

Continuation `arena-alias-secret-unassisted-continuation-01` starts from own-ROM
7080 state and runs6000 frames, pulse A plus native pause-item menu sequence,
with no replay memory writes or health refill. Initial state still inherits
the explicitly assisted setup. Native Stage1 return1356, miniboss scene0A4752,
low-health sound alias0B5124; final HP79/menu0/canonical02/cache0A. Final6000 image
inspected, no widespread yellow trail pattern seen. Cache staleness persists
without ongoing assistance. Next fix must resolve the sound alias in graphics
consumers without treating DF0D as universal identity; no criteria relaxed,
hardware touched, release promoted, or issue closed.

## Source-rebuilt alias fix passes native death/restart route (#27/#18)

Fresh `arena-alias-fastpath-natural-restart-01` tests exact585f5830 with
movement-driven native damage, ordinary B dismissal of low-health inventory,
and the explicitly assisted save-present flag for score/level cards. Two
complete death/Game Over/title/Stage1 restart cycles finish at6867 frames.
Strict verdict PASS includes102 Game Over frames and482 returned-title frame
pairs, stage cards and terrain restoration. Game Over screenshot inspected:
readable white lettering with purple accent. This tests Stage1 death/restart,
not an arena-to-dungeon progression route or hardware/audio fidelity.

The source builder now exposes explicit `--presentation --arena-alias`.
`tmp/arena-alias-source-01` rebuilt from original cartridge+palette sources
without retained candidate ROM inputs and exactly reproduced585f5830. Receipt
binds all three new builders and transitive source files. Build defaults and
release status are unchanged. Three new tests verify option guard, source
bindings and independently rerun restart oracles.

The prior presentation source-01 receipt correctly fails current-source
identity after this builder change; preserve it as historical evidence.
Fresh presentation-only source-02 is used for the unchanged d744 default
experimental branch's construction test, rather than updating old hashes.
No bug closure, promotion, deployment or broad stream-readiness claim.

## Scene-cache fast path restored; menu PASS plus native alias onset (#27)

`build_arena_alias_fastpath_trial.py` produces experimental candidate
SHA256`585f5830daa32e59c000f5ddd6b57aab545e55375b46574286702db9fc28e4db`
at`tmp/arena-alias-fastpath-trial-01/candidate.gb`. The original eight-byte
raw-scene cache-hit prefix is restored byte-for-byte; mapper/resolver work is
now paid only on misses. Compact title/story dispatch fits the original112-byte
slot; exhaustive emitted routing comparison against original covers all256
scene values, including exact DF08/DF02 writes. No native sound-state writes
are changed. Miss/alias path cost and all-scene timing still need qualification.

Fresh own-ROM Shalamar entry settles at100, versus207 for previous experiments
and102 for original parent. These are distinct phases, not equivalent states.
`arena-alias-fastpath-shalamar-phase721-01` passes all three menu cycles over1080
frames and all existing strict checks. This run has ZERO sound-alias frames;
do not use its PASS as evidence of exercising the original bug.

Continuation `arena-alias-fastpath-shalamar-idle-01`2400frames uses no keys or
memory writes. Own-ROM1440 state then feeds180-frame every-frame capture
`arena-alias-fastpath-shalamar-onset-01`:135 alias frames46..180, including47
active-gameplay frames46..92 before the automatic low-health menu. Every alias
frame retains DF0D=0C and exact Shalamar C600 policy. Native sound D880=0B remains
unchanged. Frame60 inspected: Shalamar fight, intended cyan body and purple
floor; no broad dungeon-table recolor. Setup remains synthetic boss entry;
continuations are ordinary native damage, no health/cursor/palette writes.

Previous35a8 trial frame597 mismatch investigation: the ENTIRE selected24x24
tile AND attribute planes remain byte-identical596..602; the staging source
finishes its next pose at601 and selected map flips603. This supports a
staging/publication distinction but is not scanline proof. Retain its FAIL;
no oracle relaxation. No deployment, hardware/audio/full-fight qualification
or issue closure. Next work includes cache-freshness transitions, remaining
sprite tearing and other open reports, plus integrating only qualified fixes.

## Graphics-owner dispatcher trial improves alias replay (#27)

New `build_arena_graphics_owner_trial.py` changes only six absolute read
operands (three mirrored runtime source sites) plus global checksum on4eff32d4.
Candidate `tmp/arena-graphics-owner-trial-01/candidate.gb` SHA256
`35a8d40bc9ed8cf3d967d0c01df0674bcf119a0ec0364ef1bcb60493a9448af7`.
DABB dispatcher, DBA6 semantic owner and DB80 copy gate read DF0D (installed
graphics identity), not D880 (native sound alias). Instruction widths/cycles
at these six sites are unchanged. All-transition cache freshness is NOT yet
qualified; this remains an experiment, not a replacement release.

Fresh own-ROM Shalamar state again enters207. The1080-frame phase721 replay
`arena-graphics-owner-shalamar-phase721-01` installs all three new reads and
retains intended C600/DF0D through156 native alias frames925..1080. Compared
with4eff32d4 replay, every PNG1..928 is byte-identical; every PNG929..1080
differs. Third menu cycle improves FAIL->PASS. Final1080 screenshot inspected:
actual Shalamar gameplay, HP85/menu0, versus previous trial's MEDICAL menu.
This narrows the change to the alias interval in this pair, not full speed,
audio, transition or hardware qualification. Three regression tests pass.

Overall verdict remains FAIL, cycles PASS/FAIL/PASS. The second-cycle failure
at597 (24 cells) is **VRAM0 tile IDs versus current C1A0 staging source**, NOT
an attribute-plane comparison (correcting the initial commentary wording).
Frames593..596 match; mismatch counts597..602 are24/137/243/233/201/201;
selected map flips at603 and matches. This may reflect staging of a new pose
after reveal, but the gate remains unchanged pending publication-level proof.
The raw-D880 residency failures are also preserved. No issue closure or
deployment. Next: qualify staging-versus-visible publication and DF0D freshness
on actual transitions; remove unnecessary hot-path overhead in the first trial
before treating different-parent combat/cadence as equivalent.

## Experimental arena sound-alias scene-cache repair (#27)

`build_arena_sound_alias_trial.py` builds exact d744124d parent into
`tmp/arena-sound-alias-trial-01/candidate.gb`, SHA256
`4eff32d4aa5519486371835690730bba26d2c282f3b3481199e34125d88588db`.
It replaces only the graphics scene-cache prefix using a guarded bank20 cave
and mapper-only rendezvous. Raw D880=0B resolves to FFB7 only when canonical
scene is0C..14. D880, FFB7 and native DC09 are never written by the new helper.
All other raw/canonical combinations retain raw scene identity. Exhaustive
65,536-pair emitted-bytecode policy checks pass; these do not prove IRQ safety
or timing. Do not use the apparent DAEE..DAFF padding: retained live states
show executable transition code there, contrary to older source comments.

Fresh own-ROM state `arena-sound-alias-shalamar-state-01` enters at207;
this differs from parent's102 and is not phase-equivalent evidence.
`arena-sound-alias-shalamar-phase721-01` captures1080 frames with ordinary
Select inputs and no replay memory writes. Frames925..1080 (156 frames)
retain native sound alias0B/canonical0C while DF0D remains0C and C600 retains
the exact authored Shalamar BG4 table. Broken retained parent changes its
table to Stage1 at999. The new table invariant is narrowly improved.

Overall replay remains FAIL: cycle verdicts PASS/FAIL/FAIL, raw scene-residency
failures retained, and final screenshot inspected showing the automatic
MEDICAL low-health menu. HP falls118->110 at925, reaches21 and DD06=3/menu1
by998. This is neither complete visual repair nor matched-encounter timing
qualification. Shared attribute dispatcher still reads D880; further repair
and cadence/transition validation are required. No promotion, deployment,
hardware, or audio claim. Existing broken evidence and strict gates unchanged.

## Verified Shalamar low-health renderer misclassification (#27)

Retained phase721 trace gives a causal failure, not merely an arena-residency
oracle concern. Frames997/998 keep Shalamar's C600 policy (253 BG4 entries,
blank IDs00/01/FF neutral). D880 changes0C->0B at998 while native FFB7 stays0C.
At999 DF0D becomes0B, FF91 becomes01, and C600 becomes byte-identical to the
Stage1 ROM table at37000, including12 bank1 hazard entries. CRAM is unchanged;
menu0/HP118/DD06=1, boss still rendered. Thus low-health sound alias is being
interpreted as dungeon graphics identity. A retained-evidence regression test
asserts the transition and exact wrong-table replacement; it is NOT a fix PASS.

Disassembled bank13:6F90 reads raw D880; 6FCD subtracts0C, underflows for0B,
then6FE1 uses FFBA0 to install the dungeon table. The shared attribute scene
dispatcher likewise tests raw D880. Next patch must preserve canonical arena
classification across these consumers without changing native sound state,
death/title handling, or dungeon behavior. No ROM patch yet; #27 updated.

## Combined Shalamar standard/adjacent input replay (#27/#34)

Fresh corrected-inventory `tmp/star-shalamar-native-inventory-state-01`
settles at102 on d744124d. Standard `star-shalamar-native-inventory-menus-01`
passes all three cycles and complete1080-frame arena residency; final native
image inspected. No memory writes during replay; setup remains dispatcher/health
assisted. Input-phase control `star-shalamar-native-inventory-phase721-01`
uses six-frame third Select at721 plus read-only input tracing. Native FF94=04
appears727 even though raw FF93 has returned0: queued input is delivered.
All three endpoint/cadence/map cycle checks pass, but overall verdict is FAIL
due83 scene-route observations998..1080. Preserve that verdict.

At997/998, HP118 and DD06=1 are unchanged; D880 changes0C->0B while FFB7 stays0C
and menu stays0. Final screenshot still depicts Shalamar, so the scene-only
failure should not be described as disappearance into another arena. This is
not a full-fight or visual-tearing clearance, and input tracing is not proven
observer-neutral. Five tests pass including explicit preservation of the
adjacent trial's FAIL and observed Select delivery. No audio/hardware claims.

## Ted menus pass with corrected native inventory setup (#37/#36)

Removed DCDC/DCDD health-assistance writes from both boss-entry probe and its
upstream Stage1 integrity probe. The first partial correction preserved in
`tmp/star-ted-native-inventory-state-01` still inherited cursor23 from Stage1;
it was not accepted as a native-cursor fixture. Full correction generates
`tmp/star-ted-native-inventory-state-02/boss4_ted.ss0` with cursor0, scene10,
HP240; state SHA73030b90e5b0cf9744a198cfe8d66601f3b751dd563bcad42c54ec83275ad709.
Generation still uses the explicit synthetic dispatcher/health setup, not
ordinary progression. No ROM bytes changed.

`tmp/star-ted-native-inventory-escape-02` holds Left for600frames, exact-ROM
CRC/header checked, no game-memory writes; scene10/HP240/cursor0 remain.
`tmp/star-ted-native-inventory-menus-02` then captures1080frames and passes
all three menu cycles: arena residency, rendered endpoints, return cadence,
selected-map readiness. Final gameplay image inspected. Four profile/evidence
tests pass, including re-running this oracle and preserving the unescaped
parent-matching failure. No health writes during escape/menu replay. No audio,
complete fight, or hardware qualification; related issues remain open.

## Fresh Ted entry is not a survivable menu fixture (#36/#37)

Added exact d744124d to the boss generator's inherited ABI set after verifying
fixed dispatcher and all banks16+ equal qualified4731248a parent. Test also
rejects a modified identity. No cross-ROM savestate retargeting.
Fresh `tmp/star-source-ted-state-01` passes entry capture at325, but the
unassisted1080-frame `tmp/star-source-ted-menus-01` FAILS three-cycle checks
and ends on title. At55 health103,56 health95/scene0B,120 health30/menu1,
334 scene17. FFB7 remains10 through the early low-health scene alias.
Entry includes DCDD=FF from legacy generator writes (#37), so this is not
normal inventory qualification either. Do not dismiss actual fade failures.

Independent exact-parent generation `tmp/ted-parent-entry-control-02` and
`tmp/ted-parent-entry-menus-control-02` fail identically: all1080 PNGs match
byte-for-byte and the complete failure arrays match (1066 entries). This
rules out the star overlay as the differential cause for THIS trial, not a
general health/rendering bug. Prior Ted menu PASS used a600-frame escaped
position (`ted-menu-reinstall-escape-left-01/frame-0600.ss0`), not this raw
entry. Next qualification needs the equivalent declared input prefix and
corrected generator inventory assistance. Failed evidence retained, no
criteria relaxed. Two profile/evidence tests pass. No hardware/audio claim.

## Verified palette-editor primary alias defect (#39)

Offline reproduction with actual d744124d ROM and synthetic supported MiSTer
state: edit BG0 to BG1's exact colors, then edit BG0 again. Old patch code
changes state rows96 AND104 on the second edit while changing only ROM BG0.
BG1 ROM remains unchanged but its active state row changes. This can create
inconsistent colors across reloads; it is NOT established as the recorded
yellow-trail cause. Searched existing issues and filed #39 before implementation.

`patch()` now rejects an old row shared by another primary definition in the
same BG/OBJ group, explaining Undo. This happens before upload/reload; the
outer Apply operation may already have taken a checkpoint. It still permits
multiple active copies of a single uniquely defined row and does not reject
an equal row in the separate BG/OBJ group. Fifteen offline tests pass, covering
sequential BG collision, OBJ ambiguity, retained inactive-override rejection,
legitimate duplicates and all15 actual candidate primary edits. No hardware
calls or deployment. Scene-aware disambiguation and equal private override
ownership remain outside this mitigation. #39 stays open for workflow validation;
#26 remains unproven. No ROM code changed.

## Pause effect across secret return: missing coverage checked (#26)

Four new serial guarded12000-frame trials use probe96d193447a5580a06e2d73d07a8de10c1ff6e7abd698e9dd5a615900c9e90ee5,
on reported4f5a67b8 and combinedd744124d. Scratch input schedule now allows
ENTRY_RETURN_WALK_AFTER so ordinary walking/shooting begins after return,
instead of changing the route inside the secret area. Explicit dense inventory,
health refill and one position-assisted secret entry remain; no graphics writes.

`tmp/{reported,star}-pause-return-patrol-01`: use item7 at3361; timer expires7000,
BEFORE Stage1 return8467/8433. Patrol begins9001 and visits261/252 distinct
positions through12000. Inspected9600/12000 images show no widespread recorded
yellow bands. Candidate's terminal scene02 versus reported0A means these are
not matched encounters/timing evidence.

That expiry exposed a gap in previous power-up/return coverage. New
`tmp/{reported,star}-late-pause-return-01` activates item7 at7261, timer60;
Stage1 return8559/8420 has timer42/44 respectively, expiry11103/11108.
Patrol starts10001; both complete12000frames, ending scene0A/stage00.
Inspected reported9000/10560 and candidate10560: intact purple scenery,
localized item colors, no recorded persistent yellow/red bands in these samples.
This is still an unsuccessful reproduction on the reported build, NOT evidence
that #26 is fixed or that pause can never contribute. Eight assistance tests
pass, including new coverage assertion for timer active across return and later
movement. No audio/hardware qualification. Next causal work should prioritize
the recording's earlier palette/edit-state history rather than repeating an
expired-effect route. All original receipts retained; hardware untouched.

## Stage 1 bleed replay leaves inventory state native (#37/#22/#26)

Removed continuous DCDD=17hex/DCDC=FF writes from the Stage1 no-bleed probe;
only verified health DCBB=FF assistance remains in that block. SRAM/level
selection fixtures remain declared. No ROM change. Source hashes and assistance
are now included in its receipt. Historical evidence is not reclassified.

Fresh `tmp/star-no-bleed-native-cursor-01` failed the static table check because
the verifier lacked the combined build's tooth-bank and four gold-star entries.
Its runtime checks passed. Preserved the failed receipt. Added an exact d744124d
profile with independently specified tooth tiles64..69/74..79=15 and star
tiles82/83/92/93=5; arbitrary ROMs do not inherit this exception. A regression
test rejects all256 single-cell palette mutations, not just a bad star entry.

Fresh `tmp/star-no-bleed-native-cursor-02` passes all17 runtime checks and static
table checks over1200 box-route gameplay frames (~20.09 emulated seconds),
including horizontal/vertical scroll and final Stage1 continuity. It records
1151 rendered transition captures,4605 non-pickup observations and zero detached
pickup-color pixels. Semantic-pickup publication observations are zero: this is
not a secret-return/item-use reproduction. Six-image sheet inspected; intact
purple floor/walls and localized item colors in those samples. Eight tests pass
(seven assistance tests plus the explicit profile/mutation test).

Probe SHA256 5ecc52348150b85d43ff66c4bae8d0f9f5584a25b14a9d9eab76983d5e1e3b50;
verifier SHA256 8f07fbc715c6809cd164550dc5f5fd88e1da76bb64c14903552054384c2c2d6e.
No audio/hardware qualification or deployment; #26 and #37 remain open.

## Combined source build Stage 2 Continue controls (#28)

Fresh candidate-owned Stage 2 entry from `tmp/star-source-stage-states-01`
has SHA256 f7bff2249bdb0766801c366cfc383be375ef503f3bdf8d3aa1ba00b705689112.
Decoded state CRC/header match source-built ROM
`d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5`;
no cross-ROM state retargeting. Guarded runs in
`tmp/star-source-stage2-continue-{a,neutral,start}-01` each complete all2400
frames using probe72ed0720. Death occurs1204. A produces a native A edge and
resumes Stage2 at1436, consuming the supplied credit, without returning to
title. Neutral and Start-only produce no A edge and reach title2120 after
the countdown. Resumed frame2400 was inspected visually.

Two evidence tests (three positive input subcases and a retained broken
source06 control) and ten oracle tests pass. Explicit assistance remains:
native level-select/state entry, FFE6=1 credit and DCBB=1 at1201 for native
decrement-to-zero. This verifies Continue handling on the combined build,
not natural collision, the recorded preceding corruption history, audio,
or hardware. #28 stays open. No deployment or running-game intervention.

## Natural hazard damage/restart now completes (#38/#18)

Corrected the preceding failed-route diagnosis: saved image shows inventory,
FFE4=1, DD06=3, HP1C. Original and candidate bank1:5050..5076 are identical:
below HP20hex with DD06=2, native5066 sets FF94 Select bit2 and DD06=3.
Thus the game itself opens the low-health menu. Native4F6E sets sound-context
D880=0B when DD06 is nonzero; FFB7 remains02. It was not evidence of leaving
Stage1 or a phantom Select from the new latch. Filed #38 before correcting
the harness. Preserved failed `star-source-natural-restart-01` unchanged.

Natural-damage mode now dismisses only that prompt (FFE4=1 and DD06=3) with
normal B pulses, logging each supplied B frame. No HP, menu-state or graphics
write added. Receipt records this input and oscillation setting. Fresh
`tmp/star-source-natural-restart-02` on exact d744124d passes two cycles in
6862frames, with four B-input log lines,102 Game Over frames and482 title
pairs. Stage-card/selector/terrain checks pass, Game Over image inspected.
Health damage/death are game-owned; save-present setup remains an explicit
fixture, so this is not a wholly unassisted new-cartridge playthrough.

Three restart tests pass, including native low-health code identity, new
natural route oracles and retained failed-control verdict. #38 is resolved
as a local harness defect; hardware issue18 remains open. No emulator remains,
no ROM bytes changed, no hardware interaction or audio qualification.

## Source-built combined candidate restart checks (#18/#28)

Fresh `tmp/star-source-hazard-restart-01` passes two accelerated hazard/restart
cycles on d744124d:1600-frame hazard approach, HP=0 per life, native save-present
fixture, stage selectors/cards,102 consecutive Game Over frames and482 returned
title pairs. All867 PNGs match Ted parent4731248a's retained run byte-for-byte.
Game Over image inspected: intact white lettering with purple accents.

Separate `tmp/star-source-natural-restart-01` uses movement-only damage with
PENTA_RESTART_SPIKE_OSCILLATE=1. It FAILS with native probe exit2 at24000frames.
Trace leaves scene02 for0B at2536, health76hex then, and remains await-damage
through terminal scene0B/health1Chex. No Game Over completion is established.
This route failure is retained, not converted to a pass or attributed to a
specific game cause. Next natural-route work must identify scene0B and why
the scripted route remains there before choosing different inputs. Process
check confirms no emulator remains. Two new tests re-run restart oracles and
preserve the failed route verdict. No audio/hardware qualification or deployment.

## Combined candidate palette-editor compatibility (#19)

Added exact d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5
as an explicit supported starting ROM in `mister_palette_bridge.py`, preserving
the existing default source and rejection of arbitrary variants. Checked all15
primary rows against authenticated Ted parent4731248a; every row is identical.
For each actual source-built candidate row, offline tests patch a synthetic
MiSTer-layout checkpoint, verify only that ROM row/checksum and matching state
rows change, and check the resulting checksum. A one-byte changed starting ROM
is rejected. Twelve tests pass; SSH is mocked/forbidden in constructor checks.
The BG5 label now mentions its additional five-point-star use in this experiment.

No controller server, SSH operation, deployment, restart, or hardware state
restore occurred. These tests establish patch boundaries and initial identity
acceptance, not MiSTer Apply/Resume correctness or gameplay readiness. #19 stays
open for hardware workflow validation and scene-override limitations.

## Full experimental chain reconstructed from source

`scripts/build_stream_regression_candidate.py --presentation` now reconstructs
the existing composition and palette-window/Select/handheld/title-local/Ted-menu/
five-point-star overlays after building source07. The reported-parent branch is
captured from the freshly built Sara stage, not read from an archived ROM.
Default invocation still builds source07. Every overlay keeps its exact parent
and preimage checks; final output must match d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5.

Fresh `tmp/stream-presentation-source-01/candidate.gb` matches that hash and
the previously tested star trial byte-for-byte. Its build receipt binds the
construction stages, original/palette inputs, nested restart receipt, entrypoint
and loaded project Python helpers. Three new construction tests pass: unknown
inputs rejected, chain identity/continuity, and fresh receipt/source hashes.
This is source integration, not a new emulation result or readiness/deployment.
No ROM bytes changed relative to the tested trial; open bugs remain open.
The stream runbook now distinguishes this experiment from historical r536
qualification and documents the opt-in reconstruction command.

## Native pause-item use followed by secret movement (#23/#26)

Fresh paired6000-frame runs `tmp/reported-pause-item-scroll-01` (4f5a67b8)
and `tmp/star-pause-item-scroll-01` (d744124d), probe e44a8360:
one loop-boundary doorway position at2401, dense inventory at1180, DCBB-only
health refill, native Select/Down/Right/A item7 action3300..3365, Right+pulsed
A from3426. Both consume item7 at3361, native cursor1, timer60; at6000 timer16
is still active. Both move from room01 to03 and remain secret scene09/stage07.
These are explicit assisted inputs, not reconstructed recording inputs.

At3480/3600/4800/6000 the reported build has337 tile-policy mismatches across
the two published attribute planes (153 on the selected map). Current candidate
has zero at all four snapshots, including a selected-map switch9C00 to9800.
Both terminal pictures inspected: reported has scrambled green/pink scenery;
current has intact blue/white panels against black. The specific recorded
yellow/red-band appearance is still not reproduced. Thus this qualifies the
existing secret palette repair on an actual item-use-plus-movement route,
not a causal diagnosis or closure of #26. No cross-build cadence/audio equality
claim; positions already differ by four vertical pixels at3426.

New regression verifies ROM pins, native consumption, valid menu cursors,
room progression, four snapshot policies and retained failing control. Seven
native-item assistance tests pass. No new ROM change, deployment or hardware
interaction; process check reports no emulator remaining.

## Seven-stage opening coverage with native cursor (#37)

Removed recurring DCDD=17hex and DCDC=FF writes from
`probe_stage_side_by_side.lua`; retained verified health DCBB refill and
declared SRAM/level-select setup. Capture manifests now bind probe/verifier
hashes and describe assistance. Existing output folders were not rewritten.
Fresh `tmp/star-seven-stage-native-cursor-01/manifest.json` covers all seven
stage openings, 240 play frames each, four snapshots per side, serial guarded
emulators. Parent4731248a versus star candidate d744124d: all28 corresponding
PNG files match byte-for-byte; Stage5 sampled semantic palette audit passes.
Stage5 contact sheet visually inspected. Its legacy OG label refers to the
parent DX build here, NOT the original Japanese ROM. Six focused assistance
tests pass, including fresh source/file-bound seven-stage assertions and the
retained invalid-cursor negative. No emulator remains running.

This strengthens the star-change regression check without qualifying full
stages, menu navigation on this route, audio, or hardware. Other legacy probes
with cursor writes remain under #37. Read-only palette-bridge history inspection
found locally retained edit folders dated September14/15, not yet an exact
palette/state reconstruction of the September27 recording; do not attribute
the yellow trails to an edit merely from the existence of those folders.
No ROM or MiSTer changes this turn.

## Corrected secret-entry campaign rerun (#37/#23)

Fresh `tmp/secret-palette-cursor-corrected-01/receipt.json` passes all ten
geometry/BG0 checks with health assistance restricted to DCBB. Corrected the
verifier's assistance description too; previous receipts remain immutable.
Three serial 3600-frame runs: stock 2f32570c, broken reported 4f5a67b8,
secret-only candidate e2473cbaf4060896afaa7f30b5fc250729887ae02cc12cb15f183ea3bfa09405.
Broken and candidate both enter at frame1410 and have identical full sampled
main-loop hit timelines and Stage1 baseline pictures. Stock enters at1397;
this is not a stock-versus-DX timing equality claim. Wall times 2.87/2.82/2.82s.
Candidate CHR matches all2048 original bytes; broken control is rejected.
Candidate BG0 ff7f947e4a3d0000 replaces broken 070607ff7f947eff.
Both terminal images inspected: restored pipe/panel geometry and black
background versus the broken pink fill and scrambled tiles. Other materials,
return trails, audio and hardware are not qualified by this entry-only test.

Added a source-bound regression for this receipt; five native-item assistance
tests, five CHR-builder tests and five palette-source tests pass. No ROM change
or deployment this turn. Wider read-only inventory found the same invalid
cursor writes in other probes, including stage-side-by-side, stage-speed,
later-stage-soak and natural-menu probes. #37 stays open pending scoped review
and correction of active callers; do not treat those assisted campaigns as
native inventory-navigation evidence. #26 yellow trails remain unresolved.

## Correct native menu cursor assistance and exercise pause item (#37/#26)

Issue37 filed before edits. Native fixed routine1E08 computes inventory pointer
DCBD+10*DCDB+DCDD;1E1A removes within a ten-slot page. Prior assistance wrote
DCDD=17hex every frame, an invalid cursor23. Those retained runs are still
evidence of their assisted executions, but cannot qualify native item selection.
Corrected scratch route and checked-in `probe_secret_chr_entry.lua` and
`probe_menu_icon_palettes.lua` health assistance to write **DCBB only**.
The menu probe retains its explicit initial cursor0 setup; no repeating cursor
or DCDC writes. Historical receipts/copies remain unchanged.

Native item7 dispatches via21CA to bank1:783D, setting DCF1=3C. Actor updater
23F8 skips while DCF1 is nonzero;07C6 decrements this timer. This identifies a
monster-pause action from code, not merely an assumed icon name.
New matched stimulus: dense native inventory setup, Select3300, Down3320 to
SPECIAL, Right3340 to slot1, A3360. The game consumes item7 (slot1 becomes8),
closes the menu, sets timer60, and later expires it. No direct timer writes.
Both reported4f5a and latestd744124d complete10800frames with valid menu cursors
in `tmp/reported-pause-item-return-01` and `tmp/star-pause-item-return-01`.
ProbeSHAe44a8360c979998b5e168f752551464c42b3aad5a5b8c3fee19152fff7bf9bd2.
Reported first activation3361, timer active3639 sampled frames. Both final
pictures reviewed: no recorded persistent yellow/red bands.

These corrected trajectories differ from historical resource-assisted runs.
Reported returns to Stage1 at8467 then enters native miniboss scene0A at10657;
latest returns8433 then enters0A at10748. Terminal stage00, FFBF02, menu0.
Initial test expecting terminal scene02 failed and was corrected to require
the observed earlier scene02 return followed by explicit scene0A/FFBF02,
not to silently accept any dungeon-looking screenshot. Four new tests pass,
including the native pointer/handler bytes, retained invalid-cursor negative
control, and successful native item consumption on both builds.

Fresh checked-in menu palette verifier on reported4f5a with corrected probe:
`tmp/menu-cursor-corrected-01`, one run, five pages, zero tile/palette mismatches.
Its deliberately wrong health-icon palette is caught on pages0/3. One run is
not repeated-run determinism proof despite the verifier's generic final prose.
The corrected secret geometry probe still needs its dedicated stock/parent
campaign rerun. #37 remains open for that coverage; #26 remains unreproduced
under this explicit item-use route. No ROM changes or hardware intervention.

## Yellow-band onset review and populated-menu control (#26)

New recording review under `/mnt/data/tmp/penta-yellow-onset-20260928/`:
`29m20-30m40.png` is an8x5 sheet sampled every2seconds, row-major from29:20,
SHA8fdc29fc936ec949b9ea592db66592793970846053fd5751b1b4d0401b114011.
Separately inspected30:12 gameplay crop shows yellow/red bands in returned
Stage1 **before its menu is open**;30:14 has MEDICAL open and the bands remain.
This rules out that later Stage1 menu opening as the initial trigger, not
earlier secret-area menu/power-up use. The samples bound timing only; they
do not establish the very first bad video frame or exact player inputs.
30:12 SHA1772bf922ed1ef02a2ac378117e66c76262de521b7301ca2d9ecaf64c6b137d6;
30:14 SHA1995449a890452ba24a5ea612ada46ee91a2a1f35f3f27957db122190d730c50.

The recording's densely populated menu motivated one new diagnostic on the
reported4f5a ROM: `tmp/reported-dense-secret-return-01`,10800frames, existing
secret route plus explicit native inventory seeding at1180. Medical group
contains nine item1 slots and item5; other groups contain known item IDs6..16.
This is a controlled dense inventory, NOT reconstruction of the recorded items
or activation of the reported monster-pause power-up. ProbeSHA
e6cf631bdb43552e41b13aac7e428b287b40683db79597b017cf06b78034fea0.
Native menu buffers/attributes are not written by the new assistance.
Run completes normally. Menu3360 is populated and shows the old secret-area
geometry/global-palette failures; final10800 Stage1 remains clean blue/white,
without recorded yellow bands. Both images reviewed. Terminal C600 table
matches the prior empty-inventory return control byte-for-byte, so populated
inventory alone is not sufficient on this route. No ROM fix or closure is
justified by this non-reproducing control. Investigate actual item activation
and the recording's earlier palette-edit/save-state history next.

## Latest star candidate retains secret publication repair (#23/#26/#35)

Fresh exactd744124d cold10800-frame route in
`tmp/star-secret-menu-return-01`: same explicit position/resource assists,
menu3300/3420 and firing3425 as the previous title-local route. Scene09
entry2613, encounter4299, secret return6403, Stage1 return8548. Terminal
BG0 remainsff7f947e4a3d0000; final picture inspected, clean blue/white scenery.
All3760 observed palette writes pass safe-timing checks. All29 eligible
secret snapshots have correct active-map attributes. Whole-map snapshots
6600/6840 still fail with8/16 hidden in-progress cells; do not erase these.

Fresh matched watcher run `tmp/star-secret-publication-01` retains2190 LCDC
events,1723 LCD-on/menu-closed selected-map observations, zero policy failures.
Known-broken reported-ROM control remains a failing1731/1731 comparator.
Observer-on/off exact-ROM traces, all103 saved PNGs and decoded states match.
This is saved-output/state neutrality, not native-PCM or continuous-video
neutrality. No palette/graphics/cache writes were introduced by the probe.
Tests now include this latest candidate rather than relying only on the older
8ff1c98d evidence. No deployment, hardware qualification or issue closure.
The recorded persistent yellow/red onset and claimed pause-powerup trigger
remain unreproduced: a clean assisted route is not proof those reports are fixed.

## Five-point star reproduced and recolored in a bounded local trial (#22)

Seven-stage opening guard: `tmp/five-point-star-seven-stage-01` uses the
checked-in serial single-flight `capture_stage_side_by_side.py` with240 play
frames per stage and60-frame samples. Parent4731248a is passed explicitly as
`--original`; the tool's legacy OG label means **parent DX**, not stock ROM,
in these contact sheets. All seven pairs finish; all28 paired gameplay PNGs
have identical SHA256 and decoded pixels. The Stage5 semantic palette audit
also passes. Stage5 contact sheet visually reviewed. This is short,
SRAM/level-select/resource-assisted opening-room coverage, not a natural
seven-stage playthrough or exhaustive tile-reuse test. Captures run sequentially,
on pinned libmgba20fa5dda; no hardware activity. The retained integration test
checks actual images and completion markers, not only the summary PASS.

Follow-up collection/menu qualification: exact parent/trial owned checkpoints
were each restored without identity rewriting. Down128 for20frames then idle
through120 collects the item; Select4 for6frames opens the menu, idle through360;
another Select4 for6frames returns to gameplay, idle through180. No further
position/resource/palette writes. Paired directories are
`tmp/five-point-star-{parent-,}collect-01`,
`tmp/five-point-star-{parent-,}menu-02`, and
`tmp/five-point-star-{parent-,}menu-return-01`.
All three full per-frame state traces are identical across ROMs. All21 sampled
state clocks and inventory ranges match. The first collection sample still
shows the expected star-color difference; the other20 sampled screenshots
are pixel-identical. Menu flagFFE4 changes1→0 on exit and scene remains02.
The visible menu is the same mostly-black MEDICAL/MEGA-FLASH page in both
builds, without a visible star icon: this is not icon-display qualification.

Retain `tmp/five-point-star-menu-01` as a failed attempt: process status-11
after frame120 capture. A subsequent read-only process check found no surviving
emulator. Longer360-frame reruns on both builds completed normally; this does
not explain or erase that process crash. No crash-cause claim is made.
Six source/retained-emulator tests now pass, including known-white negative
control and explicit rejection of the failed-run receipt. These tests skip
the retained corpus when unavailable, rather than fabricating reproduction.

Native map lookup at1322 expands the64-column C780 world through A400
macroblocks, then A000 metatiles. Retained Stage1 map data located metatile36
inside macroF7 at world39,22: star pixel1264,704. A fresh cold run of exact
4731248a with one camera-position assist to1192,624 reproduced the white star
at screen72,80. No palette, cache, scene, resource, or graphics writes were
used by the probe. This identifies the room; it does not prove the player's
natural teleport route.

`build_five_point_star_trial.py` creates experimental ROM
`d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5`.
Only four source-art tiles, four dungeon palette-LUT entries, and the ROM
checksum change. The star's upper white interior becomes BG5 gold; the
original lower index1 shading already becomes gold. Black outlines remain
unchanged. BG5 also makes the square backdrop red, consistent with its
gold/red power-up palette; this is not a preserved-neutral-backdrop claim.
No executable code or new runtime hooks are introduced.

Fresh paired1500-frame cold runs:
`tmp/five-point-star-live-01` (parent) and
`tmp/five-point-star-fixed-live-01` (trial). Both terminate normally.
At frame1500,152 changed pixels are confined to the star, bounds73,81..86,94;
all other screen pixels are identical. Both serialized cycle counts are
211035420 and OAM matches. WRAM differs only at eight palette-source/cache
bytes, all0→5 (state offsets4A82/83/92/93 and754A/4B/6A/6B).
PNG SHAs respectively09ef9fe8a53cd611a6b0efd7117249c1422123aa1369b58c78ae6280ea85ee8b
and87ab4baa9d20fca0973b63b412ed4d421d8ee09a8441384ebe341b41d39d7c6e.
Both images were visually reviewed.

Three source-contract tests pass. `verify_five_point_star_pair.py` passes
the new pair and exits1 on the retained broken parent, including an actual
rendered-center failure (white255,255,255 rather than gold255,255,0), not
just a provenance mismatch. This gate is deliberately frame1500-specific.
Menu display, collection, later tile reuse, native audio and hardware remain
unqualified. Issue22 remains open; neither default ROM nor MiSTer was changed.

## Recorded five-point star identified; prior Spiral control was a different item (#22)

Issue22 was filed01:02:35Z,22m07 after the recording filename's20:40:28
America/New_York start. This timestamp relationship is a search aid, not an
exact synchronized event timestamp (the container has no creation_time tag).
New1Hz review of20:40–22:00 reveals a white five-point star in a square at
21:13, immediately before collection around21:14. This is not the four-point
gold/red Spiral pictured by the old control. The stationary menu afterward
explains why coarser10second samples missed the briefly visible item.

Reviewed derivatives under `/mnt/data/tmp/penta-star-timestamp-review-20260928/`:
- `20m40-22m00.png`, SHA d4c7ee68200a645ea519ec704d0dcff63b3a9443220dd61d9a0a6a6aad18d57d;
  contact-sheet labels are relative to20:40, not absolute recording time.
- `21m13.png`, SHA8e512aa47d9617867787bf5d7db061daf393d14d5fa7f9fe6c61e11352a1d14b;
  gameplay crop1200x1080 at0,0, nearest-neighbor scaled480x432.

Stock metatile definition at ROM221A and180D8 contains82/83/92/93. Decoding
those four source tiles at1F000+tile*16 gives the matching five-point star.
The64-byte art SHA is
`d7156afbb1e8f9a310c0a1283a7fe16e4fca38839057d24ad3e966771c3aba6d`
in stock, reported4f5a, and latest4731248a. Both DX builds map all four tile
IDs to BG0 in bank13:7000. The YAML pickup_font_no_bleed category explicitly
includes80..83 and90..93; the19-item PICKUPS atlas omits this star entirely.
This supports a missing semantic pickup class, not failed Spiral recoloring.

No ROM/YAML edit yet. Need an exact-ROM live reproduction in this room and
a scoped recolor preserving geometry, neighboring tiles and menu/later reuse.
Important: star center uses stock pixel index0, so merely assigning existing
BG5 (whose color0 is white) is insufficient to promise a gold star. Preserve
this distinction when choosing the repair. No emulator or hardware launch in
this recording/source investigation; the player report's precise teleport
route is still not established, but there is now a concrete matching gray star.

## Palette bridge accepts latest expanded candidate offline (#19)

Verified recurrence before editing: Bridge rejected exact4731248a with
`Starting ROM does not match an exact supported pin`; its pure patch function
also permitted only512KiB while this candidate is1MiB. All15 primary palette
rows at36800..36837 and36840..3687F were independently compared byte-for-byte
with authenticated supported4f5a parent and match.

Added only exact4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903
to initial recognition. The pure patch path accepts1MiB only with MBC5+RAM+
battery cartridge byte1B and ROM-size code05. Unknown starting pins remain
rejected; no arbitrary-ROM or hash-skipping workflow was added. Existing512KiB
behavior and default source remain unchanged. Private title/GameBoy overrides
are not primary palette controls and are deliberately preserved.

11 tests and15 subtests pass in1.37s. Actual-candidate tests edit all15 rows
using synthetic MiSTer-layout states and assert every unrelated ROM/state byte
is unchanged, including the full expansion. Separate synthetic full-size tests
check global checksum and reject invalid expansion headers. Constructing the
actual Bridge succeeds with hardware calls forbidden by the test.
This establishes offline patch compatibility, not that a1MiB ROM resumes
correctly on physical GBC. No editor server, SSH, checkpoint, reload, deployment
or game mutation was performed. Issue19 remains open for hardware Apply/Resume.

## Faze completes menu coverage; full checkpoint generation verifies #30

Fresh `tmp/ted-fix-faze-right-01` restores exact4731248a Faze checkpoint
SHA7d048cabe0830417b86e8f4ed4317d073aee2730cb4e08d88ad4b66b08a48133,
holds Right90frames and releases30. No new memory writes. Screenshot shows
Sara at the right edge. Dungeon world-coordinate fields are not boss screen
coordinates and are not used to prove this movement. Terminal state SHA
`a63912bbac583ac95ada3c96f83177d55f2a568891c2a41bdc8cf36269b53c18`.
From there, fresh `tmp/ted-fix-faze-right-menus-01` passes all three cycles
and remains scene12 throughout1080frames (3.940s replay,1.174s check).
Terminal PNG inspected. Prior stationary/Left-route failures stay failures;
raw states show health decline and DD06 becoming1 before arena exit.
Now all nine bosses have a passing bounded menu route on this exact ROM,
not full-fight, natural-progression, native-audio or hardware qualification.
16 acceptance tests pass in25.27s, including retained failed controls.

Separately, fresh complete generator invocation in
`tmp/ted-menu-reinstall-nine-boss-qualified-01` exits0 with all nine reports
and manifest, including Penta's independent live replay (scene14, zero seed
differences,9colors). Read-only follow-up checks all nine serialized states'
CRC/header and expected scene against exact ROM SHA
`4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903`;
all nine relocated palette lookups succeed.7 storage tests and28 subtests
pass, retaining builder-based corruption rejection. This verifies #30's
observer/fixture-generation defect for the authenticated supported candidates;
it does not assert arbitrary future ROMs are recognized. Final process check:
no mGBA processes. No ROM modification or hardware interaction this step.

## Latest candidate: eight boss menu routes pass, Faze remains unqualified

Expanded exact4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903
through fresh sequential guarded1080-frame captures. Each passes only if all
three cycles satisfy endpoints, return cadence, selected-map readiness and
every frame remains in the expected arena. This is not full fights, art or audio
qualification. Input states are exact-ROM assisted generator checkpoints;
the replay itself performs only Select inputs. Cameo's passing route first
holds Left600 without memory writes, preserving the failed stationary control.

| Capture suffix under tmp/ted-fix- | Result | Replay/check seconds |
| --- | --- | --- |
| shalamar-menus-01 | PASS three cycles | 3.942/1.176 |
| riff-menus-01 | PASS three cycles | 4.574/1.236 |
| crystal-menus-01 | PASS three cycles | 3.590/1.161 |
| cameo-menus-01 | FAIL; first leaves scene0F at382 | 3.574/1.203 |
| cameo-escaped-menus-01 | PASS three cycles | 3.472/1.223 |
| troop-menus-01 | PASS three cycles | 3.950/1.210 |
| faze-menus-01 | FAIL; first leaves scene12 at602 | 3.540/1.202 |
| faze-escaped-menus-01 | FAIL; first leaves scene12 at336 | 3.389/1.243 |
| angela-menus-01 | PASS three cycles | 3.790/1.195 |
| penta-menus-01 | PASS three cycles | 3.973/1.196 |

With the separately authenticated Ted pass below, eight of nine bosses have
a passing three-cycle route. Do not report all-nine PASS: Faze's routes are
inadequate. Cameo stationary raw states show DCBB fallingF0 to7D by373,
DD06 becoming1 at377, and transition0B at382, followed by title later. A
menu visual failure outside the arena is not by itself a new menu bug.
Faze likewise leaves its arena; neither failure was removed or reclassified.
All seven new passing terminal PNGs were inspected. Test coverage reopens all
1080 states per route, checks ROM CRC/header, recomputes the checks, and keeps
the three failed captures failing. No new ROM patch or hardware interaction.
Next needed for Faze: a sustainable ordinary-input combat route, not HP writes
or acceptance limited to its one successful cycle.

## Three-cycle boss-menu acceptance is now automatic (#36)

`check_boss_menu_fades.inspect_roundtrips` checks each scheduled cycle's
rendered endpoints, native four-frame return holds, selected24x24 map, and
continuous expected-arena residency. The replay runner now writes independent
`verification.json` and exits nonzero on failure, even when capture completed.
The older endpoint-only API retains its explicitly narrow semantics. Phase
probes partition cycles using the actual requested third-entry frame.

Two fresh, sequential guarded1080-frame replays validate the integrated path:

| Capture under tmp/ | Exact ROM | Cycle statuses | Exit | Replay/check seconds |
| --- | --- | --- | --- | --- |
| ted-menu-reinstall-roundtrips-gated-01 | 4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903 | PASS/PASS/PASS | 0 | 4.825/1.223 |
| ted-menu-broken-roundtrips-gated-01 | 8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c | PASS/FAIL/FAIL | 1 | 5.093/1.265 |

Both restore their own exact-ROM escaped Ted checkpoint, inherited from assisted
checkpoint generation followed by ordinary Left600. Menu replays add controller
input only. Complete observations and failure details are retained, with launch
ROM/state/probe/runtime bindings and checker hash. Terminal PNGs were inspected;
a normal-looking still is not evidence of input responsiveness. No new game-ROM
change, audio equivalence, natural encounter, or hardware readiness claim.
33 targeted tests pass in14.23seconds, including a scratch-independent synthetic
aggregate-PASS/later-cycle-FAIL control. Final process check found no emulator
processes. Issue36 remains open for broader qualification.

## Teleport record13: left boundary and item identity (#22, no fix)

Fresh `tmp/star-native13-left-02` restores the exact reported4f5a ROM's
`star-native-entrance13-reported-01/frame-1800.ss0`, with CRC/header validation,
and holds Left for480 frames. No memory assistance was added in this segment;
the inherited entrance prefix includes position/resource assistance. WorldX
moves1576 to1544 and stops at the room boundary; WorldY remains624. Thus
continuing Left from this destination does not reach the Spiral room at1252/824.
Both maps contain the Teleport pickup signature at14,6 with attributes4/4/4/4,
but neither contains the Spiral signature. BG5 remains `ff7fff031f000000`.
The screenshot was inspected; its gold object alone is not proof of a gold
star pickup. No gray-star reproduction or palette fix is claimed.

ROM SHA256 `4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5`;
source state `e1761ccf43815c8960164e536672baf27d38b76bd58948515e4071fbcb6979d5`;
probe `078c5b0a15dcdc380caaff8f66b1303d11afd9297cb4dc6915ef87f4b2fffc4a`;
terminal PNG `9b1036ebb13c9666467f8e8447f73095ed00ebd89cbb5fbcf03d593fb4c50177`;
terminal state `6b3c64177da2ef20196ba364925b1e46c95916780a867e3f44beb81379e89cd1`.
Guarded run exited0; subsequent process check found no mGBA processes.
No native audio or observer-neutrality qualification; no hardware interaction.
The existing19–20min recording sheet was also re-inspected: its visible star
bursts are not enough to identify the reported stationary pickup. The next
useful evidence is a positively identified recorded object, not another palette
edit to the already-gold Spiral control. Issue22 remains open.

## Latest boss checkpoints: relocated-oracle correction and cold Penta (#30/#36)

Exact4731248a sweep `tmp/ted-menu-reinstall-nine-boss-01` stopped at Riff:
the generator read the obsolete bank13 LUT because this new SHA was absent
from the layout contract (3 used-ID mismatches). Kept this failed evidence.
Verified complete bank23 against both reconstructed `expected_bank23()` and
recognized4f5a, plus exact selector13:6FD5..6FE0; all nine selected tables
equal the recognized parent's tables. Added this exact identity to the
relocated-storage contract, retaining independent table-builder equality and
a deliberately damaged-table negative test. No expected colors were relaxed.

Fresh `ted-menu-reinstall-nine-boss-02` passed bosses0..7 before historical
Penta fixture loading failed (`error-state-load`, result=false). This is a
retained fixture failure, not a rendering result. Authenticated banks17,
24..27 and29..31 plus fixed1A2B dispatcher against4f5a and enabled the existing
cold Penta path for this exact build. Bank28 is NOT identical:40 changed bytes
belong to the secret-area overlay. An initially overbroad24..31 code comment
and test assertion were corrected before test acceptance; no unchanged-bank28
claim is justified.

Fresh `tmp/ted-menu-reinstall-penta-cold-01` passes cold target8 at115,
settle102; mandatory independent recapture reports scene14, LCDC83,
zero ROM-seed differences, nine rendered colors. Final native PNG inspected:
complete red/white/green Penta sprite against black. This completes nine
checkpoint checks across the02 sweep and separate Penta run; it is NOT a
single successful all-nine manifest, natural traversal or complete fight.
Seven storage tests and28 subtests pass, including table corruption rejection.
No game bytes changed in this turn. No hardware or deployment operation.

## Ted repair retains Sara raster and hazard/restart behavior (#6/#18/#36)

Exact4731248a candidate fresh `tmp/ted-menu-reinstall-sara-fire-01` passes
ordinary-input turning/firing replay:2400frames,2396 Witch walking samples,
4 absent samples retained,437639 opaque pixels checked, zero mixed/incomplete
poses or raster mismatches. This does not resolve the residual player-reported
MiSTer tear. Verifier65972220…, probe14e374fe…, pinned core20fa5dda…;
reported capture/inspection wall time7.201s. Missing-pixel negative controls
remain in `tests/test_sara_atomic_pose.py`.

Fresh `tmp/ted-menu-reinstall-hazard-restart-01` passes two cold-boot
hazard/death/restart cycles including saved-game selector, stage cards,
102 consecutive Game Over frames and482 returned-title pairs. Stimulus is
1600-frame hazard approach followed by HP=0 per life; native save-present
flag is supplied. NOT movement-only death. All867 PNGs match the retained
8ff1 parent run byte-for-byte; no images were excluded or transformed.
Reviewed Game Over screenshot retains purple accents in white lettering.

Tests added to `test_ted_menu_reinstall_trial.py` re-run the raster, terrain,
stage-card and sequence oracles on retained data, rather than trusting pass
flags. No hardware test or full-release claim; no deployment.

## Experimental Ted menu reinstall repair passes three returns (#36)

`scripts/diagnostics/build_ted_menu_reinstall_trial.py` builds exact8ff1 parent
into `tmp/ted-menu-reinstall-trial-01/candidate.gb`, SHA256
`4731248ad2d28f56539197ddfa38fcb8f79713832b7997905647caf35d34f903`.
Bank16:5CDA keeps the original ready/installer destinations but calls a
private bank20 guard. The guard retains C5FF=C9 and also requires C508=20,
the installed JR opcode overwritten by menu tiles. A failed check invokes
the full existing installer. The mapper-only09BE bridge preserves flags and
live BC/DE/HL without touching DC09. Only gate11bytes, two erased bank20
regions6/17bytes, and global checksum change. No native menu writes are skipped.

Fresh target4 generation `ted-menu-reinstall-entry-01` reaches325/settle300,
as parent. Fresh `ted-menu-reinstall-escape-left-01` holdsLeft600frames without
memory writes. Fresh `ted-menu-reinstall-roundtrips-01` then completes1080frames:
all remain scene10, and all three menu cycles independently pass black/white
endpoints, native four-frame intermediate holds, and24x24 map readiness.
At320/620/920 the helper is restored and menu flag is0. Native terminal PNG
reviewed: animated Ted and checker arena remain visible. The retained8ff1
control still fails rounds2/3. Six builder/retained-replay tests pass.

The first speed probes `ted-menu-guard-speed-{parent,trial}-01` incorrectly
watched the dungeon016C loop and yield zero events: invalid speed evidence,
retained. Corrected02 probes watch bank2:406F over600 neutral frames, each
from its own exact-ROM escaped checkpoint. Both observe101 arena iterations,
first4/last596; throughput ratio1.0 in this window. Probe078c5b0a… records
the bank filter. This is not audio, arbitrary menu-content, full-fight or
hardware qualification. No default-source promotion, commit or deployment.
Issue36 remains open pending wider validation.

## Ted menu overwrites its executable helper (#36)

Latest8ff1 exact checkpoint `title-local-ted-entry-01/boss4_ted.ss0`, SHA
`48b7c7d26ccae773823e1dcfed6ea0df81b3f6619c049e35cd32d0e6320a2fd6`,
can sustain600frames by holding Left: `title-local-ted-escape-left-01`.
No memory writes are used during escape. DCBB staysF0, DD06 stays0, Ted
remains visible, and Sara moves to the bottom-left corner. This overcomes
the immediate damage in the stationary fixture, not synthetic-entry provenance.

Fresh `title-local-ted-escaped-menus-01` captures1080frames from that exact
600-frame state. All frames retain scene10 and first return passes endpoints,
four-frame holds and map readiness. However rounds2/3 have no black/white
endpoints or return sequence. PC samples320..1080 remainC503..C52C and input
latches remain000404. The whole-run endpoint checker reportsPASS because
round1 supplies both endpoints: it must not be used as three-cycle acceptance.
New retained tests preserve both that insufficient aggregate result and the
two per-cycle failures, plus the unchangedC5FF=C9 marker beside corrupt code.

Read-only write observer `tmp/ted_menu_helper_probe.lua` in fresh
`title-local-ted-helper-writes-01` identifies native menu metatile copies:
frame170 writes C508:20→FE at post-instructionPC1FAB; subsequent copies at
1FAB/1FAE/1FB4/1FB7 replace more executable C500-page bytes with menu tiles.
Thus the ready marker survives while its runtime does not. The runtime
installer/gate must account for this menu ownership transition; no ROM fix
has yet been attempted. Observer-wide neutrality is not established.

Earlier source07 escape attempt `source07-ted-escape-left-01` did not retain
the arena: its subsequent replay starts scene0B and reaches death/title.
It is a failed control route, not evidence of the same menu hang on source07.
Eleven retained-evidence/scene-route tests pass. Issue36 was filed before
implementation; all failed artifacts remain. No hardware or deployment.

## Ted checkpoint early scene change is a low-resource branch (#32)

Fresh latest8ff1 target4 generation `tmp/title-local-ted-entry-01` passes at
frame325, palette settle300, scene10. The corrected pinned libmgba is unchanged.
Fresh neutral120-frame replay `tmp/title-local-ted-exit-trace-01` uses the exact
ROM-CRC-checked state, with no health/input assistance. Its write trace narrows
the prior early-exit description: DCBB falls F0→E8 at frame1 and repeatedly
loses8 through fixed1032. At frame43 it falls87→7F. At frame49, native
bank1:5073 writes DD06=1; at frame55 native bank1:4F71 writes scene0B while
DCBB is still67. This is not a zero-HP boss death at the first scene change.

Stock bytes at bank1:5050 compare DCBB against20 and80: the20..7F interval
sets DD06=1. Bank1:4F5D tests DD06 first and selects scene0B when nonzero;
only its zero branch restores FFB7's main scene. These byte sequences are
unchanged in latest8ff1. Thus the generated fixture's rapid resource depletion
reaches the native low-resource branch before Select120. No proof yet that
natural Ted entry inherits the same rapid depletion, and no permission to
erase this gameplay branch just to pass a menu test. The observer has not
been qualified against an observer-off video/state/PCM pair.

The next fixture work must obtain a sustained natural encounter or explicitly
label an assisted assay. Keep the existing failed scene-continuity results;
do not treat early scene0B alone as a proven game regression or boss victory.
No ROM modification or hardware operation in this investigation.

## Latest title-local build retains doorway occlusion (#14)

Fresh `tmp/title-local-doorway-01` cold1216-frame replay of candidate
`8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c`
passes the unchanged doorway verifier: world1240/1356, camera0C08, matching
four-quadrant OAM positions, all four behind-BG bits set, zero exposed pixels
in the reviewed256-pixel opaque footprint. Native PNG inspected: the black
overhang hides Sara while the surrounding purple architecture remains visible.
PNG SHA `ad18cdae7a4544b53ab1b2a37a20310b15be7fcf7e246f95d9db5c0a34f2ab7d`.
Reused stock `ceiling-stock-doorway-03` identity and reviewed screenshot are
authenticated by the verifier; reused `ceiling-source07-negative-01` still
fails with192 exposed pixels. These controls are not fresh replays.

Fresh `tmp/title-local-floor-01` cold1800-frame replay exercises600 moving
floor frames after a position assist: zero Sara behind-BG flags and zero
installed-helper mismatches. Both runs use position/resource assistance,
probe `4f4d0660e35c5431e0aea0747faa137011e2c0e88769ef291aa1eb63260b095a`,
single-flight Qt and pinned libmgba `20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`.
Both exit0. Ten tests pass across `test_title_local_doorway.py` and
`test_sara_doorway_priority.py`. This is one opaque doorway plus a floor
priority guard, not arbitrary archway/collision, audio, or hardware acceptance.
Issue14 remains open. No ROM code changed or hardware/deployment touched.

## Secret-map publication: direct physical-bank observation succeeds (#23)

Pinned scripting domain uses segmentSize=GB_SIZE_VRAM4000, despite physical
VRAM banks being2000 bytes. Bank1 direct reads therefore use4000+offset,
not2000+offset. Corrected probe removes saveStateBuffer from the CPU callback.
Fresh `tmp/title-local-secret-publication-03`, same exact8ff1c98d ROM/route:
2190 FF40 events retained,1723 LCD-on/menu-closed observations, zero selected
map palette-policy mismatches across all768 cells per observation. Other467
events remain recorded with their context; menu/LCD-off maps are not qualified
by this gameplay tile policy. Probe SHA
4f4d0660e35c5431e0aea0747faa137011e2c0e88769ef291aa1eb63260b095a.

Same-ROM observer comparison against `title-local-secret-menu-return-01`:
gameplay trace identical, all103 screenshot names/bytes equal, all103 decoded
71680-byte state payloads identical. This is captured-state/video neutrality,
not a native-PCM comparison or continuous-frame proof. It resolves the prior
publication question at observed FF40 writes without replacing or waiving the
strict whole-map failures captured mid-hidden-map transaction.

Fresh known-broken reported4f5a67b8 control, same route/probe:
`tmp/reported-secret-publication-03` has2198 events,1731 eligible observations,
ALL1731 fail selected-map palette policy. Both event streams and full check
reports retained. New `check_secret_publication.py` records all contexts and
cell differences, rejects empty/truncated input, and does not claim observer
neutrality itself. Tests cover the real broken control, newest trial, exact
observer comparison, and deliberate attribute corruption. This supports the
secret-map palette publication fix on this assisted route; it is not complete
qualification of all recorded visual/audio/hardware regressions. No deployment.

## Secret publication observer trials rejected for qualification (#23)

Two fresh sequential10800-frame exact8ff1c98d replays attempted to observe
FF40 writes and the selected map's768 tile/attribute cells. Same assisted
route as the preceding unobserved publication control, CRAM watcher unchanged.
`tmp/title-local-secret-publication-01` reads VRAM bank1 through the scripting
domain at offset+2000.2080 of2190 events return768 FF attribute bytes (the
initial all-events claim was disproved by the retained test): this API
does not expose the desired bank there. Its1723 eligible-event failures are
invalid observation, NOT verified game corruption. Gameplay trace and all103
saved PNGs match the control, but bank1 content is unusable. Artifact retained.

Trial02 switches to `emu:saveStateBuffer(0)` inside the FF40 watcher and reads
physical VRAM planes from serialized offsets.2178 events recorded,1699 with
LCD on/menu closed; none has tile-ID palette-policy mismatches. However this
observer FAILS behavioral neutrality: first gameplay trace difference3116;
encounter entry4299→4256, secret return6403→6329, Stage1 return8548→8463.
Of98 matching screenshot frame names,65 PNGs differ. Missing counterparts
for scene-transition-only captures are also retained, not aligned away.
Probe SHA898e06b9adbc062d221368394acd2cf6c056aa87cdf9732de81de9281c44de73.
Thus zero observed event mismatches does not qualify the original trajectory.
Do not waive the earlier whole-map failures based on this observer. Serialization
is not assumed passive merely because the Lua code has no explicit game writes.
Next method must obtain the physical attribute bank without serializing from
the CPU write callback, then repeat same-ROM observer-neutrality checks.
Tests bind the invalid-domain result and the real trajectory divergence.
No game ROM changes, hardware access, deployment, or issue closure.

## Latest secret/menu/encounter/return route: publication-phase gap (#23/#26/#35)

Fresh10800-frame `tmp/title-local-secret-menu-return-01` on exact8ff1c98d
candidate, cold boot with prior route inputs: one loop-boundary position
assist2401, resource refills, menu3300/3420, pulsedA from3425. No palette,
graphics, or cache writes by the probe. This is an assisted integration route,
not natural player traversal or pause-powerup activation.
Scene09 entry2613, encounter0A4299, secret return6403, Stage1 return8548.
All3760 observed CRAM writes are safely timed, zero LCD-on mode3 writes.
This fixes the observed inherited333 blocked writes on this route, but is
not continuous video/audio/hardware qualification.

Secret snapshots3240/3480/3720 have zero1536-cell attribute mismatches and
zero2048-byte CHR differences versus stock37400..37BFF. Menu3360 opens;
OBJ3 retains the new gray/olive handheld ramp. Post-encounter6600 has8
whole-map attribute mismatches,6840 has16; the strict checker remains FAIL
on those two snapshots. All mismatches are hidden9800 while LCDC8B selects
9C00. CPU is bank36:5C3C, VBK1, inside the combined copier's attribute plane,
with HDMA destinations9A20/9AA0 respectively. At6600 blankFE cells still have
palette1; at6840 some item cells have palette0 and cleared cells palette1.
Thus the initial suspicion of a completed tile-clear failure is not established:
the snapshot catches an unfinished hidden-map transaction. All29 captured
scene09/stage07/menu-closed states have zero active-map attribute mismatches.
Do not change the whole-map oracle to hide the retained failures; establish
publication-time completeness in a subsequent event-level check.

CHR remains stock-exact at6600. Final10800 returns to Stage1 with BG0 intact
and OBJ3 restored to its ordinary red ramp. Images6600 and10800 reviewed.
Resource/timing assistance and sparse capture mean this does not prove the
recorded persistent trails or later Shalamar corruption resolved. No hardware
access, deployment, or issue closure. Added retained regression coverage for
the exact two hidden-map failures and all29 active-map observations.

## Latest title-local candidate: Shalamar three-return regression pass (#27/#34)

Fresh exact8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c
native-dispatcher fixture `tmp/title-local-shalamar-entry-01` settles frame102,
scene0C, PC5756/SPDFF1/IE07/LCDC8B. No cross-ROM savestate retargeting.
Synthetic boss entry is assistance, not traversal from the reported corrupted
secret-return route. Subsequent `tmp/title-local-shalamar-menus-01` replay
uses1080 frames and six-frame Select holds at120/240/420/540/720/840;
no game-memory writes or health assistance during replay. Pinned corrected
r454 core, checked-in single-flight default; runs sequentially, local only.

All1080 captured frames remain scene0C. All three adjacent input-defined
roundtrip windows pass rendered black/white endpoints, four-frame intermediate
white-return holds, and full24x24 source/map readiness through reveal. The
additional second-return event trace records8 palette-publication events,
all576/576 source/map cells equal. Menu flags at180/320,480/620,780/920 are
1/0 in each pair, and all128 BG/OBJ palette bytes equal the corresponding
pre-menu deck at these checkpoints. Frame1080 reviewed: intact cyan boss
and patterned arena. Tests re-evaluate these oracles from retained artifacts.

This proves the bounded clean-entry menu regression scope on the newest trial;
it does not establish a fix for recorded persistent gray/red-yellow patches
after the secret route, continuous silhouette integrity, natural fight inputs,
native audio neutrality, or hardware behavior. Historical broken controls and
the earlier palette-window sampled-map failure remain retained. #27/#34 stay
open. No deployment, restart of Rivalmage, or controller changes.

## Native audio duration delta localized to title exit (#35)

Read-only analysis of the preceding complete native captures, not a rerun:
serialized globalCycles at198..19F and untouched PCM callback counts show
trial-minus-parent cycle delta4032 at native frame193, then -53448 at194.
Both transition scene01 to00 and LCDC83 to00 at194. The final frame599 delta
is still -53448 master cycles. The832 fewer delivered samples account for
53248 of those cycles; the remaining200-cycle difference is within output
batch phase. The pinned core emits32 samples per callback,64 master cycles
per sample. Every one of600 frames in each capture satisfies the observed
batch phase bound -2048 < globalCycles -64*deliveredSamples <=0.
This supports shorter emulated elapsed time at LCD-off title exit rather
than missing capture batches. It is NOT proof of unchanged music scheduling,
no audible glitches, or full audio neutrality; the unequal-count rejection
remains valid and untouched audio is retained.

Source reviewed: pinned core audio.c `_sample` emitsGB_MAX_SAMPLES32 and
serialize.c stores the global clock without transformation. audio.c SHA
41536ae04b3345154d83f63f044fefbbc4957f58c16b20a5ece7776ce95a09c6;
serialize.h SHAfe297e1f216f365b73ebc6360d79bc73bc701343223d3cdb15eeb01dbe5368bf.
`test_title_native_clock.py` binds full retained state-file hashes, asserts
this LCD-off transition localization, and rejects a deliberate64-sample
loss in the cumulative timeline. It is explicitly a diagnostic, not a new
weaker replacement for the primary audio comparator. No ROM or hardware
changes in this investigation.

## Title-local trial: restart route passes, native audio remains unqualified (#35)

Exact8ff1c98d trial, fresh guarded `tmp/title-local-guard-hazard-restart-01`,
passes the unchanged two-cycle hazard-death/saved-game/sequence verifier.
This uses1600 frames of hazard-area movement then HP0 once per life, plus
the save-present fixture: NOT movement-only natural death.102 Game Over
frames,482 returned-title pairs, stage-selector/card and terrain checks pass.
Game Over1 and returned-title2 captures visually inspected: intact accented
GAME OVER glyphs and colored title/footer. Unit coverage re-executes the
actual retained image/data oracles rather than trusting receipt status.
Probe SHA9a62bc6a3fe86b6ee654258dfc888785ecd326de661078e23b5a336b61ac9ab9;
verifier SHAcf451c1a77db292cf150a455608c3ccc0d270e29002d5fff8a7000feca9d5173.

Fresh600-frame cold native-AV captures (no CRAM/helper watchpoints):
`/mnt/data/tmp/penta-title-audio-control-20260928-01` (106c2e01) and
`/mnt/data/tmp/penta-title-audio-local-20260928-01` (8ff1c98d), with route
receipts `tmp/title-audio-control-cold-01` / `tmp/title-audio-local-cold-01`.
Pinned core SHA20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf;
native tap SHA337c75dfaa448939c5089ef60ad78fb854ce46b883eaaf7a35669b258590f2d7.
Explicit mute0/volume256/fastForwardMute-1/fastForwardVolume256 enabled audio.
Both captures have600 native frames and complete unmodified stereo131072Hz
PCM, but parent1323232 samples versus trial1322400:832 fewer, about6.35ms.
The full native-PCM comparator correctly REJECTS unequal sample counts;
no trimming, normalization, alignment or resampling was used. Native WAVs
and raw files are retained with hashes in each capture-receipt.json.
Parent PCM SHA4b615513508334902e189fe30885968922acb39c6c0ae2e38dfa80332126b799;
trial PCMSHAb7b1ec1cbeed46e04b90745237259130da5617909034579d5dc662a57d48bfdf.
Separate descriptive measurements: RMS2667.47 versus2679.46, zero clipped
samples in both, max sample step16919 versus16149. Silence intervals differ.
These measurements do NOT override the failed full-route comparison or
establish perceptual equivalence. Audio has not been auditioned here.
Added a retained test requiring that this real count mismatch stays rejected.
Next investigation: native clock/input/transition timing behind the count
difference; no new broader campaign, deployment, or hardware takeover yet.

## Title-specific guard restores mapper contract; still experimental (#35)

Fresh paired600-frame helper traces (`title-helper-control-cold-01` and
`title-helper-guard-cold-01`) found366 calls each. Original helper always616
observed cycles, shared-guard trial median4448 (3360..5744). Original changes
DC09 on zero calls; shared-guard trial changes it on76 calls. Both preserveDE.
Thus reusing the general writer violated the title caller's mapper-shadow
contract, not merely its cycle budget. This observation does not prove that
DC09 alone explains all visible/timing differences.

New builder `build_title_local_guard_trial.py` authenticates the parent and
both title source operands, puts a private copy of the6838 ramp in bank20,
and writes guarded four-byte chunks without the general scene dispatcher.
Mapper-only09BE entry/return leavesDC09 untouched. IE is restored in the
source-bank epilogue after live-register and stack restoration; IME is unchanged.
The copied ramp requires rebuilding this trial when its source palette changes.
Only exact erased bank20 regions and the original nine-byte helper are patched,
plus checksum. ROM SHA8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c.

Fresh `tmp/title-helper-local-cold-01`:3248 observed writes (same as parent),
zero blocked;366 helper calls, zeroDC09 changes, median2512 cycles
(1680..3872). Scene01 starts12/exits195, scene18 starts332 as parent;
Stage1 begins498 versus parent499. Full RGB comparison retains63/600 changed
frames, not exact video/cadence parity. Frame120/title and600/gameplay inspected;
frame498 is a black transition frame. Native PCM is not qualified. Neither
hardware deployment nor release promotion occurred; #35 stays open.
Probe SHA16cacb7f838dae91eb49027b934e4b8009bbffaa7641759a94a6772f770e39b0.
Helper trace SHAc561ec8662e6bbe5fb096eab44271023b8475509c3823ffafea0eeb79874a2b0;
CRAM trace SHA6d6d552ff42c7e0a1771d551817c64e905cd350028036e297c448ea61cc98157.
Regression tests preserve register/stack contracts, write count, safe accesses,
and the remaining one-frame difference instead of labeling it neutral.

## Title guard trial: access improved, behavior not qualified (#35)

Rechecked the retained 600-frame, cold-boot, no-memory-assistance runs
`tmp/title-cram-control-cold-01` and `tmp/title-cram-guard-cold-01`.
Parent SHA106c2e0181fa9bee1b3777f82af61d49d181415dafdd0456fea2c56a8234e317;
trial SHAd8fe220ef8dbf5a435ef41f5226d6f0346f63f8449ac54a02500b434fc77a831.
The experimental builder replaces only bank13:6A57's nine-byte copy helper
and the global checksum, calling the existing guarded eight-byte writer.

All observed CRAM writes: parent3248, blocked333; trial2992, blocked0.
The unequal write counts are retained, not discarded. Trace SHA256:
parent ec4944b990ea6b0285c45559b614942a328c6d229c531095a85f407e074c71c8;
trial 426539de3029f0d2a8c4b3c63cddf51564d8a7af64d6f94642e2c2bbe0a34787.
However, 396 of600 full RGB frames differ (first34, last600).
Scene01 starts12 and exits195 in both; scene18 begins332 versus433;
Stage1 scene02 begins499 versus596. This is a97-frame entry delay, not
an acceptable fidelity qualification. Frame120 was visually inspected in
both runs: footer appearance differs too. No audio equivalence was measured.

Do not promote this trial or close #35 based on PASS_OBSERVED_WRITES.
The title caller repairs BG0 and BG7 repeatedly and then clears the palette
phase; its source explicitly requires title/reel cadence preservation.
The reused guarded route includes mapper and scene-dispatch work, so eliminating
blocked accesses alone does not establish caller compatibility. Cause of the
observed start delay remains under investigation. Retained regression tests
bind both ROMs, preserve the broken control, and explicitly retain the delayed
entry outcome. No hardware or deployment changes.

## Handheld write timing: safe new branch, inherited cold-title failure (#25/#35)

Fresh guarded10800-frame runs with read-only FF69/FF6B watchpoints:
`tmp/handheld-palette-cram-return-01` (106c2e01) and
`tmp/select02-cram-secret-return-01` (parent7c5afca5), probeSHA
d407d14931bbecb4842a5bed774b97be7fd7fb860e1b79d55c75810e9c3c7fae.
Both retain ALL3784 observed writes. Both FAIL global palette-access safety:
333 writes occur with LCD enabled/mode3, all scene01, bank13:6A5C,
frames12..194. Source `build_title_palette_copy_helper` is an unguarded8-byte
loop. Filed #35 before any attempted fix; visual impact is not established,
and historical title issues #4/#8 are not claimed reproduced by this trace.

The handheld branch accounts for24 writes,20 in mode1 and4 in mode0, IE00
throughout; none in mode3. This scoped success does not override the global
failure. Original parent and trial have the identical inherited failure count.
TraceSHA trial7b3c6f897ea92cc288313cdff5c00f92096b51c79d6a0289f300e6de226d6377;
parentd548e7997d18ff5198c1ee416d20146d31a12dd7c7a5d9b2fbd318b00730ce25.

Observer-on versus preceding same-ROM observer-off run: gameplay trace identical,
all103 saved PNGs byte-identical, but ALL103 serialized states differ. Example
3720 has136 differing bytes beginning in audio fields A8..AF and1E0 onward.
Do not mask those fields or claim complete observer/native-PCM neutrality.
No hardware changes. `check_cram_timing.py` retains every blocked row and fails
empty/invalid/nonmonotonic observations.4 tests plus2 retained-run subtests pass,
explicitly requiring BOTH real runs to remain FAIL with333 blocked writes.

## Experimental isolated handheld palette implemented (#25)

`build_handheld_palette_trial.py` creates106c2e0181fa9bee1b3777f82af61d49d181415dafdd0456fea2c56a8234e317
from exact7c5afca5, output `tmp/handheld-palette-trial-01`. ColorsBGR555
0000/6318/2E4E/1084 give transparent/gray/olive/dark. Original pixels unchanged.
Only bank13 OBJ3 source halves6858/685C, scene09/0A AND stage07, are substituted.
The global palette deck remains byte-identical. Title spotlight is not changed.

Bank20:7320 jumps to the selector7D80; it preserves the inherited save-DE,
source-bank and saved-IE ABI. Unselected calls resume the original router732A.
Selected calls save original HL, use the same bounded VBlank/HBlank four-byte
policy, then restore HL+4. Bank20:71E7 loads13 and CALLs the original fixed
mapper at71E9; execution resumes at13:71EC, the unchanged POP-DE/restore-IE/RET
epilogue. All added payload/data/rendezvous bytes require erasedFF preimages.
No new RAM ownership or palette writes from the diagnostic observer.
This adds selector cycles; timing/audio neutrality is NOT established.

Fresh10800-frame `tmp/handheld-palette-menu-return-01` repeats the prior assisted
menu/encounter/return route. Secret samples3240/3360(open menu)/3480/3720/6600
all hold the new OBJ3. All other OBJ slots AND all BG CRAM bytes equal the
parent at those samples. Initial Stage1 sample1200 and returned sample10800
have the parent's entire original OBJ/BG decks, including restored redOBJ3.
Native sequence reaches secret2608, encounter4264, secret return6304, Stage1
8435; parent timing differs (Stage1 returned8510), so no speed-equivalence claim.
Images3720/10800 inspected: handheld now gray/olive, Stage1 colors restored.

`tests/test_handheld_palette_trial.py` checks exact parent, allowed patch bytes,
untouched base palette deck, mapper rendezvous and retained route samples. The
parent fails the requested new-palette assertion; the trial passes. Combined
with palette-window tests:7 tests,7 subtests pass. This is an experimental visual
treatment, pending CRAM timing trace, gameplay/audio guards, broader actor
ownership and title handling. Not promoted/deployed; #25 remains open.

## Game Boy-shaped actor positively identified; palette isolation still needed (#25)

Recording at27:35 (`tmp/gameboy-actor-identification-01/recording-27m35.png`)
clearly shows a red handheld-console actor, with screen, cross-shaped controls
and buttons. The exact current7c5a secret-route frame3720 screenshot shows the
same artwork. Decoding its state identifies VRAM tiles30..37 (128 bytes),
byte-identical to original AND current ROM offset22700..2277F. ArtSHA256:
5d384bf8784b6127f811119eca5ff7652627e75954e93e95e1b87123058ce781.
StateSHA2774fd5d4331b67cc2f2ad02275e21e92e6f0c00c04d3803f76c3a847f60f33f.
At3720 visible OAMslot20 uses tile34, attr03, x56/y106; live OBJ3 is
00001f0017000f00 (transparent/red/red/red). Thus this is palette art direction,
not a missing handheld sprite or a guessed enemy name.

The generic `crow` YAML family spans30..3F across scenes; it is not an actor ID.
Added a comment documenting this reuse; no functional palette change. In all
saved scene09/stage07 non-menu samples of the10800-frame current route, observed
OBJ3 tiles are30..37 only, while projectiles01/0F useOBJ0. This is sampled
ownership, not proof of every scene/form or future spawn. Other observed slots
include OBJ4/5/6, so do not repurpose those blindly. Global OBJ3 recoloring would
also affect unrelated ordinary-stage crows. The title spotlight likewise reuses
tile addresses, so its actor identity needs separate routing consideration.

Next implementation boundary: scope the palette to the identified actor/scene,
preserve other actors and palette restoration on exit, then preview in emulator.
No runtime/color edits, hardware operations or claim that #25 is finished.

## Menu route through encounter and secret return: intermediate failure retained (#23/#26)

Fresh sequential10800-frame cold runs `tmp/reported-secret-menu-fullreturn-01`
(reported4f5a) and `tmp/select02-secret-menu-fullreturn-01` (current7c5a)
use the same probe4c5b72ff, guarded r454 runtime, prior-room movement,
one doorway position setup2401, resource refill, Select3300..3305 and3420..3425,
then pulsed A from3426. Both actually enter/leave the menu (FFE4=1 at3360,
0 at3480). No powerup selection is claimed; this tests menu open/close only.

| Sample | Reported palette-cell mismatches | Current mismatches |
| --- | --- | --- |
| 3240 before menu | 271 | 0 |
| 3480 after menu | 294 | 0 |
| 3600 | 292 | 0 |
| 6600 after encounter, back in secret09 | 85 | 0 |

Counts use the existing1536-cell whole-plane policy oracle. Open-menu3360
is not evaluated against gameplay policy. At6600 both BG0 values have recovered
to ff7f947e4a3d0000, but the reported ROM still has2005/2048 CHR differences
against authenticated original37400–37BFF; current has zero. Images6600
visibly corroborate damaged old architecture versus intact current architecture.
This intermediate checkpoint matters: BOTH terminal10800 images appear clean
after Stage1 restoration (reported8512/current8510). Thus a terminal-only
return check would miss the old defect. Scene sequences differ in timing and
encounter positions, so this is not performance or frame-equivalence acceptance.

TraceSHA reported463e9a8e07f90b1b2366063cab5aafdecac596eac14222a6424b76bd6bdf5df7;
current91a78d337fef85f910199ff915be6855747a00f751b71f0ea84a42592af18ce9.
Added retained-real-checkpoint regression in test_secret_palette_planes.py:
both post-encounter BG0 values are correct, yet old85/current0 attribute errors
must remain distinguishable. Combined palette suites:9 tests,4 subtests pass.
No ROM edits, hardware operations, native PCM qualification, or claim that the
recorded yellow trails/powerup trigger are reproduced. Keep #23/#26 open.

## Current7c5a secret encounter, return and input-only movement (#23/#26)

Fresh `tmp/select02-secret-return-01` completes7800 frames on exact7c5afca5
with scratch probe4c5b72ffa1f383e0196c4ca5f09a2e328486b273dad3f477dafffd7fbea84257
and guarded corrected r454 runtime. Cold boot, one position setup at1201,
resource refill and pulsed A; no forced scene/palette/graphics/cache writes.
Native sequence: secret09 at1409, encounter0A4057, secret09 return6892,
stage00 restoration6893, card6911, Stage1 scene02 at7106.
Trace SHA256:935287345a2aecf92c86560c71929a86f70e63995019303b714796e293433a2f.
Timing differs from b09e's earlier route; not a speed-equivalence claim.

At3600: both maps'1536 published palette cells pass the existing whole-plane
policy oracle with zero mismatches, BG0=ff7f947e4a3d0000, and VRAM9000–97FF
matches all2048 original-ROM bytes at37400–37BFF (stockSHA2f32570c...).
The initial ad-hoc comparison mistakenly used the DX ROM's old stock offset
and reported2005 differences; the authenticated ORIGINAL ROM is the required
reference, as in verify_secret_chr_entry.py. No graphics change was needed.
Terminal7800 PNG inspected: blue/white terrain and colored actors present.

`tmp/select02-secret-return-walk-01` restores that exact-ROM7800 checkpoint
(SHA71ab2444fe449acc83bd186eed6bf3816a6d30f22dfb2441eabd915bc9a279f8),
CRC/header checked, then holds Right with pulsed A for960 frames. No new memory
assistance; inherited prefix remains assisted. All960 frames stay scene02/stage00;
world position1224/1472 to1400/1472, room01 to03. Images120/480/960 inspected:
colored terrain remains visible without the reported persistent yellow trails.
TraceSHAd7fa89073c29dc272467cb3a8e8a72ca66ebe36e2737a897336b178aaf2f6f73.
This is a short sampled visual check, not an exhaustive temporal oracle or the
recorded menu/powerup route. No native PCM capture, hardware test or deployment.
Keep #23/#26 open; absence on this route does not establish the yellow-trail cause.

## Stage2 prompt-relative Continue: reported-build negative control (#28)

Fresh exact-ROM Stage2 entries were generated separately with the checked-in
guarded level-select generator (not natural Stage1 completion). Reported4f5a
entry SHA256 is 4112b5c1480552041153df6aec07eb355494f59491d96f537e06cb7a54f8267f;
current7c5a entry is a6d5657d50004ab00b4fec366513aec8a1e77ef9d5fe18c72b7a5beb93ef228a.
Serialized ROM CRC/header were checked before replay. Same probe72ed0720 and
corrected20fa5dda core as below; all runs complete6000 frames.

| Run under tmp/ | Result | Death | First input | Resume | Title |
| --- | --- | --- | --- | --- | --- |
| reported-stage2-continue-prompt-a-01 | FAIL, no native A edge | 1216 | 1278 | none | 2125 |
| select02-stage2-continue-prompt-a-01 | PASS, A accepted and credit consumed | 1230 | 1292 | 1348 | none |
| select02-stage2-continue-prompt-neutral-01 | PASS, full countdown/no acceptance | 1230 | 1292 (neutral) | none | 2180 |

The reported-build control fails despite A pulses during the native prompt,
not because the input precedes death. Its trace SHA256 is
6970d74e63b82399dfde0fb419e83c1ed9361fd0d6f777038102547e914d567d.
Current A/neutral trace hashes are recorded in their verification.json files.
Terminal screenshots inspected: current A remains in Stage2; neutral reaches
colored title; reported control reaches a mostly black title/attract screen.
This qualifies the existing input repair in this assisted Stage2 case. It does
not prove the preceding secret-area corruption route, natural death, native
audio, arbitrary controller timing or MiSTer behavior. No ROM code changed or
hardware touched.17 tests and5 subtests pass. Keep #28 open.

## Current candidate Continue: retain fixed-window failure, qualify prompt-relative input (#28)

Fresh unchanged fixed-frame driver runs expose a coverage limit:
`select02-continue-a-01` (7c5a) reaches death2101, after its A schedule
1380..1799, and fails (no acceptance/resumption). `palette-window-continue-a-01`
(b09e) exits emulator0 but its oracle rejects because death is absent through2400.
`source07-continue-a-recheck-01` (eebf) reproduces the earlier PASS: death1280,
resume1438. All use probeac5bf9f9fe2fa43d865ac5cad1f8a26d7b0da1035924a0dc3a553716e9e52720
and corrected20fa5dda library. The fixed failure is not silently replaced or
interpreted as proven loss of a button pressed during the Continue prompt.

Added optional `run_continue_input.py --prompt-relative`: still sets one credit
and the same depletion stimulus at1201, but begins its420-frame input window
12 frames after the FIRST native bank1:4A9C Continue poll. Limit6000 frames;
no scene/PC/palette/controller-register forcing. This is a separate gameplay
diagnostic, not clock-aligned equivalence to the fixed-window run. Default
2400-frame schedule remains unchanged. Oracle requires complete traces,
ordered native polls, exact schedule and bindings, and rejects censored input
windows; accepted A must resume and consume the credit, neutral/Start must
observe10..1 countdown and return to title without acceptance.

Fresh current7c5a runs, probe72ed0720a6854fb255c0bad92e9ec5119162441f7e621381c7b73e0b6d6e4351:

- `tmp/select02-continue-prompt-a-01`: PASS, death1955, input begins2017,
  resume2073, no title, zero credits, active Stage1 through6000.
- `tmp/select02-continue-prompt-neutral-01`: PASS, same death1955,
  no A edge/resumption, full countdown, title2911 through6000.

Both terminal screenshots inspected: gameplay for A, cyan title for neutral.
No continuous video, native audio, Stage2, natural death or hardware claim.
The changed pre-death input history explains why these are not timing parity
comparisons; no ROM code was altered.17 tests and5 subtests pass, including
prompt-relative broken-A and incorrectly fixed-scheduled-input mutations.
Issue28 remains open for broader reported context and hardware validation.

## Remaining Stage1 event09 special transfers reached (#22, identity still unresolved)

Fresh reported4f5a cold diagnostics using probe4c5b72ff and the same corrected
core reach the other two terminal records of the Stage0 event09 table:

| Run under tmp/ | One-shot setup | Native match at1215 | Transfer flag | Terminal world |
| --- | --- | --- | --- | --- |
| star-native-entrance14-reported-01 | 968/808 | DE3841, HL410F | E0 | see retained trace |
| star-native-entrance13-reported-01 | 1608/1800 | DE7669, HL4102 | C4 | 1576/624 |

Both run1800 frames, Down through1260 after the cold start, resource refill,
and no forced destination/rendering/cache writes. The position setup breakpoint
follows each successful native match at1215. Thus all three special records
12..14 now have observed native transfers; the12 earlier corridor records are
not claimed tested. Terminal screenshots were inspected. Both maps at these
endpoints lack the Spiral8E/8F/9E/9F signature; BG5 remains gold/red
`ff7fff031f000000`. This does not identify the reported gray object.

Also continued the first destination using only Left120/idle120, then
Up120/idle120, each from its own exact-ROM prior checkpoint:
`star-native-destination-left-01` ends1320/672 and
`star-native-destination-up-01` ends1320/568. No new memory assistance in
these segments; the inherited cold prefix had position/resource assistance.
The upward endpoint contains the atlas Teleport signature, not Spiral.
These short legs establish reachable geometry but are not a whole-room search.
Restore boundaries do not establish uninterrupted audio/timing fidelity.
No ROM patch, palette change, or hardware interaction; #22 remains unresolved.

## Native Stage1 teleport reached from its entrance (#22, route progress)

Read-only reported4f5a disassembly identifies event09 handler151D, its13-byte
records selected through1636, and position setter15F7. Stage0 bank13:4058
contains15 records. Record12 at40F5 begins61/38 and endsD6/5B/2C;
the latter destination bytes decode through15F7 to world1384/640. Earlier
trials near1384/608 were near this destination, not its matching entrance.
This explains why those trials were not adequate entrance reproduction.

Fresh `tmp/star-native-entrance-reported-04` completes1800 cold frames with
one next-loop position assist to1480/808 at1201, Down through1320, then no
keys. Resource refill is explicitly enabled. Read-only breakpoints record
13E5 dispatch,151D transfer,164E successful match and15F7 position setup.
At1215, with world1480/816, DE3861 reaches handler151D, matchesHL40F5,
then15F7 receivesHL4100 and CA=D6. These are the native record lookup and
transfer path, not an observer-forced destination. Terminal scene02 is
world1368/672 after continued Down input; inspected image shows the destination
area. No rendering/cache/scene writes were added by the trace.

Probe SHA4c5b72ffa1f383e0196c4ca5f09a2e328486b273dad3f477dafffd7fbea84257;
ROM4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5;
corrected20fa5dda core unchanged. The extra breakpoint trace is not yet
qualified for full observer neutrality or PCM. This establishes one assisted
entrance followed by a native teleport, NOT the user's exact route/object,
gray-star reproduction, or fix. Next follow the destination's pickup route
and distinguish the other two non-corridor event09 records if necessary.

## Spiral menu round trip remains gold on reported build (#22, non-reproduction)

Two sequential240-frame input-only diagnostics use exact reported4f5a ROM and
probe3042e27592bf4b3fdf44ce91d6b6cdf26bc3b80598d21b8a9d02f804f7f63fa3.
`tmp/star-spiral-menu-open-reported-01` restores the authenticated prior cold
control at1500 (state SHA cfea613e3b112e1fa523cec4bb34510dc832d04a1910a543862ed21747da4c3d),
holds Select for6 frames and releases. Its terminal screenshot visibly shows
the menu. `tmp/star-spiral-menu-close-reported-01` restores that exact terminal
state (3bd85aa99dea2c4da04cbb725c06f24090daf80f23a89e71710c288ca2794ca6),
repeats the6-frame Select pulse, and visibly returns to gameplay. Both exit0,
scene02, with no new health, position, scene, palette or graphics writes.

Before/open/closed snapshots all retain BG5 `ff7fff031f000000` and attributes
5/5/5/5 for Spiral8E/8F/9E/9F at14,10 on both maps. The inspected returned
image still shows the gold/red star-shaped pickup; terminal state SHA
57a1c9bad07c922249ff6f5e98eb4c9bff5fcda55f27afdd4d86b58db000f8c4.
Thus this menu round trip does not reproduce the gray-star report.

The starting checkpoint inherited one position assist from the old cold control;
this is NOT native teleport entry. There is a savestate restore between the
two segments, so do not claim seamless timing/audio continuity. The reported
object still lacks positive identification; recoloring this already-gold
control would not be a justified fix. No candidate changes or hardware writes.

## Whole published-plane check catches stale scenery missed by pickup signatures (#23/#26)

Read-only analysis of the preceding4800-frame movement runs distinguishes global
BG0 repair from per-cell palette repair. At4800, source07 has150 palette-policy
mismatches in9800 rows0..23 and143 in9C00 rows0..23 (293 total), despite its
globally corrected BG0 and superficially clean terminal image. Trial02 has zero
in the same1536-cell scope. This compares the intended secret tile-ID lookup
policy (neutral0 except documented pickup tiles), not independent art semantics.

`check_secret_pickup_attributes.py --whole-plane` now reports every mismatched
cell's map/position/tile/attribute/expected palette, checks scene09 AND stage07,
and authenticates state CRC/header against the supplied hash-pinned ROM. Its
existing pickup-signature mode is unchanged. Rows24..31 are explicitly outside
the copier's published region; this result does not qualify raster timing,
CHR, speed, audio, or the recorded red/yellow onset. Neutral blank cells can
pass this policy check without proving any pickup was visited.

`tests/test_secret_palette_planes.py` adds a synthetic no-pickup neutral plane,
stale scenery on both maps, wrong-stage rejection, and retained real source07
failure/trial02 success. Together with the prior pickup tests:8 passed and
2 subtests passed. No emulator rerun, ROM patch, or deployment this step.
The larger bug remains open; the new check prevents a pickup-only result from
being mistaken for correct scenery attributes across the published planes.

## Secret post-menu movement control (#23/#26): persistent wrong BG0, not yellow-trail closure

Four fresh sequential cold-boot diagnostics complete4800 frames using retained
probe3042e27592bf4b3fdf44ce91d6b6cdf26bc3b80598d21b8a9d02f804f7f63fa3
and corrected library20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf.
Each uses prior-room movement, one loop-boundary doorway position assist2401,
resource refill, Select3300..3305/3420..3425, and firing beginning3426.
These are assisted diagnostic routes, not reconstructed recording inputs.
No palette/cache/graphics writes, hardware intervention, or ROM edits.

- `tmp/reported-secret-postmenu-stationary-01`: reported4f5a, pulsed A.
- `tmp/reported-secret-postmenu-right-01`: reported4f5a, Right plus pulsed A.
- `tmp/source07-secret-postmenu-right-01`: source07/eebf, same moving recipe.
- `tmp/select02-secret-postmenu-right-01`: trial02/7c5a, same moving recipe.

Reported moving and source07 moving position/scene traces are byte-identical,
SHA53698e4abd17513539fac679acb52716822da021301b4cfb8d092886d01f92f1.
Their sampled physical attribute planes also match at3240/3360/3480/3600/4800.
Nevertheless, reported BG0 remains `070607ff7f947eff` at all five samples;
source07 is `ff7f947e4a3d0000`. Inspected reported3600/4800 images have broken
geometry and persistent green/pink scenery; source07 terminal image has clean
secret geometry and blue/white scenery. Crucially, wrong BG0 already exists
at3240 BEFORE Select. This is evidence for the existing secret-source repair,
not evidence that menu closure caused the corruption.

Stationary reported control leaves scene09 for0A by4800 and restores BG0;
moving reported control remains09 and retains wrong BG0 through4800. Thus
encounter progression can hide this palette defect in a stationary endpoint.
Trial02 likewise retains correct BG0 at all five samples and its inspected
terminal image looks clean, but its trace differs
(d32d5204430b900abd6ecf427d6a6bd206c4b1730375690fe08dc5cfd6d75f4b)
and its attribute planes differ: do not claim cross-candidate timing/state
equivalence. No native PCM qualification in these runs.

The actual recorded red/yellow-band onset remains unreproduced. Next work must
distinguish stale per-cell attributes/pickup publication from this already-known
global BG0 defect; neither #20 nor #26 is resolved by these pictures.

## Ted early exit reproduces on source07 and original ROM (#32)

Fresh own-ROM controls `tmp/source07-ted-menu-control-01` (eebf3f19, fixture
`tmp/source07-nine-boss-corrected-01/boss4_ted.ss0`) and
`tmp/stock-ted-menu-control-01` (original2f32570c, fixture
`tmp/ted-stock-dispatch-control-01/boss4_ted.ss0`) both complete1080 captures.
Original goes scene10→0B at55; source07 and trial02 do so at57. All precede
the first scripted Select120. PlayerHP becomes0 at117 stock,157 source07,
156 trial02. This is not a new Select-buffer-induced arena exit.

Generator source already documents that the synthetic Stage1 dispatcher can
inherit an attack phase decrementing DCBB and that Ted/Penta may leave shortly
after reload. It refills HP/DCBB while generating a visual checkpoint. The
menu replay does not repeat those assists. Do not silently add them or call
this ordinary-play continuity. A natural sustained Ted encounter (or an
explicitly separate assisted rendering test) is needed for menu acceptance.

`check_boss_menu_fades.py --expected-scene` now optionally requires every
observed frame to retain the specified main-boss scene, keeping all offending
frames visible alongside existing rendering failures. No failed samples are
removed, and no endpoint threshold is relaxed. New tests reject absent scene
data, death/title/subscene transitions and all three retained pre-input exits.
No game ROM or hardware change. #32 remains open for remaining qualification.

## Crystal round trips pass; Ted replay exits its scene before input (#27/#32/#34)

Exact trial02 `tmp/select-buffer-crystal-menus-02` completes1080frames and
three menu round trips. Each return passes black/white endpoints, four-frame
intermediate cadence and map-readiness checks. Final native screenshot viewed.
No Crystal speed/audio or full-fight claim.

Authenticated trial02's entire Ted bank17 against recognized4f5a parent and
E072 at44364. Registered that exact identity in `relocated_ted_latches` only,
not the separate Penta state-retarget allowlist. Existing corrected-r454
runtime produces `tmp/select-buffer-ted-entry-02` at332, scene10, PC439E,
SPDFEB,IE07,LCDC83; screenshot viewed, Ted and arena visible. This extends the
earlier #32 corrected-runtime result, not a newly repaired blank-map bug.

However `tmp/select-buffer-ted-menus-02` is NOT a qualified three-menu replay.
Scene is10 at1 but already0B at120 (first scripted Select); at180 playerHP0;
scene17 at334 and title01 by600. Settled-white assertions fail334–341 and
595–623; later menu/fade assertions also fail. Frames334 and1080 inspected:
Game Over/death artwork and title, respectively, not a stable Ted menu return.
Retain these failures; do not relax the oracle or classify them as Ted menu
corruption without establishing the route. Next inspect the pre-input scene
exit and compare earlier source07's exact-ROM fixture. No health aid was added
to keep this replay artificially in an arena. Six palette-oracle tests plus
28subtests pass; no hardware operation or issue closure.

## Native audio guard and next arena fixture (#34/#30)

Fresh captures: parent b09ec41a in `tmp/select-buffer-parent-native-01` with
untouched media `/mnt/data/tmp/penta-select-parent-native-01`; trial02 7c5afca5
in `tmp/select-buffer-candidate-native-02` with media
`/mnt/data/tmp/penta-select-candidate-native-02`. Same default six-frame
Select120/240/420/540/720/840 sequence and pinned native tap337c75df…/r454 core.
Both complete three round trips and1080 replay frames; tap includes1081frames
because it also captures the pre-state-load frame. Each has2,372,288 native
stereo sample frames at131072Hz. WAV wrapping leaves PCM unchanged.

`tmp/select-buffer-native-audio-pair-02/receipt.json` PASS under the existing
unmodified dropout/clipping/level/discontinuity guard. RMS3542.12→3569.34,
ratio1.007683; clipping0/0; no>=20ms digital-silence interval in either;
maximum sample step23066→23065. All-sample differences retained in NPZ:
2,369,927 sample frames differ, first2209,last2372287,maxdifference29297.
This is NOT waveform/perceptual equivalence or proof of tap neutrality.
No audio was claimed heard. Ten audio guard tests pass.

For broader scene coverage, authenticated trial02's entire bank23 against
`expected_bank23()` and recognized4f5a parent; selector bank13:6FD5..6FE0 and
all nine arena LUTs match that parent. Registered only this exact hash in
the relocated palette oracle (#30), retaining independent table-builder
checks. Six oracle tests plus28subtests pass. Fresh Crystal fixture
`tmp/select-buffer-crystal-entry-02` settles at125, scene0E, PCDB40, SPDFED,
IE07,LCDC83 with expected relocated active table. This is entry-fixture
qualification only; next run its menu/input regression before further scope.
No deployment, ROM promotion or issue closure.

## Select trial02 phase and scoped write-ownership checks (#34)

Exact7c5afca5 trial02, unchanged own-ROM fixture, additional one-frame third
entry probes `tmp/select-buffer-short723-02` and `...short726-02` both deliver
edge04 at727 after raw has returned00. Menu flags780/900/1080=1/0/0 in both;
all1080frames complete. Together with721 this covers three selected phases,
not all phase/hold combinations or pulses that never reach the raw sampler.

Optional `--trace-latch` observes physical bank7:DF81/DF82 writes for the
whole replay. `tmp/select-buffer-latch721-03` records2690writes:1031/sample
and314/consumer writes per byte. Sites bank25(hex37):6CAE/6CB2 for sample,
6DA5/6DA9 for consume; IE00 for every write. Pending values00/04; owner00/0C.
All1080PNG files equal the same-ROM unobserved short721 replay. PCM and full
state observer neutrality are not established. This only supports ownership
within this arena/menu route, not boot, other scenes, bulk clears or all RAM.
Initial `...latch721-02` watched an exclusive-ended range covering DF81 only;
retained but superseded by03 after extending the end toDF83. The checker
requires both writer pairs and active/inactive values, so this incomplete
trace cannot pass. Mutation tests reject missingDF82, wrongbank, wrongSVBK,
foreignPC, nonzeroIE, invalidvalues and emptytraces.25tests pass.
No ROM change, deployment or issue closure in this step.

## Select trial02 removes DC09 side effect; speed/restart checks pass (#34)

Trial01's narrow throughput guard FAILS: deterministic116 versus stock112
loop anchors in600frames, ratio1.035714 outside the unchanged2% limit.
Receipt `tmp/select-buffer-speed-01/receipt.json` is retained. Inspection also
found its sampler used0847/0061, writing native DC09 on both bank switches,
unlike the original sampler. This is an unwanted side effect; the trace does
not establish it as the sole cause of the throughput difference.

Revised builder switches via mapper-only09BE and a bank37 rendezvous:
incoming RET6F68 jumps6C80; outgoing CALL09BE at6F65 returns to original
bank13:6F68. Helper pushes/pops remain balanced; no extra return address is
left on the game stack. Neither new sampler nor edge wrapper writes DC09.
Trial02 `tmp/select-buffer-trial-02/candidate.gb` SHA
`7c5afca573b80fefacfa057338ae8847bb86590f057a188112773076841972ec`.
Fresh exact-ROM fixture `tmp/select-buffer-boss-entry-02`: frame102 PC5752,
SP DFF1 IE07 LCDC8B. No cross-ROM state retargeting.

`tmp/select-buffer-short721-02`: raw04 at721, raw00 at722, edge04 later at722
with raw/held00. Three round trips and all three endpoint/four-frame cadence
checks PASS. Original six-frame test `tmp/select-buffer-phase721-02` also
completes three round trips, flags180/360/480/660/780/900=1/0/1/0/1/0.
`tmp/select-buffer-speed-02/receipt.json`: two deterministic replays per ROM,
111 DX versus112 stock anchors/600frames, ratio0.991071, unchanged2% gatePASS.
This assisted no-input arena assay is not natural combat/audio equivalence.

`tmp/select-buffer-hazard-gameover-02` PASS: two-cycle saved-game sequence,
1600-frame hazard-area walk then HP0 once per life,102 Game Overframes and
482 title-frame pairs. This is not natural lethal-contact reproduction.
17 structural/model/retained-evidence tests pass. No emulator remains running.
The latch remains active-arena-only and experimental: memory ownership across
all scenes, more input phases/holds, native audio, other arenas and hardware
are not qualified. No deployment, promotion or issue closure.

## Experimental Select latch delivers a released press in emulator (#34)

Builder `build_select_buffer_trial.py` emits
`tmp/select-buffer-trial-01/candidate.gb`, SHA
`15b009cbb3394de004664099e649afd2529eea2dacee157efb04adc3bee882c8`,
from exact b09ec41a parent. New bank37 helpers reserve experimental
SVBK7:DF81 pending and DF82 scene owner, immediately after the menu backup.
IE is saved and masked (IME unchanged); no stack access/call occurs while
bank7 is selected. Original SVBK is restored before stack/IE restoration.
The fixed edge wrapper preserves caller registers, return AF and ROM bank.
Raw FF93 and native held FF95 retain their meanings; only Select is queued.
Queue ownership applies to active arena scenes0C..14 with DD09=0/FFE4=0;
other samples/polls flush it. Cold-boot title sampling initializes it before
ordinary arena entry. All-scene RAM ownership and lifecycle safety remain
unqualified; this is NOT a release candidate or a dungeon-wide input fix.
The fixed edge wrapper executes outside arenas too and adds overhead there.

Fresh own-ROM fixture `tmp/select-buffer-boss-entry-01` settles at104, PC573E,
SP DFF1, IE07, LCDC8B. `tmp/select-buffer-phase721-01` completes all three
six-frame Select menu round trips (flags180/360/480/660/780/900 =1/0/1/0/1/0).
Because that press overlaps a poll at724, this alone could be a phase shift.
Therefore a NEW shorter diagnostic keeps all other inputs unchanged but
holds only the third entry for1frame (runner `--third-entry-hold`, default6).
It does not replace or weaken the original six-frame regression.

`tmp/select-buffer-short721-01`: raw04 at721, raw00 at722, native edge04 at724
while raw and held are00. Actual buffered delivery is demonstrated after
physical release. All three menu round trips complete. Exact-parent control
`tmp/select-buffer-parent-short721-01` misses it, edges00 at727/734; menu0 at780
and1 at900/1080. Both use their own exact-ROM fixtures, not cross-ROM states
or a claim of phase-identical machines. All replays complete1080frames.
Short-trial all three black/white endpoint checks and native four-frame
intermediate white-fade holds PASS. Viewed native frame1080: colored Shalamar
arena visible. No claim of resolving the recorded persistent arena bleed.

17 structural/model/retained-evidence tests pass. Broader phase/hold inputs,
Game Over, other scenes, native audio and throughput remain pending. No
hardware action, default promotion, commit or issue closure. Next verify
tradeoffs and RAM ownership before composing this experimental latch further.

## Separate pending Select contract, not yet a ROM fix (#34)

`scripts/diagnostics/select_edge_model.py` specifies a separate pending rising
Select bit while leaving the raw held-button sample unchanged. Consume clears
pending even when masked; disabled paths and lifecycle boundaries discard it.
Keeping the last physical sample across a boundary avoids inventing a new
press from a held button. Multiple presses between polls coalesce; this is
not a counted event queue or a guarantee of detecting unsampled pulses.

Seven design tests plus three retained-trace tests pass. On the unchanged
phase721 trace, actual FF94 remains00 at727/734; the model would deliver04
at727 and00 at734. This is counterfactual model execution, NOT emulator
success, latency qualification, or a fixed-ROM result. Tests also cover held
repeat, release/repress, masking, disabled input, boundaries, and all256 raw
button bytes crossed with all256 masks. Raw input is never made sticky.

No RAM allocated or ROM emitted. Existing HRAM/WRAM census prose overstated
scratch safety; clarified its historical/incomplete scope. FFE0/FFE1 are
already claimed, and experimental bank7 palette storage is not an all-scene
ownership proof. Implementation must separately authenticate initialization,
physical RAM ownership, atomic sample/consume, and lifecycle call sites.

## Attribute service cost is mostly safe-window waiting (#34)

Fresh exact-b09ec41a replay `tmp/palette-window-dma-phase721-02` keeps
the failing six-frame Select at721 and the same-ROM Shalamar fixture.
Bank23 matches `expansion_bank23_r456.expected_bank23()` byte-for-byte
(SHA80520bc8c12fb16e336653d60355856fb4dd49b8c0c911311be7651d09f14568).
This is the later synchronous DMA service, not the historical title painter.
Execution anchors are derived from the actual relocated service start6C9E:
wait6CAD, admitted6CC8, FF55 write6CE2, completed6CEA, restore6CF0.

Entry202546636 atLY26; wait202546836; admission202653804 atLY144;
FF55 write202654068; completion202657216 atLY147; restore202657280.
Thus wait-to-admission consumes106,968 global clock units; FF55-to-completion
3,148. Most of this service's cost is waiting, not copying. Removing that
wait is not an acceptable fix: its protected window keeps attribute DMA safe.
All1080 PNGs equal the retained same-ROM phase721 replay; this does not prove
PCM/state observer neutrality. No ROM patch, deployment, or issue closure.
The initial `...-01` trace used anchors displaced by two bytes; retained but
superseded by02 after computing the actual SYNC_PREFIX length and authenticating
the full service bytes. Do not use01 for instruction-boundary attribution.
Next choose audited input preservation or safe publication scheduling, rather
than micro-optimizing the transfer or lengthening the scripted Select pulse.

## Long Shalamar iteration includes full colorized publication (#34)

Added read-only execution anchors to the optional input trace (frames715–735),
logging global clock, PC/bank, SP/stack word, LY and SVBK. Stack words are raw
observations, not necessarily return addresses inside routines that push data.
Fresh `tmp/palette-window-loop-phase721-01` preserves the failing input route;
all1080 PNGs equal the prior same-ROM phase721 capture. No PCM-neutrality claim.
Stock comparison: `tmp/stock-loop-phase721-01`, same stock fixture/input.

DX loop anchors:201724812 at frame720 to202748688 at727 (1,023,876 clock units).
Native source generation309B begins201866348, map-dispatch028A begins202283188
(416,840 elapsed). Full dispatch through final observed028D takes382,228.
Within it: bank1F checks at202284068/202285100; bank1A at202383660;
bank1C copier202384404; bank1E202498476; bank17 relocated attribute/palette
service202546292; bank13 return202658048; final028D202665416. The previous
cached dispatch at719 took only5,752 clock units. Thus unequal publication
work is present during the missed-input interval.

Stock observed loop:198549528 at716 to199277192 at721 (727,664 units).
Source309B to028A:402,792; dispatch028A to028D:147,312. DX bank1C entry to
bank1E entry spans114,072, so that segment is not the obvious excess versus
the stock dispatch; the before/after colorization work is the next target.
These are distinct pose/phase samples, not an instruction-aligned total-cost
attribution or a claim that removing all extra work preserves graphics. Do
not remove attribute publication or accept reduced colors to match stock.
No game patch yet; next inspect compilation and attribute-publication waits.

## Shalamar average throughput matches, worst loop gap does not (#34)

Existing guarded `verify_boss_speed_parity.py` run on b09ec41a… with its
same-ROM Shalamar state and the stock same-ROM fixture, warmup60/measurement600,
produces receipt `tmp/palette-window-shalamar-speed-01`. Two sequential replays
per ROM agree in measured counts. Both complete112 bank2:406F gameplay-loop
iterations in600 observed frames: ratio1.000, unchanged2% throughput gate PASS.
Maximum loop gap is6 for stock,7 for DX; DX includes22 banked-writer parked
frames in its denominator, not dropped samples. This supports investigating
worst-iteration jitter rather than applying a blanket game-speed increase.

The verifier's continuity bound30 is not a short-input responsiveness test;
its PASS does not resolve issue34 or contradict the retained missed Select.
This assisted assay writes health/resource and arena-exit latches to keep the
encounter alive. It has no menus/buttons and does not prove natural-combat,
audio or original-relative phase equivalence. Its legacy output layout puts
traces in `tmp/boss-speed/shalamar/`, not beside the receipt; future runs must
use a fresh parent directory to avoid replacing those bound trace paths.
Next isolate the work occupying the extra loop interval before choosing a
bounded renderer optimization or separately audited lossless button latch.
No ROM patch, deployment or issue closure.

## Adjacent-phase controls reproduce missed Select on latest trial (#34)

Runner now accepts `--third-entry-frame` (700..800), pinned in launch/completion
receipts and passed explicitly to Lua. Defaults remain720; all holds remain6,
the other five presses and1080-frame duration stay unchanged. This is a new
phase probe, not an alteration of the original failed input sequence.

Exact b09ec41a… ROM and its same fresh Shalamar fixture:
`tmp/palette-window-select-phase721-01` misses the press: raw FF93 receives04,
but gameplay edge polls720/727/734 yield00. Adjacent
`tmp/palette-window-select-phase722-01` detects04 at727. Stock control
`tmp/stock-select-phase721-01` detects04 at721 using its own same-ROM fixture.
The latest palette fix therefore changes phase but does not solve input loss.
Three retained-evidence tests pass by requiring the observed failure, adjacent
success and stock success; these are NOT three passing responsiveness gates.
Stock/candidate fixtures still differ in machine phase, so no global missed-
input rate or exact slowdown is inferred. Existing guarded boss-speed tools
identify bank2:406F as the gameplay-loop anchor, a useful next cost measurement.
No ROM change or hardware interaction in this step.

## Missed Select is raw-input overwrite before gameplay edge sampling (#34)

New issue: https://github.com/struktured-labs/penta-dragon-dx/issues/34 .
Optional `--trace-input` observes FF93–FF96 writes during frames700–860,
without changing the replay's six-frame Select windows. Fresh exact e8002aea…
replay `tmp/combined-shalamar-input-trace-01` confirms raw FF93=04 writes at
720/721/722/723, then FF93=00 at726. Native edge FF94 is processed at719 and726,
both00, with no intervening edge update. The press was delivered but disappeared
between main-loop edge polls. The third entry remains absent. All1080 PNGs
match the same-ROM untraced control; no full audio-neutrality claim.

Stock control `tmp/stock-shalamar-input-trace-01`, exact stock ROM and existing
same-ROM fresh dispatcher fixture `tmp/shalamar-stock-clean-entry-01`, detects
FF94=04 at721 and has menu flag1 at780. This is not phase-identical cross-ROM
state equivalence, nor an all-phase latency/speed proof. In particular the
trace includes menu fades: its maximum edge-poll gap cannot be interpreted as
active-gameplay latency without labeling state. Parent gameplay around this
event has7-frame poll spacing. The newer b09ec41a trial detects this scheduled
press but may only change phase; it is not a general fix for missed input.

Keep this distinct from closed29's menu-wait misinterpretation and28's Continue
sampler fix. Next work: phase-varied active-combat input tests and original-
relative loop-cost investigation before choosing a speed or latch repair.
No input lengthening, dropped-failure filtering, ROM patch or hardware action.

## Shalamar reveal mismatch is later source generation, not stale reveal map (#27)

Read-only comparison of retained b09ec41a… frames591–602 shows selected VRAM
map unchanged through601, exactly matching frame595's full576-byte source.
Source changes34 cells at596,109 at597,74 at598; the map updates172 cells at602.
This motivated event-time observation rather than changing the ROM or masking
the mismatching cells in the existing frame oracle.

Optional `--trace-map` records second-return BGP writes with full source/map
snapshots and source-buffer write events, no game-memory writes. Fresh
`tmp/palette-window-shalamar-map-trace-01` uses the exact prior ROM/state and
unchanged inputs. All eight BGP publications (E4/90/40/00/00/40/90/E4) have
576/576 matching cells. Final E4 at global clock184118206; first later source
write at184221766, native bank0E PC3127, C1A0=00. Therefore the first E4 frame's
34 mismatches compare the already-started next source generation against the
correctly published reveal map. The original frame-oracle failure remains
retained, not relabeled as a full-route pass.

Complementary `check_boss_map_publication.py` passes all event snapshots;
10 tests include corrupted-cell rejection at every one of the eight events,
missing-event and truncated-snapshot rejection. This checks map publication,
not continuous scanout, CHR/attributes, arbitrary encounters or hardware.
All1080 captured PNGs agree with the untraced replay. Serialized payloads
differ at136 offsets: A8–AF (audio capacitor charge) and1E0–25F (rendered audio
samples), per pinned core serialize.h; do not mask them or claim full observer
neutrality/audio equality. Input/game-memory timing fields show no differences
in that comparison, but PCM has not been captured for this pair. Parent missed
third Select remains a separate unresolved observation. No hardware interaction.

## Palette-window trial: secret return and fresh Shalamar qualification (#23/#24/#27)

Fresh `tmp/stream-palette-window-secret-01`, exact b09ec41a… candidate,
unchanged probe3042e275… and r454 runtime, completes7800 frames. Uses the
same one-time doorway position assistance and resource refill as the combined
control, not an ordinary player route. Secret09 begins1408, fight0A4189,
secret return7002, stage00 restoration7003, card7020, dungeon02 at7211.
The prior e8002aea… fight began4213 and dungeon returned7236: combat timing
differs and is not qualified as equivalent. Frame3600 CHR2048 bytes match
stock37400–37BFF and BG0=ff7f947e4a3d0000. Native terminal7800 capture reviewed:
colored terrain/sprites visible. Timer-spacing oracle passes4171 secret
intervals, maximum137528, zero over its unchanged1.5-period bound. Boundary
intervals remain in the report. No captured-PCM fidelity claim.

Fresh same-ROM native-dispatcher Shalamar fixtures (not traversed encounters):
`tmp/palette-window-boss-entry-01` settles frame103, while e8002aea… control
`tmp/combined-boss-entry-control-01` settles113. No retargeted savestate reuse.
Each replay captures1080 frames using Select120/240/420/540/720/840 held6,
without in-replay game-memory writes.

Trial `tmp/palette-window-shalamar-menus-01`: all three endpoint and four-frame
intermediate-hold checks pass. Map-readiness passes returns1/3 but FAILS
return2:34 source/selected-map differences at596 (first E4 frame). Frames591–595
match the source, while597/598 have143/217 differences. Reviewed595–597
screenshots show boss/terrain revealed without obvious stale menu art. Source
updates may already be starting a new animation generation; that is a
hypothesis, not a waived failure. No oracle exclusions added.

Parent `tmp/combined-shalamar-menus-control-01`: first two returns pass all
three checks, but third fails missing white endpoint/return. At780 its menu
flag remains0; at900/1080 it is1, unlike the trial's entered-and-exited menu.
Thus this is not a qualified full three-return control and the missing toggle
must remain visible. Neither route proves arbitrary-input/menu fidelity.
Next decisive evidence should bind the reveal map to the generation actually
published, and inspect the parent's missed Select; do not simply mask596 or
extend inputs until a nominal pass. No deployment or issue closure.

## Bounded palette publication repairs the new restart mismatch (#24)

Optional read-only palette tracing in `probe_gameover_restart.lua` identifies
three rejected mode3 writes at frame5992, cycle2, stage age50, bank13 PCs
71E8/71EA/71EC, LY0. Values29/00/00 target the exact three stale BG1 bytes.
The trace replay `tmp/ceiling-secret-hazard-palette-trace-01` retains the
failure; all captured PNGs agree with its same-ROM untraced control. The
inherited r532 router accepted any mode1 instant before a bank-switch/stack
return and four writes, without checking time remaining before visible scanout.

Experimental `build_palette_window_trial.py` changes only bank20's router
and checksum, leaving the four-byte writer and interrupt restoration intact.
VBlank admission now requires LY144..151; late VBlank acquires fresh HBlank.
It also rejects the LY0 interval at the end of line153. New candidate
`tmp/stream-palette-window-01/candidate.gb` SHA
b09ec41a42967b2fd0fc6e88a8358d5fbfe055dcfef12be89908cf65af7c0fe8.

Fresh traced `tmp/stream-palette-window-hazard-01` passes the unchanged
two-cycle hazard/restart oracle: 102 Game Over frames,482 title pairs and
stage selector/card/terrain checks. Stage-entry trace contains280 writes,
zero in mode3 (failing control280 writes,3 in mode3). Untraced replay
`tmp/stream-palette-window-hazard-unobserved-01` also passes; all867 captured
PNGs match the traced trial. Savestate container files differ, but all42 decoded
71680-byte serialized payloads match exactly. No PCM was captured, so this is
captured-image/state neutrality, not full audio neutrality. Four focused tests pass, including
the retained failing parent terrain and passing trial terrain. Native final
Stage1 capture reviewed. No audio, full-route or hardware qualification;
late-window waiting changes timing and needs those tradeoff checks. No claim
that this fixes all recorded Stage1 bands. Issue24 remains open.

## Combined restart qualification exposes hazard-route palette mismatch (#24/#23)

Fresh combined e8002aea… replay `tmp/stream-presentation-combined-gameover-01`
passes two accelerated-death cycles, 102 consecutive Game Over frames and
482 returned-title frame pairs, plus saved-game selector/card checks. Native
Game Over capture reviewed: intact glyphs with purple accent. This is local
emulator evidence, not hardware or natural-death qualification.

The stronger `tmp/stream-presentation-combined-hazard-gameover-01` route
FAILS unchanged terrain comparison at stage-after-2. It walks upward for1600
frames then accelerates death by setting HP0; save-present flag is also a
fixture. Do not call this movement-only natural death. The compared scene,
active flag, camera and room contexts match (02:01:00:0C:05). Read-only state
analysis localizes182 differing background pixels to x116–131/y32–47, the
upper pickup tile. BG1 palette bytes at deck offsets0D/0E/0F change from
29/00/00 to30/83/30; all2048 background attribute bytes agree. Native captures
show intact level terrain, not the prior mostly-black/missing-level symptom.
Whether this is stale palette state or legitimate phase variation is unresolved.

Fresh identical-route branch controls, same pinned r454 runtime/probe/oracles:

- `tmp/source07-hazard-gameover-control-01`, eebf3f19…: PASS.
- `tmp/ceiling-source07-hazard-control-01`, f7896dee…: PASS.
- `tmp/ceiling-secret-hazard-control-01`, 00f26298…: FAIL at stage-after-2.
- `tmp/ceiling-secret-fast-menu-hazard-control-01`, 04764550…: same failure.

This brackets the first failing tested branch to the secret copier composition,
before the fast menu and boss overlays. It does not prove the failing mechanism
or establish equivalence to the recorded persistent yellow/red bands. Preserve
all failures and the unchanged oracle; next trace BG1 publication and native
phase across the matching restart route before implementing any repair.
No MiSTer interaction, deployment, default promotion or issue closure.

## Experimental multi-fix composition and secret return (#14/#21/#23/#27/#33)

New checked-in `compose_stream_presentation_trial.py` rebuilds the existing
ceiling combined-emitter, bank6 row-yield secret copier, and fast staged menu
from exact source07. It then applies independently rebuilt boss VBlank and
trial10 boss-menu branches, rejecting any changed-byte preimage conflict.
Expanded banks are preserved; checksum is computed after composition. Three
tests pass for conflicts, expanded-bank preservation and exact rebuild.
This is an experimental composition of existing fixes, not default promotion.

Candidate `tmp/stream-presentation-combined-01/candidate.gb`, SHA
e8002aea7117e6416b546e39655d7c792959913af66c827c28223bf6b01b6c57.
Receipt records exact parents/builders and branch changed offsets. It retains
source07's CHR/BG0, Game Over, projectile and Continue fixes. No claim that
all player reports are resolved; issue27 audio remains unqualified.

Fresh cold7800-frame `tmp/stream-presentation-combined-secret-01` completes
using the documented position/resource assistance, pulsed fire and Select
2400/2520. No palette/graphics/cache writes. Current probe3042e275… differs
from previous771a59ce… by optional disabled observers, optional disabled menu
capture, and inactive miniboss-selection generalization; no claim of full
observer-neutrality from this inspection. Exact runtime remains r454 corrected
core, guarded launcher. Entry09 at1408, secret fight0A at4213, secret return09
at7026, stage00 restored7027, card7044, dungeon02 at7236. Previous composition
ended the fight7040 and returned to dungeon7251: changed combat timing is
retained, not presented as gameplay equivalence.

At3600 all2048 secret CHR bytes match original bank13:7400–7BFF and BG0 is
ff7f947e4a3d0000. Native terminal7800 image reviewed: colored dungeon terrain
and sprites visible; not an all-cell color or natural traversal oracle.
Recorded persistent yellow/red bands remain unproven on this assisted route.
Boss menus, restart lifecycle, art/priority and native PCM need fresh combined
qualification; no deployment, issue closure or readiness claim.

## First-return APU trace is neutral and isolates small timing shifts (#27)

Added optional read-only `--trace-apu` to the roundtrip runner/probe. It logs
FF10–FF3F writes during frames240–320 using the core's `currentCycle()` global
timing clock. Fresh sequential trial08/trial10 captures are retained as
`tmp/crystal-menu-apu-trace-{08,10}` and
`/mnt/data/tmp/penta-crystal-menu-apu-{08,10}`. Both complete1080 requested
frames. For each exact ROM separately, the full native PCM, video, serialized
states and input/sample timeline are byte-identical to its untraced08b/10b
capture. This establishes neutrality of the added Lua APU watcher with the
same native tap enabled, not an independent tap-versus-no-tap PCM proof.

Each trace has298 writes. All address/value pairs and their order agree.
83 rows differ in timing; per-corresponding-write global-clock deltas range
from-48 to+16, first at trace frame245 (FF20, cycle140085118 vs140085110).
No dropped or substituted APU writes observed within this window. This is
not a whole-route command comparison: frame-sampled APU registers diverge
later at765, after the menu-return gameplay timing has diverged. Full PCM
strict guard remains FAIL; neither the equal command sequence nor small
cycle shifts are substituted for audible-fidelity qualification. Ten audio
tests pass including retained audio rejection and this diagnostic trace
description. No processes left running; no hardware/deployment changes.

## Native audio capture exposes unqualified timing differences (#27)

Extended the checked-in roundtrip runner with optional native tap/large-scratch
output and synchronous capture finalization. Built tap
`tmp/boss-menu-native-tap-10.so` from `native_av_tap.c` using the pinned
r454 core's CMake compile definitions/include paths. Tap SHA
337c75dfaa448939c5089ef60ad78fb854ce46b883eaaf7a35669b258590f2d7,
source3500673397012d30c8e2ecc50315d72250e140297f39a78976ebfb3c3bf57bb2.
Native files include one pre-load frame plus1080 replay frames, all retained;
no PCM trimming, alignment, normalization or resampling.

Initial captures `/mnt/data/tmp/penta-crystal-menu-native-{08,10}` were silent
through the transitions. They FAIL qualification, not evidence of game music
loss. Pinned Qt `CoreController::overrideMute(false)` assigns mute from
`fastForwardMute >= 0`, including the user's value0. Explicit capture-only
options now use fastForwardMute=-1, mute=0, volume/fastForwardVolume=256 and
disable focus/minimize muting. User configuration is unchanged. New captures
`/mnt/data/tmp/penta-crystal-menu-native-{08b,10b}` have sustained activity.
All1080 PNGs from each new capture equal its corresponding untapped replay;
this establishes video neutrality only, not PCM observer neutrality.

Each new full PCM has2,372,288 stereo frames at131072Hz. Strict unmodified
audio guard `tmp/crystal-menu-native-pair-08b-10b` FAILS: changed silent-block
and digital-silence boundaries, and maximum sample step19620 versus19616.
RMS ratio0.997849951 passes the2% level guard; neither capture clips.
960940 sample frames differ, first546877 (during the first return fade), last
2372287. Full differences retained. No listening/perceptual-equivalence claim;
these metrics do not establish an audible pop or an actual music dropout.
Nine audio tests pass including a retained test requiring this pair to FAIL.
Next: characterize Timer/APU timing around that first divergence and qualify
the recorder's audio neutrality. Visual trial10 remains experimental, with
audio acceptance explicitly unmet. No hardware or deployment changes.

## Selective VBlank defer fixes captured Crystal fade hold (#27, trial10)

Trial10 adds a private white-fade acquisition helper: save AF/IE on the native
stack, clear only IE bit0 while waiting (Timer/STAT bits unchanged), acquire
LY144–148 under DI, restore exact saved IE before returning to the64-byte
mapped palette writer. That unrolled writer remains under DI, restores SVBK1
before stack access, and reenables interrupts afterward. Late acquisition
retries instead of writing into visible scanlines. Existing full-deck backup
and black/restore publication paths retain trial09's window implementation.
The64-byte body is32 repetitions of52 CPU clocks plus setup/teardown, below
five normal-speed scanlines; actual write-cycle/IRQ bounds still need tracing.

Candidate75d5bcd5b79e8e0c060c60740ca663a132ecc438ae23e63eecb25153df19f9bf;
builder0cd7eadf3d492629b614341f748a0337c826d5a1a0bce701eb3a8cf14c84b753.
Fresh exact-ROM synthetic entries pass for Shalamar and Crystal in
`tmp/boss-menu-clean-entry-10`. Banks13/23 remain byte-identical to recognized
parent; exact descendant registered for strict relocated-table verification.
Separate sequential1080-frame captures `tmp/crystal-menu-roundtrips-10` and
`tmp/shalamar-menu-roundtrips-10` complete in3.673s and4.094s respectively.
All six return cycles pass endpoint concealment, four-frame intermediate
white-fade cadence and return-map readiness. Trial08 Crystal's five-frame
negative control remains rejected. Native Crystal595 and Shalamar780/920
images reviewed; menu intact and Shalamar returns with cyan body.

Saved128-byte palette decks and menu/cache flags checked inside/after each
cycle. An initial test incorrectly demanded the pre-entry and settled menu IE
match; native code already changes IE4/7 in trial08. Those same sampled frames
match trial08 exactly in trial10. The corrected test makes only that sampled
comparison, not an exact interrupt-restoration claim. All1080 snapshots per
boss retain Timer's IE bit. Suite30 passed,28 subtests passed in9.37s.
Artifact-dependent tests skip without retained local captures.

Native PCM, interrupt service timing, other bosses, credits fallback,
interrupted/death paths, black intermediate fades and the broader recorded
scene-damage sequence remain unqualified. This is an experimental narrow
fix, not a release/default promotion. No hardware touched or deployment.

## Crystal control and failed earlier-acquisition experiment (#27, trial09)

Fresh original-ROM Crystal entry `tmp/crystal-stock-menu-entry-01` and1080-frame
`tmp/crystal-stock-menu-roundtrips-01` pass all three intermediate four-frame
hold checks. This rules out that behavior in this particular original replay,
not all native phases. Trial09 changes only trial08 byte51042 (LY threshold143
to142) and checksum byte14F. ROM SHA
`06e0b6552cbc0517ed9a2fd3611dec4e08c765c20c53c538aa75b3e937d54d35`;
builder SHA20cdc911db49ffcfbc52a26fa5d7785335baeff6f30597e5ea81beed351332c8.
Fresh entries for Shalamar/Crystal pass in `tmp/boss-menu-clean-entry-09`.
Only Crystal replay was run: `tmp/crystal-menu-roundtrips-09` retains the same
five-frame BGP90 hold594–598. Endpoint and return-map checks still pass.
Earlier acquisition did not solve the symptom; do not promote this trial.

Read-only breakpoints in `tmp/crystal-menu-window-trace-09/window.tsv` narrow
the cause. Trace callback frame labels precede captured frame numbers by one.
At trace596 the final map window call4C08 occurs LY151; Timer vector0050 then
fires atLY140 while returning to the acquisition loop5041. Next trace597
VBlank vector0040 runs atLY144, with5041 still the interrupted return PC.
Only afterward does the publisher reach DI5049 atLY142 and return5056 at
the following LY144 (trace598). Thus the earlier threshold still loses the
window across interrupt service. All1080 traced PNGs equal unobserved trial09
byte-for-byte: video neutrality only; audio/state neutrality unproven.
Next design must retain Timer service while preventing VBlank from consuming
the publication window, with bounded write time and explicit IE restoration.
No additional boss campaign, hardware action or release claim.

## Crystal expansion exposes remaining fade timing failure (#27/#30)

Trial08 exact ROM f02af88218fb6ae2fa12f7548549e9a5250c0bbb20cea5a8d2e77443ddad9379
initially failed fresh Crystal entry in `tmp/crystal-menu-fades-clean-entry-08`:
the oracle selected obsolete bank13 data (121/256 mismatches). Full banks13/23
equal the recognized4f5a parent; loader and dispatcher equal independent
builders, and captured C600 equals the independent Crystal table. Under open
#30, registered this exact authenticated descendant without weakening table
equality. Fresh rerun `tmp/crystal-menu-fades-clean-entry-08b` passes, frame137,
settle91. Storage tests:5 passed and28 subtests passed. Failed entry retained.

`tmp/crystal-menu-roundtrips-08` captures1080 frames using the same six Select
presses as Shalamar, without gameplay-memory writes. All three black/white
endpoint and return-map-readiness checks pass; palette deck restores exactly
at180/320/480/620/780/920, menu flag1 inside and0 after, cache flag1.
However the second return FAILS the four-frame intermediate hold gate:
BGP90 remains for five frames594–598. First and third returns pass. This is
not a full passing qualification. A retained regression test ensures the
oracle rejects this real capture. Native frame320 arena and780 menu reviewed;
no claim of pixel equality to a stock Crystal control. Need that control to
distinguish native phase behavior from the private fade's timing change.
No audio, hardware or natural-route qualification; no promotion/deployment.

## Three successive Shalamar menu round trips (#27, trial08)

The checked-in `replay_boss_menu_roundtrips.py` and
`probe_boss_menu_roundtrips.lua` captured 1080 native frames/states in
`tmp/shalamar-menu-roundtrips-08`, using exact trial08 ROM
`f02af88218fb6ae2fa12f7548549e9a5250c0bbb20cea5a8d2e77443ddad9379`
and its fresh synthetic-dispatch boss entry state. Select was held six frames
at120/240/420/540/720/840; no game-memory writes or health assistance.
The completion receipt records4.091 seconds replay wall time, completed=true,
and audio_captured=false. No extra shutdown frames; subsequent read-only
process check found no mGBA processes. Launch/completion receipts pin the
ROM/state/probe/runner/runtime, but do not establish full transitive dependency
qualification or natural-route equivalence.

All1080 endpoint observations pass. Explicit adjacent windows1–419,420–719,
720–1080 each pass endpoint, four-frame intermediate white-fade cadence, and
source-to-selected-map readiness during return reveal. Reveals begin288/588/888
and reachE4 at296/596/896. White plateaus last31 frames each; the previously
recorded one-frame publication cost remains, not silently aligned away.

Settled menu windows180–239,480–539,780–839 have exact original576-byte C1A0
source, original visible20x18 tile IDs with zero scroll, saved128-byte palette
deck, FFE4=1 and DCFD=1. Third-menu LCDC differs (E3 versusAB in first two);
its selected full1024-byte map has431 differences from the original control,
all outside the visible20x18 region. Do not claim full-map equality. Native
frame480 and780 PNGs were visually reviewed: intact heading, black background,
and medical HUD. Health differs through ordinary play. At320/620/920 the
menu flag is0, cache flag1, and the pre-entry palette deck is restored.

Focused suite:22 passed in6.51 seconds, including three retained-roundtrip
cases and earlier broken controls. Artifact-dependent cases skip when local
captures are unavailable; this is not a portable full integration suite.
Still no audio, other-boss, interrupted-entry/death, credits-fallback, or
hardware qualification. The recorded persistent gray/red/yellow corruption
after earlier scene damage remains unresolved. No promotion or deployment.

## Early menu ownership prevents Shalamar checker corruption (#27, trial08)

Trial07's settled menu source C1A0 contains156 extra tile1 cells relative to the
original, and its9C00 tilemap agrees with that wrong source. A read-only range
watch in `tmp/shalamar-menu-writer-trace-07/menu-writers.tsv` identifies156
writes of1 at bank20:6101 during frame164. The native clear writes0 correctly;
this later writer is the gameplay Shalamar staging-mask/checker sanitizer.
FFE4 remains0 through construction (including164), becoming1 only before the
settled menu. All600 trace PNGs equal unobserved trial07 PNGs byte-for-byte;
this establishes video neutrality only, not audio/state neutrality.

Trial08 sets native menu ownership FFE4=1 in the private black-entry wrapper
before construction. The menu's own existing close path still clears it.
This keeps the source out of the gameplay sanitizer without replacing menu
content or changing the sanitizer's gameplay rule. Candidate
`f02af88218fb6ae2fa12f7548549e9a5250c0bbb20cea5a8d2e77443ddad9379`, builder
`db0154aacbfb61a339f01d0d8a287c74f391d5bc284a851e1ad6c21b68ef9d1b`.
Fresh exact-ROM synthetic entry and600-frame Select replay are retained under
`tmp/shalamar-menu-fades-clean-entry-08` and `tmp/shalamar-menu-fades-replay-08`.
Both guarded commands exit0. Endpoint, white-cadence and return-map-readiness
reports all PASS. Native frame180 was visually reviewed: clean black menu
background, cyan heading and intact medical HUD; frame295 shows intact boss
during return fade. At180/200/239 both576-byte source and1024-byte9C00 map are
byte-identical to the original control. Retained regression tests extend this
layout comparison to every settled frame180–239, with trial07's156 differences
as the negative control. This does not compare intended CGB colors to DMG RGB.

Still experimental: early ownership must be qualified on other bosses and
menu routes, including interrupted entry/death; black intermediate fades,
entry latency, audio, bank7 ownership and the broader recorded corruption
remain open. No promotion, deployment or issue closure.

## Boss return map refreshed before reveal (#27, trial07)

Read-only trial06 trace `tmp/shalamar-menu-map-trace-06/map-sites.tsv` records
0AB2 at274,0AB5 at277,3485 with destination9800 at277, then0AB8 in that same
frame without a copy-tail observation. FFE4=0 and DCFD=1. Normal gameplay later
reaches3485 at297 and copy/tail work at298–299. Banked breakpoints also captured
unrelated banks; interpret bank1-only events at42C3/42ED. All600 PNGs match the
unobserved trial06 replay byte-for-byte (video neutrality only, not audio proof).

Trial07 scopes a forced native publication to0AB5. It saves DCFD in experimental
SVBK7:DF80, clears it for the native4295 call, and restores it at the existing
private0AB8 scroll/fade wrapper. This selects the existing unconditional copy
path without changing normal gameplay cache decisions. Stack continuations
preserve native4295 ->0AB8 ordering. Candidate
`ac98c8e5f8d0088a190be68cc65ff62656a73423bea9a0a2d9f5c1283a08c203`, builder
`498cb83de7a7a9456abfc3c1f04c7f375a895f25a7a08aed25ad0f268df8fe80`.
Fresh entry/replay in `tmp/shalamar-menu-fades-clean-entry-07` and
`tmp/shalamar-menu-fades-replay-07`; guarded commands exit0. No deployment.

The reviewed white-stages.png now reveals an intact cyan Shalamar rather than
scrambled tiles. New return-map-readiness.json compares all576 source C1A0 cells
to the LCDC-selected tilemap throughout the intermediate reveal and its first
E4 frame: original PASS, trial06 FAIL556 mismatches in each frame287–295,
trial07 PASS (frames288–296). Black/white endpoints and four-frame intermediate
holds also PASS. White plateau is31 frames versus30 in trial06/original: retain
this one-frame refresh cost, do not claim exact transition timing. DCFD reads1
again at280/286/295/301/320/600. Fourteen focused tests pass.

Scope remains a single synthetic-entry boss/menu replay. Tilemap equality is
not a CHR/attribute/OAM/audio oracle. The menu itself still shows repeated
background motifs absent from the original control; black intermediate fades,
cache ownership across other callers, repeated round trips, edited palettes,
bank7 allocation and persistent recorded corruption remain unresolved. Issue27
stays open. This trial fixes the observed local scrambled return reveal only.

## White-return cadence corrected; intermediate tile corruption confirmed (#27)

Trial05's white-return intermediate register holds were five frames, versus
four in the original control. Waiting four native ticks and then acquiring
the next VBlank introduced the extra tick. Trial06 waits three completed ticks
and publishes at the fourth. Candidate
`eef676e76d23d1d25c303308f6e5c013e6f8bb52580f7fa9a0b67f61c90aae49`, builder
`d80501903c81431788e413034b3f7272ef683dc716109e00fa7c1354330a4c3a`.
Fresh exact-ROM entry and600-frame replay: `tmp/shalamar-menu-fades-clean-entry-06`
and `tmp/shalamar-menu-fades-replay-06`; both guarded commands exit0.
Unchanged black/white endpoint gate still PASS. A new cadence check retains
every BGP run after frame240 and rejects missing sequences or intermediate
holds other than four frames. Stock PASS, reported parent FAIL, trial05 FAIL,
trial06 PASS; eleven focused tests pass. The trial06 register runs are90 at
249–252,40 at253–256,00 at257–286,40 at287–290,90 at291–294,E4 from295,
matching this original control's white-return boundaries without retiming
the evidence. This is not an overall native-speed or audio equivalence claim.
All64 BG CRAM bytes match the saved-deck remapping for every frame249–295;
the full128-byte BG/OBJ deck matches pre-menu at180/239/320/600.

Visual review contradicts a complete transition fix. Compared native-size
pictures243/249/253/257/271/287/291/295/301 in retained nearest-neighbor
`white-stages.png` sheets (stock and trial06 folders). The original reveals an
intact boss at287/291/295. Trial06 reveals scrambled tiles at these frames,
then an intact cyan boss at301. Candidate VRAM0:9800 map hash remains
`e7541fb7ee5b…` at239/280/286/295/301; the original switches from
`4ff788434cf9…` at239 to `58221922f158…` by280. Candidate attribute bytes at
9800 contain only0/1/4 at these snapshots, not alternate tile-bank flags.
Scroll positions differ between independent entries and LCDC selects different
maps over this transition; these hashes alone do not identify the faulty writer.
Next investigation: native map preparation and LCDC map selection before
reveal. Do not extend the endpoint PASS to art correctness or close issue27.

## Atomic menu handoff and white-return endpoint pass (#27, experimental)

Trial04 separates read-only palette backup (before native fade entry) from
single-VBlank publication. Its candidate
`dc918405c88a94cff38c14612399436f89dda603dff8c016b3d473e341038469`
reaches full black at frames141–168 with no settled black failures. The same
600-frame replay still fails for the missing white endpoint. Live128-byte
BG/OBJ deck matches frame120 at180/239/300/600. Evidence retained in
`tmp/shalamar-black-menu-04`; entry freshly generated for this exact ROM.

Trial05 adds private boss-menu white fade-out/in handling at0A9F/0AB8.
It retains native four-counter waits and scroll/LCDC setup, maps the saved
BG deck through E4/90/40/00 and00/40/90/E4, and publishes each complete deck
in one VBlank. A synthetic stack continuation returns through native2E12
arena setup and then the original0AA2 caller. No global fade hook is changed.
Candidate `66e228ba30ad18fed3d92ffcf2a9502c9a78ef3073312a17ce748e11342d2dd5`;
builder `d0fe77e73f29fc563bd96552c4a956270bd83a7bf864c19f3c27e40610881858`.
Fresh entry: `tmp/shalamar-menu-fades-clean-entry-05`, settles frame124.
Fresh replay: `tmp/shalamar-menu-fades-replay-05`, Select120..125/240..245,
600 requested PNG/state pairs, extra shutdown callbacks retained. Both guarded
commands exit0. Unchanged endpoint checker PASS:28 settled black frames141–168
and30 settled white frames262–291; original stock PASS and reported parent FAIL
remain retained negative/positive controls. Exact128-byte live BG/OBJ deck is
restored at180/239/320/600. The reviewed20-picture contact sheet shows black,
menu, white and resumed cyan gameplay. It also shows a partially revealed
arena during the intermediate return fade; endpoint PASS is not a complete
intermediate-picture oracle.

This does not qualify native timing: backup adds latency and each publication
defers VBlank/Timer service. Original stock and candidate entry phases differ.
Black intermediate fade is still unchanged; private credits fallback gains
dispatch cycles. Audio, all-scene bank7 ownership, repeated transitions, edited
palettes and recorded persistent corruption remain unverified. No deployment,
promotion or issue closure. A retained-replay regression checks both endpoints
and exact deck restoration; it skips when these ignored artifacts are absent.

## Shalamar menu black-entry trial: rejected first run, partial improvement (#27)

Fresh trial02 (`6853a1f5ed6ca548350347a358a8903591dedc0fe7aac56c45da74662cf3b702`)
failed its 600-frame Select replay in `tmp/shalamar-black-menu-02`:
466 nonblack settled BGP=FF frames and a missing white endpoint. The contact
sheet shows prolonged partial palette changes and broken transition graphics.
Retained states place the CPU in the early-VBlank wait for many frames; the
foreground IME-enabled wait competes with the native VBlank handler. Its
32-byte batch also lacked adequate margin for late entry. Do not deploy it.

Trial03 changes only acquisition/batch timing: acquire scanline143, disable
interrupts and recheck before waiting for144, then transfer16 palette bytes.
Candidate `43982c2095706454bb480d7fdc6b7efb3761e28d32cad69c03810da87d617260`,
builder `c5e0a9adf0d1e4b81235e6f2a3b4b5ab9236685dae3d60235a00b73614cddd9d`.
Fresh synthetic native-boss entry settles at frame124, followed by the same
600-frame Select120/240 replay, without probe game-memory writes. Evidence:
`tmp/shalamar-black-clean-entry-03`, `tmp/shalamar-black-menu-03` (PNG/states,
contact sheet, immutable fade-endpoints.json). Both guarded commands exit0.
The transition now reaches a black screen and the menu, then resumes a cyan
boss. The endpoint gate still FAILS: 11 nonblack settled BGP=FF frames plus
the unchanged missing white endpoint. Entry/restore batches visibly expose
intermediate colors; the return still exposes rebuilding graphics. No gate
thresholds or input timing were changed to accept this trial.

This is partial offline improvement, not a fix of the recorded persistent
arena corruption, full native fade fidelity, cadence, audio, or all-scene RAM
ownership. It remains an experimental branch using SVBK7:DF00-DF7F. No default
ROM promotion or hardware access. Next change must address visible batch
boundaries and the native white return, not merely relabel the endpoints.

## Continuous Gargoyle tear reproduction (#21)

Fresh `tmp/gargoyle-tear-native-01` runs the reported4f5a67b8… build for1800
cold frames with the previously documented native-spawn/resource assistance
and Select1350/1470 round trip. Corrected-latch core, probe9d9b737b… and
native tap337c75df… capture every frame/state. No ROM edits or hardware access.
Raw artifacts `/mnt/data/tmp/penta-gargoyle-tear-av-01/`: video SHA256
`4d436e5f4d0711a60be1c13deee15919d35f9049dcf3892148c5081aa712ea4f`,
states `50dd500488efe190fbfa4d677a8653a799b7b93dfe39e244ce2dc71eb9e4a10a`.
Finalizer confirms1800 frames and3956064 native stereo samples.

Reviewed consecutive native frames844..847 (one-based), retained as nearest-
neighbor strip `frames-844-847.png`. Frame845 visibly separates/displaces the
lower Gargoyle section;846 restores a coherent silhouette. The matching
frame845 state has all16 boss tiles30..3F, but their inferred4x4-grid origins
split between raw OAM(y32,x72) and(y32,x64). Other mixed-position samples
include835,855,957,1038,1159,1210,1495,1526,1536,1646,1756. These are candidate
events, not all individually visually verified. Some legitimate animation
poses contain blank tiles or nonsequential tile IDs: a simple tile-range count
is not a valid missing-piece oracle. The old offline silhouette checker covers
Troop/Penta, not this Gargoyle encounter.

This establishes a local visible tear on the reported build before its menu
round trip, not the exact recorded hardware moment or a menu-induced cause.
Next: original-game control and DMA/emitter phase tracing, then a rendered
coherence regression with a failing control. Issue21 remains open/unfixed.

### Original control and VBlank partial-shadow finding

Fresh1800-frame `gargoyle-original-native-01` uses the same assistance/inputs
on original2f32570c…; native artifacts under `/mnt/data/tmp/penta-gargoyle-original-av-01/`.
States SHA256 `1bb9aefb404d1cf1501a0d7da884975865bf160970c8340c5f2d8363cd14ffaa`;
video `1f84ea6ad2b56c0582ad9535ec05cc088b3cc20401b561dfc1ca20b04ee0aa6e`.
Reviewed819..822 strip shows a comparable transient split at820 in stock.
For FFBF1, stock has1053 full-visible coherent4x4-position samples,20 mixed-
position samples and153 not-fully-visible samples; reportedDX has1049/12/165.
Do not claim DX uniquely introduced or worsened the tear from these different
encounter timelines. Also do not close21: coherent animation remains the target.

Fresh900-frame `gargoyle-dma-trace-01` observes VBlank entry0040 over830..860,
reading native shadowC110..C14F, returnPC and registers without writes beyond
the documented spawn/resources. Probe SHA256
`a2fd9d684e5ca6718b69f53d3cb7bbbc0a75d30abec7a1a4cb5c795ae29b1d50`.
At callback frame844 (preceding delivered frame845), VBlank catches the same
two shadow origins(y32,x72)/(y32,x64), interruptedPC09B5, DE=C145,C=0B.
At834, analogous mixed shadow originsx88/x80 occur atPC09B7,DE=C143,C=0E.
The retained frame845 hardware OAM uses DMA sourceC1 and matches this split.
This connects the visible defect to partially updated native shadow data at
VBlank, rather than a palette-only artifact. Next source investigation: the
09B5/09B7 update path and boss-wide publication boundary. No fix implemented.

### Boss publication atomic trial: improvement, not a completed fix

The follow-up caller trace (`tmp/gargoyle-dma-caller-01`) identifies return
2BD9 from the interrupted memcpy, i.e. the boss's CALL at 2BD6. Experimental
`build_boss_shadow_atomic.py` folds DE=C100 plus16 into DE=C110 and protects
only the 64-byte C010-to-C110 copy with DI/EI. No RAM or ROM cave is added.
The interrupt-entry contract and timing/audio tradeoffs still need validation.

Candidate `19d042860a71813acbfeab049d9e7c59a94d4ed0c3296aa17872618374dcb5d0`
in `tmp/boss-shadow-atomic-trial-01` derives from reported4f5a, not the latest
composed source candidate. Fresh `gargoyle-atomic-native-01` completed1800
frames, status0, same assisted spawn and menu inputs. Native artifacts:
`/mnt/data/tmp/penta-gargoyle-atomic-av-01/`; states SHA256
`7c17a7eaa44be42de1f73a04404d45a7f54231c687278288ce96dc9b2490e51b`,
video `780d536073df1a70629f6ce4866beb10b6b0d5d85b8e7331c3f3fee6290f51c6`,
WAV `921be692937baa9d0d916a3c929e0fd204c684c8d2e6f706835002a9231a98e7`.
Finalized3956064 stereo samples at131072Hz, without normalization or trimming.
This is capture completeness, not acoustic acceptance.

The new `check_gargoyle_geometry.py` retains every mixed-frame index and
not-fully-visible sample. Reported parent:1049 coherent,12 split,165 censored;
trial:1060 coherent,1 split,165 censored. Both correctly FAIL. The trial's
remaining split is frame855, visibly confirmed in the854..856 native-frame
strip: one upper section is displaced. Synthetic one-piece mutations, absent
boss, censored-only evidence and truncated capture tests reject false success.

Fresh900-frame `gargoyle-atomic-dma-01` (status0; probe e45f078de2ed3854…)
places VBlank preceding frame855 at WRAM emitter DA58, DE=C02C, caller2BB0.
C110 shadow is coherent at VBlank entry, unlike the earlier interrupted-copy
failures. This narrows the remaining investigation to publication during boss
construction/the interrupt path; it does not yet establish which later copy
changes hardware OAM. Do not protect the entire generic emitter blindly or
declare the race fixed. No promotion, deployment, issue closure, or hardware
interaction occurred. Issue21 remains open.

### Remaining tear: alternating DMA reads the construction buffer

Fresh `gargoyle-atomic-dma-source-01` completed900 frames with status0 on
the same19d04286… trial. Probe SHA256
`f8404ff2f6697b9456806ef44c9d3f88a510cb79e93dc6cd7e09b565c2abda3e`
adds a read-only breakpoint at FF89, the installed HRAM routine's actual
`LDH [FF46],A` instruction. Source trace SHA256
`e9b085538660284f1e27026f7cf1d8ac37759562d89851be0c819cd35624a751`.
It reads all64 boss bytes from the selected page immediately before DMA.
Callback853 selects C1 with coherent origin(y32,x56);854 selects C0 with
mixed origins(y32,x48)/(y32,x56);855 selects C1 with coherent(y32,x48).
This matches the already visually reviewed delivered frame855 defect.

Installed FF80 routine increments FFCB, masks it to1, stores it and adds C0
to select alternating C0/C1 pages. Thus C110 coherence alone cannot prevent
the construction buffer C010 from being displayed partially built. The
remaining defect is now linked to actual selected DMA source, not merely
inferred from VBlank entry. Next fix must preserve complete boss geometry on
both selected pages without disabling native sprite alternation, losing
other sprites, or slowing gameplay/audio. Whole-emitter interrupt blocking
would need explicit timing qualification; the copy-only trial is incomplete.

### VBlank-only publication guard: symptom pass, audio guard failure

`build_boss_vblank_guard.py` saves IE on the stack, masks only VBlank bit0,
and restores IE after the full16-piece construction and64-byte copy. Timer
and STAT bits remain unchanged; per-entry emitter EI remains intact. Native
C0/C1 alternation is unchanged. Immediate pointer setup saves enough bytes
for this within fixed2B91..2BD9, without new RAM or a cave. Return AF is
recreated as A=10/F=0 after restoring IE. Broader caller/interrupt contracts
remain to be dynamically checked.

First trial4d7ba5f… had an incorrect one-byte slice boundary in the retained
emitter body; both the four-call test and zero-visible-boss geometry check
rejected it. Artifacts remain in `gargoyle-vblank-guard-native-01` and native
capture directory ending `av-01`. It is rejected, not evidence of a fix.
Corrected slicing uses original CPU address boundaries; three builder tests
pass before the second launch.

Corrected candidate SHA256
`698ab8dd5ea722554f49e69076b8e6a85ab4ca49334654bb3e9c7a5754fe7d4f`
is retained in `tmp/boss-vblank-guard-trial-02` (parent reported4f5a).
Fresh `gargoyle-vblank-guard-native-02` completed1800 frames, exit0.
Native files `/mnt/data/tmp/penta-gargoyle-vblank-guard-av-02/`:
states `43ab109502051d75b5dbc1c98fd1633ebd42bb81c373c5dd118230b75c2bcc44`,
video `2bf8f8590a737a37593a6a1ea2c1e9408dfcddd986f3e6b1f9d78489ed79a7b3`.
Geometry:1061 coherent,0 mixed,165 not-fully-visible samples, versus the
reported parent's1049/12/165. Reviewed native854..856 strip shows intact
boss poses, including the previously torn frame855. This remains one assisted
Gargoyle route, not ordinary-input/all-boss acceptance.

Audio capture contains3956064 stereo samples at131072Hz. Unchanged full-route
`verify_native_audio_pair.py` reports FAIL (`tmp/gargoyle-vblank-audio-02.json`):
digital-silence intervals differ. RMS ratio1.00306049; same50ms silent blocks,
no added clipping or larger maximum sample discontinuity. First PCM difference
1629515, total1740297 changed sample frames. No trimming/normalization or
listening claim. Gameplay cadence, interrupt latency, exact audio change and
cross-boss behavior must be checked before promotion. No hardware touched.

### VBlank guard timing follow-up (not yet qualified)

Fresh sequential1800-frame `gargoyle-parent-timing-01` and
`gargoyle-guard-timing-01` both exit0. Probe SHA256
`03e70a7c5322959f0356e798ff6bffea55b9b4d358a8be1436791323bd972754`
observes main-loop016C, boss entry2B91, build-specific return and sound events.
Both have191 boss-entry events on exactly the same delivered-frame sequence,
2668 Timer entries, and36 sound-command events with identical event/frame/
command/active/caller sequence. Global maximum Timer gap262984 cycles is
unchanged; this does not establish that every individual gap is unchanged.

Paired boss calls preserve entry SP/IE and native return registers. Parent
durations25776..43080 cycles; guarded25488..40848 cycles. However guarded trace
has192 return events against191 entries: an unmatched return at frame1494,
cycle210218732, SP=DFFB/IE07. Retain this inconsistency rather than zip-shifting
events or dropping it. Main-loop entry counts238 versus237 also differ.
The next investigation must explain both before a no-gameplay-slowdown claim.
Trace hashes: parent boss `bef1ce30a7df997c22a649c94531d8c2e3eae014d06dbcac581eca55ffb98db4`,
guard boss `4484dd5af12f7dd2c2b530e7b54ac7065c392e060ee855d98b02a0e050ea6586`.

Full untouched native audio receipts show only two differing >=20ms digital-
silence intervals: parent[1833660,1841489) versus guard[1833660,1841476), and
parent[1868734,1878698) versus guard[1868734,1878699). That is13 samples shorter
and1 sample longer respectively at131072Hz; all other listed intervals match.
This characterizes the existing strict failure, not a relaxed PASS or proof
of perceptual equivalence. Broad PCM differences remain retained. No deployment.

### Extra return observation resolved as pre-instruction STAT interruption

Fresh1520-frame `gargoyle-guard-irq-return-01` exits0 on unchanged698ab8dd….
Read-only probe6e9328b5… observes interrupt vectors and the return site over
frames1488..1500. Trace SHA256
`6aee565eaac89ed2ccd3a5bfba35b9ed05928e1bf8420d707db8ac47d9319479`.
At frame1494 the exact event sequence is:

- cycle210218060: breakpoint2BD7, SP=DFFB, caller2842;
- cycle210218100: STAT vector0048, SP=DFF9, saved interrupted PC2BD7;
- cycle210218732: breakpoint2BD7 again, SP=DFFB, caller2842.

The second observation is therefore resumption of the same pending RET after
STAT, not a second completed boss call. Keep both raw events; a breakpoint
visit is not an executed-instruction count.

Fresh1800-frame `gargoyle-guard-caller-01` also exits0 and observes caller2842
once at cycle210218764 in that same frame, SP=DFFD, confirming a single
completed return there. Trace SHA256
`df115667acab94d19195997aa1d521bea14d956f4d326699aa790ef7806c2b9b`.
Across the full route this particular caller has190 observations vs191 boss
entries: coverage of other callers/initialization still needs checking before
using this single site as a global completion count. The original237/238
main-loop observation difference likewise is not yet a proven slowdown.
This resolves the specific frame1494 control-flow concern; it does not turn
the timing/audio qualification into a PASS. No ROM changes this follow-up.

### Frame-state guard and source07 integration trial

Direct unaligned comparison of all1800 delivered native states, reported4f5a
versus guarded698ab8dd, finds identical DC00..03 player world position,
DC85..8C boss-slot coordinates/state, FFBF boss identity and D880 scene on
every frame. Full DC00..BF comparison differs on40 frames: DC09 on39,
DC19 on1 (frame789:06 versus04), DC0B on1 (frame989:01 versus00).
These bytes are retained as unresolved state differences; this is not full
gameplay equivalence or a reason to silently exclude them.

Applied the same experimental builder to source07 eebf3f19…, yielding
`tmp/boss-vblank-source07-trial-01/candidate.gb`, SHA256
`66cc13cc95e04e0ea9b71118928dcbe64181c1d86135fe8ba8555d3ef5259aa2`.
This is a separate local trial, not a change to the default source chain.
Fresh `gargoyle-vblank-source07-native-01` completes1800 frames, exit0,
probe2ab95693…. Native capture `/mnt/data/tmp/penta-gargoyle-vblank-source07-av-01/`
has1061 coherent boss frames,0 split frames,165 not-fully-visible samples.
States SHA256 `50c778201e63bd9931d829888653180f301f552496cab4375d2f508703f7b056`.
Complete native video and PCM are byte-identical to guarded698ab8dd's replay:
video2bf8f859…; WAV77503ff3…;3956064 samples. Reviewed854..856 strip remains
visually intact. This establishes source07 composition for this narrow route,
not audio equivalence to its unpatched parent or coverage of other scenes.
Seven geometry tests pass, including pinned retained positive capture and
known-broken controls. No deployment, issue closure or readiness claim.

### Boundary comparison and main-loop count explanation

Fresh1800-frame parent/guard runs `gargoyle-{parent,guard}-boundary-01`
both exit0, probe dd22145d…. All192 bytes DC00..BF are identical at all191
boss-entry observations, on identical frames. This resolves the earlier
frame-sampled byte differences at this boss boundary, not globally.
Raw boundary trace hashes: parent
`dc5437be812b8bceefb8e6dab3c2500c5d26e738dd2b1172a11dc5f1f78cdcad`, guard
`edf334c1b113ac7e885e47b092651ce3894f9b4fa421c3ccf95cf147f4bbadc6`.
The comparison script retains every unaligned difference and unequal count.
DC09 is also ROM-bank tracking state (documented by the full mapper contract
in palette_publisher_story_guard_r533.md), not purely an actor property.

The parent's238 versus guard237 main-loop visits arise from a duplicate at
frame1739. Fresh1742-frame `gargoyle-parent-loop-irq-01`, exit0, observes:
016C at cycle244748824/SP=DFFF, then Timer vector0050 at244748864/SP=DFFD
with saved PC016C, then016C again at244751904/SP=DFFF. Thus this extra visit
is another pre-instruction interrupt, not an extra executed game update.
IRQ trace SHA256
`9fdf10d4d972dc1e2e384784371d9f311e5797753dec37174e1cf63d36de3c76`.
Keep all raw observations; any collapsed instruction-visit comparison is an
additional diagnostic, not a trimmed primary timeline or blanket fidelity pass.
The additional diagnostic pairs237 executed visits after removing only that
proven pre-interrupt visit from a derived comparison. Actor-block differences
then consist solely of DC09 on10 visits. Frame placement still differs for
some visits, so exact main-loop temporal equivalence is not established.
No hardware interaction or new ROM patch was needed for these findings.

### Movement/menu replay: additional tearing negative control

Fresh sequential2400-frame `gargoyle-patrol-{parent,guard}-01` runs both exit0,
source07 eebf3f19… versus patched66cc13cc…. Probe f950b0e2… uses existing
ENTRY_FLOOR_PATROL=1: alternating Left/Right100-frame holds after1200, with
Select1350/1470 overriding movement during the menu. Native boss spawn and
resource assistance remain enabled; this is not an ordinary unaided route.

Parent geometry:1633 coherent,18 split,175 not-fully-visible samples. Guard:
1651 coherent,0 split,175 not-fully-visible. Raw capture roots are
`/mnt/data/tmp/penta-gargoyle-patrol-{parent,guard}-av-01/`.
Parent states SHA256 `b20feb9db5c48c509e67256a7f78786576bd0853638035335365fc7fe3bfb51a`;
guard `ffec263d2a9e85137ae49eb4536ab2150d6d95c92597a1337a43e2c1bda2f4a7`.
Reviewed side-by-side native frame2130: parent boss has a displaced lower-right
section, guard silhouette is intact. Preserve all other mixed indices in raw
states; geometry checker reports them without removing off-screen counts.

Both captures finalize2400 frames and5272768 stereo samples. The unchanged
audio guard (`tmp/gargoyle-patrol-audio-01`) still FAILS exact digital-silence
interval equality, while level ratio0.99880109,50ms silent blocks, clipping
and maximum sample-step guards pass. Full2932696 changed sample frames are
retained; no resampling, normalization, waveform alignment or listening claim.
This expands local symptom evidence but is not final audio/hardware acceptance.

### Audio characterization and Game Over guard on source07 boss trial

Movement replay retains25 >=20ms digital-silence intervals in both builds.
Only four intervals differ: sample endpoint deltas[0,-13],[0,+1],[+1,0],
[+8,0]. This is additional characterization of the unchanged FAIL, not a new
threshold or perceptual PASS. Stationary sound traces retain exactly95 FF14,
95 FF19,273 FF1E,216 FF23 and4 FF26 writes with identical ordered values.
Their cycle deltas range from-1824 to+8128 (FF26 unchanged); the observed
APU subset is not all sound registers. Timer-event counts match2668, but38
sampled TIMA values differ and IRQ timing is not identical. Do not equate
unchanged commands with unchanged acoustics.

Fresh `boss-vblank-source07-gameover-01` on candidate66cc13cc… passes the
checked-in single-flight Game Over verifier with `--saved-game --sequence`.
Two complete Game Over/title/new-game cycles, HP-zero-per-life stimulus,
blank SRAM launch,102 consecutive Game Over frames and482 title frame pairs.
Verifier SHA256 `cf451c1a77db292cf150a455608c3ccc0d270e29002d5fff8a7000feca9d5173`;
probe `06b3b826c62190767a1da427788d84d2cdfe076d53ddca1d4f72870a167735dd`.
Scope excludes natural hazard damage, traversal, hardware and audio. This
protects the earlier restart fixes on the new local boss trial; no default
build promotion or deployment. Issue21 updated, left open.

### Shared miniboss path coverage investigation

Issue27 is a separate Shalamar arena-presentation report; do not treat the
Gargoyle OAM test as its acceptance. The arena gallery's historical-state
retargeting/rearm machinery also is not ordinary-route cross-boss evidence.

Extended the scratch native-spawn probe with bounded section selection
ENTRY_MINIBOSS_SECTION=0..5; default0 unchanged. Receipts now explicitly
record the selected DCB8 write rather than always claiming0. Fresh
`miniboss-section1-guard-01` completes1800 frames on66cc13cc…, but the final
state is still scene0A/FFBF1/descriptor3031323334: **Gargoyle again**, not
Spider coverage. Do not count this as a second boss passing. Probe SHA256
3042e27592bf4b3fdf44ce91d6b6cdf26bc3b80598d21b8a9d02f804f7f63fa3.
Static original-ROM inspection locates section-based descriptor selection at
0BED and section increments before loading at224C/28C9. Next cross-boss
recipe must verify the native descriptor actually selected, without forcing
FFBF or transplanting sprite graphics. No release candidate changed here.

### Spider shared-path replay and negative control

Read native table through FFAC/FFAD=4000, bank13 pointer4024: six5-byte
descriptors; zero-based entry2 is3031323334 (Gargoyle), entry5 is3536373839
(Spider). Setting section4 before the native increment selects Spider without
forcing FFBF or editing descriptors. Fresh sequential1800-frame
`spider-{guard,parent}-native-01` both exit0, FFBF2 active1239 frames.
Same spawn/resource assistance, Select1350/1470; guard additionally observes
boss entry/return without memory writes. Probe3042e275….

Source07 parent eebf3f19…:1057 coherent,16 split,166 not-fully-visible frames.
Guard66cc13cc…:1073 coherent,0 split,166 not-fully-visible. Shared4x4 emitter
layout is checked with explicit boss-id2; other IDs remain rejected. Eight
geometry tests pass. Parent is a real failing control for Spider, not only
Gargoyle. Reviewed frame900 side-by-side shows displaced Spider pieces on
parent, intact alignment on guard. This is sprite-position evidence, not a
claim that Spider palette or all animation tiles are correct.

Native artifacts `/mnt/data/tmp/penta-spider-{parent,guard}-av-01/` finalize
1800 frames and3956064 stereo samples each. Parent states SHA256
`c376bb4b1c792db862248e50e02d69c98687d0380dbdf85341114a097da62bd2`, guard
`8d3f7645874008cfc71ea8c9eb8f22cbdfb0791ce2616d83e742c6dd6c3e48d1`.
WAVs e8bba313… /655e3e5b… retained, not yet audio-qualified. No hardware
access, promotion or closure. Shalamar and other BG-based arenas are not
covered by these two miniboss routes.

### Issue27: recorded Shalamar symptom characterized

Reviewed retained recording sample `sample-02160.png` (36:00) and derived
`/mnt/data/tmp/penta-shalamar-review-20260928/34m-36m30.png` contact sheet.
The sheet starts at recording34:00; labels are relative to that seek, not
absolute recording time. Five-second sampling is diagnostic only and cannot
establish frame-level sprite tearing or transition timing.

At approximately35:50 and36:00, the boss has gray/white upper regions beside
cyan lower regions and yellow/red patches. The full36:00 sample shows a cyan
body, orange/red upper pieces and a green central patch. At36:05–36:15 the
`BOSS 01` screen has red/yellow patches in the heading. These observations
characterize the player's report as spatially inconsistent coloration across
both arena and interstitial presentation; exact intended per-part colors still
need a palette/source comparison. They do not prove missing geometry.

Yellow/red dungeon bands are already visible throughout34:00–35:40, before
the boss. That establishes preceding corruption in this recording, not a
causal dependency on secret return or a shared cause with the boss. Candidate
identity remains launch-provenance-only, not independently recoverable from
the video. No hardware touched, no fix or readiness claim.

Next discriminating check: compare clean-entry Shalamar on the reported
candidate against this observed pattern, then inspect attribute publication
and inherited palette state if clean entry differs. Existing synthetic boss
dispatcher fixtures are useful isolation tools, not proof of ordinary-route
transition correctness. The shared Gargoyle/Spider OAM guard does not cover
this BG arena.

### Issue27: clean-entry isolation on reported candidate

Fresh `tmp/shalamar-reported-clean-entry-01` uses exact reported4f5a67b8…
and checked-in single-flight generator, target0, patched CGB-latch runtime.
Generator180b44b59691494f41c166135237bddbc9c134024aea16a062aa6a90bab4d233,
probea970cf1ddd4bd81d29d818d10e86a0194cd108fd039e1319df549e0aa9ed9f3d.
Fresh cold Stage1 followed by synthetic stock-dispatcher entry settles at
frame124, scene0C; generator acceptance passes. Rendered checkpoint is cyan,
without the recorded gray upper-body region. State SHA256
0104f7e90cb57f85a62c407a623d0f2926cac8fe434762a1bb9a289d4564791c;
PNG c7fa06525e1240318b24e884181f2221ff666b8c2bffdfff6791fca8a3008b55.

Then `tmp/shalamar-reported-passive-01` reloads that exact same-ROM state and
runs600 frames, no input, health assistance, palette resets or game-memory
writes. Twenty unselected30-frame checkpoint PNGs/states retained. All20
pictures reviewed in contact.png: cyan boss body throughout sampled poses;
orange/red upper objects and green projectiles occur even on clean entry.
Therefore orange/red/green alone are NOT a valid corruption oracle. The
recording's gray body regions and contaminated BOSS heading remain the
discriminating symptoms. This does not exclude between-sample failures,
longer fights, pause effects, preceding traversal or hardware differences.
No audio evidence collected; no broad fidelity or fix claim.

Scratch probe0c292843d3c98bca4b42ccc0b1741b5f0a189376a3526f91d6e37e7a1f5b52a6,
runneracc000d7d9fd8ec4553f734745b46978d084398ea7718d0cd80bbb29f8456ceb.
Frame600 PNG c5942a676de7e8b4f9d66ab90a5ba67bbca8cf8488caee5085295e23a978e7db.
Both processes completed; read-only safety check reports no mGBA processes.
Next test should exercise pause/interstitial transition from this clean
checkpoint before attributing corruption to inherited secret-area state.

### Issue27: clean-entry Start and Select isolation

Fresh sequential `shalamar-reported-button{8,4}-01` replays use the same
reported4f5a ROM and same clean-entry checkpoint. Six-frame button holds at
120..125 and240..245, otherwise no input or game-memory writes. Requested600
frames; retained every-frame PNG/state. Start8 did not open the interstitial
in the inspected pictures; Select4 did. Frame180 Select shows cyan `BOSS 01`,
frame300 returns to cyan boss. A20-image diagnostic sheet additionally shows
garbled transitional tiles at frame151 and partial boss restoration at271.
Do not call this a clean transition or dismiss it without a stock comparison.
The recorded persistent gray-body/yellow-red-heading pattern was not
reproduced by this clean-entry Select trial's reviewed samples.

All complete captured states retain identical64-byte BG CRAM and C600 table
hash, scene0C. Thus no CRAM change in this trial explains the transitional
images; tile/attribute publication and native transition behavior need the
next comparison. This is not a full rendered-frame oracle or audio test.

Probe SHA2568c99c574dac2176d10d751e90c18374ad0eb6ccb2424d94198d63ff6782a2db3;
runnerafa9b36daf3c4ccd4241eba649bb8463be944b7e46849e4cb8fee2717b95d28a.
The marker-based parent exits after the probe's600-frame marker; callbacks
continued briefly: Start retained607 complete states, Select612 complete
states and incomplete terminal613. All requested600 are present; surplus and
partial tail are retained, explicitly listed in state-characterization-v2.json.
Do not describe these as exactly600-file captures. Read-only post-run process
check found no mGBA processes. No ROM modifications, deployment or closure.

### Issue27: original-ROM menu fade control

Fresh stock2f32570c… `shalamar-stock-clean-entry-01` settles frame89; same
single-flight generator/core, synthetic native dispatcher, not a DX-retargeted
state. `shalamar-stock-button4-01` uses the same Select holds120..125/240..245
and every-frame capture probe. Reviewed20-picture sheet shows black entry
fade, white return fade and intact monochrome boss afterward. DX's equivalent
review shows exposed scrambled tiles and partial boss reconstruction instead.
Checkpoints settle at different phases (stock89/DX124); no exact clock or
frame-equivalence claim is warranted.

Concrete state observations: stock151 has BGP=FF, BG0 all0000; stock271 has
BGP=00, BG0 all7FFF. DX151 has BGP=FF, unchanged colored BG CRAM and scrambled
tiles. DX271 has BGP=E4, unchanged CRAM and partial boss restoration. The
600-requested-frame raw corpus is retained, including any parent-shutdown
tail. This establishes missing visual concealment during this isolated DX
transition; it does not reproduce or explain the persistent recorded patches.

Source `build_native_dmg_fade_fixed_service` explicitly normalizes active-play
fade steps back to E4 unless a fade owner is set. `build_death_fade_helper`
provides a separate death-specific white CRAM path. Next implementation must
respect existing ownership and timing rather than enabling a global fade
rewrite that regresses gameplay flashes, Game Over or attract mode. Issue27
updated before any fix. No ROM changes or hardware access in this comparison.

### Issue27: failing rendered fade-endpoint regression

Added `check_boss_menu_fades.py` and five tests. Checker reads every requested
frame's PNG and serialized BGP, retains hashes/colors/frame indices, requires
both black and white endpoints, and rejects wrong-color/nonuniform endpoint
pictures. First endpoint frame is explicitly reported as transitional; stock
frame133 itself straddles the black change (two colors). No alignment, pixel
normalization, masking or deleted tail evidence is used. Scope is endpoint
concealment only, not complete intermediate fades, timing, sound or boss art.

Reused exact retained600-frame corpora: stock PASS; reported DX FAIL on all26
settled black-endpoint frames135..160 and missing white endpoint. Output
`fade-endpoints.json` in each replay directory retains all600 observations
plus surplus-state filenames. Five tests pass under `uv run --with pytest
--with pillow python -m pytest -q tests/test_boss_menu_fades.py`; system and
project venv lack pytest, so those initial attempts failed before collection.
Native boss-menu fade endpoints leave FFE4=0 in both builds. The settled menu
itself does set FFE4=1 (e.g. DX180/239), then clears it before the return fade.
A fix cannot rely solely on that flag to identify the transition interval.
No ROM patch yet; the real broken candidate is now a failing regression
control, and the original supplies a passing endpoint control.

### Issue27: fade call-site trace localizes both mechanisms

Fresh `shalamar-reported-fade-trace-02` runs the same Select replay with
read-only breakpoints at0A0F/0F5E/0F90/0FB3. At133,0A0F sees A=FF with stack
return0A8A: the unchanged fixed-ROM boss-menu path calls0A16 at0A87, which
requests black BGP/OBP without updating CGB CRAM. It then calls0C84 and rebuilds
the menu. FFE4 is clear during this entry interval, becomes1 in the settled
menu, and clears again before return; it is not an always-clear separate menu.

On exit,0F5E observes requested A=E4,90,40,00 at244,248,252,256, while stored
BGP remainsE4 after each DX RST08 service. Return stack includes2E12 and0AA2.
After rebuilding the arena,0F5E sees00,40,90,E4 at281,285,289,293, with caller
0ABB. Native menu branch0A72..0AB8 is byte-identical in reported and original
ROMs. Thus the return's missing white phase is concretely due to fade-step
normalization, while entry's missing black is a separate CRAM-mirroring gap.
A scoped transition service must handle both and restore the existing tuned
palette deck; simply removing the normalizer is insufficient in native CGB.

Failed observer setup `fade-trace-01` produced an empty buffered trace because
it used the unsupported register accessor; no causal claims use that file.
Trace02 uses readRegister and flushes every record. Both runs terminated;
the intervening read-only process check found no emulator running. No ROM
changes or qualified timing/audio claim from instrumented execution.

### Issue27: palette-service placement investigation

Inspected current reported ROM and source before allocating a fade service.
No fixed-bank0 run of ten or more zero/FF bytes exists; apparent empty palette
LUT entries cannot be used as code caves. Existing ending fade machinery
already solves bank-safe CRAM-before-BGP publication: bank1:4289 contains
`F5 3E14 CD6100`, landing bank20:428F=`F1 C32A74`; fixed09BE provides the
coherent FF99/MBC bank restore. The separate story trampoline starts428F in
bank1 and lands4295 in bank20. Existing credits dispatch and its cadence must
remain intact for original callers; a future menu dispatch needs exact full
return-address discrimination, not only a low-byte match.

The ending mirror is not directly reusable as the menu palette policy: its
uniform story rows/restore deck would discard distinct boss and user-edited
colors. The menu needs either an authenticated scene-specific source deck or
a separately justified live CRAM snapshot allocation. No unused WRAM region
was established in this investigation; do not infer one from zero snapshots.
Stack snapshots across the native menu require preserving all original return
addresses/POP behavior and bank1 mapping at every native call. This rules out
both blindly reusing the ending deck and unreviewed scratch RAM as shortcuts.
No experimental ROM emitted yet; the next patch can use the existing banked
entry architecture while preserving its earlier clients.

### Issue27: scoped live RAM ownership probe

The apparent SVBK6/7 ownership in `build_stage7_exact_triple_cache_r264.py`
belongs to a rejected experiment (`do_not_emulator_run=True`), not established
production allocation. Exact reported4f5a has no literal3E06E070/3E07E070
selectors; that scan alone does not exclude computed or indirect selection.

Fresh `shalamar-reported-ram-trace-01` observes every FF70 write and all
DF00-DFFF writes during the same600-frame clean-entry Select replay. Registered
watchpoints fail visibly on initialization errors (no pcall swallowing).
Observed81 writes selecting1 and50 selecting3; no bank7 selection or bank7
DF00-DFFF write. The range observer counts796740 bank1 and988 bank3 writes,
so its zero bank7 result is not an entirely inactive watchpoint. All600 native
PNG files are byte-identical to the uninstrumented Select replay. This is
picture neutrality only, not audio/input/state neutrality qualification.

This makes bank7 upper RAM a candidate for a **scoped experimental** backup,
not a proven all-scene allocation. Boot, other arenas, dungeon transitions,
Game Over and other writers still need ownership checks before promotion.
No ROM patch or memory writes were made by this observer.

## Source evidence

- Recording: `/home/struktured/Videos/2026-09-27 20-40-28.mkv`, resolving to
  `/mnt/data/Videos/2026-09-27 20-40-28.mkv`.
- SHA-256: `459facd00aed66b615cf93bb1873f20a2f203dfe3e7186786c63927b7b8da664`.
- Probed duration: 7716.955 seconds; size: 2226422999 bytes; video 1920×1080,
  60 fps. Penta footage occupies approximately the first 42 minutes;
  subsequent footage is a different game and is outside this investigation.
- Session launch ROM: `4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5`.
  This is deployment/launch provenance, not a hash derived from recorded pixels.
- Review samples: `/mnt/data/tmp/penta-stream-review-20260927/`.
  `secret-return.jpg` samples 22:00–32:30 at 30-second intervals. Samples
  locate candidate windows; they do not establish exact onset frames.
- Original recording remains untouched. Diagnostic samples are not substitutes
  for continuous footage or exact frame evidence.

## Visually inspected observations

- 24:00–30:00: secret-stage scenery includes white vertical strip tiles and
  scrambled-looking patterned regions. This corroborates #23's visual report.
- 28:30: boss/large actor and star-shaped objects are gray in the secret area.
  This does not by itself identify the earlier teleport-area pickup in #22.
- 30:30: normal dungeon scenery has returned, with conspicuous yellow/red
  regions along walls and adjoining floor tiles. Similar regions remain in
  the 31:00 and 32:00 samples, corroborating #26's persistent return corruption.
- Sampled images do not establish whether the monster-pause power-up is a
  cause, nor whether all palette and sprite reports share one cause.

## Reproduced doorway occlusion regression (#14)

`tmp/ceiling-stock-doorway-03` and `tmp/ceiling-dx-doorway-03` reproduce a
foreground-layering difference before the secret-stage transition. Both cold
boot, receive a one-shot position assist1240/1344 at frame1201, Down through
1212, then no input; health/resource assistance is explicit. At frame1216 both
are in scene02/stage00, world1240/1356, SCY/SCX=0C/08 and identical four OAM
quadrant positions. Stock hides Sara completely in the reviewed black16x16
overhang footprint; candidate7130c04a draws192 nonblack pixels there. Stock OAM
priority is set on all four quadrants; DX clears all four. This establishes a
real visual regression at this doorway, not a claim that it is the exact
archway from the player's earlier report. Movement frame timings differ despite
matching endpoints; collision and speed equivalence have not been proved.

New read-only gate `scripts/diagnostics/verify_doorway_occlusion.py` validates
ROM/state CRC, world/scene/camera, native OAM footprint, reviewed stock screenshot,
and all256 pixels of that opaque region. It rejects a blank-background shortcut.
Stock control passes; current DX fails with192 leaked pixels. It does not qualify
floor bleed, collision, other archways, audio, or speed. No ROM fix yet.

Stock bank1:50DF reads the map-block byte through each DC10..17 pointer and tests
FFA0 <= byte < FFA1; the observed Stage-1 bounds are86/8D. The flags are per-Sara
quadrant, not generic screen-edge flags. Stationary position injection alone
does not necessarily recompute them; movement was needed in this reproduction.
The existing FFC4 ownership conflict remains. Also, bytes118B..119F are now an
active publication shim, so restoring the full old1188 helper in place would
overwrite unrelated executable code. Any repair needs an audited placement and
must preserve that shim and the physical-map target while restoring occlusion.

## Star pickup investigation (#22)

The existing 19-form pickup atlas identifies a star-shaped Spiral pickup as
tiles8E/8F/9E/9F, selecting BG5. That is a candidate identity, not proof it is
the specific object in the player's report. A fresh cold boot with one-shot
position assistance to1252/824 at frame1201, then no input until1500, renders
this star gold/red on both reported build4f5a67b8 and current7130c04a.
Runs: `tmp/star-spiral-cold-control-02` and `tmp/star-spiral-cold-01`.
Both maps contain the four tiles at14/10 with attributes05/05/05/05. Live BG5
is `ff7fff031f000000` (white, gold, red, black). The entire screenshots match
SHA-256 `7176d0418b9d477e974dc992312eec5c612650372ec791acd2b0a7c395a8d219`.
Read-only analysis: `tmp/review_spiral_pickup.py`, including exact ROM/state
and executed-probe bindings. This is a nonreproducing control, not a fix.

Receipt correction: the first run incorrectly wrote observer_memory_writes=false;
its retained probe/environment explicitly show the position assistance. The
diagnostic runner now reports that assistance. Original evidence is preserved.
No graphics/palette/cache injection was used. Nearby-pad trials
`star-native-teleport-01` through03 did not establish a native teleport transition;
they cannot qualify transition behavior. Sampled recording galleries0–23min
did not positively identify the reported pickup. Later secret-area gray stars
remain separate observations, not substitutes for this report. Next requirement:
identify the actual recorded object/transition and reproduce its gray rendering.

## Verified coverage gap

### Native-entry reproduction and graphics-source fix (#23)

An exact-candidate cold boot reaches Stage 1. A one-shot position assist sets
DC00..03 to world coordinates 1240/1344, then Down+A for 120 frames crosses
the native secret-door rectangle. Health/resource refill is explicit. No
graphics, palette, scene, cache, or mapper state is injected. The game's own
transition reaches scene18/stage07, then scene09. This reproduces white bars
and scrambled secret scenery on the reported `4f5a67b8…` build.

The original ROM using the same assisted entry renders intact scenery.
Comparison identifies **2005 mismatching bytes of 2048** in VRAM 9000–97FF.
The intended bytes exactly match original ROM offsets 37400–37BFF. DX's
injected bank-13 code/tables occupy that original graphics source. The native
graphics loader at fixed 0CBB still selects bank13 and pages74–7F for tile
selectors40–4B, so it copies injected code as graphics. Unlike the earlier
artificial attribute experiment, this replay has no bank-selection bits set
in its attribute maps: that hypothesis does not explain this reproduction.

`scripts/diagnostics/build_secret_chr_restore.py` preserves the entire parent
ROM except the graphics-loader bank operand and required header/checksums.
It relocates the original bank13 into a new immutable graphics bank32 and
expands the existing MBC5 image to 1 MiB. The loader's instruction count,
page table and copy lengths remain unchanged. Existing bank13 runtime code
is untouched. Candidate:
`tmp/secret-chr-restore-01/candidate.gb`, SHA-256
`22b3909b5ef3653abb1a40d227c2f9f0d6d6a276010ca08299af1c688eb15e6c`.

New checked-in regression `verify_secret_chr_entry.py` performs three serial
cold-boot/native-entry replays (stock, known-broken parent, candidate), each
3600 frames. `tmp/secret-chr-regression-01/receipt.json` passes all eight
checks: stock/candidate exact CHR, broken control rejected, all entries complete,
unchanged Stage-1 screenshot, unchanged parent/candidate secret entry at frame
1410, and identical full main-loop hit timelines. The stock entry is frame1397;
no cross-ROM speed equality is claimed. Runs took 4.3–4.6 seconds each.
Five structural builder tests pass separately; these do not replace integration
coverage. A second run additionally pins all resolved shared libraries.

Visual inspection confirms restored panel geometry but still-wrong bright
background/material colors. This is **geometry-only**, not a complete fix for
the secret scene. Palette semantics, return corruption, native audio, unassisted
route and hardware acceptance remain unqualified. No deployment or issue closure.

### Secret-stage out-of-bounds BG0 source (#23)

The six-byte normal-stage source table at bank13:7BAC covers FFBA=1..6.
Secret-stage FFBA=7 instead reads the next routine's C5 opcode and copies
unaligned bytes at 68C5 into BG0. The geometry-only replay's live BG0 is
`070607ff7f947eff`, exactly matching that unintended ROM source.

`build_secret_palette_sources.py` relocates the table into eight explicitly
reserved padding bytes at 7FEA after the existing two retired-pointer leaves.
It preserves all six normal-stage entries, supplies the existing Dungeon BG0
for indices 7/8, and changes only the two lookup address operands plus data
and checksum. Runtime instructions/cycle counts are unchanged. Candidate:
`tmp/secret-palette-source-01/candidate.gb`, SHA-256
`e2473cbaf4060896afaa7f30b5fc250729887ae02cc12cb15f183ea3bfa09405`.

`tmp/secret-palette-regression-01/receipt.json` passes ten checks across three
serial 3600-frame replays: the eight geometry checks above plus correct live
BG0 (`ff7f947e4a3d0000`) and rejection of the broken control's BG0. Replay
wall times were 4.36–4.41 seconds. Visual inspection of frame3600 confirms
intact panels and a black background instead of the invalid bright fill.
Five new structural tests cover all eight indices, preserved normal rows,
unchanged runtime opcodes/leaves, checksum and rejection of altered owned
regions. Both builder suites pass (ten unit tests total).

This does not establish correct colors for every actor/material or fix the
return trails. The palette editor must support the new table location before
this candidate can be offered for editing/deployment. Neither candidate has
been deployed or hardware-qualified; issue #23 remains open.

### Return-route exploration (#26): not yet a discriminating regression

`tmp/secret-return-route-01` resumes the exact new candidate's owned frame3600
state (CRC/header checked, no identity retargeting), pulses A for 12000 frames
and explicitly refills health/resource. It reaches secret fight scene0A at
frame383, returns to scene09 at3286, restores stage00 at3287, takes the native
scene18 transition at3304, and reaches Stage1 scene02 at3496. The final screenshot
after another 8504 frames has intact blue/white dungeon geometry with no obvious
yellow trails. No scene/cache/palette/position writes occur in this segment.

The same input recipe on the broken build's own checkpoint is **not an equivalent
return control**: `tmp/secret-return-broken-01` enters scene0A at347, then takes
scenes00/17/01 before a different Stage1 room05 at1644. Its final screenshot also
does not show the reported trails. Initial restored position/timing already
differs. This experiment supplies a candidate native-return route, but does not
prove #26 fixed or establish equivalent savestate continuation. A continuous
entry/fight/return replay and the reported power-up/menu conditions remain needed.

Continuous follow-up removes the savestate boundary. The retained executed
probes in `tmp/secret-return-continuous-fixed-01` and
`tmp/secret-return-continuous-broken-01` use identical cold-boot inputs,
frame1201 doorway positioning and explicit resource refill. Their full
15600-frame scene/stage/position traces are byte-identical; both take the
death/title route when firing starts at3601. Thus the earlier restored-state
divergence is not evidence of a gameplay difference caused by either fix.

Starting pulsed fire at1321 instead produces the successful native return
on **both** builds: secret fight at4085, stage00 restored6857, transition6874,
Stage1 scene02 at7062. `tmp/secret-return-continuous-fire-01` and
`tmp/secret-return-continuous-fire-broken-01` again have byte-identical full
traces and identical final PNG SHA-256
`b03be1a15d5ebd4bf223e3e30190d2d497bdca554958594c6849326db0d48bdb`.
The inspected final picture has blue/white scenery without the reported yellow
regions. This is a non-reproducing control, not a passing yellow-trail gate.

`tmp/secret-return-walk-broken-01` extends the successful broken-build route
with Down/Left/Up/Right, 480 frames each, repeated after7200. It remains in
scene02 through11040 and moves into room03. Inspected frames8640 and11040
still lack the recorded yellow/red regions. Pure secret return plus this
scrolling route does not suffice to reproduce #26. Menu/power-up history and
the player's preceding route remain important missing conditions. These
exploratory runs pin their executed Lua and ROM but are not release acceptance.

Additional menu controls on the broken build:
`secret-return-menu-broken-01` opens Select at2400 for six frames and closes it
120 frames later during secret flight; native return reaches scene02 at7216
and the inspected final frame15600 still lacks yellow trails.
`secret-return-menu-after-broken-01` performs the same round trip at7300 after
return, combined with the scrolling recipe. Neither test activates an item.
`secret-menu-observe-01/frame-2460.png` confirms the Select input actually
opens the MEDICAL/HP/MEGA-FLASH window during scene09 rather than relying on
an unchanged scene ID to infer menu state.

Recording samples1770/1800 (29:30/30:00) clearly show red/yellow secret-area
walls **before** returning; sample1830 shows the same palette family on dungeon
walls with the item window open. Thus onset is not limited to the exit itself.
The prior-scroll experiment `secret-prior-scroll-broken-01` does not enter the
secret stage after moving the doorway warp to2401, so it cannot evaluate the
prior-hazard hypothesis. It ends in Stage1 scene0A and is a rejected route,
not negative secret-transition evidence.

The historical GBC doorway fixture (SHA
`aef1d7ee0f4eb08d6d0447bcf38e2ed77ba0477a7b82c55094e2a006a733db05`)
is paused in scene0B. `secret-historical-doorway-01` retargets only ROM identity,
then sends Down+A; it stays in that menu for720 frames. A Select exit is needed
before that fixture can explore the real doorway. This historical state is not
an authenticated current-build baseline and must not substitute for cold replay.

### Stale tile-bank experiment (local diagnostic, not a natural-entry replay)

Four serial 840-frame experiments on exact ROM `4f5a67b8…` used the same
identity-retargeted bonus fixture, SHA-256
`900335a266b294aeb29419a91a3af4f990d72791dd53a8d09e0738a09758f064`.
Each explicitly reused the legacy verifier's palette/cache initialization and
health/resource assistance. At frame 241 the mutation sets attribute bit 3
in both maps, preserving all other attribute bits. Results:

| Experiment directory under `tmp/` | Result through frame 840 |
| --- | --- |
| `secret-stale-attrs-control-01` | Zero bank-1-selected cells; scenery remains drawn. |
| `secret-stale-attrs-mutated-01` | All 2048 mutated cells persist; scenery disappears into a green field. |
| `secret-stale-attrs-transition-01` | Also sets previous-scene cache to 02, exercising scene-09 transition service; all 2048 cells still persist. |
| `secret-stale-attrs-rearm-01` | Same mutation/cache setup plus explicitly rearming DF08; all bank-selection bits clear by frame 242 and remain clear. |

Each directory contains the exact executed Lua copy, its SHA in `receipt.json`,
per-frame counts, screenshots and states. Runs took 3.1–3.4 seconds each.
This establishes that the existing secret-scene service does not repair stale
bank selection, and that the existing cleaner can remove it. It does **not**
establish that natural entry leaves those bits behind or that it explains the
recording's white stripes: the mutated historical fixture has different bank-1
tile contents. No ROM patch or hardware deployment resulted from this experiment.
The next decisive test must exercise native entry with Stage-1 VRAM history.
Blindly rearming DF08 is not yet a qualified fix: the cleaner switches off the
LCD and neutralizes all palettes, so its transition timing and visual effects
must be checked before adopting it.

Visual inspection of the rearm trial rejects it as a standalone fix: panel
geometry returns, but the background becomes bright red rather than the
control's black background. Clearing bank-selection bits is therefore not
equivalent to restoring correct scene colors. Final-state reads confirm
DF0D=09 and DF08=5A in all four trials, including the forced-transition case;
the scene cache did advance, so that case did not merely skip scene detection.

Fresh command on the reported ROM:

```sh
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
  python3 scripts/diagnostics/verify_bonus_stage_live.py \
  tmp/sara-atomic-pose-source-16/candidate.gb \
  --output tmp/stream-bugs-20260927-bonus-baseline
```

All seven existing checks pass. Receipt:
`tmp/stream-bugs-20260927-bonus-baseline/receipt.json`.

This is not evidence that #23/#26 are fixed. The probe loads a historical
secret-stage savestate, resets DF00/DF02 for 40 frames and DF0D on frame 1,
assists player health/timer, and runs only 240 frames. It checks palette
values, safe attribute bits, and broadly chromatic screenshots. It never
requires a dungeon → secret stage → dungeon transition or compares the
intended scenery tile graphics. A new regression must exercise entry and
return without repairing palette/cache state in the observer.

A further 24,000-frame run of `capture_hidden_shmup_gallery.py` using the
identity-retargeted historical fixture also reports PASS:
`tmp/stream-bugs-20260927-bonus-long/manifest.json`. Inspection of its trace
shows scene 09 initially, 0A during combat, and 0B from frame 3752 through
24000; FFBA remains 07 and FFD0 remains 01. Thus it did **not** return to
normal Stage 1. Its broad nonblank/chromatic checks cannot qualify the
reported return path either. The frame-12000 image shows recognizable
secret-stage panels rather than the recording's white strip corruption.

Existing fixtures include `level1_sara_w_before_entering_secret_stage.ss0`
and `level1_sara_w_secret_stage_sequence_started.ss0`; these are investigation
leads only. Validate their provenance/state compatibility before using them,
and ultimately reproduce through an exact-candidate entry rather than
treating an old already-in-secret-stage state as equivalent.

### Entry-fixture screening and fresh baseline

Two 1200-frame identity-only historical-state trials made no palette/cache,
health, stage or position writes:

- `tmp/stream-secret-entry-unmodified-01`: the sequence-started fixture stays
  scene 02, stage 00, bonus 00, mode 00 throughout. It does not enter the bonus.
- `tmp/stream-secret-before-unmodified-01`: the before-entry fixture changes
  scene 02 to unexpected 31 at frame 2; the final picture remains the old
  monochrome corridor. This is not a trustworthy current-build entry replay.

Neither result is counted as a reproduced gameplay bug or accepted fixture.
Their historical machine state remains an uncontrolled compatibility factor.

`tmp/stream-secret-cold-route-01` instead boots an isolated exact 4f5 ROM copy
with no adjacent save file and uses only Down/A/Start inputs. Native Stage 1
is reached at frame 492 (scene 02, stage 00, bonus 00, mode 01). The frame-1200
snapshot is visibly colored gameplay and is retained as a candidate-owned
navigation starting point. No palette/cache/health/position writes were used.
This proves a clean starting point, not the secret transition or a fix.

### Suspected stall ruled out: paused item menu (#29, closed)

Correction after control-flow tracing: this was not an established freeze.
`tmp/stream-stall-call-trace-01` records 55 complete VBlank helper returns in
60 frames. The longer `stream-stall-input-trace-01` records 172 returns in
180 frames and confirms Start reaches FF94 as 08. Native menu code routes
that bit to an item action; Select bit04 follows the close path. A six-frame
Select press from the same state (`stream-stall-select-response-01`) removes
the menu/HUD and resumes visible enemy/projectile animation. No timing patch
is justified. #29 was closed as a diagnostic false alarm; #28 remains open.
The observations below are retained to explain the rejected hypothesis.

The unexpected menu entry is also explained by stock code, not an input
glitch: original and candidate bank-1 routine 5050 are byte-identical. When
DCBB is below 20 and DD06 equals 02, code at 5066 loads HL=FF94 and executes
`SET 2,(HL)`, then stores DD06=03. This deliberately synthesizes the Select
edge. The fine-grained cold trace shows the normal joypad poll produces
FF94=00 at frame3001; the subsequent native routine makes it 04 before the
menu dispatch. Evidence: `tmp/stream-menu-entry-register-trace-01`.
Navigation must account for this native resource/menu behavior. It must not
be “fixed” by changing the VBlank helper or input handling.

From the clean frame-1200 checkpoint, hold Up+A. Two serial 1200-frame
segments reach a stationary Stage 1 picture near a horizontal spike bar.
A confirming **continuous cold boot**, with no state restores and only a
final screenshot/state save, uses the same title inputs, idles through frame
1200, then holds Up+A through frame 4800. It reaches the same stationary
picture (`tmp/stream-secret-cold-continuous-02`). Scene is 0B, room 01,
position bytes are 60/180, and the sampled health byte is 12.

The subsequent 1200-frame retained-state trial has 11 identical sampled PNG
hashes; sampled PCs are bank 20:7F16/7F18/7F1A in the menu reveal wait.
**That sampling does not yet prove the wait loop is the cause.** Breakpoint
diagnostics see LY 144 and a zero comparison flag at the guarded recheck.
Further tracing must distinguish repeated normal calls from true starvation
before modifying timing. A six-frame Start press followed by 594 idle frames
also leaves the picture, position, and scene unchanged
(`tmp/stream-stall-start-response-01`). All are local diagnostics, not a
claim that this explains the player's hardware failed-continue report.

The scratch trace was corrected to read D880 from physical WRAM, like the
existing speed probes: bus reads during a switched-bank callback can show
the wrong bank. Earlier reported transient scene IDs, including the old
fixture's 31, therefore cannot establish invalid game state on their own.
The old fixture's failure to reproduce entry remains, but its interpretation
requires this correction. No acceptance claim depends on those IDs.

## Work inventory

### Game Over color trial (#18)

The YAML explicitly configures a neutral GAME OVER row at bank13:7C34:
`ff7fff7fb5564a29`. Existing restart/death tests require that grayscale RGB
identity; passing them did not establish the player's requested color treatment.
The exact current secret-fix candidate passes the old two-cycle restart check
in `tmp/gameover-color-parent-01` and renders 276 gray accent pixels.

`build_gameover_color.py` changes only the accent word56B5 to the existing
death-screen spectral purple7E1F, plus global checksum. Both white entries and
the shared charcoal fade-seam byte remain unchanged. Trial candidate:
`tmp/gameover-color-01/candidate.gb`, SHA-256
`7130c04a3ef9ad9239ae693dad9d5d61953437fa3eccc0c137071b79faeacc23`.

The unmodified old verifier intentionally reports RGB mismatch in
`tmp/gameover-color-trial-01`; its route nevertheless completes two full
death/Game Over/title/new-game cycles. Independent `verify_gameover_color.py`
requires the exact ROM delta and exact per-pixel substitution from gray
(173,173,173) to purple (255,132,255), with no other changed pixels. Both cycles
change276 pixels. Full game-state trace and all six title/gameplay PNGs match
the parent byte-for-byte. `tmp/gameover-color-comparison-01.json` passes13
checks; visual inspection confirms purple accents with intact lettering.

This is a palette-only implemented/offline-tested trial, not a release claim.
Canonical YAML/build integration, consecutive-frame/death-fade coverage, mutation
tests of the new oracle, and hardware appearance review remain. No existing
grayscale oracle was weakened or rewritten to accept an arbitrary new image.
MiSTer was not modified. Issue #18 remains open.

Follow-up oracle hardening requires the parent image to match the independently
reviewed intact grayscale GAME OVER hash before comparing the accent change.
Seven synthetic unit tests pass, including missing glyphs, extra colored pixels,
unchanged-gray output, wrong dimensions and common-mode corruption rejection,
plus the builder's strict byte delta/checksum. This closes a gap where two
equally damaged images could otherwise satisfy an accent-only comparison.

Fresh paired sequence runs are retained under
`tmp/gameover-color-parent-sequence-01` and
`tmp/gameover-color-trial-sequence-01`. The updated independent checker passes
all14 checks in `tmp/gameover-color-sequence-comparison-01.json`: 102 consecutive
GAME OVER frames (ages10–60 across two cycles) have exactly the intended accent
substitution, and all723 cold/returned-title frame pairs (ages60–300 across
three visits) are byte-identical between builds. Full trace remains identical.
These are selected phase windows, not every frame of the fade/death sequence.
The legacy candidate result still correctly fails its old gray-only identity;
source-YAML and central-oracle integration remain pending rather than silently
claiming the broad suite passed.

Integration follow-up: canonical `death_gameover_palette.gameover_colors` now
uses the tested purple row. A unit test executes the actual palette compiler
function from source and verifies exact agreement with the trial ROM row.
The central death/restart and sequence checks select between two reviewed,
exact RGB identities using the ROM palette bytes; unknown rows fail closed.
The original gray identity remains available for historical controls. The
purple identity was established by the paired geometry-preserving comparison
above, not by accepting an arbitrary new screenshot. Nine focused unit tests
pass, including palette selection/rejection and YAML compilation.

Fresh `tmp/gameover-color-integrated-01` passes the normal checked-in restart
verifier with `--sequence`: two full cycles, 102 GAME OVER frames, and482
returned-title comparisons against the same-run cold title. Candidate remains
`7130c04a…`; no hardware deployment occurred. Full source-chain rebuild, all-boss
death/fade coverage and hardware acceptance remain separate unfinished work.
The wider `test_gameover*.py` unit group passes42 tests after adding an asset-free
ROM palette fixture to the sequence tests (their previous fixture had no ROM).
Missing-frame and corrupt-frame rejection tests remain active.

`tmp/gameover-color-hazard-saved-01` additionally passes two saved-game restart
cycles after1600 frames of hazard-area movement, then HP-zero stimulus. This
is not a movement-only native-death claim. It also checks the selector/splash,
102 Game Over frames and482 returned-title frame comparisons.

Shalamar death/fade verification passes in
`tmp/gameover-color-shalamar-death-02`: exact576-cell native-art publication,
noncollapsed viewport/lower body, coherent CRAM3/3,2005 chromatic illustration
pixels, exact white fade and276 purple Game Over pixels. Its checkpoint was
freshly generated on7130c04a before the initial generator failed at Riff.
That initial failure is retained in `gameover-color-shalamar-death-01`.
Issue #30 tracks the test lookup defect: new exact descendant hashes were
missing from relocated arena palette storage recognition, selecting obsolete
bank13 bytes instead of unchanged bank23. All three new candidates preserve
bank23 byte-for-byte. Support was added with the independent table-builder
check retained. The fresh rerun under `tmp/gameover-color-shalamar-death-03`
successfully generates bosses0–7, including Riff, then fails Penta Dragon's
historical-fixture recapture path. This is not a full generation pass. The
remaining exact-pin cold-Penta route selection needs investigation. Fresh
Shalamar/Cameo/Troop/Faze checkpoints are available for separate death tests.
Those four cases pass in `tmp/gameover-color-four-deaths-01`: all publish576
stock-art cells, maintain coherent CRAM3/3 and the exact white fade, and render
the reviewed purple Game Over identity. Illustration chromatic pixel counts
are2005/2820/3129/6899 respectively. Penta Dragon remains untested on this
candidate because its checkpoint generation failed; no all-boss pass claimed.

Follow-up: `tmp/gameover-color-all-deaths-01` successfully generates all nine
boss checkpoints after the exact-pin cold-Penta selector update. All five
supported death cases (Shalamar, Cameo, Troop, Faze, Penta Dragon) complete;
Penta's report records the native publication, white fade, and purple Game
Over row. This supersedes the incomplete Penta coverage above, not the retained
failed runs. Nine checkpoints are not nine death tests or hardware acceptance.
Issue #30 now has synthetic regression tests for relocated table selection,
table corruption rejection, cold-Penta selection, and the Ted instruction guard.

Source reconstruction: `tmp/stream-regressions-source-04/build-receipt.json`
reproduces exact candidate `7130c04a3ef9ad9239ae693dad9d5d61953437fa3eccc0c137071b79faeacc23`
from the original cartridge and source, without retained candidate inputs.
Attempts 01–03 remain failed evidence. The final mismatch was the already
integrated atomic Sara emitter: modern factory `a5dc175b…` differs from the
historical `e5601c68…` only at the two emitter copies and global checksum.
The historical adapter accepts that exact modern identity, restores the two
reviewed historical emitter bodies, and still requires the complete old
factory and r120 hashes. The final successor chain reapplies the atomic fix.
An explicit historical YAML profile differs from canonical parsed YAML only
at the gray Game Over row; the final overlay restores canonical purple.
Construction passes; release qualification and hardware acceptance do not
follow from this source-build result. MiSTer was not touched.

### Experimental doorway priority restoration (#14, not qualified)

`scripts/diagnostics/build_sara_doorway_priority.py` builds trial
`a5844f7d9e75355e883307e6e9db9744db52481fd4565fe47f8f9407d95bb81b`
from exact `7130c04a…`. It retains the DX FFC4 map selector, stores native
quadrant-2 priority at DB70, and installs a DB40 helper through unused ROM
banks 33/34. It leaves the existing publication shim at 118B intact.
Apparent ROM gaps at 70E0/78FF/79BB were rejected: they belong to live
palette tables. DB40..DB70 lifecycle safety is still experimental; historical
Stage-4 code ends at DB3D, but this is not current all-scene ownership proof.

Fresh cold replay `tmp/ceiling-priority-doorway-01` used the retained doorway
probe, position/resource assistance, Down through 1212, and capture 1216.
All four OAM priority bits are now set, and the 256-pixel Sara mask is black
(zero visible sprite pixels). **The exact doorway verifier rejects this
trial:** world position is 1240/1352 rather than reviewed 1240/1356. The full
movement trace differs; this is not a passing visual/speed comparison and
the verifier was not relaxed. PNG SHA-256:
`6a17ca7dbad5f388bb1c254b76c7c0de359416364b10bd6ceb199e0ea2255e05`.

Fresh stationary floor control `tmp/ceiling-priority-floor-01` reaches
1252/824 at frame 1500 with Sara priority clear. Compared with retained
`star-spiral-cold-01`, all four Sara OAM entries match; the whole rendered
frame differs in 418 pixels, so this is not full-frame equivalence.
PNG SHA-256:
`21e3c3d190eac7aba2869dd2949228e49cdcb38b5ce489ad91e93fdafbea89f9`.
Both replays completed normally under the single-flight wrapper, sequentially.
Four new builder allocation/preimage tests pass. No deployment, hardware
acceptance, audio claim, issue closure, or release promotion. Next: quantify
the added priority-helper cost and retain the exact movement/cadence guard,
then test ordinary-floor motion and menu/death/later-stage lifecycle.

#### Combined flash/priority successor: doorway passes, timing still pending

The next simple fast-path trial (`9afea487…`, `ceiling-priority-doorway-02`)
still failed the reviewed endpoint at Y=1352. The combined successor
`707507de35c1e0c638d7b9837c3d19009ac6f059564f3e92de5ecdde4f8172ac`
(`build_sara_doorway_priority.py --combined`) fuses the existing native flash
prefix and priority tail, avoiding duplicate HL save/restore and a second
CALL. It leaves fixed 1188 unchanged, changes the two mirrored emitter call
sites, places quadrant-2 state at DB3E, and bounds helper code below DB7F.
It does not change the Stage-4 DB00..DB3D payload.

Fresh `ceiling-priority-doorway-03` **passes the unchanged narrow doorway
verifier**: world1240/1356, camera0C08, identical four OAM positions, all four
priority bits set, and zero visible pixels in the reviewed 256-pixel mask.
PNG SHA: `629103e8f8dd17abfc5eb1d943f53be34b1bf8f52df1feb1b5c65ee886868271`.
The broken `7130c04a…` reference still exposes192 pixels. The successor's
probe adds a read-only 016C game-loop breakpoint (SHA
`7d6295a9a06bb873ea2cabe239316f95798080a4d6b52afcb98f0a978942ae65`);
the earlier stock capture used the previous probe. Observer neutrality has
not been separately qualified.

Fresh paired stationary cold tests (same probe and assist/input environment)
were run sequentially at1252/824, ending1800. In the complete declared
1201 <= frame <1800 measurement window:

| Run | ROM | Main-loop hits | Observed inter-hit gaps (display frames: count) |
| --- | --- | ---: | --- |
| ceiling-loop-parent-01 | 7130c04a… | 136 | 4:83, 5:52 |
| ceiling-loop-trial-01 | a5844f7d… | 134 | 4:74, 5:58, 6:1 |
| ceiling-loop-combined-01 | 707507de… | 135 | 4:74, 5:59, 6:1 |

Initial and terminal partial loop intervals are censored by those fixed
window boundaries; they are not assigned guessed durations. Full loops.tsv
and per-frame traces remain available in each run. These figures do not
prove speed equivalence, and enemy-state divergence can affect later load.
No timeline was aligned or trimmed to manufacture equality. The combined
stationary Sara footprint matches the parent in all256 pixels with identical
OAM and clear priority; the **whole frame differs by1068 pixels**. Full-frame
equivalence is not claimed. Six allocation/preimage tests pass. Moving-floor
bleed, lifecycle, timing, audio and hardware qualification remain pending;
neither trial is deployed or promoted to the source successor chain.

#### Moving-floor and lifecycle checks on 707507de…

Fresh `tmp/ceiling-floor-patrol-01`: cold boot, one-shot position assistance
to1252/824 at1201, alternating Left/Right every100 display frames through1800,
with explicit DCDD/DCDC/DCBB resource assistance. All600 post-warp frames
remain scene02; world X spans1160..1260 and Y stays824. None of the four
sampled hardware-OAM attribute bytes has OBJ-behind-BG bit7 set in those
600 frames. The DB40 helper matches its installed bytes throughout. The
frame1440 screenshot was visually inspected. This establishes a moving-floor
priority-clear control, not exhaustive per-pixel animation or all-room
floor-bleed qualification. Trace probe SHA:
`e32ec7d4a365785213cf7b2373bfa6496a98ba745be7cf8dc1ae2c623093117c`.

Fresh paired7800-frame secret runs use identical probes, inputs and resource
assistance (`ceiling-secret-parent-01`, `ceiling-secret-lifecycle-01`). The
parent7130c04a… reaches miniboss scene0A at4085 and returns via scene09 at6856,
Stage1 at7062. The candidate707507de… reaches0A at4068, then death scene17
at5521 and title at5810, starting Stage1 again at6153. The candidate's helper
bytes remain intact in every post-warp sample, including death and restart.
**This is an outcome divergence, not a successful secret-return test.** The
boss-entry world Y also differs (parent1184, candidate1216); the cause has
not been proven. Neither a memory-corruption diagnosis nor harmless timing
equivalence follows from the intact helper. Both complete traces and raw
transition captures are retained. No collision/palette/scene writes were
added to force the expected result.

Independent `tmp/ceiling-gameover-lifecycle-01/receipt.json` passes the
checked-in Game Over regression with `--sequence --saved-game`: two full
cycles,102 reviewed purple Game Over frames,482 returned-title frame pairs,
stage selector/cards and returned terrain checks. Death was accelerated by
HP=0 once per life; this does not qualify natural damage or the divergent
secret fight. No hardware was touched. The candidate remains experimental
and absent from the promoted source-build chain while timing, secret-return
outcome and broader lifecycle questions remain unresolved.

#### Occlusion-off counterfactual and scratch-register trial

`build_sara_priority_negative_control.py` derives diagnostic
`213be80ca42196d17bfb3de706d51c88a0b0bb6892a8b6966175cd3032c7f6bd`
from exact707507de… by changing only the two copied-helper SET7,A instructions
to RES7,A plus the global checksum. Both instructions are two bytes,8T,
and leave flags unchanged; installer, flash, branches and relocated flag
are untouched. `ceiling-negative-doorway-01` fails the unchanged doorway
verifier as intended: same1240/1356 endpoint and camera, but192 exposed
sprite pixels and all four priority bits clear.

Fresh `ceiling-secret-negative-01` uses the exact same probe/environment as
`ceiling-secret-lifecycle-01`. Their entire7800-frame gameplay trace files
are byte-identical, SHA
`577f37e90e5adec257573edafccb695b4332f4288769bd132df0f40ccad7d87d`.
Both die and restart at the same frames; their final PNGs are identical,
SHA `889ab3cb1fb1057706077efc8d80d410aae38fb2d06aaee6915ee3e7c3085cb6`.
This rules out the OBJ-priority-bit change itself as the cause of that
outcome divergence in this replay. It does not isolate timing from all
other nonvisual helper/installation changes, and does not qualify the
candidate as gameplay-equivalent to the parent.

An additional `--combined --scratch-b` trial saves the attribute in B,
which the sole central-emitter caller already saves and does not read again
before POP BC. The caller overwrites F with AND F8 immediately afterwards;
the copied native flash prefix remains unchanged. The patch replaces only
one PUSH AF and two alternative POP AF instructions in the combined helper
with LD B,A / LD A,B (20T saved on either executed path). Candidate:
`d5087e0d9c212cbb5d4f10fc3795eebda47516827f07c782bfe899a39dfc33b1`.
Seven builder tests pass. `ceiling-loop-scratchb-01` observes136 iterations
in the same1201..1799 window, gaps4:80,5:53,6:2. Counts match the parent but
timelines do not. `ceiling-priority-doorway-04` fails the original endpoint
requirement with Y1352; that failure is retained. No broad qualification,
source-chain promotion or deployment follows from the optimization.

#### Secret-fight death: observed native energy-underflow path

Read-only write/breakpoint tracing in fresh
`tmp/ceiling-secret-damage-trace-01` follows exact707507de… through5600
frames. The complete5600-frame gameplay trace is identical to the retained
un-instrumented `ceiling-secret-lifecycle-01` prefix. This is trace neutrality
for the recorded fields, not a full video/audio observer-neutrality claim.
Probe SHA: `516943d909663c00941665e43c4b1bcc740f1f877bc94035f68a9c8978f2582a`.

At frame5519 the native damage entry1004 is invoked three times:

| Incoming damage A | DCBB before hit | A after subtraction at1028 | F |
| --- | --- | --- | --- |
| 32 | FF | CD | 40 |
| 3A | CD | 93 | 40 |
| B7 | 93 | DC (borrow) | 70 |

The first two hits store CD and93 at1032. The third sets carry/borrow,
takes the native `JP C,4A44`, and reaches the death routine at5519;
sound-scene17 is written at5520. Resource assistance runs only once per
display frame, so it does **not** guarantee survival of multiple same-frame
hits. The damage code1004..104B and collision caller5BC0..5BD9 are
byte-identical across the original cartridge, parent7130c04a… and
candidate707507de…. Death entry4A44..4A54 is identical between parent and
candidate, but **not** identical to stock (it retains earlier DX changes).
The initial issue comment incorrectly included that entry in the stock
identity claim; the subsequent correction records the actual byte check.
This establishes the immediate death path without
an unexplained jump or a helper overwrite. It does not prove that every
damage value or changed encounter is correct; timing/encounter divergence
and secret-return qualification remain unresolved. Do not change the damage
routine or add within-frame invulnerability merely to make this replay win.

### #31: native projectile records overwritten by injected bank-13 code

Issue: https://github.com/struktured-labs/penta-dragon-dx/issues/31

The death investigation found an independent data/code overlap, already
present in parent7130c04a, not caused by the ceiling priority bit. The native
loader at2AE0 indexes bank13 table5300 and copies eight six-byte records.
At5CFE, the original contains two active records followed by36 zero bytes;
DX's Shalamar sanitizer at5D0A occupies those inactive records. Live source
observations confirm instruction bytes are being copied as projectile data.

`build_native_projectile_templates.py` changes only the bank operand at2AE1
from0D to20 and the global checksum. It requires exact parent/stock hashes,
the native loader preimage, and entire bank32 equality with original bank13.
No code is removed, no damage/invulnerability logic is changed, and the
loader's instruction count/cycles are unchanged. Whole-game timing is not
qualified by that static statement.

Source-only oracle `verify_native_projectile_templates.py` checks all48 bytes,
including inactive tails, and binds ROM/probe identities. Fresh observations:

| Replay | ROM SHA-256 | Source observations | Outcome |
| --- | --- | --- | --- |
| `tmp/projectile-template-broken-01` | `707507de35c1e0c638d7b9837c3d19009ac6f059564f3e92de5ecdde4f8172ac` | 10/11 incorrect, five patterns | Negative control fails. |
| `tmp/projectile-template-fixed-01` | `c52e85a078f2515114ab78139db9dae83417dcfbd5a7ba94d743b2d9733deb3b` | 21/21 exact, five patterns | Secret fight exits6893; Stage1 resumes7106; run ends7800. |
| `tmp/projectile-template-parent-fixed-01` | `3c5951bf86f429f2d6299ea68704514672b5e90d4726572b8c2981bd2963b73e` | 19/19 exact, four patterns | Independent of ceiling patch: fight exits6902; Stage1 resumes7109; run ends7800. |

All use probe SHA256
`4d64439c5472b7938377cb880153c953cb8765e9d4a600a63261a667ffc48e3a`.
The two fixed runs cold boot, position-assist secret entry at frame1201,
hold Down+A120frames and pulse A thereafter. They explicitly refill
DCDD/DCDC/DCBB each frame; these are assisted diagnostics, not normal-play
survival claims. There are no palette/graphics/cache writes. Viewed the
combined fixed run's native frame7800: Stage1 terrain is present. This single
image does not certify all tile colors or eliminate persistent trails.

Eight synthetic unit tests pass for patch boundaries, checksum, exact pins,
structural guards, all48 bytes, inactive-tail corruption, source binding and
malformed/empty observations. Actual broken-ROM capture also fails the oracle.
Remaining: destination-copy validation, wider pattern/encounter coverage,
source-chain integration, unassisted combat and relevant visual regressions.
No hardware, audio, full-speed or release qualification; #31 stays open.

Follow-up: `scripts/build_stream_regression_candidate.py` now includes #31
after the Game Over palette overlay, without the experimental ceiling helper.
Fresh source build `tmp/stream-regressions-source-06` reproduced
`3c5951bf86f429f2d6299ea68704514672b5e90d4726572b8c2981bd2963b73e`
from the original cartridge and palette sources. Attempt05 is retained as a
failed construction: editing verifier/tests during construction invalidated
its source snapshot. No emulator launched from attempt05; the attempted
capture directory `tmp/projectile-copy-fixed-01` contains no successful run.

The destination oracle now supports `--copies`: observe BC and DE at2B17,
then all48 destination bytes at2B34. Require DE=DC55; for every six-byte record
only byte2 adds C and byte3 adds B modulo256, exactly as the native loop does.
Source bytes must independently equal original bank13. A faithful copy of
corrupt source therefore still fails. Completed copy count must equal source
count; pending copy at run termination fails the Lua probe.

`tmp/projectile-copy-fixed-02` on source-built3c5951bf passes19/19 source and
destination observations across four patterns. `tmp/projectile-copy-broken-01`
on707507de fails10/11 source observations while all11 destination copies
faithfully reflect their source. This isolates incorrect source data rather
than a broken copy operation. Copy trace SHA256 values respectively:
`c6ca82785cdbd32411321766d985cca1921021934d12bec5bdefacd3488f59b0`,
`a6cb6f394ba9ac15189447e309f9bf9711e0efbb3a8825dcce6c57605191e639`.
Probe SHA256: `831655701db75a823456cedcf27822c329cf6dca7bbd3ce55a74a4fc73c0eb45`.
The fixed run's entire7800-frame state trace equals its previous source-only
observer run (SHA256 `12765a3371978bba99a0c4e24b8c59ef612c4cfbb3e2df91dcd133e1f903f61c`).
This is state-trace agreement, not full video/audio observer neutrality.
All11 projectile unit tests and19 existing Game Over/secret builder tests pass.

`tmp/projectile-gameover-lifecycle-01` also passes two cycles on3c5951bf:
102Game Over frames,482returned-title pairs, saved-game stage selector/cards,
and restart terrain checks. Stimulus remains HP=0 once per life, not natural
hazard death. Wider encounters, unassisted combat, visual/audio checks and
hardware acceptance remain open; no device was modified.

### #28: Continue input investigation on source-built3c5951bf

Reviewed recorded footage around38:00–38:36. Stage2 gameplay transitions to
a visible Continue countdown (10 through1), then plain Game Over and title.
Input buttons are not displayed; footage cannot establish which buttons were
pressed. Diagnostic contact sheet:
`/mnt/data/tmp/penta-stream-review-20260927/continue-38m-1s.jpg`.

Native bank1:4A9C reads FF94, AND01, then branches to4AD4 on an A-button edge.
This check is byte-identical in original and current ROM. Start is not accepted
by this native check; do not infer that the player pressed the wrong button.

Fresh cold-boot diagnostic `tmp/continue-a-poll-01`, ROM
`3c5951bf86f429f2d6299ea68704514672b5e90d4726572b8c2981bd2963b73e`:
frame1201 supplies one Continue credit (FFE6=1) and one DCBB=0 death stimulus.
Six-frame A pulses repeat every12frames from1380 through1799. Death marker17
appears1280, countdown runs1335..1935, title returns2191. All450 observations
at native4A9C see FF93/FF94/FF95=00. No Continue occurs. This is a Stage1
assisted reproduction of input rejection, not exact recorded Stage2 history.
Probe SHA256 `83ea729e37800ec48d91e4219c2b92fa0547ea439530833f58e2e22847a52761`;
poll SHA256 `ec9d2faa7f0da6c0e582fc58ade3c4f9da724c1840b329764b3a2deb9c127d1c`.

Static causal lead: wrapper6F1D calls death router570E ->7100 ->7133 for
scene17. Its tail718F POP HL; JP6F8C skips wrapper joypad sampler6F3D..6F68.
This explains how the countdown can advance while game-owned input remains
zero. Next fix must preserve death rendering and restore joypad sampling;
validate A acceptance, neutral timeout, stock button semantics and restart.
No ROM change for #28 has been made at this point.

Rejected/incomplete controls are retained: `continue-a-current-01` restored
a Stage1 checkpoint but did not enter death, and `continue-a-stock-01` used
the same cold-frame stimulus on original stock but also did not enter death.
Neither is a valid Continue comparison. Prior Game Over restart passes used
zero native credits, so they never exercised Continue input acceptance.

Implemented diagnostic fix in `scripts/diagnostics/build_continue_input.py`:
replace the death tail7189..7192 with a fixed-ABI far call to private bank35,
then retain the original discarded return and wrapper teardown. Bank35 mirrors
bank13, runs the original two visual tail calls (6530 and69D0), samples the
joypad with the existing6F3D..6F67 bytes, and returns bank13 through0847's ABI.
The mirror's palette reader at71DB must restore bank35 rather than13; only
its return-bank literal and the private6C80 helper differ from the source bank.
Bank35 must be allFF before construction. No shared gameplay sampler, native
A-only Continue semantics or input edge algorithm is modified.

Candidate `tmp/continue-input-01/candidate.gb`, SHA256
`b902240052bcdf743dbf4583edcc52b4584b5eae3757c613100238c934483df9`.
Builder SHA256 `e55f5172fda168d0de5702ce22fb12292a2d6e560267cf13959231fec721ba13`.
Four structural unit tests pass, covering exact parent/preimages, blank bank35,
bounded edits, mirrored visual dependencies, return bank and checksum.

New oracle `verify_continue_input.py` requires bound ROM/probe, complete2400
frames, native input-check evidence and actual death; unavailable/deathless
controls are errors, never passes. The exact same assisted cold probe gives:

| Capture | Button | Result |
| --- | --- | --- |
| `continue-a-poll-01` (parent) | A | FAIL:450 checks with zero input, title2191. |
| `continue-a-fixed-01` | A | PASS: native A edge1380, credit consumed1381, gameplay resumes1437; no title. |
| `continue-neutral-fixed-01` | None | PASS: full countdown10..1, no continuation, title2191. |
| `continue-start-fixed-01` | Start | PASS for native non-A semantics: no continuation, title2191. |

Probe SHA256 remains
`83ea729e37800ec48d91e4219c2b92fa0547ea439530833f58e2e22847a52761`.
Viewed frame2400 of successful A replay: Stage1 terrain and player are visible.
`tmp/continue-gameover-lifecycle-01` independently passes two HP-zero assisted
restart cycles on the patched ROM, including102Game Over frames and482title
frame comparisons, stage selector/cards and restart terrain. Exact Stage2
history, other death art paths, timing/audio and hardware remain unqualified.
Source-chain integration and a checked-in replay driver remain pending.

Follow-up: checked-in `probe_continue_input.lua` and `run_continue_input.py`
now reproduce A acceptance from a fresh guarded cold boot in
`tmp/continue-driver-a-01` (same death1280/accept1380/resume1437). The small
probe contains only the explicit credit/death stimulus and actual input calls.
Ten Continue builder/oracle unit tests pass, including broken-A, neutral/Start,
missing evidence, truncated trace, changed ROM and wrong input-schedule cases.

**Promotion blocked by a real new fade regression:** full death-art expansion
first encountered #30's obsolete ROM-identity layout selection for Riff. Both
3c5951bf andb9022400 have banks16..31 byte-identical to7130 (SHA256
`f4e4140423d2a77e176591b6cb84ae71d519e4ee2f44dc69c495fcd6b0435e81`).
The generator/storage identity lists now recognize those two exact builds;
independent table-builder equality and Ted latch preimages remain enforced.
Four arena-storage unit tests pass with the new identities.

Fresh full checkpoint generation then fails Ted: mostly blank white arena,
Sara and three projectiles. Same target-only generation on3c5951bf produces
the identical PNG (`6435ceeae68f6c58e062e67be7d35e454fcc47ff22661d4f574fdf8102bad61f`).
This predates Continue; issue #32 tracks it, not assumed natural gameplay
failure. Evidence: `tmp/continue-death-art-02/generated-states` and
`tmp/continue-ted-parent-control-01`. The full nine-boss campaign remains failed.

Separately generated the five supported death states in
`tmp/continue-five-death-states-01`, then ran all five death tests in
`tmp/continue-five-death-art-01`. Shalamar/Cameo/Faze/Penta pass; Troop fails
coherent white-fade CRAM (one old4A29 word remains in its64-byte palette).
All other Troop art/publication/Game Over checks pass, but that is not an
overall pass. Fresh target5 parent state and death test in
`tmp/continue-troop-parent-states-01` / `tmp/continue-troop-parent-art-01`
pass3/3 palette phases. Thus b902 introduces a timing-sensitive fade defect.
Do not integrate/promote this Continue variant; the source builder still ends
at projectile-fixed3c5951bf. Next: retain input sampling during Continue while
preserving the white-fade publication window, then rerun both decisive tests.

### Continue settled-window experiment: rejected

Candidate `d270fe0fa2359ac86cd4df0d06dca1071ef821e325a4a3cc51a44f698b21b8b6`
in `tmp/continue-input-window-01` samples input only when LCDC.window is
enabled and BGP equals E4. It retains the private-bank visual-call mechanism.
The checked-in cold Continue replay (`tmp/continue-window-a-01`) passes:
death1280, native A observed, gameplay1438, no title return through2400.
This is assisted Stage1 evidence, not the reported Stage2 route or hardware.

Fresh candidate-owned Troop checkpoint generation passes in
`tmp/continue-window-troop-states-01`, but its death replay in
`tmp/continue-window-troop-art-01` still fails CRAM2/3. The white-fade row
contains stale4A29 at byte20, just as the ungated experiment did. Suppressing
the sampler during the fade did not resolve the regression; investigate
the bank-switch/mirrored visual-call mechanism and its timing before another
variant. Do not integrate this candidate into the source chain.

Banks16..31 were compared byte-for-byte against3c595 before registering this
exact experimental identity in the arena layout and checkpoint tools. Their
table and structural gates remain unchanged. Eleven Continue structural/oracle
tests and four arena identity tests pass; these do not override the failed
emulator fade test. No hardware access or deployment was performed.

### Continue post-visual sampler: local regression checks pass

Candidate `eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc`
preserves both original visual CALLs at7189..718E. The six-byte tail (including
two source-owned unreachable padding bytes before OAM clear7195) now enters
the fixed bank-call ABI with bank35. That bank contains only the existing
sampler and a stack adapter: replace the discarded death-service return with
6F8C, return through084D to restore bank13, then use the original wrapper
register epilogue. No pre-palette bank switch or mirrored visual calls remain.

Fresh guarded evidence:

- `tmp/continue-postvisual-a-01`: death1280, A observed, gameplay1438, no title
  through2400; 2.87s replay wall time. Final gameplay screenshot inspected.
- `tmp/continue-postvisual-neutral-01` and `...-start-01`: full timeout,
  title2191, no A acceptance; 3.12s and2.77s respectively.
- `tmp/continue-postvisual-parent-negative-01`: identical driver on3c595
  rejects A,450 native checks, no accepted edge, title2191. Negative control
  fails the behavior oracle as required.
- `tmp/continue-postvisual-five-states-01` / `...-five-art-01`: fresh
  candidate-owned Shalamar/Cameo/Troop/Faze/Penta checkpoints and death art
  pass all three palette phases, source publication, viewport and GameOver.
  Troop's previous stale4A29 fade defect is absent. Its GameOver image was
  inspected, showing the expected white/purple text on gray.
- `tmp/continue-postvisual-lifecycle-01`: two HP-zero-assisted restart cycles
  pass, including102 GameOver frames and482 returned-title frame comparisons.
- Thirteen Continue builder/oracle tests,42 GameOver tests and four arena
  identity tests pass. Banks16..31 are byte-identical to3c595; exact new
  identity registration does not relax palette-table or checkpoint gates.

Source construction now includes only this post-visual Continue variant.
`tmp/stream-regressions-source-07` rebuilds the exact eebf candidate from the
original cartridge and palette source, with no retained candidate-ROM inputs.
Historical mirrored variants remain reproducible failed controls, not defaults
of the integrated source chain. Issue28 remains open for the reported Stage2
and secret-area history, broader timing/audio and hardware validation. Ted
checkpoint issue32 still prevents full-nine-boss qualification. No deployment
or hardware access; all work was local while the user played.

### Ted blank-map isolation (#32)

Fresh target4 generation fails on pre-projectile7130 in
`tmp/ted-pre-projectile-control-01` with the identical blank screenshot SHA
`6435ceeae68f6c58e062e67be7d35e454fcc47ff22661d4f574fdf8102bad61f`.
It also fails on restart-parentc693 in `tmp/ted-restart-parent-control-01`;
that image is white apart from Sara (SHA
`77b1cce082a8f07b33b4af1e1e89fb8b0c473783e8a5136812b443b570463d68`).
Thus the defect predates Sara atomic, secret graphics, projectile and Continue
overlays. No new ROM fix has been chosen from this observation alone.

Stock2f325 target4 generation passes in `tmp/ted-stock-dispatch-control-01`
(frame292); its screenshot was inspected and shows Ted and the arena.
Offline inspection of the serialized states finds117 Ted body tile IDs in
the C1A0 source buffer of all three builds. Stock has117 in each physical BG
map; both DX checkpoints have1024 zero tiles in each map. All three have1929
nonzero bytes in the signed BG graphics region9000..97FF. Missing source
graphics therefore does not explain the blank DX maps at these endpoints.
The checkpoints are at different simulation frames, not pixel-parity pairs.

Added opt-in `TED_BLANK_TRACE` to the existing generator probe: read physical
WRAM/VRAM counts at fixed native publication call028A/return028D, and log
FF55 write-watch observations without changing bank registers or game data.
The normal probe behavior is unchanged when the option is absent. This is
diagnostic instrumentation; observer neutrality has not been established.
On currenteebf, `tmp/ted-blank-dma-01.tsv` repeatedly observes576 nonzero
source cells and zero tiles in both destination maps before and after the
publication call, beginning at frames55/57 and persisting through470.
The resulting rejected PNG matches the uninstrumented blank image above.
No FF55 events were logged, but that watch needs a positive control before
absence of events can prove absence of DMA. Next inspect the private bank16
cached publisher/installer and its destination publication, not color values.

Probe SHA256 at this run:
`0196a43c7a5850b2112c54cc6587b89410a657cdde98fe4e194d8a43018c5c7a`;
trace SHA256:
`213fdef552a00e998b5cc97afa460e6ddb903c78de260699dfab91b2d3511801`.
No hardware access or deployment; issue32 remains open.

All issue numbers refer to `struktured-labs/penta-dragon-dx`.

| Issue | Remaining requirement |
| --- | --- |
| #6 | Capture and eliminate residual Sara sprite tearing; retain speed/audio guards. |
| #14 | Restore intended archway occlusion without floor bleed; separate collision from visual layering. |
| #18 | YAML/source rebuild and local restart/five death cases pass; hardware acceptance remains. |
| #19 | Current pin support implemented; validate hardware palette Apply/Resume and position restoration. |
| #20 | Reproduce miniboss red bleed, including suspected menu round trip. |
| #21 | Identify first miniboss tear in continuous frames and add rendered-sprite regression. |
| #22 | Identify teleport-area star palette; make intended pickup gold. |
| #23 | Geometry/BG0 fixes pass assisted native-entry replay; full scene and hardware validation remain. |
| #24 | Verify normal Stage 1 tile colors across scrolling and transitions. |
| #25 | Requested Game Boy-monster palette treatment; art-direction enhancement, not a proven code defect. |
| #26 | Verify secret-area return with/without monster-pause power-up and sustained dungeon rendering. |
| #27 | Characterize recorded Shalamar defect before choosing a fix. |
| #28 | Post-visual sampler source-integrated; A/timeout, five death-art paths and repeated restart pass locally. Exact Stage2 history and hardware remain unqualified. |
| #29 | Closed: paused menu mistaken for a freeze; Select exit verified, no ROM fix. |
| #31 | Source-integrated projectile fix; source/destination copies, assisted return and restart pass locally; broader combat and hardware acceptance remain. |
| #32 | Blank Ted checkpoint isolated to known-broken default libmgba; identical current ROM renders with the documented corrected runtime. Standalone generator now rejects that bad library before testing. Natural-route/hardware and broader qualification remain outstanding. |

Priority: locate first bad entry/return frames, reproduce the transition on the
exact candidate, fix the demonstrated mechanism, then qualify affected routes.
Continue handling the independent sprite, occlusion, palette-art and continue
requirements; a shared fix is not assumed. Keep issues open until their own
acceptance evidence exists.

### Ted #32: destination-latch runtime control (September 28)

Candidate remains `eebf3f190d9d307cb1d3fa714fa2e68b7890fc5309d5da26682ce38cce0134fc`
at `tmp/stream-regressions-source-07/candidate.gb`; no ROM edit was needed for
this generated-checkpoint failure. In `tmp/ted-blank-store-01.tsv`, the CPU
executes `E073` with A=9C but FF73 immediately reads 00. The populated 1024-byte
cache is consequently transferred to $8000 rather than $9C00. The existing
blank-picture gate rejects the result.

This matches the previously documented [mGBA register defect](mgba_cgb_latches_r454.md),
not evidence of a new Ted ROM regression. With the existing isolated library
SHA-256 `20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`,
the identical ROM/probe in `tmp/ted-corrected-runtime-01` passes at frame337,
settles at283, retains FF73=9C, and publishes1024 nonzero map bytes. Its image
was inspected: Ted and the checker arena are visible. The optional trace is
diagnostic; observer neutrality and audio fidelity have not been established.

The standalone generator now applies the existing known-bad-library preflight
for CGB ROMs before cache reuse or emulator launch. A fresh default-runtime
invocation was rejected before creating `tmp/ted-runtime-preflight-current-01`;
the six existing runtime-tools unit tests pass. This does not qualify an unknown
library merely because it is absent from the denylist, nor make old cross-runtime
results interchangeable. Issue32 stays open pending remaining acceptance work.

A fresh run without optional diagnostic breakpoints,
`tmp/ted-corrected-runtime-clean-01`, also passes at frame337/settle283. Its
final PNG matches the traced run exactly (SHA-256
`405172913bf7ca980be6d92cb4f87f2a17234a318a1ef69adb046c97ed50dc60`).
This checks that endpoint only, not full video/audio observer neutrality.

### Corrected-runtime expansion and Stage2 Continue setup

On unchanged source07/eebf, `tmp/source07-nine-boss-corrected-01` freshly
generates all nine boss checkpoints successfully under the documented corrected
library. These are assisted dispatcher entries, not a complete playthrough.
`tmp/source07-death-art-corrected-01` then passes all five supported death-art
cases (Shalamar, Cameo, Troop, Faze, Penta), with all576 phase-specific cells,
noncollapsed viewports, three palette phases, white fade, and colored GameOver.
Ted/Riff/Crystal/Angela are not silently included in the five death cases.

Issue28's driver now optionally accepts a recorded entry state and Stage2,
binds the state hash, records the resolved emulator runtime, and rejects the
known-broken CGB library. The oracle requires the requested active scene at
the death stimulus and return to that same stage. Fourteen Continue builder/
oracle tests pass, including state-tampering and wrong-stage controls.

Fresh level-select-assisted Stage2 state in
`tmp/source07-stage2-continue-entry-01` reaches scene03 at frame614.
The Stage2 trials `tmp/source07-stage2-continue-a-01`, `...-a-02`,
`...-resource-01`, and `...-up-01` all correctly reject: no death scene occurs.
The resource trace verifies that the explicit zero writes take effect at1201;
DCBB subsequently changes to EF by frame2400, and an Up input approaches the visible
enemy without reaching death during this bounded replay. This disproves the
assumption that zeroing these fields alone is a sufficient Stage2 death setup.
No Continue success/failure or new game cause can be inferred from these trials.
Next: establish an actual Stage2 damage/death route before evaluating the A edge;
do not force the scene/PC or relax the death requirement to obtain a pass.

The extended driver still passes its fresh Stage1 control under the corrected
runtime: `tmp/source07-stage1-continue-corrected-01`, death1280, A accepted,
gameplay1438, no returned title through2400. That result remains Stage1-only.

### Stage2 Continue: native decrement-to-zero path qualified locally (#28)

The failed zero-resource setup was explained by the actual bank1:4200 sequence:
`FA BB DC 3D EA BB DC A7 28 10` decrements DCBB before testing zero; setting it
to zero wraps to255. The later zero branch reaches the native death entry4A44.
Setting DCBB=1 at frame1201 instead reaches death1216. This is explicit resource
assistance after a level-select-generated Stage2 state, not natural progression,
collision death, or a recreation of the reported secret-area corruption history.
No scene/PC/palette/controller-register writes are used.

Same retained probe SHA-256
`a9e0c198daef09951e43c7c38d855a0c616959b9448335f8e7fd9e0a15f2ad14`, corrected
runtime, and full2400-frame observation for all four trials:

| ROM / fresh output | Input | Result |
| --- | --- | --- |
| source07/eebf `source07-stage2-continue-one-01` | A | PASS: native A edge; Stage2 resumes1436, no title; credit consumed |
| source07/eebf `source07-stage2-continue-neutral-01` | none | PASS control: full countdown, title2125, no A edge |
| source07/eebf `source07-stage2-continue-start-01` | Start | PASS control: full countdown, title2125, no A edge |
| source06/3c595 `source06-stage2-continue-negative-01` | A | FAIL as required:450 native polls, no A edge, title2125 |

All output directories are beneath `tmp/`. Parent and candidate use independently
generated, ROM-owned Stage2 states (`source06-stage2-continue-entry-01` and
`source07-stage2-continue-entry-01`), both entering at614. Receipts bind ROM,
probe, entry state and resolved runtime; reported wall times are retained there.
The resumed Stage2 endpoint image was inspected. This does not establish full
visual/audio equivalence, natural-route acceptance, or hardware qualification.
Fourteen builder/oracle unit tests pass. Issue28 remains open for those missing
scopes, but the Continue repair now has both Stage1 and Stage2 behavioral controls.

### Secret-return expansion and recorded onset (#23/#26)

Fresh `tmp/source07-secret-return-scroll-01` runs11040 frames on exact eebf,
with the existing corrected library and retained probe83ea729e… . It uses
cold inputs, one doorway-position assist at1201, resource refill, pulsed fire
from1321, and480-frame directional legs after7200. No rendering/cache writes.
Observed route: secret scene09 at1410, fight0A at4085, scene09 at6902,
stage00 restored6903, intro18 at6920, dungeon02 at7109. It remains in dungeon02
through11040, room03. The final image was inspected: the widespread recorded
yellow/red corruption is absent. At3600, all2048 secret CHR bytes match stock
bank13:7400–7BFF, and BG0 is `ff7f947e4a3d0000` (Dungeon).
This is a non-reproducing assisted route, not closure of the yellow-trail report.

A five-second-sampled derivative of the original recording's27:00–28:00 window
is `/mnt/data/tmp/penta-yellow-onset-20260928/contact.png`, SHA-256
`a5c0c41cd78879c686a4a7ec478efb19eb6414a5a74d7b1da283a3d2d505fe53`.
It crops the1200x1080 gameplay region, scales each panel to240x216 and labels
times relative to27:00; use the original recording for exact-frame conclusions.
The sampled sequence shows the item menu initially, then scrolling after menu
closure, partial red wall patches around27:30, widespread yellow/red bands
around27:40, and a gray monster later. Cyan wall patches already exist in the
earlier sample. The separate original27:30 sample also shows a clock-shaped
pickup while red wall patches are already visible. Neither input nor item
activation is proven by these pictures. Secret exit is not required for onset;
the next reproduction should examine scrolling palette publication around
menu/pickup history, without presuming the monster-pause effect is the cause.

### Prior hazard-room history plus secret menu: new paired control

The old later-warp experiment did not test its intended condition: the
frame2401 coordinate write was overwritten at2402, and a hardcoded post1320
input condition canceled the later doorway Down+A press. The exploratory
probe now optionally applies its single position assist at the next016C
game-loop boundary and derives the doorway input window from the warp frame.
No ROM change, scene/cache/palette write, or repeated position forcing.

Retained probe `a75539c085d216544728ab11e4b91bd306539fba8da527e2ae4be8383c124a30`
visits room01 via Up+A before2401, then enters secret scene09 at2612 on both
reported4f5 and currenteebf. Without menu inputs, both enter fight0A at4154;
their exits differ (6243 current versus6269 reported), so do not infer cadence
equivalence. At7200, both remain in scene09 and both attribute planes contain
only palette0. The reported picture has broken CHR; current has restored CHR.
Directories: `tmp/source07-secret-prior-hazard-loop-02` and
`tmp/reported-secret-prior-hazard-loop-01`. Neither reproduces persistent bands.

Adding Select at3300..3305 and3420..3425 opens/closes the item menu during secret
flight. The inspected3360 snapshots give a new visible negative control:

| Run beneath tmp/ | BG0 bytes at3360 | Observed menu background |
| --- | --- | --- |
| reported-secret-prior-hazard-menu-01 | 070607ff7f947eff | pink/green with red speckling, broken CHR |
| source07-secret-prior-hazard-menu-01 | ff7f947e4a3d0000 | expected Dungeon palette and restored geometry |

Both have the identical physical attribute histogram:1850 palette0 cells,
183 palette6,15 palette1. This supports the already integrated BG0-source fix
on a menu path with prior-room history; it is not proof that every stale
attribute is correct. The reported build's7200 picture no longer shows those
bright menu colors, so the trial does not reproduce persistent post-menu bands
from the recording. All runs7200 frames, resource/position assisted, no hardware.

### Recorded pickup review, 23–27 minutes (#22; not a fix)

Additional recording derivatives are retained in
`/mnt/data/tmp/penta-star-review-20260928/`. The 23–26 minute contact sheet
samples every5 seconds (SHA256
`65266b1a0e9740176a3920d78344c0a8ef0dff3cb67b2ffd01edc64c1c21cc11`);
the 26–27 minute sheet samples every3 seconds (SHA256
`432bad131e0b01df81b985b3f65205b4132847ff77c0f261ebeb62590a11a428`).
These are cropped/scaled diagnostic views, not pixel-identity acceptance data.
Labels are offsets plus the indicated23m/26m origin.

Visual inspection shows entry into the already-corrupt secret flight area
between23:30 and23:35, followed by a long item-menu interval. At25:15 the
sheet shows gray P-marked and bright circular pickups; at25:40–25:45 gray
question-mark pickups are visible; at25:50 onward gray multi-point shapes
appear alongside a purple up/down-arrow pickup. At26:00–26:57 that picture
remains stationary with the menu open. A full-size25:45 frame is retained as
`frame-25m45.png`, SHA256
`cc72301317c46e3b9029fe4e2ec5c402390e9beb2630641d23a1bd2c56bd713a`.

This locates additional observable gray pickups, but does not identify them as
the player's earlier teleport-area star. In particular the existing Stage1
atlas's Spiral icon is not enough to label the secret-area multi-point art.
A read-only scan of both retained3360 menu snapshots from the paired runs
above finds none of the atlas's complete19 pickup tile signatures in either
physical map. That scan is limited to those snapshots, not the recorded
pickup locations, and cannot establish a secret-area tile identity or cause.
Next diagnostic must capture the actual pickup location and its native tiles
before assigning a palette. No ROM or palette changes, emulator launches,
hardware access or readiness claims were made for this recording review.

### Current secret pickup attribute inconsistency reproduced (#23/#24)

Fresh `tmp/source07-secret-pickup-gallery-01` completes4080 frames on exact
eebf3f19 candidate using the corrected CGB-latch runtime and single-flight
launcher. It cold boots, applies the established one-shot doorway position
assist at the next game loop after1201, refills resources, and pulses A after
1321. No graphics/palette/cache writes. Snapshots every120 frames reveal a
remaining coloring defect despite repaired secret CHR and BG0 sources.

At frame2880, tile signature CE/CF/DE/DF appears twice on each map. On9800,
the left copy at4/0 has attributes06/00/06/06, while the right at14/0 has
00/00/00/00. On9C00 at4/2 and14/2 the corresponding assignments are all06
and all00 respectively. The screenshot visibly shows the two pale multi-point
icons. The Stage1 atlas calls this signature Dragon, but secret-item semantics
are not independently verified. State SHA256:
`ea6d313f5e1b1982896d926a8e20f3e1d1e47cc4707efe4c254263ce6336c814`;
PNG SHA256 `9ee08c2a4e303809af1323e65212021b72daa70d38ee876a38896b348d669349`.

Frame1920 likewise has AA/AB/BA/BB signatures with mixed06/00 on the left
and all00 on the right; frame2760 has the same disparity for C6/C7/D6/D7.
BG5 itself retains the intended gold/red bytes ff7fff031f000000. The immediate
problem is therefore not an absent gold palette: these cells select00/06.
This does not yet prove which writer leaves those assignments or that it
explains #22's earlier teleport report or #26's persistent yellow trails.
Read-only `tmp/review_secret_pickup_attributes.py` validates ROM CRC/header
bindings and enumerates signatures/attributes in both physical maps, including
offscreen cells. No new ROM patch is proposed until the native secret map
publication and attribute writer are traced. No hardware changes.

Attribute-writer trace follow-up: `tmp/source07-secret-attribute-writers-01`
completes3000 frames on the same exact candidate, core and input/assistance
recipe, adding watchpoints on9804/980E/9C44/9C4E andFF55. The four cells'
last VBK1 stores occur in scene02 at1209–1228, PC6CE4 bank17(hex23decimal).
During scene09 the774 observed target writes all select VBK0:387 at bank1C
PC6DDE and387 at6E36. Thus these tile updates do not update their attributes.
Absence of watched DMA events alone is not relied upon: independent serialized
snapshots at1440,1560,1920,2400,2880,3000,3360,3960 all preserve the exact
2048-byte physical attribute plane SHA256
`254b6c50541dae42c62ff6d3319c586e9a681bedcec1b61eec0e1da74d0aef22`
(1846 zero cells,202 cells assigned06), despite changing tile maps.
This establishes retained dungeon attributes across the sampled secret route,
not merely a missing gold CRAM value. The current scene's C600 table also
does not provide the ordinary Stage1 gold pickup assignments, so forcing the
existing compiler without checking its table would not be a sufficient fix.

Traced and untraced frame3000 PNGs match SHA256
`e718455b798a3293e401fd569fd2fa0184cc88c2ef0c5b8ff96aaa0fdaaa7824`.
This is a terminal-picture check only, not full observer/audio neutrality.
Probe SHA2564ca9b8b37f0fee33ae9adb3d8b80e0bf2fb5f20440214c3eb06906566dfcf626;
the retained trace contains all watched writes, including boot and Stage1.
No fix deployed or implemented yet; repair needs coherent secret-scene palette
lookup and publication rather than a one-time neutral clear.

### Secret attribute trial 01: visual improvement, timing rejection

`scripts/diagnostics/build_secret_attributes_trial.py` constructs an exact-parent
diagnostic in erased bank36, called from bank28's native tile copier. For only
scene09/0A with FFBA7, it compiles a pickup-signature palette table into the
existing SVBK3 attribute scratch and synchronously publishes the destination
plane before copying tiles. This is not integrated into the source build.
Candidate `tmp/secret-attributes-trial-01/candidate.gb` SHA256
`4b00c3134d0f1f6f2508a7e3ed9c129381a0d5d862f361266b348b6430fa3c54`.

The assisted4080-frame cold replay `tmp/secret-attributes-replay-01` completes,
and inspected frame3360 shows both formerly pale multi-point pickups in gold.
Physical attributes now change with the tiles (at3360:2032 neutral cells,
16 BG5 cells), instead of retaining dungeon BG6. However, **reject this as a
release fix**: parent enters boss scene0A at4054; trial remains scene09 through
4080, with world_y1688 versus parent's1188. Even initial Stage1 entry moves
from492 to496 because the shared mapper wrapper adds overhead outside secret
scenes. The plain synchronous compile/wait path changes game progression and
does not meet fidelity requirements. No audio qualification was attempted.
Preserve this candidate as a causal/visual experiment only. A replacement must
avoid the shared-path cost and schedule attribute work within the existing
copy/publication timing budget; changing the test's expected progression would
not be an acceptable fix. Main source07 ROM and hardware remain unchanged.

Trial02 changes only transfer scheduling to48 single-block GDMA transfers in
fresh HBlanks (or the whole transfer with LCD off); it retains trial01's
compilation and shared entry. Built with `--chunked`, SHA256
`c29265219f9ef5b288ce0e1a0e18efba8b1352a3c81a8bf3ec04f7dc86b23ad7`.
`tmp/secret-attributes-replay-02` completes the identical4080-frame assisted
recipe, but still ends in scene09, world_y1580. Trial01 ended at1688; parent
has already entered scene0A at4054 and is at1188 by4080. The chunked wait
reduces the lag but does not remove it, so this variant is also rejected.
Do not infer a speed percentage from coordinates across different scenes.

Three structural unit tests in `tests/test_secret_attributes_trial.py` pass:
helper placement, wrong-parent rejection, and exact hashes/checksums/owned-byte
boundaries for both variants. The ROM-dependent test skips explicitly if the
local parent is unavailable. These tests preserve experimental integrity and
are not gameplay acceptance. The next approach must integrate attribute work
with existing copy/publication rather than adding a separate synchronous pass.

### Combined-copy experiment: partial visual success, transition timeout

`build_secret_combined_copy_trial.py` replaces the secret copier instead of
prepending an attribute-only pass. A bank28 local gate avoids the far call for
non-secret scenes. Bank36 stages both768-byte planes in existing SVBK3 scratch,
then transfers32 bytes per fresh HBlank, returning the native copier register
shape. This is an unqualified diagnostic design, including unqualified audio
and scratch-lifetime behavior; no production integration.
Candidate `tmp/secret-combined-trial-01/candidate.gb`, SHA256
`91f45fd07be958c6e95e87664c07d71010a3e60a9d2550aa224fc94ff40cd607`.

`tmp/secret-combined-replay-01` requested the same4080-frame assisted route.
Stage1 entry returns to parent frame492; secret entry is1404 (parent1406).
Viewed frame2880 shows paired gold pickups and intact secret geometry.
However, the run **times out at40 seconds**, with complete trace rows only
through3981 and a partial3982 row, near world_y1212 in scene09. There is no
success receipt and no4080 terminal frame. Do not count this as a completed
replay, repaired transition, speed match or pass. The timeout's exact cause
is not yet established; do not label a suspected deadlock as verified.
The required read-only post-interruption process check reports no mGBA
processes. The next investigation is the copy/scene-transition boundary,
including LCD/DMA/interrupt state, before any wider test. Source07 and
Rivalmage remain untouched.

### Combined-copy follow-up: scratch collision and bank6 diagnostic

Correction to the preceding timeout analysis: the buffered trace ended at3982,
but a retained `secret-combined-replay-01/frame-4047.ss0` proves that the run
reached scene0A. Trace truncation was not the last executed frame. Replaying
that exact candidate/state for120 frames in `secret-combined-boundary-01`
shows PC D46D, SVBK3 and IE00 from frame4 through120. The trial used D400
in bank3 for staged tiles, overlapping the existing executable row compiler.
This collision is introduced by the experimental copier, not source07.

Changing only the three scratch-bank selectors to6 produces candidate
`tmp/secret-combined-trial-02/candidate.gb`, SHA256
`7c149ac86c0163dc1c60b607e852e3b145c07965a78515f7c7019a621ec93c79`.
The cold, position/resource-assisted `tmp/secret-combined-replay-02` completes
7200 frames with exit status0 and a receipt binding probe SHA256
`db9e8eadfe40a7a3286ef338e064271f78b5ce3aa2a70de482cc7747acf866a2`.
It reaches secret boss scene0A at4047 and returns to scene02 by7037;
terminal7200 is scene02 at world1224/1472. Inspected images3600 and7200 show
secret geometry and the returned dungeon respectively. This establishes that
the bank3 transition lockup is avoided on this assisted route, not that all
secret palette assignments or gameplay fidelity are correct.

The old process handle is gone; a fresh read-only process check found no mGBA
processes. Four new structural tests bind both experimental ROM hashes,
checksums, body placement, rejected inputs and the exact three selector
changes. Together with the attribute-only experimental tests, seven pass.
These tests are not an emulator symptom gate. Current bank6 ownership,
interrupt/DMA safety, full output timing and native audio remain unqualified.
The historical absence of immediate bank6 selectors is not an allocation proof.
Neither experiment is integrated into source07 or deployed to Rivalmage.

#### Paired loop-cadence check of bank6 experiment

Fresh sequential7200-frame cold runs `secret-combined-parent-cadence-01`
and `secret-combined-trial-cadence-01` use the same bound probe, corrected
core path, assisted route and `ENTRY_LOOP_TRACE=1` breakpoint at016C.
Both finish with status0. In the fixed frame window1500 inclusive to3900
exclusive, all sampled iterations are scene09: parent580 versus trial595.
Consecutive sample frame gaps (no exclusions) are parent
`3:20, 4:525, 5:32, 12:1, 65:1`; trial
`3:58, 4:526, 5:8, 13:1, 63:1`. Window boundaries censor the first/last
intervals. This is a measured cadence difference, not an exact speed pass
or a universal speed percentage: route events also differ.
Boss entry is4054 versus4047; returned scene02 is7042 versus7037.
Even the pre-secret stage-index transition differs1231 versus1228.
The local gate still changes execution outside secret scenes.

Loop trace SHA256: parent
`34d4e4d4855c393b4348a556c947a00e63e5186ac516be609917f3c7cb529f8a`;
trial `21e726db31a2e03dd928c9c25d293311ab0b4d5cc9c77647d5ad3db2b3cd3bb9`.
Trial observer-on versus retained observer-off has identical full selected
state trace SHA256
`c0164cc343bdba06d938411d126ab0f273ebe3f48dd1aad9ed813f8e126485a6`
and terminal PNG SHA256
`b2c63c04139dbadf97377277c61ed67bef81dcb9c2533e7de233f36367af0849`.
This is limited observer-neutrality evidence, not full video/native PCM
equivalence. Keep the experiment unintegrated; replacing the copier has not
yet demonstrated preservation of the requested original gameplay timing.

#### Copy-duration isolation

Fresh sequential4080-frame runs `secret-parent-copy-timing-01` and
`secret-trial-copy-timing-01` bind probe SHA256
`2e527df0ff504fc894fc267a6ff97c7f637644019fa617f82b748968562a9b7f`.
The optional observer pairs bank28:6C80 entry with bank1:42ED return,
recording `emu:currentCycle()` and the entry FF01 tag. Both runs complete.
For scene09, all640 parent copies and656 trial copies have an even tag:
the native continuation at42F0 tests that low bit and bypasses the attribute
compiler/publisher on this route. This agrees with the earlier stale physical
attribute-plane finding. Scene0A has both even and odd tags, so it must not
be treated as having the identical missing-publication behavior.

Scene09 entry-to-return cycle deltas, without trimming: parent
min141752, median153760, max185392; trial min128048, median139328,
max167320. These are emulator cycle units and include interrupts/waits,
not an instruction-only estimate or whole-game speed percentage. Different
copy counts prevent interpreting totals as equal-work benchmarks. The trial
really does shorten this copy region; the cadence mismatch is not merely a
different terminal coordinate. The next repair should preserve native
publication scheduling and add secret attributes, instead of compensating
with an arbitrary end-of-copy delay. An existing HBlank-overlap experiment
in `build_later_metatile_overlap.py` is a design reference, not qualified code
for this candidate. No production bytes changed and no hardware was touched.

#### Native-publisher trial: corrects stale attributes, rejected for slowdown

`build_secret_native_pipeline_trial.py` tests the existing pipeline instead
of replacing it. A scene09/stage07-only local gate invokes existing DA13
atomic setup, installs an explicit256-byte pickup lookup table into C600,
invalidates the prepared-buffer marker and resumes the native bank28 copier
at6C85. Native copy body and42ED continuation remain byte-exact; no extra
WRAM bank is allocated. This shared-LUT experiment still requires exit/menu
restoration validation and is deliberately not integrated.

Candidate `tmp/secret-native-pipeline-trial-01/candidate.gb`, SHA256
`f1b981ed779f61fa95911f9124e7ce8747988592e49b32b97baa28c7c6f815e6`.
`secret-native-pipeline-replay-01` completes4080 assisted cold frames using
the bound copy-timing probe and loop observer. Frame3600 visually shows
colored secret pickups and intact geometry; physical attributes have counts
`0:2008, 5:8, 2:8, 4:24`, replacing the stale dungeon plane.
However the fixed1500..3899 window has only467 loop iterations versus parent580.
Scene09 copier samples:522, min133624/median192120/max216552 cycle units.
At4080 it remains scene09, world328/1684, while parent enters boss at4054.
Reject this as a release fix: enabling existing attribute publication alone
does not preserve gameplay cadence. No audio claim or hardware test.
Trace SHA256 `49ce8ff083fcd92f1bb78968152b870a6b629b0128fc8e36b57098277f504411`.
The result narrows the next design to overlapping necessary attribute work
with existing copy waits, rather than a separate publisher or arbitrary delay.

#### Original-game cadence control changes the comparison baseline

Do not treat the color hack's timing as the definition of original fidelity.
Fresh `secret-original-cadence-01` uses original ROM SHA256
`2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30`,
the same bound probe and assisted cold recipe, and completes4080 frames.
It reaches scene09 at1397 and scene0A at4064. The fixed1500..3899 window
contains599 game-loop samples, all scene09. The combined-copy bank6 trial
has595, parent580 and native-publisher trial467. Thus the combined trial is
closer to original loop cadence on this route; its difference from source07
alone is not grounds to reject it as a speed regression. Keep it as a leading
experimental candidate, still unqualified for release. Do not claim complete
fidelity from aggregate counts: the ROMs enter scenes at different frames,
encounters may diverge, and original monochrome versus DX hardware modes and
native audio need explicit qualification. No traces are aligned or trimmed
to manufacture equality. Original loops SHA256
`be5a35098f0fccbb97b574ce4ac75a089aa3fc057ef9d7d4d6fbf5d9d16e2a9b`.
Inspected original frame3600 shows intact monochrome secret geometry.
The next useful combined-trial work is memory/VRAM safety and output/audio
qualification, not adding delays merely to imitate the slower color hack.

#### Combined bank6 trial: observed DMA/interrupt safety boundaries

Fresh4080-frame `secret-combined-dma-safety-01` completes on candidate7c149ac8.
Probe SHA256 `4ed2232e92af18b49fdd64f6f1c6ef4a164e64c19d82f25c17d86c66c2b5e52f`
observes the two decoded bank36 DMA instructions5B65/5BA5 and their return
PCs, all FF70 writes, and interrupt-vector entries. Of31920 paired transfers,
31321 start in mode0 and599 in mode1; ends are31293 mode0,599 mode1 and28
mode2. None is observed starting or ending in mode3. Each uses bank6,
command01, idle FF55 before/after, and148 emulator cycle units between
instruction boundaries. All14181 observed interrupt entries are outside
bank6. Bank6 selectors occur only in the helper at4008,5B5F,5B9F on this run.

`check_secret_dma_safety.py` reports PASS_OBSERVED_BOUNDARIES, deliberately
not a release/hardware-safety status. Four tests include deliberate mode3
and scratch-bank-interrupt mutations plus empty/truncated traces. These
controls reject the targeted bad observations. They do not cover every
possible interruption, bank lifetime, or a transfer crossing a whole unseen
mode interval. Endpoint samples alone must not be promoted to such proof.

Full selected-state trace and terminal4080 PNG equal the earlier
`secret-trial-copy-timing-01` run: SHA256 respectively
`49e1c2247fabc8f301c60afb1d63dff2775b3f832caf6885baa8c2acf494986a` and
`70fc91a86e70b1b47e84b945e2cd13f444aab85731c08c51ca2bb51e07b7c62e`.
This supports limited observer neutrality; full video/native audio remain
unchecked. Candidate remains experimental, source07 and Rivalmage unchanged.

#### Menu plus return route and real broken-parent palette control

Fresh sequential `secret-combined-menu-return-01` and
`secret-parent-menu-return-01` both complete11040 frames. They use the same
probe4ed2232e, cold boot, one next-loop position assist at1201, resource
refills, pulsedA, Select2400..2405 and2520..2525, then directional movement
after7200. Candidate7c149ac8 enters boss at4222 and returns to scene02 at7160;
terminal11040 is scene02/room03, world1176/1048. Inspected frames2460,7680,
11040 show menu, returned dungeon and later movement with intact geometry;
no yellow trails are visible in those inspected return frames. This assisted
route is not a reproduction of every action in the player's recording.

New `check_secret_pickup_attributes.py` validates exact-ROM state identity,
requires scene09, and checks all four palette attributes for each recognized
2x2 pickup tile signature on both physical maps. It includes offscreen cells
and makes no independent secret-item semantic identification claim.
At2460 the trial passes all10 signatures; the matching broken-parent run
has9 signatures and fails all9. This is a real failing parent control, not
only a synthetic mutation. At3600 the trial passes4 signatures; parent has
none and therefore fails closed as unsupported, not as9 repeated failures.
Four tests preserve this control and reject identity/scene mutations; local
ROM-dependent tests skip explicitly if evidence is absent. Do not close
yellow-trails #26 on this result: it proves the sampled secret palette
improvement and a completed assisted return, not the reported full history.

#### Native AV attempt: complete files, invalid gameplay-audio coverage

Fresh sequential4080-frame captures `secret-native-av-parent-01` and
`secret-native-av-trial-01` retain full native AV under
`/mnt/data/tmp/penta-secret-native-av-{parent,trial}-01/`.
Both contain4080 frames and8959520 stereo PCM16 sample frames at131072Hz.
`finalize_native_av_capture.py` validates sizes and wraps unchanged PCM in WAV;
it reports file completeness, not audio acceptance. Tap binary SHA256
`337c75dfaa448939c5089ef60ad78fb854ce46b883eaaf7a35669b258590f2d7`,
corrected core SHA256
`20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`.

The full untrimmed comparison in
`/mnt/data/tmp/penta-secret-native-audio-comparison-01/` fails level/silence
checks (RMS ratio1.09979589). However all11782 changed sample frames occur
at75360..87141, before gameplay. Parent's last nonzero sample is76995,
trial's87141; both have exactly zero output after20 seconds. This is an
invalid gameplay-audio qualification, not proof that the ROM's secret audio
is identical or regressed. Preserve the failed result and full sample deltas.
The launcher uses fast-forward; Qt has explicit fastForwardMute/Volume
overrides. Check capture configuration and require active gameplay PCM before
repeating acceptance. No perceptual listening claim was made.

#### Audio capture recovered; active full-route guard still fails

The current Qt source `CoreController::overrideMute(false)` assigns mute from
`m_fastForwardMute >= 0` while fast-forwarding. Thus explicit0 still mutes
through that branch. The short parent02 capture with CLI mute0/volume256/
fastForwardMute0/fastForwardVolume256 again has no gameplay PCM. Changing
only that override to-1 in parent03 restores active PCM through30.18 seconds
(gameplay peak23028). Saved user configuration was not changed.

Fresh full4080-frame captures parent04 and trial04 use CLI mute0, volume256,
fastForwardMute-1, fastForwardVolume256. Both retain8959520 native stereo
sample frames and all4080 video/state frames under
`/mnt/data/tmp/penta-secret-native-av-{parent,trial}-04/`.
Their complete video and input/sample timelines are byte-identical to their
respective muted01 captures; audio output is now active. WAV SHA256:
parent `d2502d263ab402dc53c00fc19c4e122bf9373dabe5be7c58281ee412c0330ac0`,
trial `4ce09f56b72e3d3eec093fdee9cb991cd1fa6f59ed847381ff8a810434927c25`.

The untrimmed comparison04 still FAILS: RMS ratio1.0111994 passes the2% level
guard and no-added-clipping passes, but silence intervals/blocks differ and
the maximum sample discontinuity is larger. All sample differences remain
in its NPZ; no alignment or exclusions were applied. Different full-route
encounter/timing histories can affect sound, so this is not yet an isolated
secret-copier acoustic diagnosis. It is also not an audio pass. Further
event-local diagnosis and original-game comparison are required; do not
integrate or deploy on the strength of the visual improvements alone.

#### Audio failure localization and row-yield experiment

Retained native timelines locate the largest sample step in scene09 for
both parent (18653 at sample3251708/frame1479) and combined trial02
(20757 at4604552/frame2095). Their scene09 digital silence intervals are
roughly48–57ms, but occur at different events. Registers show the APU enabled;
that is not proof that the silence is intentional or perceptually harmless.

A fresh original-ROM AV control completes4080 frames with8954144 samples,
versus8959520 for DX. Keep the unequal native counts; do not trim to force
comparison. Evidence `/mnt/data/tmp/penta-secret-native-av-original-01/`,
WAV SHA256 `e4c9b2193c8d38a367730b9e75c015b8b3b3bffa0035bec2cce1860e4f783842`.

Combined trial03 adds23 interrupt-service opportunities between compiled
rows, restoring SVBK1 before EI/NOP/DI and selecting bank6 only afterward.
This tests reducing the long interrupt-disabled compilation interval without
changing the palette table or DMA design. Candidate SHA256
`886485509bc0fd33f6515b139e8ab78d5e4e0f940339b9120e22f42a0c3a9c05`,
built with `--scratch-bank 6 --yield-between-rows`. Historical defaults and
trial hashes remain unchanged; four existing structural tests still pass.
Fresh `secret-native-av-trial-05` completes4080 frames and captures full AV.
The fixed1500..3899 window has592 loops (previous trial595, original599).
Frame3600 passes12 pickup signatures. Terminal4080 remains scene09 at328/1120,
so do not claim its boss/return transition verified.

Full-route audio comparison05 still FAILS silence/discontinuity checks;
RMS ratio1.0145244 and no-added-clipping pass. This does not establish an
audio improvement from row yields. WAV SHA256
`610f3fe91c9819f5a2142a61ba7c581f565be6da0a80c30c72a93435f3fa1f8c`.
Retain the variant for bounded interrupt-latency measurement; do not promote
it over trial02 on intention alone. Original audio, event histories and
audible discontinuity still need causal comparison. No deployment.

#### Timer starvation confirmed; row yields remove the measured delay

Fresh completed 4080-frame assisted cold replays in
`tmp/secret-sound-timing-{parent,trial02,trial03}-01/` use probe
`c0ad2f64c6a7047260ac64b39eb575b9abc2fcc3b38cba66dc314e6ccf26da34`.
Each receipt records the exact ROM and assistance. Trial03 exits0; the
read-only process check afterward found no running mGBA. No MiSTer access.

The D2/FC timer nominal period is94208 emulator cycle units. Across every
consecutive pair of scene09 timer entries (not just the prior fixed window):

| ROM | Intervals | Maximum gap | Gaps over1.5 periods |
| --- | ---: | ---: | ---: |
| source07 parent | 3947 | 118696 | 0 |
| combined trial02 | 3938 | 190304 | 286 |
| row-yield trial03 | 3989 | 113208 | 0 |

Trace SHA256 respectively:
`e69d147eec34385b4173e2fc6320994e2f4ec6e0e4a107a6b797f91ea998f3ff`,
`e2d993571f415ffb691bf74eacdbfab82d258035270115b13a7640c475aabe7c`,
`63fe4c360d1e9071e6f1c03fb1b32475ea2b9889a5cabbb769c26f2deb8efc35`.
The comparable1500..3899 frame window likewise has264 late intervals in
trial02 versus0 in parent/trial03. This supports the compilation interrupt
starvation hypothesis and the row-yield mechanism for that specific symptom.
It does NOT resolve the retained full-route PCM failures.

New `check_secret_timer_spacing.py` checks all consecutive scene09 entries,
reports every late interval and cross-scene boundary interval, rejects changed
timer configuration, nonmonotonic clocks, missing observations and IRQ stack
banks other than1. First/last intervals are censored. Trial03 ends still in
scene09, whereas the other runs exit it; this is not transition qualification.
Its test authenticates all three retained traces and requires actual trial02
to fail. `python3 -m unittest discover -s tests -p 'test_secret*py'` passes32
tests, including the new row-yield structural check. Local evidence tests
skip when their ignored fixtures are absent; these are not32 fresh emulator
campaigns. Observer neutrality, audible fidelity, shifted DMA boundaries and
trial03 boss/return coverage remain unqualified. No integration or deployment.

#### Row-yield DMA boundaries and assisted return replay

Follow-up `tmp/secret-row-yield-dma-safety-01/` completes4080 frames, exit0,
same trial03 ROM/probe as above. DMA sites were decoded from the exact helper:
bank36:5C62 and5CA2. There are26 bank6 selector return PCs (entry,23 row
yields,2 DMA loops); these differ from trial02 and must not reuse its three
hardcoded selectors. The retained test binds the ROM SHA, helper bytes and
trace SHA, derives the26 selectors, and requires the old selector set to fail.

Observed31824 paired transfers and14192 interrupt entries pass the boundary
guard. Starts:31216 mode0,608 mode1. Ends:31210 mode0,608 mode1,6 mode2;
none mode3. No observed interrupt runs with bank6 selected. Trace SHA256
`e82ee32b03a4072a7cf5d166997bd1c19e4e825a7025a8936803e41fdcdaa7fa`.
This is still endpoint evidence, not full hardware VRAM access proof.
The full gameplay trace and terminal PNG match the timer-observed trial03
run exactly; no full PCM/state observer-neutrality claim follows.

Separate `tmp/secret-row-yield-return-01/` completes7200 frames, exit0,
with the same assisted recipe, audio enabled, no additional DMA observer.
Scene09 begins1404, scene0A4137, scene09 resumes6748, stage card6766,
Stage1 scene02 resumes6959. Terminal7200 is scene02 at1224/1472.
Visually inspected4080 secret corridor and7200 returned dungeon: geometry
is present and dungeon colors are restored in that terminal image, with no
obvious yellow trails there. The first scene0A image still contains the
prior corridor during transition; it is not a boss-art acceptance screenshot.
No claim of matching the player's full trail/monster-powerup reproduction.
Return trace SHA256
`47bb321f06430fa07505c192910a02a4f0505ee788415cd65ab672139ce3e508`;
terminal PNG `a5ad469b46fee077f68edb2bf4abe1eb4b92944972e4cdd6ab0e13deec997b14`.

Focused secret tests now33/33 passing (unit/retained-evidence tests, not33
fresh emulator runs). Audio comparisons remain failed and bank6 ownership
is not globally audited. No promotion, deployment, or hardware interaction.

#### Memory-owner search and original-audio control review

Read-only current-source search found an older Stage7 exact-triple-cache
experiment describing SVBK6/7 ownership. Its builder explicitly records
`do_not_emulator_run: true` and rejects its cost/ownership; it is not in
`build_stream_regression_candidate.py`'s construction chain. Do not confuse
this abandoned experiment with a live owner in source07.

The exact source07 ROM contains63 `E0 70` byte matches and no `EA 70 FF`
matches. None has an immediately preceding `3E 06` instruction. Many matches
are graphics data, and indirect stores/copied WRAM code are not excluded by
this scan: it is NOT a complete ownership proof. Existing nine corrected-core
boss checkpoints all pass source07 ROM CRC identity and contain identical
4096-byte bank6 data, SHA256
`237b8e72d9f0a43fffbdd4444b1e4673b9a1283bf7589c8dfdd78749af3ad2ed`.
These are generated checkpoint observations, not nine complete campaigns or
a writer canary. They give no evidence of a competing bank6 owner there.

Re-measured the retained full, unmodified active native WAVs with the existing
audio measurement routine, including the original-ROM control:

| Capture | Native sample frames | RMS | Peak | Largest adjacent sample step | >=20ms silence intervals |
| --- | ---: | ---: | ---: | ---: | ---: |
| original01 | 8954144 | 3078.789 | 24519 | 23080 | 40 |
| parent04 | 8959520 | 3158.101 | 24025 | 18653 | 39 |
| trial04 (combined02) | 8959520 | 3193.470 | 25932 | 20757 | 39 |
| trial05 (row-yield03) | 8959520 | 3203.971 | 23759 | 21518 | 37 |

All four have zero clipped samples. The original's largest step exceeds
both trials', so a step larger than this particular DX parent's maximum is
not sufficient evidence of a new pop. Conversely, these aggregates cannot
prove that either trial sounds correct: routes/encounters and native sample
counts differ, and the original is a DMG-mode control. Preserve failed
full-route comparisons unchanged. Next audio work should identify whether
the differing events are native music/effects or unintended commands before
another timing patch; do not weaken the current guard to force acceptance.
No acoustic listening claim and no release qualification.

#### Sound-command origin/consumption replay

Fresh sequential4080-frame runs `tmp/secret-sound-commands-{parent,trial03,original}-01/`
all exit0. Exact candidates remain source07, row-yield03 and original above.
Probe SHA256 `307382672078b2cd25a4fd6f4aa7f893d62cddc4b315ca5ba808ad0bdd6414af`
adds optional, uncapped RST38 request and bank3:45B6/45C2/45C7 engine
read/reject/accept records. Those engine bytes are identical in all three
ROMs. RST38 itself ends RET in DX versus RETI in original; do not assume
identical interrupt timing. Existing assistance/input/audio options unchanged.

All consumed commands match the last pending request, and all accept/reject
decisions obey the native priority comparison. No terminal pending event.
Parent236 events,5 overwritten requests; trial289 events,10 overwritten;
original272 events,2 overwritten. Overwrites are explicitly retained, not
silently dropped as unmatched telemetry. Largest request-to-read delay:
parent91784, trial98984, original91160 emulator cycle units.
Trace SHA256 respectively:
`5d1c002ab468679de12f9a6dac7f7a231e83b240a82f79298531f00eee0353e4`,
`391856e838a246ac6255e0fca11f832a18a8f10a8284218037e5cfa56c016afa`,
`ed5909757f40663653c07fceeb351bb3102f886ec38fe7db1af3e6a3479f2cfc`.

Scene09 differs in native request history: command26 requests are40/43/49
in parent/trial/original, with21/22/18 accepted. Command1B is accepted18/24/24
times. Thus full-route WAVs include different sound-effect sequences; they
are not isolated identical-event acoustic comparisons. This does not prove
the changed gameplay histories benign or establish music/output fidelity.
No unrequested engine command was observed in these runs.

`check_secret_sound_commands.py` records every overwritten request and fails
unrequested consumption, wrong priority, missing decisions, clock reversal,
empty or terminally incomplete evidence. Deliberate FF-command mutation
fails.37 focused secret tests pass, including all three authenticated retained
traces. All three gameplay traces and terminal PNGs match their respective
earlier captures; full PCM/state observer neutrality remains unproven.
No ROM change, integration, deployment, or hardware interaction this pass.

#### #20 Gargoyle menu hypothesis: short paired replay does not reproduce bleed

Added an optional scratch-probe native-spawn recipe based on
`probe_all_minibosses_visual.lua`; no ROM descriptor, palette or map edits.
Failed setup runs `miniboss-menu-source07-01`, `miniboss-menu-reported-01`
and `miniboss-menu-source07-02` never reached FFBF1. The copied setup wrongly
reset DCB8 repeatedly, preventing section progression; preserve these as
unsupported encounter tests, not passing red-bleed controls.

Corrected setup resets DCB8 once at560, moves Right with pulsed A from492
until FFBF nonzero, and accelerates spawn counters/entity slots as explicitly
recorded in each receipt. Resource assistance remains enabled. Probe SHA256
`f1ec803e33f64937c38244b2691af6053a4ad8bf01963fe324614aa2966be68f`.
Fresh sequential1800-frame runs, all exit0:
`tmp/miniboss-menu-source07-03/`, `tmp/miniboss-menu-reported-03/`, and
`tmp/miniboss-no-menu-source07-03/`. Source07 is eebf; reported build is4f5a.
Both menu runs press Select1350..1355 and1470..1475. This tests the game's
menu button, not the player's uncertain literal Start-button hypothesis.

By sampled frame600, all three have scene0A, FFBF1 and the full native
descriptor3031323334. Inspected source07 screenshots1320/1410/1800 show
Gargoyle before menu, menu open and restored gameplay. Reported-build1800
looks the same; no obvious red scenery bleed in these reviewed samples.
In both menu runs the64 BG palette bytes and OBJ6 remain unchanged at
1320,1410,1560,1800. Both physical attribute maps change during the menu,
then return byte-for-byte to the1320 state at1560 and1800. This short,
assisted, stationary combat sample does not reproduce #20 and is not a fix.
It excludes neither transient raster artifacts nor the player's longer
moving/firing/damage sequence. Issue remains open; no ROM or hardware changes.

#### #20 recording context and spike-room combat extension

Additional diagnostic recording samples are retained in
`/mnt/data/tmp/penta-miniboss-recording-review-20260928/`: native1080-second
frame plus downscaled contact sheets over240–360 and480–720 seconds.
The contact sheets are sparse search aids (5s/10s sampling), not continuous
onset evidence. They show an early Gargoyle fight beside rotating spikes;
the later fight around600–640 seconds is in the pickup/start corridor.
No clear red-bleed onset was identified in these reviewed sparse images.

Extended the reported4f5a build replay to a spike-room context using only a
one-shot position assist at the next game loop after frame520, world72/388
(coordinates read from the historical spike fixture, not a restored old
machine state), plus the previously documented native-spawn/resource aids.
`tmp/miniboss-spike-menu-reported-01/` completes1800 frames and reaches
Gargoyle FFBF1. Reviewed1320/1410/1800 show the spike, boss, menu and resumed
fight. BG palette SHA prefix2df58b72d35d and OBJ6 `00001f600f400000` remain
stable across1320/1410/1560/1800. No obvious red scenery bleed in those samples.

`tmp/miniboss-spike-combat-reported-01/` completes2400 frames with Up+pulsedA
after1200 and the same Select menu round trip1350..1475. Reviewed1560/1800
show movement/firing through the rotating-spike corridor without obvious
scenery bleed. By2400 the native descriptor has advanced to a different,
red miniboss near the northern edge; do not label that red actor itself as
Gargoyle palette corruption. This extended run still does not establish the
reported transient defect or exactly reproduce the player's input history.
Both runs exit0, probe remains f1ec803e…, receipts record every assistance.
Trace SHA256 respectively:
`cf0a0303bc8129b4793c3ad2a22666ea27b08c95aa886703f52c00f815f73577`,
`b51b1606dfaf4b9aaa3ed74cdfa59e5dae40d19880fa31db08ec2e4445e41ab7`.
No fix claimed for #20; no candidate changes or deployment.

#### #14 ceiling repair rebased onto projectile/Continue-fixed source07

The priority builder now explicitly accepts source07/eebf in addition to its
exact historical7130 parent; all byte preimages, two mirrored caller sites,
and entirely-empty extension banks33/34 remain checked. Receipt parent SHA
comes from the actual input. Historical default construction is unchanged.
Eight builder tests pass; the source07 test bounds every changed byte and
checks stock graphics bank32 and Continue bank35 are untouched.

`tmp/ceiling-source07-combined-01/candidate.gb` SHA256
`f7896dee8620a85ca3e1a9596647968557cf3fa8f4cee58a9b10189ebaad0898`
contains the same combined flash/priority mechanism on source07. It is a
separate experimental build, not integrated into the default source chain.
Fresh cold1216-frame doorway replay `ceiling-source07-doorway-01` passes the
unchanged original-ROM gate: world1240/1356, camera0C08, identical OAM
positions, all four priority bits set, zero exposed pixels in the256-pixel
overhang footprint. Its reviewed PNG is byte-identical to the earlier passing
trial. Fresh source07 control `ceiling-source07-negative-01` fails the same
gate with192 exposed pixels. Both use the same current probe f1ec803e…;
the retained original reference remains an explicitly reused older capture.

`ceiling-source07-floor-01` exercises600 post-warp moving-floor frames:
zero frames with any Sara OBJ-behind-BG bit set, zero installed-helper byte
mismatches. Priority trace SHA256
`8c444d2f8cabb7fc1c544d7f1ce0dd3cb0108d91a478a1559e127d2ae2efd5e2`.

`ceiling-source07-secret-return-01` completes7800 frames: secret09 at1414,
boss0A4068, secret09 return6893, card6911, Stage1 scene02 at7106. Unlike the
old projectile-corrupted parent experiment, no unexpected death/restart is
observed on this assisted route. The helper remains intact in all6600
post1200 samples. Full trace SHA256
`1c3ba6d7ba69fa05151d35b539bd72b4ebcfada6c5798ccba8d73ce09a00818e`.
This clears that specific prior outcome failure, not all collision/cadence,
audio, arbitrary-archway or later-stage lifecycle qualification. All four
new replays exit0. No MiSTer interaction, source-chain promotion or deployment.

#### #14/#23 combined repair: lifecycle pass, menu timer guard still fails

Experimental `tmp/ceiling-secret-composition-01/candidate.gb`, SHA256
`00f2629895d886d36dee8c1e1a9e1c3d47e681760ac40ec9d71f99f94a683492`,
combines ceiling-source07 with bank6 secret copying and row yields. This is
not the default source chain or a release-qualified build.

Recovered the earlier run's terminal receipt (exit0, no emulator left running).
`ceiling-secret-composition-return-01` completed7800 cold-boot frames with
position/resource assistance, pulsed fire and Select menu at2400/2520.
Frame2460 passes all10 observed pickup-signature palette matches on both maps;
these signatures do not independently establish secret-item semantics.
Reviewed native frame7800: returned level geometry and colors are visible.
This is not a full yellow-trail or arbitrary-transition acceptance claim.

Fresh `ceiling-secret-composition-gameover-01` passes the checked-in
`verify_gameover_restart.py --sequence --saved-game`: two accelerated HP-zero
Game Over/title/new-game cycles,102 Game Over frames and482 title-frame pairs,
including stage-card/selector validation. Corrected mGBA CGB-latch library used.
This does not establish natural hazard damage, sound fidelity or hardware parity.

The unchanged timer guard FAILS the combined route:4109 scene09 intervals,
three over141312 cycles, maximum147120, all during menu frames2400..2519.
Trace SHA256 `d7efa2d19d8cc0b017ad454f866291c6a94cd94407eb8b850b7043a11d5b7753`.
Fresh4080-frame controls use the same probe f1ec803e and menu/assistance settings:

- `secret-row-yield-menu-timing-01` (886485, no ceiling repair):3989 intervals,
  three late, maximum144128; trace
  `777f65ad03702f721c310c7b2dd0d89874657787522e2ea7a6d9ea13d70cc6f1`.
- `secret-source07-menu-timing-01` (eebf parent, neither repair):3986 intervals,
  five late, maximum147752; trace
  `33293c8b5788cecc4e93716564aa03b144ed9738c0f5381efdafb39f1f0f0923`.
- `secret-original-menu-timing-01` (original2f325):4000 intervals, zero late,
  maximum112048; trace
  `9eead241aaf5197ea948801d6fe94b09c54a4722aebbab1bcf09335c14f2bf3e`.
  The CGB bank1 assertion is unsupported on the original DMG run (SVBK reads
  differently), so the overall checker result is NOT a pass. Interval statistics
  above remain raw observations; no bank normalization or trace editing applied.

These controls disprove the ceiling repair as the sole cause of menu timing
failures, and identify a parent DX menu-path difference worth investigating.
They do not establish the responsible instruction or audible impact. Preserve
all failures; do not omit menu frames or relax the threshold. Added retained
negative-control coverage for both experimental menu traces;39 focused secret
tests pass, including assertions that these actual runs FAIL the timing guard.
No MiSTer interaction, deployment, issue closure or readiness claim.

#### Menu timing localization: delayed IRQ returns to bank20 reveal

Read-only investigation for #23 extended the scratch sound-timing observer to
record the stack word at each event. At timer vector0050 this is the interrupted
PC; at audio-register writes it is merely a stack word, not necessarily a caller.
New probe SHA256
`6a457941d527ec3b376069214a34a40d8a08011001dd54363700c5d891b2ad0b`.
Fresh `secret-menu-irq-return-01` replays source07 for2600 frames with the same
assisted secret/menu inputs. Exit0. All five late intervals exactly reproduce
the prior source07 trace's cycle gaps:147576,144120,147752,145424,141976.
Every delayed timer entry has bank14(hexadecimal bank20) and interrupted
PC7F0C. This localizes servicing to the menu reveal's interrupt-enabled wait,
not the new secret copier or Sara priority helper.

Source review: `menu_icon_colorization.build_menu_helper` disables interrupts
before its six-row, ten-two-cell-HBlanks-per-row attribute pass. Bank20's
retained reveal helper at7F00 saves IE, restricts service to Timer and enables
interrupts before waiting for the safe reveal edge. The long preceding DI
region is the next causal hypothesis to measure; no instruction-level duration
measurement or repair is claimed yet. A prospective yield must preserve VBK,
registers, window publication ordering and VRAM-safe write timing, not merely
make the timer-spacing statistic pass. No ROM change or hardware interaction.

#### #33 menu timer yield: first measured improvement, experimental only

Filed https://github.com/struktured-labs/penta-dragon-dx/issues/33 after searching
open/closed issues. Fresh source07 `secret-menu-critical-01` measures116 paired
bank20 DI4031/reveal-EI7F09 boundaries:55032..55752 emulator cycles each, with
no unmatched entry. The timer-pending flag is present at many reveal entries.
Probe SHA3824e6fb750548ef1ce6168a1d7de280aa925ec0c0f39af26ed9dbc8aa991c7c.

`build_menu_timer_yield_trial.py` makes an exact-source07-only experimental
patch: a checked free bank20 cave saves all caller registers and IE, exposes
VBK0 and enables only Timer for EI/NOP/DI, restores VBK1/IE/registers and
executes the displaced pair-prefix instructions. The unchanged pair body
reacquires its HBlank after the yield. No cached safe-edge reuse.
Trial `tmp/menu-timer-yield-trial-01/candidate.gb` SHA256
`18e34994fed287d66af648c8756ce78c5c28c1943e1ac154446df59e3643df68`.

`secret-menu-yield-timing-01` completes2600 frames using the same assisted
secret/menu recipe, with audio enabled and no critical-boundary observer.
The unchanged timer guard passes1780 scene09 intervals, zero late intervals,
maximum118696. The source07 control has five late intervals in the same prefix.
Trial trace SHA256
`c44f6fdd73037012f5fe6296ab994d763a63f4d8db4c0af275142f6b8862f29e`.
Reviewed frame2460: menu image matches source07 byte-for-byte, PNG SHA256
`a964efa75d00b363d61277002cc1048f8de072767cc446519c2f8d702be9e2b6`;
serialized VRAM and both palette arrays also match exactly at that snapshot.
Three focused tests pass, including the retained failing-parent timing control.

Not yet qualified: full temporal menu graphics/VRAM safety, refresh/input
cadence, native PCM, all menu routes, or composition with ceiling/secret repairs.
The per-pair save/yield overhead is an explicit remaining tradeoff to measure.
Issue33 stays open. No default-source promotion, deployment or MiSTer activity.

#### #33 tradeoff check rejects per-pair refresh slowdown

Fresh paired2600-frame replays with identical probe47603d8e…:
`secret-menu-parent-safety-01` completes116 menu publications,6960 attribute
pairs; `secret-menu-yield-safety-01` completes only59 publications,3540 pairs.
All observed before/after pair boundaries have STAT mode0 and VBK1. The timer
fix nevertheless roughly halves menu refresh count and is NOT accepted.
Parent attribute-pass/reveal spans55032..55752 cycles; pair-yield spans
118488..134208. Critical-trace hashes respectively
`a56a1b451774ad41e60f2fa0812883398ed4297b3622de87f49bef047a8f91d7`,
`ca6b15e47116ce1916bda9d3b2539e6dc86757b515b751bc04ee46b695e9b969`.

First row-yield variant ce447b9… was invalid: overwriting the two-byte row
prefix also overwrote the inner loop's PUSH BC target. It timed out after40s;
partial output is failed evidence, not a completed replay. Read-only process
check confirmed no remaining emulator before the next run. Retain this failure.

Corrected row-tail variant `tmp/menu-timer-row-yield-trial-02/candidate.gb`
SHA256 `b6f637e8fdf55b816834b670386cb1d1c39fc42f0de69ae17f3e2b9ec1b1ff9b`
preserves that branch target. `secret-menu-row-yield-safety-02` exits0 at2600:
112 publications,6720 pairs, all pair-boundary samples mode0/VBK1, pass spans
60104..79992 cycles. Timer guard passes1780 intervals, maximum118696, zero late;
timing trace `bff3c9a95da8e1e5bb50b8043e4dcb725fb08e257da0e9b0f093d054dbef8288`.
Critical trace `a15a9d43dc902d59629baf3e090bb65ad3310870355b9f9605b22d0c31255455`.
Menu frame2460 PNG remains identical to parent. Added source test preserving
the inner-loop target and pinning the corrected row variant.

112 versus116 publications is still a measured cadence difference, not an
equivalence pass. Further optimization or original-game cadence comparison,
temporal graphics/input validation and PCM remain required. No promotion.

#### #33 conditional yields do not recover the missing refreshes

Two further source07 experiments retain all previous variants and add explicit
builder switches. Pending-only row-tail trial03 SHA256
`ddccb54e26681485a8f8008ff4d439b5f5bb45db2b561ae71166cb94ab6cbdfd`
skips register/IE/VBK shuffling when IF.Timer is clear. Midpoint-only trial04
SHA256 `cf5f517c29978cb119725d1ee4c0aeefcf51299e245bf2943d758f6aa744e8ad`
additionally checks only the third row tail (B=4 before native decrement).
Both preserve AF on conditional exits and reacquire HBlank before later writes.

Fresh2600-frame `secret-menu-row-yield-safety-03` and `-04` exit0 with the same
probe47603d8e and assisted menu recipe. Both still complete112 publications,
6720 pairs; every observed pair boundary is mode0/VBK1. They therefore do NOT
recover the116-publication parent cadence despite lower minimum pass durations.
Trial03 pass duration59800..79624, timer maximum118696; trial04 duration
58608..79616, timer maximum119976. Both have1780 scene09 intervals, zero late.
Timer trace SHAs respectively
`411bea64f55f62fab5feff7bd89ec47ce502333d342e2250e759f8b20939d14f`,
`9157febe99ac21628a8810a0e06c66e31d3ac34aeda46fbba47c9b19deaed74c`.
Critical trace SHAs respectively
`53f66f79bc2c7d55e60c2971d36a31f4570eb9f112cd52e2d9e68f4680ce252f`,
`f436adb896613f268603ccece4b15952fdb7399f58f650403581a1cfcb32169f`.

Five focused builder/timer tests pass, including pinned variants and conditional
branch targets landing on POP AF. These are not broad release passes. Successive
overhead reductions have not changed publication count: next compare original
native menu cadence and frame-boundary behavior before further byte-level
optimization. No cadence waiver, ROM promotion or MiSTer action.

#### #33 original native menu-copy cadence comparison

Fresh2600-frame cold assisted replays instrument fixed-bank native tile-copy
entry200E, common to original and DX. Probe SHA256
`3cdc8615814013a43e98e0bc4c5116078810f58756d7d0502dca56b686e917cd`;
all use Select2400/2520 and exit0. Counts over the explicit2400..2519 window:

| Run | ROM | Calls | Consecutive frame-gap counts |
| --- | --- | ---: | --- |
| secret-original-menu-cadence-01 | original2f325 | 258 | 141 zero-frame,116 one-frame |
| secret-parent-menu-cadence-01 | source07/eebf | 116 | 111 one-frame,4 two-frame |
| secret-midpoint-menu-cadence-01 | trial04/cf5f | 112 | 103 one-frame,8 two-frame |

Original first/last entries are frames2403/2519; both DX runs2400/2519.
These are routine-entry counts, NOT unique rendered frames or a measured input
latency result. The original can call more than once within a display frame.
Raw trace hashes, in table order:
`64035e53e63e6d3cd5b76ac6f24b9acedeea7b9f79fbfc3ad5f55ef62d1e49f5`,
`5bf24344fecc06af0baa67c743212f947859d135bcb0e964ec5f888f13283131`,
`fe056ced657f37afb8925e8cff13347f0259cbf4e21fe39b1e505d2e2e802985`.

The parent is already substantially different from the original on this menu
work metric. Matching116 alone would not establish native fidelity. Further
yield tuning alone has not recovered cadence; investigate redundant attribute
publication/ordering and actual menu input delivery next, while retaining the
timer-delay guard and graphics safety. No acceptance claim or deployment.

#### #33 native menu-category input comparison

Initial `secret-{original,midpoint}-menu-input-01` traces watched DC0B, which
is the map selector, not the menu category. Right/Left also interact with
DCDC/DCDD, continuously refilled by the resource-assistance recipe. Retain
these runs as non-coverage; they cannot establish menu responsiveness.

ROM inspection identifies native Down/Up handlers1EA9/1E9D updating DCDB at
1EB5. Corrected probe9567ff4646c18c3692499b0134b77e09a4947badf2b1258367e63a2fae6daad0
watches DCDB and presses Down2420..2425, Up2460..2465 (Select2400/2520 unchanged).
Fresh `secret-original-menu-input-02` and `secret-midpoint-menu-input-02`
both complete2600 frames. Each records category01 at frame2420 and category00
at2460, with writes from1EB5. Thus neither six-frame pulse is lost or delayed
to a later sampled frame on the experimental midpoint trial relative to the
original. This is state-update timing, not rendered cursor latency, single-frame
pulse coverage, item consumption, repeat-rate or all-menu responsiveness.

Input trace hashes: original
`f19fa1895c3d363afbb70531105243b72e0250c4a1008c0636618a0a63c13a31`, trial
`410340e5a9380e019a0ac1fd293d86fa28d4cfa51f5e91bd0a1125ecf3550cc7`.
Added retained trace test for exactly these native category updates. Refresh
cadence differences and audio/composition qualification remain open. No deploy.

#### #14/#23/#33 composition replay and restart lifecycle

The menu-yield builder accepts the exact ceiling-secret00f262 parent in addition
to source07, retaining preimage/free-cave checks and recording actual parent SHA.
Seven focused tests pass; the new composition test bounds changes to bank20
and checksum bytes and preserves extension banks32..36 byte-for-byte.
Experimental `tmp/ceiling-secret-menu-composition-01/candidate.gb` SHA256
`0847fb0fda65b365a65a816f06b5a6ebd970613c3ff5acc09b297f8c7e20b853` uses the
pending-only midpoint menu yield. Not integrated into the default source chain.

`ceiling-secret-menu-return-01` exits0 after7800 cold assisted frames with the
Select2400/2520 recipe and probe9567ff46…. Secret09 at1408, boss0A4284,
secret09 return6903, card6921, Stage1 scene02 at7116. The route timing differs
from the no-menu-yield parent; this is not gameplay/audio equivalence evidence.
Full trace SHA256
`cbd9f22bac0c0fe2629ca61d586b534ca8ef6ab8accbbecb4dfcfa94da0a3a1c`.
All6600 post1200 priority-helper samples match the previously validated helper.
The unchanged timer guard passes4313 scene09 intervals, zero late, max120880;
trace SHA256 `083a25d2ae804915e07a294cad09c7075869cdb8941a495440c69bc4a6c6a711`.

Frame2460 passes10 pickup-signature matches. Frame3600 yields FAIL with zero
matches, retained as unsupported coverage rather than a palette pass; reviewed
frame shows combat imagery and room geometry, and its world position328/1744
matches the no-menu-yield parent's frame3600. This does not establish why no
pickup signatures remain. Reviewed terminal7800 has visible colored returned
dungeon geometry; not an exhaustive trail/transition visual qualification.

Fresh `ceiling-secret-menu-gameover-01` passes checked-in accelerated two-cycle
Game Over/title/restart verifier with --sequence --saved-game:102 Game Over
frames,482 title pairs and stage-card/selector checks. Corrected CGB-latch mGBA
library used. No natural hazard damage, PCM or hardware acceptance claim.
Cadence tradeoff, temporal graphics and audio remain unresolved; no deployment.

#### #33 quartet-copy experiments: intact graphics, timing still fails

Rather than add more yields, `build_menu_quartet_trial.py` tests preparing four
attributes on the stack, then writing four cells in one fresh HBlank. The row
entry404A jumps to a checked free bank20 cave; original row-tail406F, hidden
columns and palette lookup table are retained. All stack words are balanced;
the output span is48 CPU cycles of four LD-A/LD-[HL+] pairs. This static count
is not hardware acceptance. No new persistent scratch allocation is introduced.

Trial01 SHA `c5b3e60e794b4df4dd7d399bc0b3b0b32a5090a1d978f80ecdde660de26da1b9`
uses the existing palette lookup subroutine. Trial02 SHA
`0d1264f9127be15310ac2651a1c4443251aa54b87e50fde711e39a039062c24e`
inlines lookup because destination HL has already been saved.
Fresh2600-frame runs `secret-menu-quartet-safety-01`/`-02` both exit0 with
probe3cbb42e8… and exact builder-supplied write-boundary addresses. Both give116
publications and3480 quartets, all sampled before/after write boundaries in
mode0/VBK1. Frame2460 PNG matches parent exactly (a964efa7…), and full serialized
VRAM has zero differing bytes. Three focused builder tests pass.

Neither trial solves the timer symptom: trial01 has7 late intervals/max148664
and copy durations57064..60472; trial02 has4/max146864 and54680..55544. Despite
halving HBlank write groups, preparation/phase waits do not halve pass duration.
Timer traces respectively
`ae6319a240d7865ae4f0b0556c12ea1dcc8425343ab555dc2c29110864a94bfb`,
`bbb8a4b6014406cb80ee55fd47bac1790a612f46970a5dfcd5cee18283908b72`.
Critical traces respectively
`31a5c27c6071d849c831a8ccabda8f38e696d60f932f60f636e79db165f1c68e`,
`e76cf142338cc6b223c7ea676e2a49b8086f5829da4a85a8fd2aa819484cad3f`.
Both remain rejected as fixes. No main-source promotion or deployment.

#### #33 full-row stack staging reduces, but does not eliminate, delay

Experimental `--stage-row` variant prepares20 palette values in transient AF
stack words, then consumes five four-cell groups right-to-left with fresh
HBlank waits. This uses46 additional live stack bytes including saved registers,
no persistent scratch bank. The sampled parent menu SP is DFEB; allocation
notes and source search did not identify a DFBD+ persistent owner, but full
stack-depth/lifecycle qualification remains outstanding. Code occupies checked
empty bank20 space starting7C00, not the prior7E00 cave.

`tmp/menu-row-staged-trial-01/candidate.gb` SHA256
`ef44aeb52511c76e2d42b1a81566114341ac2ffe912d2a714025fd955ddf7118`.
Fresh `secret-menu-row-staged-safety-01` exits0 at2600 frames, same assisted
Select2400/2520 recipe. The probe accepts every builder-supplied quartet boundary
so all five groups are observed, rather than only the first. There are116
publications/3480 quartets, all before/after samples mode0/VBK1. Pass durations
49128..49864 cycles improve over parent's55032..55752. Frame2460 PNG matches
parent a964efa7… exactly and full serialized VRAM has zero differing bytes.

The unchanged timer guard still FAILS: two late gaps141672/142984 at2440→2441
and2493→2494,1780 total scene09 intervals. Timer trace SHA256
`4f43eaf4569e607aef3b14e9c838b193dbff9c75aef7186dce270e9bef212749`;
critical trace `223816f22a708bba22cff9991db2adce3e1c6572dd13ada8c1c5a1e340e791cf`.
Within-row write gaps mostly872/936/952 cycles; row-compilation gaps mostly
4520/4584/4600. This localizes remaining cost to row preparation rather than
per-quartet output. Four focused builder tests pass, not the runtime timer gate.
Retain as incomplete improvement. No deployment or readiness claim.

#### #33 fast row compilation passes timing without the yield slowdown

`--stage-row --fast-compile` unrolls the20 lookups and loads the ROM-table high
byte once per row, preserving the same46-byte transient stack budget and all
five HBlank write groups. Prior builder variants retain their exact bytes.
`tmp/menu-row-staged-trial-02/candidate.gb` SHA256
`32bd961cd7a5eb70f65d5a47820ffcba11cd82856ff0c6ce18260e55bc29e628`.

Fresh `secret-menu-row-staged-safety-02` exits0 at2600 frames with all five
before/after group sites observed. It preserves116 publications/3480 quartets,
all write-boundary samples mode0/VBK1; pass durations43688..44392 cycles versus
parent55032..55752. Frame2460 PNG remains exactly a964efa7… and full serialized
VRAM has zero differences. The unchanged timer guard passes1780 intervals,
zero late, maximum137520 (threshold141312). Timing trace SHA256
`3749bd0ec8b7810dac6b636c85e1231cfa5d1048ca877c3d414ac22684c0e0bd`;
critical trace `eeeb021a806f605b6c8f4c46cbe6491eb6a9d71315211522d20d26bfe8b6041b`.
The prior staged variant remains an authenticated two-late-interval negative
control. Twelve focused menu-builder/trace tests pass, not a full integration
or audio qualification claim.

Fresh `secret-fast-row-menu-input-01` also exits0 at2600, records native DCDB
category01 at2420 and00 at2460, matching original sampled-frame consumption
of the two six-frame Down/Up pulses. Input trace SHA256
`8468365ab114f9308f710ada49c066f1f7805e94fd5a38fb60ab944609923b42`.
Still pending: all-route stack depth, temporal rendered menu contents, native
PCM, original cadence/input-repeat fidelity, and composition with other fixes.
This is the first menu-copy variant to pass the observed delay check while
retaining the parent's publication count. No promotion or deployment.

#### #33 fast menu copy composed with ceiling and secret fixes

Extended the experimental quartet builder to accept the exact existing
ceiling/secret parent `00f2629895d886d36dee8c1e1a9e1c3d47e681760ac40ec9d71f99f94a683492`.
The receipt now records the actual input hash. A new unit test checks every
changed byte is in bank20's hook/cave or checksum, preserving other fix banks.
Thirteen menu tests and39 secret tests pass; source07 variants retain their pins.

Candidate `tmp/ceiling-secret-fast-menu-composition-01/candidate.gb` SHA256
`047645505180530404816dbe59d27cad1e9c31332e6eea7a355cb0e817ebb381`.
Builder SHA256 `85d998b6c9288e260959c2ba47386a71c1c700cdf1e0bbc63cc84a58544e216a`.
Fresh7800-frame `ceiling-secret-fast-menu-return-01` exits0 using the recorded
position/resource assistance, pulsed fire, and Select2400/2520 recipe. No
hardware interaction. Unchanged timer guard passes4208 scene09 intervals,
zero late, maximum137528. It observes114 menu publications,3420 quartets,
all before/after endpoints mode0/VBK1; copy spans43872..44368 cycles. This is
not the isolated source07's116 publications; do not transfer that cadence claim.
Secret boss enters4213, returns to secret7040, stage card7058, Stage1 at7251.
Changed encounter timing is not a gameplay-fidelity pass. All6600 post1200
priority-helper samples remain intact. Reviewed terminal7800 image shows
visible colored dungeon terrain and sprites, not a full tile-art correctness
oracle. Temporal menu contents, all-route stack safety, and PCM remain pending.

Trace SHA256 bindings:
- timer `2091dbc325d52d89819e55d8a7102e2b36715518ea69ac3c52e24f09e10e238d`
- critical `21a754d6300ea250737be23ea9e57c83fb7141f59e86fe8ed5056c26007cc4a1`
- route `a29d4439bc49d0b1039fa96e6ecf86cc9cd7ad90aabb5dd63661dac2a606ea46`
- priority `5f0224e72f6b5638014ec46b3be4e192dfb4496038bb9f335f3b26ab6faf87f7`

Then fresh `ceiling-secret-fast-menu-gameover-01` passes the checked-in
gameover/restart verifier with `--sequence --saved-game`: HP-zero death
stimulus,102 GameOver frames and482 title-frame pairs. This is emulator
sequence coverage, not walking into hazards, hardware or acoustic qualification.
No default source-chain promotion, deployment, readiness claim, or issue closure.

#### #33 consecutive menu-navigation pictures match the source07 parent

Fresh sequential cold runs `menu-parent-temporal-01` (eebf3f19…) and
`menu-fast-temporal-01` (32bd961c…) both complete2600 frames with the same
corrected-latch core, audio enabled, assisted secret entry, Select2400/2520,
Down2420..2425 andUp2460..2465. Probe SHA256
`96176bdbdd1f28691151db17e22948690ca4c72a775216e87c8231f09c601d67`
adds consecutive screenshots/states for2399..2530 inclusive. All132 rendered
RGB images match exactly, including entry, category navigation and exit;
no alignment, masks or discarded frames. Reviewed frame2425 shows the Special
menu with its colored icons. This establishes parent-relative visual equality
for this window, not original-game fidelity, audio, or observer neutrality.

Full VRAM matches on131 of132 frames. At2522, six bank0 tilemap bytes differ
at98D4/98D5/98F4/98F5/9906/9907 while both frames are atLY144/LCDC8B;
sampled PCs differ (6E4D parent,6E24 candidate). Both rendered images still
match, and VRAM matches again on2523. Retain this transient exit-state
difference; do not claim machine-state equivalence or infer a cause from PCs.
No differing attribute-bank bytes were found in this window.

Full comparison `tmp/menu-temporal-comparison-01.json` SHA256
`831ed9a7ef57c1d09fd5ae838a54be9510cf18616b073b13df74839ab632f341`;
comparison script SHA256
`975500fdcdcec77a0058a1ae1bd60dd81b5a254c53ffa58a6727fa63395dabd2`.
The comparison is diagnostic, not yet a mutation-tested acceptance gate.
All-route stack safety and native PCM remain outstanding. No hardware touched.

#### #33 observed row-stack balance in the composed candidate

Fresh `menu-fast-stack-01` completes2600 cold frames with exact composed
candidate04764550…, corrected-latch core, audio enabled, the documented
secret-entry/resource assistance and Select/Down/Up navigation. Probe SHA256
`9d9b737bbb5878182800d99aa5e1f64088334f2ced8bd1bdef8e5e4e2e91098b`
observes bank20 row entry7C00, first quartet7C8C, native row tail406F, and
timer0050 while a row is active. All678 rows have46-byte stack depth, exact
SP/BC restoration, DE/HL advance20, bank1 throughout and no timer during
staging. Actual observed entrySP DFF1 and lowestSP DFC3 supersede the earlier
sampled-parent DFEB estimate for this run only. No ROM change in this test.

Trace SHA256 `2a2081e26cdaabf33f5c7a8c56b17dfa533cac3da40485052c8b16099cbdebfe`.
Added `check_menu_row_stack.py` and tests for incorrect restored registers,
wrong depth/bank, interrupt intrusion, empty/partial traces, plus a corrupted
restore mutation of the authenticated real trace. This proves observed balance,
not global WRAM ownership, all-route stack bounds or acoustic fidelity.
Issue33 remains open; Rivalmage remains untouched.

#### #33 native audio comparison localizes divergence to menu navigation

Fresh sequential2600-frame captures `menu-parent-av-01` (source07eebf3f19…)
and `menu-fast-av-01` (fast-row32bd961c…) use the identical assisted secret
entry and Select/Down/Up recipe, corrected-latch core, audio enabled, probe
9d9b737b…, native tap337c75df…. Large raw artifacts are retained under
`/mnt/data/tmp/penta-menu-parent-av-01/` and `penta-menu-fast-av-01/`.
Both complete2600 native video/state frames and5711648 stereo samples at
131072Hz. Finalizer validates all file lengths and wraps unchanged PCM as WAV.
Parent WAV SHA256 `94d4709e6c78caa00cb0d65f6f504b5d3d792551cf24ff49dbaf87ce10b18538`;
candidate `1155a08d10324600a88c95d7cc7f2382548cdb9921f13d1777f7fcbe80027e7f`.

Unchanged `verify_native_audio_pair.py` FAILS only the exact digital-silence
interval check. RMS3066.9943→3065.7463 (ratio0.9995931), peak23759 and maximum
sample step18653 unchanged, no added clipping, identical50ms silent-block
indices. The final qualifying silence interval shifts from[5354223,5362580)
to[5353903,5362576): starts320 samples earlier, ends4 earlier,316 samples
longer. All preceding qualifying intervals match exactly. Full PCM first
differs at5319816, between delivered frames2420 and2421 (Down input), with
379117 differing sample frames through the endpoint5711647. PCM was identical
through menu entry before this navigation input. This localizes a question
about navigation sound timing; it does not prove the reason or perceptual
acceptability. No listening claim. No trimming, resampling or guard changes.

`tmp/menu-native-audio-comparison-01/` preserves the full sample differences
and receipt. Next useful diagnosis is native command/APU timing around the
first Down input, not another broad route or a relaxed silence threshold.
No promotion/deployment; audio qualification remains incomplete.

#### #22 denser recorded-area review, identity still unresolved

Re-read the prior Spiral control and recording review before changing colors.
The known8E/8F/9E/9F BG5 Spiral control was already gold on the reported build;
repeating it would not reproduce the player's gray teleport pickup.
New derivative `/mnt/data/tmp/penta-star-detail-20260928/19m-20m.png`
samples19:00..19:58 every2 seconds, cropped to recording x0..1279 and scaled
for review, with relative timestamps. SHA256
`38283c3966e8f7ec60bf112d923485e51ef3fb5637c09991d996f28bb42380c6`.
At19:14..19:18 pink/gold multi-point moving shapes accompany Sara's form
change;19:24 onward shows gold-bordered square/diamond forms near red/yellow
spike bars. This sample does not positively identify the gray pickup or prove
its absence between samples. Do not substitute these shapes for the reported
object. Original footage is unchanged; no ROM/palette edits or emulator runs.
Asked the user asynchronously for an approximate timestamp/destination detail;
other local work is not blocked by that question. Issue22 stays open.

#### #33 sound-command diagnosis and original-game timing control

Fresh2600-frame `menu-parent-sound-events-01`, `menu-fast-sound-events-01`
and `menu-original-sound-events-01` complete sequentially with identical
assisted route/input recipe and probe9d9b737b…. Parent and fast-row traces
each contain109 mailbox events (37 requests,36 reads, same overwritten
request at825). Ordered event/command/active/caller tuples match throughout;
both pass the unchanged command-semantics checker. Down requests sound0A
from caller1EB9 at2420; fast request16 cycles earlier, but read/accept cycles
and the five sampled audio-register writes at2420 are identical. Thus the
recorded waveform divergence is not explained by a changed navigation command.

At2421 the parent has timer entries340405336/340464192; fast has340469720
in that frame. The subsequent FF23 write is5528 cycles later. Over the full
2400..2519 window both have178 timer entries with identical first/last cycles;
do not interpret the per-frame count difference as proof of lost interrupts.
Both have1337 sampled audio-register writes overall, but ordered register/
value/PC tuples first diverge at2571 after menu exit. These five watched
registers are incomplete APU coverage; they do not establish the first PCM
divergence's exact cause. No patch or acoustic-pass claim follows this trace.

Original game also requests08 for menu entry and0A for Down/Up. Its menu
entry occurs2403, unlike DX2400; Up acceptance2461 versusDX2460. Original
menu-window timer count178/max gap111944; parent178/145040; fast178/137520.
Original timing is not interchangeable with the delayed DX parent, and raw
cross-ROM clocks/encounters are not equivalent. Fast reduces the worst gap,
but remains above the original observed gap. Preserve the native-PCM failure.

Trace bindings (command then timer):
- parent `c86f735dfb64ca1b1bf1176cbced6566faeb075962f072eccc0c4f763b94e20e`,
  `21230d79cf5c8c8b2ca892564a19a0b55ac9f52f71da328ff1a1994f23bf9d6a`
- fast `5a2b12c3ce4a132a4123a38d3868f71daa9fa9dca0e50fe8fc3dfa14419c7d91`,
  `4a84cb8b48d94b45fd3892b6e774d7bfb9ae482c490d0d48e6593c4c7d33d52a`
- original `ce2829a0e062b432c48f1eaee03f964a9748bf808ee744270d58d95917f55f36`,
  `00409206c2e6109661611fa64f08b3569937a75fd039e60f5106716d6bbeb848`

#### #33 fast-row plus midpoint yield improves timing without count loss

The previous yield-only variant reduced publication count. Test the same
pending-timer-only third-row-tail yield after the faster row compiler instead.
Extended the yield builder's exact allowlist to32bd961c…; pair-site yielding
is explicitly rejected for this parent. Row staging is fully popped before
the row-tail timer opportunity. The separate7E00 cave leaves7C00 compiler
and write groups unchanged; a new regression test verifies that byte range.

`tmp/menu-fast-midpoint-trial-01/candidate.gb` SHA256
`c55a4f55c79d7705dedf5cebe8c01483b3d9d7ce1bb9de1472a6690fca704109`.
Builder SHA256 `14e09fcd98a1051a0a5fe2621c74336937d2aa923b61a33f34623a62a620a6fa`.
Fresh2600-frame `menu-fast-midpoint-safety-01` completes the same assisted
Select2400/2520 replay:116 publications and3480 quartets, all observed
write endpoints HBlank/VBK1,1780 scene09 timer intervals with zero late and
maximum118696 (fast-only137520). Overall DI-to-reveal duration43856..58200
includes the permitted timer work, not an uninterrupted-DI duration.
Frame2460 PNG remains exactlya964efa75d00b363d61277002cc1048f8de072767cc446519c2f8d702be9e2b6.
This removes the publication-count drawback of earlier yield-only trials in
this replay, not a full speed or audio qualification. Native PCM, consecutive
navigation images and other-fix composition must be tested for this new hash.

Timer trace `6e0a61f754b0facf8e12df906a4e932ddf57c6de7dd9270daa7e4d6b44945273`;
critical trace `f7c0531bc287af753e41b7f5b0ef59444e9a7c7f6ffb378b444eb5c86475d1d0`.
No deployment, main-source promotion or issue closure.

#### #33 midpoint variant retains visuals but does not qualify audio

Fresh2600-frame `menu-midpoint-av-01` captures candidatec55a4f55… with the
same assisted route and Select/Down/Up navigation, consecutive menu pictures,
audio-enabled corrected core and native tap337c75df…. Captures are under
`/mnt/data/tmp/penta-menu-midpoint-av-01/`; complete2600 frames and5711648
stereo samples at131072Hz. WAV SHA256
`c9b6ff96decb1eecc444cdb8846082d9f39e390d9e8900d334cb77070e0b6c16`.
Parent WAV94d4709e… was rehashed before reuse. Eight audio-guard unit tests pass.

The unchanged full-sample guard still FAILS exact digital-silence intervals:
final interval[5353891,5362576) versus parent[5354223,5362580),328 samples
longer. RMS ratio1.0015771, silent50ms blocks identical, no added clipping or
larger maximum step. First PCM difference5287173 falls between frames2405/2406,
earlier than fast-only's2420 navigation divergence.403796 sample frames differ.
No trimming, alignment, resampling or acceptance-threshold change was applied.
Audio receipt SHA256
`c80e2d44956abc3e2013d9212899d7e6a6b88c98187941cd7e53049e424e9eb6`.

All132 consecutive menu RGB images2399..2530 still match parent exactly;
VRAM differs only at2522, as with fast-only. Comparison SHA256
`eca51cf51b87d4b92df49958870963e70e05d59051db50580e198638649b1724`.
Retain as timing improvement, not audio-qualified replacement. The known
delayed parent is not an original-sound oracle: further scheduler tuning just
to recover its waveform would be unjustified. Original-relative timing and
audible output remain necessary; other player-reported bugs remain open.
