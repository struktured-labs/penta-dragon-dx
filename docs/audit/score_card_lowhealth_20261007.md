# Stage 2 card coverage extension (#60)

The card checker formerly required exactly2400 frames and recognized only raw
scene03 as Stage2 gameplay. The current3300-frame assisted boss-handoff replay
ends in native low-health scene0B with owner03. Its clean card measurements
could not establish route completion under that older contract.

The producer now appends read-only FFB7 `native_scene` telemetry. The checker
uses the receipt's requested frame count, requires every frame in exact order,
and recognizes alias0B only with native owner03 and stage01. Older traces with
an unrecorded alias owner do not receive guessed coverage. Empty, duplicated,
reordered, truncated, wrong-owner and missing-owner cases remain failures.

Fresh local replay: `tmp/score-oam-lowhealth-current-01`,3300 frames, source
candidate SHA256 `126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
Exact-ROM starting state is the source-suite02 candidate secret frame7200.
Assistance remains explicit: native1A2B call from live016C and boss HP zero
at900; no scene, palette, cache or OAM repair by the harness. This is not an
organic-input end-to-end playthrough.

- Score:376 frames starting1945; zero visible hardware/shadow sprite records.
- Stage2 card:164 frames starting2361; zero visible hardware/shadow sprites.
- Native low-health Stage2 gameplay first observed2525.
- All19 sampled score/card maps have neutral full-map attributes.
- Screenshots2100,2430,3000 inspected. This checks lingering sprites and
  attribute cleanup, not every intermediate glyph or full-route art fidelity.
- All artifact hashes in the fresh producer receipt were revalidated.
- Twelve card-checker tests pass; with the current Select construction/oracle
  tests,27 tests pass. These are unit tests, not27 additional emulator gates.

## Retained mismatch / no determinism claim

Against the previous same-ROM source-suite02 handoff capture,82 of111 periodic
PNGs and all111 periodic states differ. The first score frame is1945 here
versus1949 previously. No frame trimming or retiming was applied. The longer
handoff runner does not use the newer startup barrier used by the short Select
replay, so this comparison cannot demonstrate observer neutrality or identical
gameplay cadence. It is not a new complete comparative PASS. Both full capture
sets remain intact for investigation alongside #67.

No ROM bytes, release default, hardware deployment or issue closure changed.
The existing97-check receipt belongs to its recorded source/tool revision;
these unmerged harness edits have not undergone a fresh full source campaign.

## Startup repair and integrated regression

The handoff runner now source-builds the exact core's native capture adapter
and blocks CPU execution until restoration and all Lua callbacks are installed.
The shared replay defers its ready marker to the outer transition probe, which
signals only after its final input override is registered. This preserves the
original callback order; no frame selection or emulated timing is adjusted.

Fresh `tmp/score-oam-startup-barrier-01` and `-02` runs completed3300 frames
each. All six full native streams match after rehashing, and both restore
epochs pass. Both have identical score/card/gameplay timings1945/2361/2525,
no card hardware/shadow sprites, and19 clean attribute snapshots. The earlier
ungated mismatches remain retained; they are not relabeled as passing.

The checked-in `check_shalamar_repeat.py` requires exact ROM/state/tools,
input recipe, runtime and adapter identities, rehashes dependencies and full
native streams, validates capture boundaries and sizes, and rejects dirty or
insufficient card coverage. No optional-skipped local fixtures or phase shifts
are used to supply this integrated gate's acceptance.

`verify_playtest_boss_handoff.py` now requires this repeat check before passing.
The complete fresh focused run `tmp/handoff-repeat-gate-01` passed: rearm-only
broken-control comparison, exact candidate transition repeat, low-health Stage2
attributes, actual water scrolling, and secret-return visibility. It used the
unchanged126861... ROM. The targeted unit runs passed34 tests plus16 subtests,
then18 related tests plus8 subtests. A fresh full source suite remains required
before publishing a new all-gates receipt for these tool revisions.

The repeat-validator tests also exercise actual file rehashing with synthetic
local files: changed input/tool/adapter/native streams, truncated primary files
even with refreshed digests, invalid restore epochs, shortened metadata and
missing stream inventory must fail. These isolate the card parser and epoch
verifier and are not emulator evidence. Together with the comparison tests,
20 tests plus16 subtests pass. The complete source campaign remains running.

The combined pre-merge unit run (palette ownership/transactions, current title,
fixture contracts, score/card coverage, native replay setup, repeat validation,
menu-close input, Select construction/delivery/writers and handoff integration
contracts) passed144 tests plus54 subtests. One historical Select writer-trace
test skipped because its old ignored trace is absent; it supplies no acceptance
evidence. No emulator was launched by this unit run. The staged source snapshot
still matches the running full campaign.

## Completed source campaign

`tmp/handoff-barrier-source-suite-01` completed successfully on2026-10-07,
12:52:52–13:40:47UTC (47m55s). All97 serial gates passed and both independent
source builds produced SHA256
`126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
The source fingerprint is
`65fc3d103e657c15dd4d3d122105c397887f070cf8e49e220d3af6eeab431594`.
The final source-bound receipt is `docs/release/verification/latest.json`.
This supersedes the pending-campaign notes above, not the retained failures.
Fresh candidate transition frames2430 and3000 were visually inspected: no
lingering bullet on the sampled Stage2 card, and colorized Stage2 gameplay.
The final read-only process check found no running mGBA processes.

The buffered Select experiment is excluded from this candidate and is not
qualified by these97 gates. MiSTer retest, art approval and remaining input
qualification are separate; no hardware issue is closed by this receipt.
