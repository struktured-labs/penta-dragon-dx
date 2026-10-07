# Issue #34 current-source input experiment — not promoted

Released parent: `126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
Legacy-context buffer: `bc481bb1562be96068cdd331f9be9fecd0e2e021dab3b7686587467cc55ae275`.
Canonical-context buffer: `cb7996f97e319d25084793bc5fa5ca1d8bc96a36e8d65474e1e960a5c2035f6f`.
Scratch construction: `tmp/build_current_select_trial.py`; all four legacy
hook preimages and blank bank37 authenticated before patching. Between the two
buffer variants only the two context routines and cartridge checksum differ.

## Fresh normal-health observations

Each ROM has its own fresh native-dispatcher Shalamar fixture, generated through
the guarded runner. This is assisted entry, not organic traversal or matched
cross-ROM CPU phase. The 1080-frame menu replay itself performs no memory writes.

- Six-frame third Select at721: released parent and canonical trial both pass
  three menu cycles. This alone does not establish a six-frame fix.
- One-frame third Select at721: parent receives raw04 then00, but native edge
  polls at726/732/738 remain00; third cycle fails. Trial delivers at722 with
  raw/held00, and all three cycles pass.
- One-frame trial press at723: delivered at728 with raw/held00; three cycles pass.
- Normal-health phase721 full native video, states, PCM, WAV, timeline and
  metadata match observed/unobserved after all files are rehashed. Restore
  epochs pass. Frame780 screenshots inspected: parent combat, trial menu.

## Low-health experiment and retained failure

For each buffer variant, restore its own fixture and use the existing
`ENTRY_ONCE_HP=109` option once at physical WRAM bank1 DCBB. Capture60 frames
with the native startup barrier. Frame1 remains native scene0C; the game
subsequently enters low-health alias0B without scene/palette/cache writes.
Menu replay restores that exact ROM's frame1 and makes no further memory writes.

- Canonical trial, short press723: delivered at729 after release, all three
  rendered cycles pass,1074 alias frames retained. Full native observed/off
  hashes match again; no trimming or phase alignment.
- Legacy-context control, short press723: third menu cycle fails. Preserve
  `tmp/select-current-legacy-lowhp-short723-01/replay` as the control.
- The new strict delivery oracle still rejects the canonical low-health trace:
  no raw-write events at727/728. Frame snapshots show IE=04 (VBlank masked)
  while LCD remains enabled. Do not relabel this oracle result as PASS.
- Canonical trial, short press727 inside that gap: third menu cycle fails.
  This is a distinct sampling limit: a pending-edge buffer cannot preserve a
  pulse that never reaches the native sampler. The trial is not a universal
  short-press fix.

Artifacts use `tmp/select-current-{parent,canonical}-short721-01`,
`tmp/select-current-canonical-short721-off-01`,
`tmp/select-current-canonical-short723-01`, and
`tmp/select-current-{canonical,legacy}-lowhp-*`. Native bulk streams live under
the receipt-bound `/mnt/data/tmp/penta-lowhealth-native-*` directories.

## Current six-frame reproduction (phase739)

The release parent's uninterrupted pre-press combat interval has native edge
polls at738 and745. A six-frame Select pulse at739..744 is sampled by the raw
input path but is gone before the next edge poll. The parent delivers no Select
edge through751 and fails the third rendered menu cycle. Its strict delivery
oracle also reports missing raw samples; retain both failures.

The canonical trial receives the same scheduled six-frame pulse and delivers
exactly one edge at740. Its strict delivery oracle and all three rendered menu
cycles pass. This uses each ROM's own generated state, not a claim of identical
cross-ROM CPU phase. Parent frame780 remains in combat; candidate frame780 is
in the black entry fade and frame810 visibly shows the MEDICAL menu.

Artifacts: `tmp/select-current-parent-phase739-01/replay`,
`tmp/select-current-canonical-phase739-01/replay`, and
`tmp/select-current-canonical-phase739-off-01/replay`.
Both candidate runs completed1080 frames. Rehashing all six complete native
streams (PCM, WAV, video, states, timeline, metadata) confirms exact observer
on/off equality, and direct ROM/state/probe/runner/tap bindings still match.
This is observer neutrality, not original-relative audio fidelity.
The existing physical latch-write checker accepts the candidate's full trace:
only its declared writers, bank7, IE masked, and observed set/consume/clear.
That remains scoped ownership evidence, not an all-scene allocation proof.

`scripts/diagnostics/build_current_select_buffer_trial.py` now reproduces the
exact measured `cb7996f9...` trial without mutating the historical builder's
globals or changing release defaults. Its fresh construction output is
`tmp/select-current-reproducible-build-01`. Nine construction tests and six
delivery-oracle tests pass (15 total). Neither system Python nor the project
venv contains pytest; the successful invocation used `uv run --no-project
--with pytest python -m pytest`, with no repository dependency changes.

## Low-health six-frame sweep

`tmp/select-current-six-frame-sweep-01/summary.json` retains all16 runs:
parent and canonical trial at each phase721..728, six-frame holds. Every run
delivered one Select edge within12 frames. This sweep is therefore not a
discriminating six-frame negative control.

Parent721..724 and canonical721..722 failed the full rendered-cycle check;
the remaining ten runs passed. In those six failures, later combat damage
triggered native automatic low-health MEDICAL entry after the scheduled menu
return. Endpoint and map-readiness checks passed, but cadence correctly still
failed. Do not remove the extra native menu or relabel the whole runs PASS.

## Remaining qualification

Separate the original six-frame responsiveness contract from optional one-frame
stress probes. Sweep adjacent phases for the original hold without lengthening
it; retain sampling gaps explicitly. Check physical bank7 ownership, menu/death
boundary flushing, other arenas, original-relative speed and native audio.
The new delivery oracle and six negative-control tests are not release gates
yet. Neither buffered ROM is merged, deployed or claimed ready.

## Portable ownership-oracle mutations

The writer-oracle mutation tests formerly all depended on an ignored historical
trace, so absent local evidence also skipped checks for wrong banks, enabled
interrupts, foreign writers and invalid values. They now use an explicitly
synthetic four-writer inventory for mutation testing, including missing
pending-set/consume and active/inactive-owner values. Twelve tests pass without
an emulator. The separate historical live-trace test remains skipped here
because its old trace is absent; this is not a new live ownership PASS or an
all-scene allocation proof. Current phase739 evidence above remains separate.
