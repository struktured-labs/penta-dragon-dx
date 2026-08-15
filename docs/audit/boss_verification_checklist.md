# Boss arena verification checklist (item 12) — 2026-06-14

Method: reach each arena via boss-teleport (load level1_sara_d_alone.ss0 -> D880=0x02
FFC1=1; set FFBA=idx-1; pulse SELECT+START; wait D880=0x0C+idx). Sample active
tilemap 200-300 frames; count steady-state palette flips (a cell's BG palette
changing frame-to-frame while its tile ID is stable = flicker).

RESULT: ZERO flicker on all 9 arenas. The colorizer is stable (inline hook +
bg_sweep read the same per-arena 0xDA00 table, so no competing-writer flip — the
old position-sweep work is not needed in this build). Crystal Dragon's red-flood
history is RESOLVED (now cyan). Only remaining items are palette QUALITY (flat
vs multi-color), not bugs.

Performance disposition (2026-08-12): `v3.01-boss-speed-5pct-checkpoint` is a
recoverable checkpoint, not the final performance gate. Crystal Dragon's
phase-sensitive ghost/portal effect is the sole accepted exception at about
5%. Every other boss targets repeatable <=1% slowdown against the original ROM
across independently generated fixtures. Do not trade Crystal's visual contract
for a marginal timing gain without new side-by-side and geometry receipts.

Ted review policy (updated 2026-08-15): screenshots and palette-only traces are
not a pass gate. The official `ted_determinism` release gate scans 2,800 visible
frames twice. It requires deterministic replay, membership in the stock pose
contract, exact crown-relative positions for every numbered body tile, legal
positions for each sparse tentacle tile, an intact checker floor, stable tile
palettes, and no horizontal material bands. C1A0 is future-pose scratch and is
diagnostic only; the visible physical map is the correctness boundary. The
`ted_contract_controls` prerequisite proves the classifier accepts a canonical
117-cell native pose and a legal limb, then rejects deliberately displaced
numbered and sparse edge cells. It also accepts the intended BG6/BG7 checker
materials and rejects an all-BG0 uniform floor. The full gate must pass before
generating a one-minute browser receipt.

`ted_release_readiness` is the single shipping receipt. It consolidates the
entry fixture, harness controls, 2,800-frame visible-map replay, checker tiles
and materials, numbered/sparse identity, and the fresh 600-frame OG cadence
comparison. It runs even when an upstream Ted gate fails so the rejection
reasons remain available together instead of being hidden by dependency skips.
Its controls now include a fully green synthetic aggregate and independent
negative controls for >1% cadence, uniform/wrong checker materials, displaced
numbered/sparse identities, and incomplete or nondeterministic replay. A
measured duplicate-cluster control also rejects the exact seven numbered edge
artifacts seen in the current trace.

The 2026-08-15 BG6/BG7 parity experiment is retained as diagnostic evidence,
not a release candidate. `tmp/ted-floor-parity-determinism-v2/report.json`
proves zero checker tile or palette mismatches across 758,013 floor samples and
deterministic dual replay. `tmp/ted-floor-parity-readiness/report.json` still
rejects it: all 2,156 numbered violations are four duplicate tiles with only
two displacement vectors (`$13/$14`: +10,+6; `$1C/$1D`: +12,+8), sparse
identity has 89 violations, and the fresh cadence receipt measures 9.53% fast
against the absolute 1% limit. Faster is not a cadence pass.

The follow-up pair-qualified crown experiment is recorded at
`tmp/ted-crown-pair-readiness-v7/report.json`. Requiring `$02,$03` instead of a
solitary `$02` reduces numbered violations to 1,993 and eliminates all 89
sparse-position violations, while retaining zero checker mismatches. It is
still rejected: multiple valid-looking staging crowns remain, the numbered
duplicates resolve to +10,+6 and +10,+12 translations, and cadence is 8.36%
fast. Runtime-anchor provenance matches the selected physical-map crown in
1,848/1,892 measurable frames, while every surviving numbered duplicate lands
in three-cell publication slot 1 or 2 (never slot 0). This shifts the next
implementation audit from crown selection to the per-group rejection mask and
register materializer. The official `ted_materializer` gate now executes the
real ROM assembly from a deterministic injected state for all eight rejection
masks and four checker parities (32 cases). It passes, proving `B/C/FFA8` emit
the intended source-or-checker triplet and ruling the downstream materializer
out. The complementary official `ted_classifier` gate executes the real C4FC
runtime against all seven measured duplicate coordinates, their seven
canonical counterparts, and the stock partial `$02,$03,$77` initial crown.
The partial crown must be accepted provisionally: rejecting it damages native
publication before the remaining crown cells exist. A minimal `$02,$03,$04`
production experiment was rejected after its hot-path timing increased the
2,800-frame numbered failures and introduced a wrapped `$03` artifact. The
pair-qualified candidate was restored byte-for-byte afterward. Visible edge
identity remains owned by the full-plane gate; a narrow crown fixture may not
override it.
A complete `$02..$06` source-signature experiment was
also rejected after it increased numbered violations to 3,531; its additional
hot-path timing changed publication phase despite matching stock snapshots.

Every new Ted experiment must also pass `verify_ted_candidate_delta.py` against
the current qualified 2,800-frame baseline. This monotonic gate rejects any
worse identity, sparse-edge, checker, crown, or native-pose metric even when an
isolated classifier passes. Use `--require-improvement` before replacing the
baseline.
Candidate-delta v4 additionally requires `--baseline-readiness`,
`--candidate-readiness`, and `--baseline-pin`. It rejects loss of any previously passing aggregate
check, increased absolute cadence deviation, new foreign publication cells,
or additional next-frame completion failures. Its controls independently
inject all four regressions and prove each is rejected. A visual counter may
therefore no longer improve by silently spending publication correctness or
timing.
`verify_release_candidate.py` now owns this comparison as the
`ted_candidate_delta` gate. Full matrices use the portable checked receipts in
`docs/audit/ted_baseline_v4/` by default; explicit
`--ted-baseline-determinism` and `--ted-baseline-readiness` override them.
Their paths and hashes are recorded in the resumable manifest. Use
`--ted-require-improvement` only when promoting a new baseline. The dependency
closure forces fresh entry, cadence, source/publication, deterministic replay,
and readiness evidence before the delta command can run.
The runner deliberately separates receipt production from final enforcement.
Ted cadence, determinism, publication sequence, and the first readiness pass
run in `--receipt-only` mode: a broken candidate still yields complete,
comparable evidence instead of blocking its own delta audit. After
`ted_candidate_delta`, the final `ted_release_readiness` gate reruns without
that option and fails the release unless every v2 check is actually green.
Thus receipt-only is not a bypass; it is an evidence dependency for the later
enforcement gate.
Readiness v4 also binds the aggregate to its deterministic replay: it records
the candidate ROM SHA-256, determinism ROM SHA-256, state SHA-256, both trace
hashes, and the copied geometry counters. Candidate-delta v4 rejects either
baseline or candidate when those identities differ or when the readiness
geometry payload is not byte-for-value consistent with its determinism
receipt. Positive and independently tampered ROM/geometry controls lock this
pairing, preventing cross-build or stale JSON evidence from being combined.
The same aggregate now joins every remaining component by identity: cadence v3
records DX/OG ROM, state, and trace hashes; classifier and materializer record
their ROM and fixture hashes; publication sequence records both source-trace
hashes. Readiness requires the DX cadence/source state to equal determinism's
state, every candidate-ROM receipt to equal its ROM hash, and both publication
hashes to equal the source-publication trace. Independent tampering controls
for cadence, source state, publication trace, and runtime-contract ROM prove
that each mismatched join is rejected without disturbing the others.
The word "baseline" is itself receipt-locked by
`docs/audit/ted_candidate_baseline_v4.json`. That checked manifest pins the
qualified determinism/readiness file hashes plus ROM, state, trace, frame, and
geometry identities. Candidate-delta refuses arbitrary or edited baseline
receipts, and the release runner records the pin path/hash in its resumable
manifest. The pin is part of the deterministic suite fingerprint; promoting a
new baseline therefore requires an explicit reviewed manifest update rather
than merely pointing the CLI at an easier comparison target.

Stock's physical-map handoff is independently locked by
`verify_ted_publication_sequence.py`. Across the deterministic 2,800-frame
trace, every partial map consists only of cells from the prior physical plane
and the current source plane, then becomes source-exact on the immediately
following frame. Built-in negative controls reject both foreign cells and a
delayed/missing completion. A DX policy must preserve that semantic boundary;
atomically exposing an intermediate source plane is not stock-equivalent.
`verify_native_tile_copy_contract.py` additionally requires a stock-copier
diagnostic to restore the RST `$30` entry, the full `$42A0-$436D` copier, and
the native `$3482-$34A2` emitter tail. The former `--stock-tile-copy` path
restored only the first two and therefore was not valid architectural evidence.
Ted's publication cadence is measured over at least 2,800 frames. A 600-frame
window is too quantized for the ±1% gate: the corrected native path appears
1.29% fast there (102/104 copies) but measures 0.21% fast over the authoritative
window (484/485 copies).
The native-copy/full-plane-postcopy prototype is retained only as a negative
control. Its deterministic 2,800-frame receipt measured 456 DX publications
versus 484 stock publications (5.76% slow), proving that a second 24x24
semantic pass cannot satisfy the absolute +/-1% release boundary. Contract
controls exercise both slow and fast failures so over-publishing cannot
masquerade as a performance fix.
Exact source planes are now captured at every native `$42A7` publication by
the cadence probe and consumed by
`verify_ted_two_plane_cache_contract.py`. The qualified DX trace contains 485
publications but only 42 distinct attribute layouts. A two-plane LRU reuses
441 publications and needs 44 full compiles (9.07%); the receipt-locked
22-cell palette signature distinguishes every layout with zero false hits.
Removing its final sample deliberately creates 14 false hits, proving the
negative control. This contract is a dependency of Ted readiness in the
release runner and establishes the bounded implementation target: two WRAM
attribute planes, 22 sampled palette identities, and no more than 50 full
compiles over the authoritative horizon. The production runtime key is
measured independently: a collision-free but publication-unique key is an
explicit negative control because it defeats reuse and causes the measured
slowdown even though it never returns a false hit.
The required storage is independently reserved by
`verify_ted_cache_plane_reservation.py`. Two deterministic 2,800-frame runs
observe zero reads and writes to WRAM banks 2 and 3 at `$D000-$D305`; synthetic
foreign reads and writes are both rejected. The release dependency
intentionally fails as soon as an implementation accesses these planes until
its exact helper PCs are added as declared readers or writers. This turns the
reservation into a bidirectional ownership boundary, not a permanent
assumption that would become meaningless after allocation.
The cadence trace also records the return address at native copier entry.
Across the corrected 2,800-frame Ted receipt, all 485 DX publications and all
484 stock publications have caller `$028D`, identifying the sole `$028A`
`CALL $4295` path. Readiness rejects a missing or mixed caller histogram; this
prevents a replacement publisher from matching counts while bypassing stock's
alternating-map control flow.
These fields are mandatory in
`penta-boss-publication-cadence-v3`; the Ted readiness aggregate is now
`penta-ted-release-readiness-v4` and deliberately rejects legacy or
schema-less cadence receipts.
The corrected native-copy baseline now has a portable consolidated v4 receipt
at `docs/audit/ted_baseline_v4/readiness.json`. It passes entry,
deterministic replay, materializer, classifier, source capture, cadence, and
caller provenance, but remains rejected by six named visual/publication gates.
The physical sequence has no foreign cells, yet 5 of its 42 partial events miss
stock's next-frame completion. The 2,800-frame geometry replay also reports
2,800 non-native poses, 430,365 numbered-position mismatches, 6,846 sparse-edge
mismatches, 5,762 checker-lattice mismatches, and 565,492 checker-palette
mismatches. These are the official baseline deltas a replacement must reduce;
the passing 0.24% cadence result cannot mask them.
The aggregate Ted readiness gate consumes the 2,800-frame publication-sequence
receipt. `stock_publication_sequence` rejects physical changes containing cells
from neither the prior map nor current source or failing stock's next-frame
completion. C1A0 source capture remains mandatory evidence but is deliberately
not a pass boundary: it is a staging workspace containing invisible future
poses. The release runner captures source traces even when their diagnostic
bounds fail, then applies the gate at the physical-map boundary.

The stock edge receipt is independently reproducible with
`verify_ted_edge_invariant.py` over the 2,800-frame OG source/map trace. It
checks both physical maps (280,000 cells total): rows 12/16–19, columns 14–23
contain no `$02..$20`, `$27`, or `$28` art in stock. Runtime experiments using
that invariant still require the monotonic candidate gate because extra hot
publisher cycles can change Ted's animation phase.
The same receipt deliberately records that source-order deduplication is not
valid: four frame-1021 cases publish `$1F/$20/$27/$28` staging copies before
their canonical copies. A "first identity wins" experiment was rejected after
the monotonic gate measured 2,139 numbered and 89 new sparse violations.
`verify_ted_writer_ownership.py` also proves that canonical and staging cells
are both emitted by the shared fixed-bank `$3127` two-by-two blitter (466 body
records and 626 staging records in the focused probe). Suppressing that writer
would delete future native poses, so repair belongs at the publication-policy
boundary rather than the source-art generator.

| # | Boss          | D880 | reached | flicker | status |
|---|---------------|------|---------|---------|--------|
| 0 | Shalamar      | 0x0C | yes     | 0       | GOOD — multi-pal body (p1/p4/p0). Best-colorized. |
| 1 | Riff          | 0x0D | yes     | 0       | OK — mono purple (p2) by table design. Flat but clean. |
| 2 | Crystal Dragon| 0x0E | yes     | 0       | OK — mono cyan (p4). No red-flood, no flicker. Flat. |
| 3 | Cameo         | 0x0F | yes     | 0       | FLAT — mono red (p1, 387/432 cells). Looks heavy; candidate to enrich. |
| 4 | Ted           | 0x10 | yes     | unknown | BLOCKED — checker materials and sparse identity now pass, but the aggregate receipt still rejects translated numbered duplicates and the authoritative 2,800-frame cadence is 10.51% fast. Do not demo or ship. |
| 5 | Troop         | 0x11 | yes     | 0       | GOOD — multi-pal (p0/p7). |
| 6 | Faze          | 0x12 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p6); drop-shadow present. |
| 7 | Angela        | 0x13 | yes     | 0       | GOOD — multi-pal (p0/p7/p1/p2). |
| 8 | Penta Dragon  | 0x14 | yes     | 0       | GOOD — multi-pal (p0/p1/p2/p3/p4/p5). |

TO VERIFY YOURSELF: boss-teleport to each (SELECT+START in a dungeon), look for
flicker (none expected) and overall color. Flat ones (Riff/Crystal/Cameo) are by
arena-table design — enriching them to multi-palette body parts (item 6 "more
colorful") is a low-risk follow-up that needs a per-boss tile-position re-probe
to know which tiles are which body part (scripts/arena_tables_data.py ARENA_TILE_PAL).
