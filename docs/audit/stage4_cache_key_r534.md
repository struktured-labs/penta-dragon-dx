# Stage 4 private cache-key repair r534

## Result

r534 is the current experimental candidate, rejected by headed operator play
on 2026-09-09 (see the final incident section below):

- path: `tmp/stage4-cache-key-r534/candidate.gb`
- SHA-256:
  `727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`
- MD5: `1bd65503ff407e44114dc206087e92f2`
- direct parent: r533, SHA-256
  `4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba`
- exact base: r475, SHA-256
  `59384e3c0ea5508ade2ff8d08af2f3012c4eff1f5f9cf1cebb2f04273cd1693f`

It is not READY: the operator's exact-ROM menu regression overrides the
historical automated passes. It also remains non-promotable without the separate
hardware and audience requirements. The current530 deterministic suite passed
all 86 gates with intact source/runtime identities and the exact pinned ROM,
after two independent traced original-source builds. Its final receipt also
passed independent verification, including the repaired read-only pre-stream
manifest check and local-only hardware preflight. Current528, current497, and
current427 remain exact-ROM historical evidence, not current-source qualification.
The subsequent START-regression test additions invalidate current530's source
qualification too; its green result cannot be used for the expanded 87-gate
roster or to dismiss the headed failure.

The source-only r534 profile is integrated with the deterministic suite,
approval recorder, and final packager. Verification-only palette proof passed
in current531 against the current source; no audience approval was recorded.
A ROM-free PREHARDWARE package was checked against current530. The ledger
retains 19 measured policy exceptions
(boss pacing and attract timing), rather than equating a gate pass with perfect
native timing. Reservation-backed hardware evidence and explicit audience
approval remain pending.

The original-cartridge source-only entrypoint now reproduces exact r534
without historical observations or a retained factory image
(`tmp/r534-deterministic-current530/build/source-a/`). Two syscall-traced factory builds feed
identical artifact-read-guarded 105-step constructions. The resulting receipt
revalidates against current source, tools, inputs, traces, and both reconstructions.
The explicit approval/packaging profile revalidates this source evidence without
treating it as an audience decision or a live/hardware pass.

## Defect

r533's corrected palette timing exposed a real false hit in the private Stage
4 page-pair cache. The old key used raw layout offsets 81 and 337 plus the room
number. During transition callbacks 140 through 143, the semantic source plane
changed while those two bytes remained `$04/$02`. The cache therefore skipped
attribute compilation and DMA even though 28 visible material cells needed
attribute 4. The tile plane advanced, but those cells remained attribute 0 for
four callbacks.

The strict callback oracle caught the defect. The retained DMA trace confirms
that no `$FF55` transfer occurred in the mismatch window, so weakening the
display oracle or treating the frame as a transient would have hidden a real
publication failure.

## Repair

r534 replaces only the two-byte Stage 4 raw signature while preserving the
room byte and the existing shared compare path:

- B = `raw[210] XOR raw[357]` (`$C272 XOR $C305`)
- C = `raw[25] XOR raw[187]` (`$C1B9 XOR $C25B`)
- third key byte = room `$FFBD`

The bank-22 fragments are at file offsets corresponding to runtime `$DB32`
and `$DB0D`. Including the cartridge checksum, the exact r533 parent delta is
25 bytes, 23 of them functional. The old key-to-compare path costs 104 T-cycles
and the new path 108 T-cycles: +4 T-cycles per Stage 4 decision while retaining
36 T-cycles of headroom over the native route.

## Static proof

The exact-key verifier evaluates three retained, hash-pinned Stage 4 layout
event corpora: 653 total records. The old key has seven collisions and 31
false hits; every false hit is in the newly exposed transition corpus. The new
key has zero collisions, zero false variants, and zero false hits. It trades
ten additional legitimate cache misses for the removal of all 31 false hits.

```sh
python3 scripts/diagnostics/verify_stage4_cache_key_r534_static.py \
  tmp/stage4-cache-key-r534/candidate.gb
python3 -m unittest \
  tests.test_stage4_cache_key_r534 \
  tests.test_story_neutral_guard_r533 \
  tests.test_palette_publisher_atomic_r532 \
  tests.test_r527_inherited_profiles
```

The combined suite passes 22 tests. It pins the exact digest and parent delta,
machine code, branch target, timing, retained output, all inherited observer
profiles, relocated tables and latches, and mutation rejection.

## Fresh exact-ROM emulator evidence

All runs used the r534 SHA above, the patched mGBA CGB-latch build, and the
checked project single-flight launcher.

- `tmp/r534-stage4-strict-current303`: focused 1,200-frame strict Stage 4
  verification passes all rooms with 81,230 expected material observations
  and zero mismatches.
- `tmp/r534-stage4-strict-8000-current304`: full 8,000-frame strict Stage 4
  verification passes with 26,367 expected material observations and zero
  mismatches.
- `tmp/r534-stage4-speed-current305/manifest.json`: exact Stage 4 speed parity
  passes at 764 original and 764 DX frames, with 14/14 scroll events.
- `tmp/r534-later-soak-current306`: the strict 8,000-frame Stage 2-through-7
  semantic soak passes every stage with zero unexpected, unsafe, lava, pickup,
  material, or display mismatches.
- `tmp/r534-inherited-release-gates-current307/manifest.json`: all 16 selected
  inherited release gates pass. The manifest records intact source inputs,
  runtime tools, and source/tested ROM identities; both tested MD5 values are
  `1bd65503ff407e44114dc206087e92f2`.
- `tmp/r534-title-isolation-current313/manifest.json`: the exact historical
  `title_color` -> `title_showcase` -> `title_visual_receipts` ordering passes
  3/3 after each mGBA title verifier was moved to a clean private ROM/save
  runtime. The returned-title receipt reaches frame 10,919 and observes 276
  demo-miniboss samples with zero palette mismatches. The shared tested-ROM
  directory remains free of title-verifier save sidecars.
- `tmp/r534-live-palette-isolation-current316/manifest.json`: the complete
  private-runtime live-palette deck passes in 87.6 seconds and its dependent
  story-attribute production gate passes in 16.6 seconds. This closes the
  late-suite path that had previously opened the shared tested ROM directly.
- `tmp/r534-full-release-current317/manifest.json`: all 86 release gates pass
  in one fresh serial run. The manifest status is `emulator-pass`; all source,
  tested-ROM, source-input, and runtime-tool identities remain intact. The
  tested copy has the same r534 SHA-256 and MD5, and the manifest SHA-256 is
  `a88e4ddd1061a5f742d73dd5852e17117aa6987e527c2f62e0efe88c6584c8a0`.
  Its hardware status is still `pending-reservation-backed-mister`.
- `tmp/r534-full-release-current427/manifest.json`: the refreshed matrix after
  the release-bundle screenshot-path repair and the 86-gate, explicit-input
  MiSTer preflight repair passes 86/86. ROM, source, and runtime-tool identities
  are intact; the tested copy remains SHA-256 `727ee496...b260b`. The manifest
  SHA-256 is `b0ccf751aea093add0a7f674439ad7115c848e2a0a6f1b9fdb7ce8457efa254e`.
  `tmp/r534-full-release-current427/penta_dragon_dx_r534.ips` reconstructs the
  exact candidate and has SHA-256 `b7a4a99e...bb74f`. The deterministic,
  ROM-free `PREHARDWARE` archive has SHA-256 `fc5cfa62...eddfa` and remains
  explicitly non-publishable.

The reservation checker currently fails closed because
`MISTER_RESERVATION_ID` and `MISTER_RESERVATION_CHECKER` are not configured;
no MiSTer connection was attempted. The audience approval recorder also
correctly refuses r534: the canonical expanded palette builder does not yet
reproduce this experimental post-r475 repair lineage byte-for-byte. No palette
approval was recorded. These are release blockers, not waived gates.

## Harness isolation repair

Two failures during the complete-matrix qualification were verifier defects,
not accepted waivers:

- The old title route reused a PyBoy-generated `.gb.ram` sidecar beside the
  suite ROM. Title animation, color, showcase, and visual receipt probes now
  run exact ROM copies from repo-local private runtimes with isolated save and
  savestate paths.
- A later full run exposed a one-off mGBA SIGSEGV during the live-palette
  cold-title capture. The mandatory read-only process check reported no
  orphaned emulator before the retry. The cold-title capture and all four
  live-deck launches now use a private exact-ROM runtime instead of the shared
  suite path.

`tests.test_capture_probe_contracts` pins those runtime-copy and command-line
contracts. The final related unit run passes 35 tests, including the r534
static key, expansion ownership, Ted layout, arena-writer ownership, and
Stage-1 oracle wiring suites.

ROMs, savestates, manifests, traces, and captures remain ignored scratch
artifacts.

## Stage-1 Stop qualification and reproducibility follow-up (2026-09-09)

The exact r534 candidate passed all 17 Stage-1 gates in
`tmp/stage1-stop-hook/stage1-ready-current470-1788928145184951171-421241/attempt/receipt.json`.
The receipt SHA-256 is
`e6ed9c3f2b15dfb238f1212fe745cb2abeb48ec34afd192042bf88e07d132c1c`.
The outer Stop hook accepted that receipt, and cached validation also passed.
This qualification covers Stage 1 and its named speed inputs; it does not
refresh the separate full release matrix or authorize hardware deployment.

The subsequent build audit found that the r475 composer imported executable
Stage-7 builders from ignored `tmp/`. Both modules and their machine-code
tests now live under `scripts/diagnostics/` and `tests/`. The r475 composer no
longer adds scratch storage to its import path, and `suite_contract.source_paths()`
includes both builders in the release fingerprint.

An isolated interpreter test prohibits opening any scratch `.py` or `.pyc`
file, rebuilds r475 from the exact retained r456d input, and then builds r534
twice. The outputs match the pinned r475 and r534 SHA-256 values. The copied
Stage-7 tests also retain the exhaustive dispatcher and service-guard checks,
the 576-cell copier model, the 41-machine-cycle critical-window bound, and
patch ownership checks. The focused run passes all 16 tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_boss_stage7_r475 \
  tests.test_stage7_pure_six_r465 \
  tests.test_stage7_guarded_services_r467 \
  tests.test_stage4_cache_key_r534 \
  tests.test_boss_repairs_r462
```

The retained r456d ROM remains an explicit prerequisite. This proves the
repair chain from that input; it does not yet establish a production build
from the original cartridge and palette YAML. The current
`record_palette_approval.py --rom tmp/stage4-cache-key-r534/candidate.gb
--expanded-ted --menu-icon-colors --verify-only` still rejects the production
rebuild because its output differs from r534. No audience approval was
recorded. Closing that production-build gap and regenerating the complete
release matrix remain required before release qualification.

### In-memory lineage replay from r442 (2026-09-09)

`scripts/diagnostics/rebuild_r534_lineage.py` now rebuilds the exact r534
candidate through ten pinned composition steps, starting from retained r442.
It applies the deferred-DMA/pretest and reload-flag repairs, Nightfall v6
title/ISR merge, fused copier, attract recovery, synchronous boss DMA, arena
table relocation, title-idle transaction, combined boss/Stage-7 repairs, and
the r534 repair chain. Every intermediate output is hash-checked in memory;
no intermediate ROM or historical receipt is loaded.

The previously CLI-only copier and r453 recovery now expose their existing
composition and validation logic as in-memory build functions. The reload
builder no longer mutates its module-level cave addresses, and its receipt
records the actual supplied input hash. Previously the r443f invocation
incorrectly recorded the default r443d input hash despite producing the
correct bytes. Historical receipts have not been rewritten.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-subscene-tracking-r442/candidate.gb \
  --out-dir tmp/r534-lineage-current476
```

The CLI double-builds both ROM and step evidence and records the current
source fingerprint. The resulting ROM SHA-256 remains
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`.
The focused test run passes 29 tests, including
`tests.test_r534_source_lineage`, the reload/pretest and copier suites, and
the previous r475/r534 repair suites. The new isolated-interpreter test
forbids **all** scratch-file reads after loading the one r442 input, then
imports the maintained generators and double-builds the complete chain.
Negative controls reject input, output, receipt, and patch-preimage drift.

This extends source closure back from r456d to r442; it is not a production
build from the original cartridge. The production builder, palette-audience
approval, fresh full release matrix, and reservation-backed hardware gates
remain open. No candidate pin, Stop policy, emulator result, or historical
receipt was changed by this source-only follow-up.

### Source replay extended to r343 (2026-09-09)

The same replay command now accepts the exact r343 input and executes 60
pinned composition steps. Its new `r534_lineage_prefix.py` supplies 50 earlier
steps, including the r392 early-admission variant with its exact four-line
window. Receipt-dependent builders receive newly generated, canonically
serialized static build records whose hashes match their original pins.
No live test record or approval is manufactured by this process.

The scratch-access test exposed two hidden reads in the r380 and r434 merge
builders. They now accept the freshly generated r374 and r424 checkpoints
as explicit inputs. Their existing exact-base and patch-scope validations
remain in force; their standalone historical entry points remain compatible.
The replay rejects a missing checkpoint instead of falling back to disk.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-hazard-terminal-silhouette-r343/candidate.gb \
  --out-dir tmp/r534-lineage-current480
```

The corrected replay double-builds the unchanged r534 candidate. The ten-test
source-lineage suite forbids every scratch-file access after reading either
supported initial ROM (r343 or r442), including imports, saved receipts, and
reference ROMs. It also checks generated receipt chains, reference rejection,
unchanged legacy merge outputs, and the independent bank24 ownership pins.
The broader machine-code/build regression run passes 82 tests; it uses
`PYTHONPATH=tests` for older tests that import sibling test helpers directly.
No emulator was launched.

The exploratory `tmp/r534-lineage-current479/` result preceded the two hidden
read repairs. It is explicitly marked invalid for scratch-independent source
closure and must not be used for that claim. The new v2 receipt records the
actual starting hash and each generated receipt/reference dependency.

The retained r343 ROM is still required. Reconstructing that earlier lineage
from the original cartridge and palette sources, refreshing the complete
release matrix, and obtaining the required audience/hardware evidence remain
unfinished. Neither candidate pins nor Stop policy changed.

### Explicit-input replay extended to r314 (2026-09-09)

The replay now supports 68 pinned steps from r314. This earlier start has
three explicit inputs: the retained r314 ROM, its exact static build receipt,
and the original Japanese cartridge used by the terminal-art compiler. All
three are hash-authenticated before composition. The r343/r442 single-ROM
starting points remain supported and reject unused extra inputs.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-scene0b-publication-commit-r314/candidate.gb \
  --base-receipt tmp/stage1-scene0b-publication-commit-r314/build-receipt.json \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --out-dir tmp/r534-lineage-current481
```

The new v3 receipt identifies the starting ROM, static receipt, original
cartridge, and generated intermediate dependencies. It still marks the output
experimental and non-promotable. The r314 build-receipt SHA-256 is
`730ddfb4acc6a71dadf7404ad0e000378fe62972ff87d3a5dd0f315357819bf1`;
that initial historical record is consumed, not fabricated or regenerated.

Two further hidden ROM reads in r342/r343 merely counted r335's runtime
regions. A shared source-owned region description now supplies both that
layout count and the original payload selection. The terminal-art builder
accepts the explicit cartridge bytes while preserving its standalone
behavior and exact postimage checks. No machine-code or ROM bytes changed.

The 13-test lineage suite double-builds all three supported starts with every
scratch-file access, and every subsequent cartridge read, forbidden after
the explicit inputs are loaded. Negative controls reject missing/wrong input
receipts, wrong cartridges, missing final steps, and reference/receipt drift.
The focused early-lineage, art, and downstream repair run passes 90 tests.
No emulator was launched and no live qualification evidence was refreshed.

Original-cartridge production reproducibility remains incomplete. The earlier
r311/r313 builders authenticate historical failed live diagnostics, and r314
and its build receipt remain prerequisites of this replay. Those historical
validation requirements have not been removed or converted into fabricated
live observations. Full release requalification and audience/hardware gates
also remain outstanding.

### Historical-evidence replay extended to r287 (2026-09-09)

The new `r534_lineage_ancestry.py` regenerates the r288-r314 ancestry,
including the r307 installer-mirror branch and its exact disjoint merge with
r310. The full replay now performs 79 sequential steps and one separately
recorded component build. Every generated ROM and static receipt in this
earlier section is hash-checked, including the regenerated r314 receipt.

This entry point explicitly requires five authentic historical evidence
inputs: the r290 room-01 packed capture, the rejected r303 live receipt, the
corrected r310 live receipt, and the rejected r311/r313 live receipts. Those
observations are neither synthesized nor relabeled as current qualification.
The replay records them with `fresh_live_qualification: false`.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage4-menu-exit-invalidation-r287/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --room01-capture tmp/stage1-report-hook/r290-natural-north/candidate/c1a0.bin \
  --r303-rejected-receipt tmp/stage1-fast-scene0b-gates-r303/live-scene0b-dcbb40/receipt.json \
  --r310-live-receipt tmp/stage1-precompile-effective-room-r310/publication-owned-oracle-r2/receipt.json \
  --r311-rejected-receipt tmp/stage1-final-scene0b-r311/live-scene0b-r1/receipt.json \
  --r313-rejected-receipt tmp/stage1-scene0b-runtime-selfheal-r313/live-scene0b-hardening-diagnostic-r7/receipt.json \
  --out-dir tmp/r534-lineage-current482
```

Isolation testing found hidden capture/evidence reads in the r297-r303,
r305, r310, and r311 validation paths, plus a retained r305 ROM read in the
r311 composition proof. These paths now accept explicit inputs and the
freshly generated r305 checkpoint. All original identity, population,
rejection, and disjoint-composition checks remain active. Standalone
historical builders retain their existing default inputs.

The 15-test lineage suite preloads only the declared initial inputs and then
forbids every scratch-file access and subsequent cartridge read while
double-building all four supported starts. It checks the branch-to-merge
provenance as well as missing/extra/changed historical evidence rejection.
The broader wall, scene-$0B, installer, publication, art, and downstream
repair run passes 173 tests. No emulator or fresh live test ran.

The v4 replay receipt binds the current source snapshot and all five
historical inputs. The candidate still matches pinned r534 byte-for-byte.
This is an ancestry audit, not an original-cartridge-only production build:
retained r287 and historical evidence remain prerequisites. Closing the
earlier build chain, production reproducibility, fresh release qualification,
and the audience/hardware requirements remains unfinished.

### Historical-evidence replay extended to r273 (2026-09-09)

`r534_stage4_ancestry.py` now generates r277, r278, r279, r281, r285, r286,
and r287 from retained r273. The r285/r286 composition checks receive the
generated r279/r281 references in memory. All seven ROMs and their exact
static receipts are hash-pinned; the original unsorted receipt serialization
is preserved through r286. The complete replay now has 86 sequential build
steps and the separate r307 component build. This count describes build
steps, not release gates.

The Stage-4 builders additionally require two historical corpora, one speed
manifest, and six WRAM snapshots with their six metadata files. Their
existing corpus, speed, memory-ownership, and byte-exact regeneration checks
remain active. The replay also pins the full metadata files, not only their
previously checked prefixes. Missing explicit evidence cannot fall back to
the builders' standalone file defaults.

The v5 CLI accepts `--historical-input-manifest`, a JSON object mapping the
twenty logical input names to explicit file paths. Relative bundle paths
resolve against the repository, not the bundle's directory. Duplicate,
unknown, empty, and non-string entries are rejected; an input cannot appear
both in the bundle and in an individual command-line option. Required-input
sets depend on the selected retained starting ROM. The five existing r287
options and the later starting points remain supported.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage7-skip-invisible-padding-r273/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --historical-input-manifest tmp/r534-lineage-inputs-current483.json \
  --out-dir tmp/r534-lineage-current483
```

The bundle uses the historical paths documented in
`r534_stage4_ancestry.HISTORICAL_INPUTS` and
`r534_lineage_ancestry.HISTORICAL_INPUTS`; the build does not discover or load
those defaults itself. Its receipt records the actual input paths/hashes,
the bundle identity, generated references, and the current source snapshot.
All historical evidence remains marked `fresh_live_qualification: false`.

The 18-test lineage suite double-builds all five supported entry points in
isolated interpreters, with every scratch-file access and subsequent original
cartridge read forbidden after input loading. Negative controls cover all
fifteen additional input hashes, incomplete/extra bundles, ROM/receipt drift,
and truncated ancestry. The broader ancestry/art/downstream regression set
passes 176 tests. The CLI double-build still reproduces exact pinned r534.

This extends the source audit; it does not change the game ROM or establish
production reproducibility from the original cartridge alone. Retained r273
and historical evidence are still prerequisites. Fresh full-release,
audience, MiSTer, and Pocket qualification remain outstanding. No emulator
was launched, and neither Stop policy nor candidate pins changed.

### Explicit historical-static replay extended to repaired r264 (2026-09-09)

`r534_stage7_ancestry.py` reconstructs the dual-plane candidate, r265 menu
signature invalidation, r269 transition-state guards, r271 visible rows,
and r273 invisible-padding trim. Its retained starting ROM is the repaired
Stage-1 r264 (`aa4c1560...`), not one of the similarly named Stage-7 r264
experiments. The full replay now has 91 sequential construction steps and
the separately recorded r307 component build.

This earlier section explicitly consumes two authentic historical static
receipts: the dual-plane r264 audit (`b724cfae...`) and its transferred r265
static receipt (`3bf962c1...`). These include old corpus/reachability evidence;
the replay does **not** regenerate that repository-wide historical census or
claim it is fresh. Both complete receipts are SHA-256 authenticated before
construction. The existing full audit and historical validators are unchanged.

The replay reruns eleven source-only contract sections: strict preimages,
runtime guards, emitted guards, caller/camera checks, banked-stack checks,
timing, DMA, timer service, mutation controls, runtime-router construction,
and final candidate construction. Results must match the authenticated
historical identity. Its generated dual-plane receipt is explicitly labeled
`construction-only`, distinct from the retained full static receipt. The
following four generated static build receipts are byte-exact and pinned.
Retained r264 references and the generated r265 reference are recorded
separately. The r265 builder accepts explicit receipt/control bytes while
preserving all existing checks and its standalone defaults.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-menu-hidden-repair-r264/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --historical-input-manifest tmp/r534-lineage-inputs-current484.json \
  --out-dir tmp/r534-lineage-current484
```

The bundle contains the twenty previous inputs plus
`stage7_dual_plane_static` and `stage7_transferred_static`; source registries
document the historical labels and exact identities. The v6 build receipt
binds actual paths/hashes for all twenty-two inputs and the source snapshot,
and continues to mark the output experimental and non-promotable.

The 21-test lineage suite double-builds all six entry points in isolated
interpreters after forbidding scratch-file and subsequent cartridge reads.
New negative controls reject changed static inputs, ROM/receipt drift,
incomplete ancestry, changed source-only contracts, missing controls, and
incomplete bundles. Explicit r265 inputs preserve its standalone output.
The broader ancestry/art/downstream regression set passes 179 tests; the
CLI double-build matches pinned r534 byte-for-byte.

Retained repaired r264 and historical evidence are still prerequisites.
Original-cartridge-only production reproducibility, fresh full-release
qualification, audience approval, MiSTer, and Pocket remain unfinished.
No emulator was launched or live evidence refreshed, and no Stop policy or
candidate pin changed.

### In-memory X-flip/Stage-2 replay extended to r210 (2026-09-09)

`r534_stage2_ancestry.py` adds eight exact construction steps from r210:
r231, r255, r256, r257, r258, r260, r263, and repaired r264. The chain follows
the actual parent hashes: r263 descends directly from r260, not the rejected
r261/r262 alternatives. Every generated ROM and static receipt is pinned.
No additional historical input is needed beyond the twenty-two already
required by the repaired-r264 entry point.

The r231 CLI now delegates to an in-memory `build(source)` function. Its
helper preimages, width, allowed-byte changes, checksums, and all 327,680
existing model comparisons remain active. The resulting ROM and serialized
receipt are byte-identical to the retained r231 artifacts. Later Stage-2
generators already supported in-memory installation and needed no edits.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-deferred-palette-r210/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --historical-input-manifest tmp/r534-lineage-inputs-current484.json \
  --out-dir tmp/r534-lineage-current485
```

The v7 receipt records 99 sequential build steps and the separate r307
component build. The r264 control used by the Stage-7 builders is now marked
as generated for this entry point; it remains explicitly retained when
starting directly at r264. All previous entry points remain supported.

The 23-test lineage suite double-builds all seven starts in isolated
interpreters, forbidding every scratch-file access and subsequent original
cartridge read after declared inputs are loaded. New negative controls reject
wrong initial/final identities, changed receipts, truncated Stage-2 ancestry,
missing evidence, and an intentionally broken X-flip model. Reference checks
prove that generated r264/r265 controls came from earlier recorded steps.
The broader ancestry/art/downstream regression run passes 181 tests; the CLI
double-build remains byte-identical to pinned r534.

This is source-replay progress, not a game-byte change or release approval.
Retained r210, the original cartridge, and historical evidence are still
required. Original-cartridge-only production reproducibility and fresh
full-release/audience/hardware qualification remain unfinished. No emulator
ran, no historical observation was relabeled fresh, and Stop policy and
candidate pins were unchanged.

### Historical transition-corpus replay extended to r199 (2026-09-09)

`r534_stage1_phase_ancestry.py` regenerates r208, r209, and r210 from r199.
The two key builders consume six explicit, SHA-256-pinned transition traces:
five profiles from the r74 transition rerun and the r199 box-copy cold-live
profile. Both existing transition assessments rerun on those bytes. The
source-defined corpus labels preserve their exact static receipt serialization;
the build receipt separately identifies the actual supplied paths and hashes.
There is no trace discovery or disk fallback once explicit inputs are supplied.

The r208/r209/r210 CLIs now delegate to in-memory builders. The transition
assessor accepts explicit text while preserving its original file interface,
including cold-$FF cache behavior. r209 retains its independent content/phase
comparison, plane-width checks, and rejection of missed semantic transitions.
The six traces are historical observations, not new live qualification.

The first isolated replay exposed a genuine r210 reproducibility defect:
the diagnostic imported the production `DEFERRED_ENTRY_GATE`, which had since
acquired a DF5B reset. It produced SHA-256 `fdc9b690...` instead of retained
r210 `dbc1001b...`, differing at four payload bytes plus two checksum bytes.
The r210 diagnostic now owns its historical 14-byte gate:
`FA FD DC E0 91 3E 11 18 00 00 C3 E5 55`. Its `LD A,$11; JR +0; NOP`
sequence preserves the original scene-edge timing without storing DF4C.
The current production gate and palette handoff implementation were not changed.
The corrected builder reproduces the exact retained r210 ROM and static receipt.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/stage1-stale-window-hide-r199/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --historical-input-manifest tmp/r534-lineage-inputs-current486.json \
  --out-dir tmp/r534-lineage-current486
```

The v8 replay receipt contains 102 sequential steps plus the r307 component
build and binds twenty-eight historical inputs. The 26-test lineage suite
double-builds all eight starting points with scratch and subsequent cartridge
reads forbidden after input loading. New controls cover all six trace hashes,
missing/extra inputs, changed generated identities, unused trace paths,
transition rejection, malformed planes, and file/in-memory assessor parity.
All three extracted builders also match their retained ROMs and static receipts.
The broader ancestry/art/downstream/Stage-card regression set passes 187 tests.

The CLI still double-builds exact r534, but this remains an experimental source
audit requiring retained r199, the original cartridge, and historical evidence.
Original-cartridge-only production reproducibility and fresh release, audience,
MiSTer, and Pocket qualification remain unfinished. No emulator ran, no live
observations were refreshed, and Stop policy and candidate pins were unchanged.

### Source-integration baseline replay extended to r120 (2026-09-09)

The Stage-1 ancestry now starts at the retained source-integration r120 ROM
(`029a413b...`) and regenerates r190, r194, and cycle-balanced r199 before the
existing phase-key chain. The actual lineage jumps from r120 to r190 and
then r194; the intervening numbered experiments are not parent ROMs and are
not included. The `build_stage1_stale_window_hide_r197.py` filename contains
the final r199 recipe, as confirmed by its schema and exact output hash.

All three historical CLIs delegate to in-memory `build(source)` functions.
Their exact base/preimage, runtime-width, checksum, and mutation-boundary
checks remain unchanged. The stale-Window cleanup still proves a 192-cycle
normal fallthrough with registers, flags, and memory preserved. Each ROM and
serialized static receipt reproduces its retained counterpart byte-for-byte.
The r190 receipt's historical r74 oracle label is preserved; it does not
claim a new rendered test or require reading an r74 ROM.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_lineage.py \
  --base tmp/source-integration-r120/candidate.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --historical-input-manifest tmp/r534-lineage-inputs-current486.json \
  --out-dir tmp/r534-lineage-current487
```

The v9 receipt binds 105 sequential steps and the r307 component build, with
the same twenty-eight explicit historical inputs. All nine starting points
are covered by isolated double-build testing with scratch/subsequent cartridge
reads forbidden after input loading. The 28-test lineage suite adds exact
early-builder receipts, timing checks, changed ROM/receipt pins, missing input
rejection, and truncated-chain controls. The broader ancestry/art/downstream/
Stage-card regression run passes 189 tests. The CLI reproduces pinned r534
byte-for-byte and records the current source snapshot.

This closes the replay between the r120 integration baseline and r534, not
the original-cartridge-only production build. Reconstructing that baseline
from current maintained production source is the next dependency. Retained
r120, the original cartridge, and historical evidence are still required;
fresh release/audience/MiSTer/Pocket qualification remains unfinished. No
emulator ran, and neither candidate pins nor Stop policy changed.

### Original-cartridge reconstruction without retained candidate ROMs (2026-09-09)

`rebuild_r534_from_original.py` now reconstructs exact r534 from the original
Japanese cartridge, maintained sources/palette files, and the twenty-eight
explicit historical evidence inputs. It no longer needs a retained r120 (or
any later candidate) ROM. This is an **experimental source-reconstruction
pipeline**, not the default production/palette-approval builder and not new
release qualification.

The complete factory option set is native sparse Ted, native pose table,
menu-icon colors, Stage-card handoff, exact destination tags, cached Stage-1
attributes, and the WRAM-local scene guard. Omitting the last guard failed the
handoff preimage check in current488/current489; their partial candidates are
explicitly marked invalid. With the complete options, the maintained factory
produces `e5601c68...`, which differs from r120 at 301 bytes.

`r120_historical_profile.py` accounts for those differences through nineteen
named, bounded source fragments. It reuses existing historical/runtime/helper
generators where available and owns the remaining historical instruction/tile
recipes explicitly. Every modern preimage, fragment width/range, and complete
factory/r120 hash is checked. It rejects overlap or drift. The profile reverses
later integrated changes solely to establish the exact replay baseline; the
105-step lineage then reconstructs r534. The normal production builder and its
current palette/art configuration are unchanged. This profile is not a bypass
for any live gate and is never deployed as r120.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/rebuild_r534_from_original.py \
  --historical-input-manifest tmp/r534-lineage-inputs-current486.json \
  --out-dir tmp/r534-original-current493
```

Both complete builds start with a fresh factory run. `strace -f` records file
opens across its subprocesses; the audit rejects retained scratch artifacts,
undeclared ROMs/states, cached repository bytecode, ambiguous directory changes,
and incomplete/empty evidence. Factory bytecode caches are redirected to the
fresh output tree, with bytecode writes disabled. The first tracing attempt
(current491) failed closed because sandbox ptrace was unavailable; the traced
rebuild requires that permission, not an untraced fallback. Current492 was an
exploratory success before tightening bytecode/provenance handling and is
superseded by current493.

After factory construction, a Python audit hook forbids every scratch-file
and subsequent original-cartridge read during the historical profile and
lineage replay. The two final ROMs and their semantic receipts must agree.
The final receipt records source/input/tool hashes, both actual commands and
filesystem traces, the generated r120 provenance, all historical evidence,
and `retained_candidate_roms_read: false`. Generated intermediates remain
explicitly disclosed. The output still matches r534 SHA-256 `727ee496...`.

Six new offline controls exercise profile identity/overlap/width/preimage
checks, exact r120 reconstruction, filesystem trace rejection, and immutable
output-directory requirements. The broader regression set passes 195 tests.
No emulator ran, no live observations were refreshed, and neither candidate
pins nor Stop policy changed. Integrating this experimental reconstruction
with the production/palette approval workflow, fresh full-release evidence,
audience approval, and MiSTer/Pocket qualification remains unfinished.

### Verification-only palette interface (2026-09-09)

`record_palette_approval.py --verify-only --r534-original-replay` now exposes
the experimental original-cartridge reconstruction through an explicit,
verification-only profile. It requires the historical input manifest and a
fresh repository-local replay output. Approval confirmation/output options
and the legacy expanded/menu flags are rejected before construction. The
normal audience recorder and final packager approval policy are unchanged.

The new reconstruction receipt verifier checks current source/tool/input
identities, both exact factory commands and environment policies, trace hashes
and parsed filesystem evidence, then regenerates both historical baselines and
complete lineages. Changed, stale, or approval-like evidence fails closed.

The end-to-end current494 attempt passes and reproduces exact pinned r534:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/record_palette_approval.py \
  --rom tmp/stage4-cache-key-r534/candidate.gb \
  --palettes palettes/penta_palettes_v097.yaml \
  --verify-only --r534-original-replay \
  --historical-input-manifest tmp/r534-lineage-inputs-current486.json \
  --replay-output tmp/r534-palette-source-current494
```

The reconstruction receipt SHA-256 is
`c48a6fd5ff5053f0e21e2550c5577a094ab89092b8980a8e01e794abb36d478b`;
the separate `palette-verification.json` receipt SHA-256 is
`981ca1c5be853014bf64878eac75582e1f1f576991fe8c2f855768d27504d87b`.
The latter explicitly records `audience_approval_recorded: false` and
`release_qualification: false`. Eleven focused offline tests pass, including
changed evidence and forbidden approval/profile combinations; the broader
ancestry/art/downstream/Stage-card regression set passes all 200 tests. The strict
read-only Stop check passes without changing its definition or candidate pins;
the reported main-speed manifest rejection was not reproduced. No emulator
ran. At that point, production release integration, fresh full-release evidence, explicit
audience approval, and reservation-backed hardware qualification remain open.

### Fresh complete matrix and explicit runtime control (2026-09-09)

`tmp/r534-full-release-current497/manifest.json` passes all 86 gates against
the unchanged r534 candidate. Its SHA-256 is
`85aae5636e50043366199ef43573b275bf654b626081065e699aeee0a207c736`.
The source/tested-ROM hashes, source snapshot, and resolved runtime libraries
are intact and were independently rechecked after completion. The host process
audit reports no remaining mGBA processes.

This refresh exposed a runtime-selection mistake before the successful run.
Current495 omitted `LD_LIBRARY_PATH` and loaded installed libmgba SHA-256
`df25d1ec...55e4`, instead of the documented CGB-latch build `20fa5dda...b4cf`.
It is retained as failed: 67 passed, 4 failed, 15 dependency-blocked. Ted's
four-color, near-blank screenshot was correctly rejected. No ROM or image
threshold was changed. The existing instrument audit explains the missing
CGB latch writes; the focused current496 control passes with the documented
library and the same ROM, yielding the historical 11-color image and frame-289
settlement. Current497 is a wholly fresh matrix under that explicit runtime;
none of current495's results were resumed or mixed into it.

```sh
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/verify_release_candidate.py \
  tmp/stage4-cache-key-r534/candidate.gb \
  --output tmp/r534-full-release-current497
```

Stage 1–6 strict speed ratios range from 0.999 to 1.007. All-nine boss timing
passes the existing acceptance policy, but several bosses remain faster than
the original; this is not exact timing parity for every boss. The full
trajectory and negative-control checks pass. Boss rendering, flicker, story,
ending, and live palette gates all pass in the same complete matrix.

The fresh `current497/prehardware-package/` bundle revalidates the deterministic
IPS from current427 against the exact candidate and new matrix, includes no
ROM, and retains four distinct native screenshots. Its status remains
`prehardware-do-not-publish`, with hardware and audience approval pending.
No card deployment, MiSTer connection, publication, candidate promotion, or
Stop-policy change occurred. Release documentation now shows the explicit
runtime setting to avoid dependence on inherited login-shell configuration.

### Source-only early construction prefix (2026-09-09)

The six r208/r209 transition traces validate fixed instruction recipes; they
do not choose emitted bytes. Both builders now expose a pure `construct()`
function for those recipes. Their historical `build()` functions call that
same emitter and still require the transition corpora, reject false negatives,
and reproduce the original hash-pinned audit receipts. There is no skip-audit
switch, substituted evidence, or fabricated historical pass.

`r534_stage1_phase_ancestry.construct()` chains all six r120 -> r210 steps with
per-step ROM pins, retaining static-receipt pins for source-only steps. Its
distinct receipt explicitly says `construction-only`, with no historical
transition checks or live qualification. `build_r534_source_prefix.py` combines
that path with the bounded factory -> r120 adapter and the eight source-only
r210 -> repaired-r264 steps. No historical evidence file is needed by this
fourteen-step prefix. Its input is an exact factory image; original-cartridge
provenance for that image remains an upstream obligation, not an inferred claim.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/build_r534_source_prefix.py \
  --factory-image tmp/r534-palette-source-current494/build-1/factory.gb \
  --out-dir tmp/r534-source-prefix-current498
```

The double build reproduces repaired-r264 SHA-256 `aa4c1560...55dbf5a1`.
The construction receipt SHA-256 is
`6033a271acaa77bfcd7ffbbf048ffb5676ea46b7fc888363e0cf76c6933b0060`.
The emitted `intermediate-r264.gb` is not a deployable candidate.

An isolated interpreter test preloads only the factory image, original ROM,
and remaining twenty-two inputs; it never loads the six phase traces. After
loading, it forbids all scratch/original-ROM opens, imports the source modules,
and double-builds the prefix plus remaining lineage to exact r534. All six new
controls pass, including changed inputs/recipes/pins and preserved historical
corpus rejection. The broader regression set passes 206 tests. This refactor
does not change ROM bytes or the default audit/approval profile.

Remaining construction/audit separation work is explicit:

| Segment | Historical inputs still required by the continuation audit |
| --- | --- |
| Stage 7 r264 -> r273 | Two static receipts |
| Stage 4 r273 -> r287 | Fifteen corpus, speed, and WRAM-ownership inputs |
| Stage 1 r287 -> r314 | One room capture and four live/rejected receipts |

The default original-cartridge reconstruction still reruns its full 28-input
historical audit. The new prefix is a production-integration component, not a
new production default or release gate. Current497's full-matrix evidence must
be refreshed after source integration stabilizes. No emulator, deployment,
hardware session, or audience approval is part of this refactor.

The unchanged complete historical audit was also rebuilt twice from the
original cartridge on the refactored source through the verification-only
palette command, retaining all 28 historical checks. Current499's reconstruction
receipt SHA-256 is
`1fbb24f2b4d66cc52520b9e496819eb1f2fea90ecdda64ff17df22b26f8e9f32`;
its palette-source verification receipt SHA-256 is
`f17324e6b93b56e5104acdb61f243de36fe9650c50e47b049b5b18cb71cbd53e`.
The current source snapshot and exact pinned r534 bytes revalidate. The strict
read-only Stop check passes without policy changes.

### Source-only Stage-7 construction (2026-09-09)

The source-only prefix now extends through r273. The r265 menu repair and
r269 transition-state repair expose construction APIs independent of the
historical static receipts. Their historical entrypoints still authenticate
the receipts/control ROM, preserve the old metadata, and rebind the original
static evidence. The source APIs neither synthesize that evidence nor include
the historical patrol summary as a new observation.

The dual-plane constructor reruns all eleven source contract sections without
reading a historical receipt: preimages, runtime and emitted guards, caller/
camera, banked stack, timing, DMA, timer service, mutation controls, router,
and in-memory construction. Source-owned hashes bind these freshly evaluated
contracts and the new r265/r269 construction receipts. The existing exact
ROM pins remain mandatory at all five steps, along with the applicable
source-only static-receipt pins. r271 consumes the generated r265 reference,
not a saved ROM. The historical path uses the same emitters and checks.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/build_r534_source_prefix.py \
  --factory-image tmp/r534-palette-source-current499/build-1/factory.gb \
  --out-dir tmp/r534-source-prefix-current500
```

The v2 prefix receipt records nineteen sequential steps after the factory/r120
adapter and output revision r273. Both builds produce SHA-256
`09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8`.
The construction receipt SHA-256 is
`95c8431b7aac5acdfd109bedb0280ad1c78ff51a99b6d7351f3d12d11df9bbe9`.
The `intermediate-r273.gb` filename and construction-only/non-promotable
metadata make its intermediate role explicit.

The isolated full-lineage test now loads neither the six phase traces nor
the two Stage-7 receipts. With all further scratch/original-ROM reads forbidden,
it double-builds the source prefix and the remaining 86-step audit to exact
r534. Twenty historical inputs remain in that continuation: fifteen Stage-4
corpus/speed/WRAM inputs and five Stage-1 room/live/rejected inputs. The default
original-cartridge audit continues to require all 28.

Twelve focused controls pass. New negative controls cover every Stage-7 ROM
pin, static/source-contract receipt pins, incomplete chains, wrong references,
helper width/preimages/boundaries, caller/mapper contracts, semantic and timing
checks, helper overlap, and missing historical receipts. No emulator, candidate
promotion, deployment, audience approval, or Stop-policy change is involved.

The broader regression set passes 212 tests. Current501 refreshes the unchanged
complete original-cartridge/28-input audit on this source: both builds reproduce
exact r534, and the current source snapshot revalidates. Its reconstruction
receipt SHA-256 is
`14a34be4078f85e12591e04640cd719a676c3ca6dc996ad132abd5702e552e87`;
its verification-only palette receipt SHA-256 is
`567992aa8b299540cfdb8b6904732ee95118064110bad2c488005417b92b3688`.
The strict read-only Stop check passes. Full current-tree emulator qualification
and production release integration remain open, alongside audience/hardware
approval; the source-only prefix is not a substitute for any of them.

### Source-only Stage-4 construction (2026-09-09)

The prefix now constructs r287 without any Stage-4 historical input. The
r285/r286/r287 emitters are shared by separate source-construction and
historical-audit APIs. Their source path retains exact generated r279/r281
references, byte/preimage/ownership-boundary checks, unchanged runtime mirrors
and Stage-7 code, allocation widths, atomic install ordering, checksum/change
counts, cycle arithmetic, and menu semantic controls across all 65,536
FFE4/scene pairs. Per-step ROM pins and source-contract receipt pins reject
recipe or proof drift.

Historical observations stay explicitly outside the construction receipts:
no zero-WRAM snapshot assertion, corpus collision pass, measured route count,
or projected saving is carried as a source-only finding. The old `install()`/
`build()` entrypoints still require the fifteen authentic inputs, rerun the
corpus/WRAM checks, authenticate upstream receipts, and reproduce the exact
historical metadata. This separation neither weakens those audits nor certifies
WRAM lifetime or gameplay behavior from source emission alone.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/build_r534_source_prefix.py \
  --factory-image tmp/r534-palette-source-current501/build-1/factory.gb \
  --out-dir tmp/r534-source-prefix-current502
```

The v3 prefix has twenty-six sequential steps after the factory/r120 adapter.
Both builds produce r287 SHA-256
`a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898`.
Its construction receipt SHA-256 is
`ecf7160d620e6e5f25c3cee49f0806cf85b92e365768fa62c14493599966a419`.
The output is explicitly `intermediate-r287.gb`, construction-only and
non-promotable; factory-image provenance remains a separate upstream obligation.

The isolated full-lineage test loads only the factory image, original cartridge,
and the five remaining Stage-1 inputs. It never loads the six phase, two
Stage-7, or fifteen Stage-4 historical inputs. With subsequent scratch/original
reads forbidden, it double-builds the prefix and remaining 79-step audit to
exact r534. Eighteen focused tests pass, including six new Stage-4 controls for
missing evidence, changed references, ROM/receipt pins, incomplete chains,
emitter guards, and accidental historical claims. No emulator, deployment,
approval, candidate promotion, or Stop-policy change is involved.

The broader regression set passes 218 tests. The default original-cartridge
audit also passes a fresh double build with all 28 historical inputs still
required. Current503 binds the current source snapshot and exact r534 bytes;
its reconstruction receipt SHA-256 is
`1c2000f2e2141ca52be22f67585b73117094a96d834e703119414d4ad1a7de39`,
and its verification-only palette receipt SHA-256 is
`9de6cb97e760af5491240ec3162cac27f63cfe8a9b2ac60c51b1108a9725d2ec`.
The strict read-only Stop check passes. The five remaining construction
dependencies, production release integration, fresh current-tree full matrix,
and audience/hardware approval remain open.

### Source-only Stage-1 room/semantic component (2026-09-09)

The room capture is reused by several later builders, so it cannot yet be
removed from the entire continuation audit. Its first consumers now expose
separate source-construction APIs: r297 wall/scene emission, r300 contextual
semantic rows, and r303 fast scene gates. Their historical `build()` paths
still authenticate the r292 receipt, require the real room capture, check the
35-cell population, and produce the exact old hash-pinned receipts.

The source path retains preimages, helper/cave boundaries, stack layout,
register preservation, scene truth tables, semantic LUT/helper generation,
timing, change ownership, and component ROM identities. It checks the
repository-owned room05 oracle as a source specification, not a new live
observation. Its distinct construction receipts omit captured room01 cell
counts and population claims, and do not impersonate the historical receipts.

`r534_stage1_room_source.py` constructs r287 -> r303 through four existing
source-only setup steps and the new room/semantic/scene component. Source
contract hashes bind all three component receipts, and all sequential ROM/
static-receipt pins remain mandatory:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_room_source.py \
  --base tmp/r534-source-prefix-current502/intermediate-r287.gb \
  --out-dir tmp/r534-room-source-current504
```

Both builds produce r303 SHA-256
`1137bcd557c7ea08f3e57c1f9b4a69fcec41c080ae817fbb139563509c4b08fe`.
The construction receipt SHA-256 is
`033fa77897b831c7652e58bc079a1ff4b8b45cc6de2b575fa95a025b363de712`.
This historical intermediate remains explicitly non-promotable and is saved
as `intermediate-r303.gb`, never as a release candidate.

An isolated test loads only the exact factory image, then forbids all scratch
and ROM/state reads before importing the modules. It double-builds the existing
26-step prefix plus this five-step component to exact r303 without loading
any historical observations. Six new controls cover missing/invalid historical
capture rejection, wrong inputs, source/static pins, scene/wall preimages,
and absence of captured-population claims. The r287 prefix's five-input full
r534 join remains unchanged; r310/r311 still consume the same room capture,
and four live/rejected receipts remain downstream. No emulator, deployment,
approval, candidate promotion, or Stop-policy change is involved.

The regression set passes 224 tests after adding the six room-source controls.
Current505 refreshes the default original-cartridge reconstruction with all
28 historical inputs required: both builds reproduce exact r534, and the
current source snapshot revalidates. Its reconstruction receipt SHA-256 is
`ceb2b2d832f3085bb52c0cc8d48040e499d292b34ac2a511617fa3a93387811d`;
the verification-only palette receipt SHA-256 is
`a82bc6ec9a5f73621d8ddbe876444258d60052814e9fc725c3f607cadcd99caa`.
The strict read-only Stop check passes. The source-only r303 component still
needs integration with subsequent receipt/capture-consuming Stage-1 repairs;
it is not yet a complete source-only r534 build or fresh emulator qualification.

### Source-only r305 repair and r310 precompile (2026-09-09)

The room component now reaches r310. Both builders expose distinct
`construct()` APIs: r305 validates the fixed bank bridge, relocated attr
gateways, wall/cache helper, tagged destination, stack ABI, ownership, and
exhaustive scene model; r310 validates the native FFE5 resolver, erased helper
bank, sole FFBD-to-FFE5 operand change, ownership, and all 65,536 resolver
cases. Neither constructor consumes the rejected-r303 receipt or room capture.

Historical `build()` entry points still authenticate their base receipts and
require the original evidence. The r305 rejection receipt and r310 captured
35-cell population remain mandatory in that audit path, whose original ROM
and serialized receipt hashes are unchanged. The source-only metadata also
omits the old observed bad-tag and r309 live-sample statements; those remain
only in historical metadata. No historical receipt is synthesized as evidence
by the source component.

`r534_stage1_room_source.py` v2 now constructs seven sequential steps from
r287 through r310, plus the r297/r300 component checks. All five construction
receipt identities and every sequential ROM pin are required. Current506
double-builds the component:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_room_source.py \
  --base tmp/r534-source-prefix-current502/intermediate-r287.gb \
  --out-dir tmp/r534-room-source-current506
```

The non-promotable `intermediate-r310.gb` SHA-256 is
`84bf45826c1acd2ae36a971c61aaf05c0ba761b723cd87e568607f9ffac6f36c`;
the construction receipt SHA-256 is
`9f3c258416e80cd29ff94d3fba012a48d309e3b5757e4bca9545750878ce2e6c`.
The isolated no-artifact-read test now covers the 26-step factory prefix plus
all seven room-component steps. Negative controls cover invalid historical
receipts/captures, changed source models and preimages, altered ROM/receipt
pins, and leakage of old observation claims into construction metadata.

Current507 refreshes original-cartridge reconstruction against the current
source snapshot: both builds reproduce exact r534 with all 28 historical audit
inputs still required. Its reconstruction receipt SHA-256 is
`2678562512641b275a1c3da2edc3575e4d7312eb0ffaba3dcd964aec6619bd2b`;
its verification-only palette receipt SHA-256 is
`1a16c105dc452c282807ceea741e55b2933de0c5f2c2adc6bd13cf13b891f948`.
No audience approval or release qualification is recorded.

The default source prefix still ends at r287 and its historical continuation
still requires five inputs. The separate source component removes the r303
rejection dependency only through r310; later construction still needs work
on r307/r311 composition and the room capture plus three live/rejected receipt
dependencies. Production integration, fresh current-tree full emulator
qualification, and audience/hardware approval remain pending. Current497 is
historical exact-ROM evidence, not qualification of these source changes.

All 226 tests in the reconstruction/Stage-1/downstream regression set pass.
The final current-source/tool/input/nested-receipt recheck also passes, as
does the strict read-only Stop check (`{}`, exit 0). No emulator was launched
and no Stop definition, pin, or readiness policy was changed.

### Source-only bank16 mirror and r311 composition (2026-09-09)

r307 now exposes a source-only constructor retaining its exact r305 input,
installer entry census, four bounded mirror repairs, runtime-image simulation,
ownership, checksums, and output identity. Its historical `build()` still
authenticates the exact r305 build receipt and reproduces the old receipt.

r311's constructor takes exact r310 plus an explicit exact r305 reference.
It generates the r307 branch in memory and proves the non-overlapping byte
union, bank16-only ownership, canonical installer image, and unchanged r310
behavior outside the overlay. The FFE0 scratch-lifetime checks, DI callsite,
immediate native reinitialization, immutable BG0 defaults, and source-owned
room05 oracle remain mandatory. The source receipt has no captured room01
population, historical live-pass claim, or historical receipt hash.

The historical r311 entry point still checks all supplied base/branch/live
receipt hashes and schemas, the actual 40-publication/zero-mismatch live
evidence, and the reviewed room01 capture. It independently checks the supplied
r307 branch's composition, not only the newly generated branch. All original
serialized build-receipt and ROM hashes remain exact.

The room-source component v3 now has eight sequential steps from r287 to r311
and the separate generated r307 branch. It pins all seven component receipts.
Current508 double-builds it from the existing r287 source-prefix fixture:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_room_source.py \
  --base tmp/r534-source-prefix-current502/intermediate-r287.gb \
  --out-dir tmp/r534-room-source-current508
```

The non-promotable `intermediate-r311.gb` SHA-256 is
`be8e78761470b811111e74d47c1cbb9923e34d136c420ccb76314a6be22ab84d`;
the construction receipt SHA-256 is
`b9c2112f08953a1ab716ac479000a5e02c29c01fc60d3b71b7eca069a57fa61d`.
The isolated double-build now covers the 26-step factory prefix plus eight
sequential room steps and the generated branch, with scratch/ROM/capture reads
forbidden after loading the factory input. Ten room-source tests cover the
independent path, all component pins, corrupt/missing audit inputs, required
reference identity, altered generated branches, and scratch-lifetime checks.

Current509 refreshes the original-cartridge audit with all 28 historical inputs
still required. Both builds reproduce pinned r534, and verification-only
palette replay passes. The reconstruction receipt SHA-256 is
`627c9773f016f3ccf4d6ae286eb9e2973e4d006b3ac1edd724b0c2f35d8b98cd`;
the palette verification receipt SHA-256 is
`6d0a5a9177a32c87cd5f26206925cdfc4e8f05790bf2771055bb0e7f886a0b0b`.
Neither approval nor release qualification is recorded.

This component no longer needs the room capture or the r310 live receipt.
The default r287-prefix historical continuation still requires its five inputs;
the new source path still needs the later r312/r313/r314 and r317-r343 repairs
separated from historical receipt dependencies before integration into a full
source-only r534 build. The r311 and r313 rejected live receipts remain the
two downstream observation inputs. Production integration, fresh current-tree
full emulator qualification, and audience/hardware approval remain pending.

The 228-test reconstruction/Stage-1/downstream regression set passes, as do
the final current-source/tool/input/nested-evidence recheck and strict read-only
Stop check (`{}`, exit 0). No emulator, deployment, approval, or Stop-policy
change was involved.

### Source-only epoch, self-heal, and publication commit (2026-09-09)

The room-source component now reaches exact r314 through eleven sequential
steps from r287, plus the generated r307 branch. All ten component construction
receipts are pinned. r312 retains exact epoch preimages, mirror equality,
eight-byte ownership, all 256 epoch decisions, and one-shot installer behavior.
Its source constructor neither consumes rejected-r311 evidence nor consults
the captured stale runtime template.

r313's emitted-opcode model now starts from the candidate-owned DAD7 source
and substitutes explicit gateway test cases. Its historical validator also
checks that the captured template is identical outside that gateway, preserving
the old model's identity. Source-only checks retain stack/mapper/IME behavior,
2,052 semantic executions, exact stale-triplet scope, and decoded per-path
timing. Captured-installer claims and the observed 23-entries/162-frames density
and derived average costs remain only in the historical audit metadata.

r314 retains exact handler/cave/caller preimages, transaction/stack semantics,
publication ordering, semantic controls, and change ownership. Its constructor
does not consume the rejected-r313 receipt or report its observed mismatch
population. The historical entry points still require their exact base and
rejected-run receipts, validate all old rejection predicates, and reproduce
the original serialized receipts and ROMs exactly.

Current510 double-builds the v4 component:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_room_source.py \
  --base tmp/r534-source-prefix-current502/intermediate-r287.gb \
  --out-dir tmp/r534-room-source-current510
```

The non-promotable `intermediate-r314.gb` SHA-256 is
`010f9b78e5294f436d4a6735e799f12546a26827637db5ce1d6646eeff06c303`;
the construction receipt SHA-256 is
`1bb218b21fa931e50cde02e468442f2ae66d0e3133989c4a9a256e3648bbf884`.
The isolated double-build covers the 26-step factory prefix plus all eleven
room steps and the branch, forbidding subsequent scratch/ROM/capture reads.
The 12 room-source tests include disabled historical validators and captured
runtime constants, mutated source preimages/models/pins, and corrupt or missing
historical evidence. The existing r312-r314 regression tests also reproduce
all three original receipt identities.

Current511 refreshes original-cartridge reconstruction against the current
source snapshot. Both builds reproduce pinned r534 with all 28 historical
audit inputs still required; the verification-only palette check passes.
The reconstruction receipt SHA-256 is
`ea7113eaa5aeab6303919c9d05f9787144ea6e670ce1aa7df35c530a6aa50987`;
the palette verification receipt SHA-256 is
`8aa06ea0053d1fd93bf6654b8b767a17be33ec4dc75262edd8ff7e418dc5240c`.

The separate r287 -> r314 source chain no longer needs any of the five
historical observation inputs. This does not change the default r287-prefix
audit or authorize fabricated historical build receipts: r317-r343 still
need source-construction integration before the later r343 continuation can
be joined into a full source-only r534 production build. Fresh current-tree
full emulator qualification, audience approval, and hardware evidence remain
pending; no emulator, deployment, approval, or Stop-policy change was involved.

All 230 tests in the reconstruction/Stage-1/downstream regression set pass.
The final current-source/tool/input/nested-receipt recheck and strict read-only
Stop check (`{}`, exit 0) also pass. These are construction/audit results,
not new live emulator or hardware qualification.

### Source-only selector latches and effective row dispatch (2026-09-09)

r316-r319 now expose separate source constructors. The r316 relocation retains
the operand inventory, native reader/writer/reload preimages, collision model,
CGB-only header, ownership, and checksum checks. r317 generates r316 in memory
and retains first-use domination, installer/trampoline/serial-vector preimages,
the 2,304-case cold/hot dispatcher model, and preservation of live hot tokens.
r318 retains the complete-scene B-register ABI, owner/miniboss predicates,
branch targets, exact accepted-path timing, and relocated latch ownership.
r319 retains the four FFE5 operand repairs, native resolver, generated semantic
helper/LUT identities, register/flag behavior, timing, and prior repairs.

All four historical `build()` paths still authenticate their original base
receipts, and the 40 existing tests reproduce the exact old ROM and serialized
receipt identities. Source-only metadata does not claim an executed SC-access
audit or carry the observed popped-B value; historical output is unchanged.
Pocket/register round-trip, executed owner census, SC/IE safety, live visual,
and speed requirements remain explicit and unfulfilled by construction alone.

`r534_stage1_latch_source.py` constructs r314 -> r319 through three sequential
steps and an independently checked r316 component. All four construction
receipts and all output ROMs are hash-pinned. Current512 double-builds it:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_latch_source.py \
  --base tmp/r534-room-source-current510/intermediate-r314.gb \
  --out-dir tmp/r534-latch-source-current512
```

The non-promotable `intermediate-r319.gb` SHA-256 is
`2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db`;
the construction receipt SHA-256 is
`9f5e4c19102fa771b129c886b2606bbbf83061226a47c2051f476bc11c0d8bf9`.
Six new tests cover independent construction, no historical reads/calls or
observation claims, exact historical receipts, corrupted preimages, altered
models, and ROM/receipt pins. An isolated process double-builds the 26-step
factory prefix, eleven room steps, and three latch/row steps (including their
generated components) with subsequent scratch/ROM/capture reads forbidden.

Current513 refreshes original-cartridge reconstruction with all 28 historical
inputs still required. Both builds reproduce exact r534; verification-only
palette replay passes. The reconstruction receipt SHA-256 is
`5e7d9de14f0a93607aeb781c9d362a027ec212bbfd5c52fbd304495e210ba8d8`;
the palette verification receipt SHA-256 is
`822397b941273fac6a32559e2b24ac3763f86981ea622a53d0d8c9ca3d21a575`.

The source path through r319 still needs r320, r336 and its nested admission/
art constructors, and r341-r343 hazard repairs integrated before joining the
later r343 continuation. The default historical replay is unchanged, and no
historical receipt is fabricated to bridge this gap. Current-tree full emulator
qualification, production approval integration, and audience/hardware evidence
remain pending. No emulator, deployment, approval, or Stop-policy change was
involved in this work.

All 236 reconstruction/Stage-1/downstream tests pass. The final current-source,
tool, input, and nested-receipt recheck passes, as does the strict read-only
Stop check (`{}`, exit 0). These do not replace fresh live qualification.

### Source-only atomic presentation and admission art (2026-09-09)

r320 now separates exact construction from historical build metadata. Source
checks retain the scroll-first interrupt-closed publisher, both selector clones,
caller/return/mapper census, exhaustive transaction semantics, mutation controls,
and byte ownership. Construction does not report the old g1040 frame, 101-cell
terrain mismatch, or retained comparison captures. The historical entry point
still requires the r319 receipt and reproduces its original metadata exactly.

The nested r336 path also has independent source APIs: r321's return handler,
r324's phase/art helper, r325's menu wrapper, r331's resident-runtime copier,
r335's selected runtime regions, and r336's admission-time art restore. The
source path retains exact r320 input, canonical signed-art identity, erased
caves, native menu invalidation, payload bounds, copy layouts, checksum checks,
existing ownership checks, and the preserved atomic publisher. The source
selected-DA16 recipe is not represented as newly authenticated capture evidence.

r335 no longer temporarily assigns `r331.regions`. Explicit selected-region
entry points pass the fixed layout to the shared emitter. The historical path
still authenticates its r320 receipt through the nested builders; all six
intermediate historical receipts and final ROMs compare byte-exactly with their
retained originals. No receipt is manufactured to satisfy an audit requirement.

`r534_stage1_admission_source.py` constructs r319 -> r320 -> r336, independently
pinning all seven component ROMs and construction receipts. Current514
double-builds this component:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/r534_stage1_admission_source.py \
  --base tmp/r534-latch-source-current512/intermediate-r319.gb \
  --out-dir tmp/r534-admission-source-current514
```

The non-promotable `intermediate-r336.gb` SHA-256 is
`484cd678bd6724f7ab9c128a985a0a50db1c523ad406103a8f57bd84784f4611`;
the construction receipt SHA-256 is
`e610b78ee19939f29da26d1823fa856beceb2f402b9f3eedc4fb10a01ff0526c`.
Six new tests cover missing historical receipts, exact historical serialization,
source preimages/models/pins, absence of observation claims, immutable module
region selection during emission, and an isolated factory-to-r336 double-build.
The isolated test forbids scratch/ROM/capture reads after loading the factory
input and covers the 26-step prefix, eleven room steps, three latch/row steps,
and two presentation/admission steps plus their generated components.

Current515 refreshes the default original-cartridge audit with all 28 historical
inputs still required. Both builds reproduce pinned r534 and verification-only
palette replay passes. The reconstruction receipt SHA-256 is
`2fa0d7c6900a107c11e77b807c54e2b84057051d6d2a2f2d10b0ec8e488fdb96`;
the palette verification receipt SHA-256 is
`b762c36da5c9a0e565e7cd42c08c138fcc11d0e6600be711a6f3b1179aa31e83`.

Source integration still needs r341-r343's hazard repairs, followed by a
verified join to the r343 continuation and original-cartridge production
profile. Current-tree full emulator qualification and audience/hardware approval
remain pending. No emulator, deployment, approval, or Stop-policy change was
involved in this work.

All 242 reconstruction/Stage-1/downstream tests pass. The final current-source,
tool, input, and nested-receipt recheck and strict read-only Stop check (`{}`,
exit 0) pass. These remain construction/audit results, not fresh live gates.

### Source-only hazard closure and complete factory-to-r534 join (2026-09-09)

r341-r343 now expose separate source constructors. The terminal palette/LUT/
cold-entry compiler, exact native art preimages, source-owned YAML silhouette,
conditional runtime repair, GDMA completion loops, cave bounds, checksums, and
byte ownership remain checked. r343 requires explicitly supplied original
bytes; its constructor never opens the default cartridge path. Historical
builders still validate their base receipts and reproduce all original receipt
and ROM identities. The 17 existing hazard tests pass unchanged.

`build_r534_source_candidate.py` joins the generated r343 with the existing
60-step continuation. Before that join, 45 source-construction steps cover the
factory prefix, room repairs, latch/row repairs, atomic/admission repairs, and
the three newly separated hazard repairs. Every hazard component receipt and
ROM is pinned, and the join requires the exact r343 and r534 identities. The
continuation must consume no historical evidence or ancestry inputs. Its old
"retained r343" label is not copied into the new generated-input receipt.

Current516 constructs the complete exact r534 ROM twice:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 scripts/diagnostics/build_r534_source_candidate.py \
  --factory-image tmp/r534-palette-source-current515/build-1/factory.gb \
  --original-rom 'rom/Penta Dragon (J).gb' \
  --out-dir tmp/r534-source-candidate-current516
```

The output candidate SHA-256 is the pinned r534 identity
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`.
Its construction receipt SHA-256 is
`adc01ca6c47e87f19e6cd5e86eea4cb115111850b9c466c000de5315fc4e56f5`.
The CLI forbids scratch and ROM/state opens during both in-memory builds,
rechecks source and input identities before writing, and labels the result
experimental, construction-only, and non-promotable.

Six new tests cover source-only hazard construction, exact historical receipts,
original/input/ROM/receipt pins, YAML/art/preimage/cave guards, rejected joins,
and an isolated full double-build. The isolated process loads only factory and
original bytes before forbidding subsequent scratch/ROM/capture reads; both
105-step runs produce identical ROMs and metadata with zero historical inputs.

Current517 separately refreshes the historical original-cartridge audit with
all 28 historical inputs still required. Both runs reproduce exact r534 and
verification-only palette replay passes. Its reconstruction receipt SHA-256 is
`f8bcda4b107875db7a27f0ee1bb4519e41464c4614139f6a83da192173f976c0`;
the palette verification receipt SHA-256 is
`453555a3122072bf973b1055ba738371a8b429a487c20ed57d764bc058353023`.
This audit has not been silently switched to the new construction semantics.

The source-only factory-to-candidate chain is now closed, but the CLI still
accepts a separately built factory image. Next is an original-cartridge build
entry point using this chain without a historical-input bundle, followed by
production approval integration and fresh current-tree full emulator gates.
Audience/hardware evidence and deployment remain pending. No emulator,
deployment, approval, or Stop-policy change was involved in this work.

All 248 reconstruction/Stage-1/downstream tests pass. The source-only receipt's
current snapshot and the historical replay's source/tool/input/nested evidence
revalidate, and the strict read-only Stop check passes (`{}`, exit 0). None of
these checks represents a new emulator or hardware playtest.

### Original-cartridge source-only entrypoint (2026-09-09)

`scripts/build_r534_candidate.py` now builds the exact experimental candidate
from the original cartridge, selected palette YAML, and repository source. It
accepts no historical-input bundle, retained factory ROM, or approval options.
The shared factory tracing helpers preserve the separate historical replay's
invocation, environment policy, filesystem audit, and input verification.

Current522 is the fresh successful source-only proof:

```sh
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/build_r534_candidate.py \
  --out-dir tmp/r534-original-source-current522
```

Both factory runs check 745 filesystem open calls. Each then performs all 105
source construction steps with scratch/ROM/state reads forbidden. Both ROMs
and raw construction metadata must match before serialization. Verification
rechecks the complete persisted JSON contract, current tools and source
fingerprint, exact original/palette identities, both factory invocations and
traces, and both regenerated candidates. The new entrypoint itself is included
in the source fingerprint. An independent post-CLI receipt recheck also passes.
The output SHA-256 remains
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`;
the build receipt SHA-256 is
`b8eef46492f190a81ab9a82e72242606663445606d2b238b42c91f86897c430e`.

Current518 is retained as a failed verification attempt: construction produced
the correct bytes, but comparing Python integer-keyed maps with JSON's string
keys rejected the serialized receipt. The fix compares canonical persisted
JSON while preserving the raw double-build comparison and distinguishing
booleans from integers. Current520 verified that fix; current522 supersedes it
with the entrypoint included in the source fingerprint. No failed or older
attempt was overwritten or relabeled as current evidence.

The independent historical replay remains unchanged in meaning and still
requires all 28 authenticated historical inputs. Current523 refreshes that
audit and verification-only palette replay against the final source snapshot.
Its build receipt SHA-256 is
`4aad545a0e8a28f8fa8393f6a2a85ff0b06d2471d10ede9b90cf7c0ebbfae775`;
the palette verification receipt SHA-256 is
`28207134839bfeb0487fbe8b6c96c1493371bc8af529decdcabf34bc067404c8`.

New tests cover JSON round trips and type-sensitive mutations, entrypoint
fingerprinting, fresh-output and tracing requirements, rejected historical/
approval CLI options, artifact guard enforcement/deactivation, current-source
and exact-ROM checks, both factory records, and policy/tool/input/metadata
mutations. These source proofs remain experimental and non-promotable. Full
current-tree emulator qualification, hardware evidence, production approval
integration, and audience approval remain pending. No emulator, deployment,
approval, or Stop-policy change was involved in this work.

All 258 reconstruction/Stage-1/downstream tests pass (162.882 seconds), including
the new source-entrypoint fixture and mutation checks. The final strict
read-only Stop check passes (`{}`, exit 0) with the pinned CGB-latch runtime;
the reported main-speed-manifest failure did not reproduce in either direct
check. The trusted Stop hook remains enabled and unchanged. These results do
not replace fresh current-tree emulator or hardware qualification.

### Source-only palette approval and packaging integration (2026-09-09)

The new `r534_source_profile.py` binds the exact original-source build receipt
by canonical path, SHA-256, and current source fingerprint. Independent binding
verification regenerates both candidates and revalidates all factory traces,
inputs, tools, and source identities. The new `--r534-source` recorder profile
does not accept historical bundles or legacy build-profile switches.

Current524 exercises only verification mode:

```sh
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/record_palette_approval.py \
  --r534-source --verify-only \
  --rom tmp/stage4-cache-key-r534/candidate.gb \
  --palettes palettes/penta_palettes_v097.yaml \
  --source-output tmp/r534-palette-original-source-current524
```

Both traced constructions produce pinned r534. The build receipt SHA-256 is
`6682ad888973e16409d2bc582a711559cbd7132a180f80fabd824c70f904acad`;
the separate palette source-verification receipt SHA-256 is
`869442a23f62f91a067653a41e978cf0f7a39824677dce7a4101cc26d4d7b511`.
That receipt explicitly records no historical inputs, audience approval, or
release qualification. Its complete source binding was independently rechecked
after the CLI passed. Candidate identity remains
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`.

Approval capability is implemented but was not invoked: recording an audience
decision still requires the exact existing confirmation phrase, a fresh
approval output, and another fresh source build. Verification-only mode rejects
confirmation/output options. The new profile never overwrites an existing
approval, and both source and ROM/YAML bindings are checked again before any
approval write. Unit tests exercise serialization through an in-memory mocked
file handle; their synthetic approvals are never saved as release evidence.

The final packager recognizes `r534-original-source-v1`, independently
revalidates the bound reconstruction, and rejects substituting the older
expanded-Ted approval profile for exact r534. Its separate hardware and audience
requirements remain mandatory. For all profiles, packaging now also checks the
authoritative full gate order and compares source/runtime identities to the
current tree and runtime. The old check only proved stability within the prior
run. A direct read-only control confirms that the otherwise-passing current497
86-gate manifest is rejected as stale; no fresh emulator evidence is implied.

The separate historical replay still requires all 28 authenticated inputs and
passes in current525. Its build receipt SHA-256 is
`5a33b1ae7b6aa46034a4407c75bf588d995420982f8ea9d0b59fc363e570c989`;
its palette-verification receipt SHA-256 is
`e911c71d51720e8297fd09cb25e0b2c9981ed65fb4d89934747c57418333bf4e`.
Its complete receipt was independently revalidated against the final source.

The next source integration is the deterministic-suite build/receipt profile,
followed by a fresh full serial emulator matrix. Actual audience approval,
reservation-backed hardware qualification, and deployment remain pending.
No emulator, hardware contact, approval recording, package creation, deployment,
or Stop-policy change occurred during this integration.

All 274 reconstruction/Stage-1/downstream/profile/packaging tests pass in
170.893 seconds. The MiSTer input tests use mocked transport, not hardware.
The strict read-only Stop check also passes (`{}`, exit 0) with the pinned
CGB-latch runtime. Source-only and historical receipts both revalidate against
current source/tools; these results do not confer live or hardware qualification.

### Deterministic-suite integration and fresh run started (2026-09-09)

`run_deterministic_suite.py --r534-source` now performs two independent traced
original-source builds and uses their exact outputs for the full serial matrix.
The profile requires a fresh repository-local scratch output and rejects legacy
flags and resume. Both source-build bindings are retained in the run and final
receipt. The r534 receipt verifier requires the actual canonical matrix path
even when a summary receipt is copied elsewhere: it revalidates source builds,
current source/runtime identities, source and tested-ROM bytes, matrix hash and
result summary, and the regenerated nested exception ledger. No staging,
published-receipt replacement, approval, or deployment is implied.

The ledger now has an explicit r534 mode. The Stage-7 gate emits a strict
world-position `receipt.json`, not the old frame-patrol `manifest.json`.
Historical required slowdown IDs also no longer describe current r534.
The new mode consumes the actual patrol receipt, reports observed loop-speed
and publication-cadence exceptions (including previously omitted bounded
speedups), and rejects target misses without an explicit acceptance in their
gate evidence. It does not require fixed historical slowdowns to recur. The
complete regenerated ledger must match the suite receipt; legacy mode retains
its earlier path and required-exception contract.

The combined suite first exposed a test-isolation issue caused by an older
screenshot test reloading the packager module. After correcting the mock target,
all 281 tests passed in 171.320 seconds. Current527 separately refreshed the
source-only palette verification at that source snapshot; its build and
palette-verification receipt SHA-256 values were respectively
`ca1a1566fefd42f0f550114590794e2027179ca7b23cd1a5e747fcde92a0fee1`
and `f3d48d14d2d73af4eed07238c670eb40ff32800b93fb10ae7cbbf0ea50c8acbb`.
The strict read-only Stop check passed (`{}`, exit 0).

The first integrated attempt, current526, failed in source build A before any
emulator launch: its factory filesystem audit rejected the inherited emulator
`LD_LIBRARY_PATH` pointing into retained scratch storage. That attempt remains
untouched. Source-build subprocesses now remove `LD_LIBRARY_PATH` and
`LD_PRELOAD`; the matrix retains the explicitly selected emulator runtime.
The factory filesystem audit was not weakened. After this isolation change,
all 30 focused source/profile/suite/screenshot tests passed in 27.795 seconds.
Current527 is historical to that final change, not current-tree qualification.

The fresh retry is current528:

```sh
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
TMPDIR="$PWD/tmp" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/run_deterministic_suite.py \
  --r534-source --output tmp/r534-deterministic-current528 \
  --receipt tmp/r534-deterministic-current528/suite-receipt.json
```

Its source fingerprint is
`68823c15258fb25be54467e8d5d33bbdd59b74960baa01b29d065d6fc7c50654`.
Both independent builds reproduce the pinned r534 SHA-256
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`
and MD5 `1bd65503ff407e44114dc206087e92f2`. The host was checked empty before
launch, and the existing serial single-flight runner owns the matrix. At the
initial progress check, 15 gates had passed and stage-card stability was
running. This is explicitly an in-progress run; a completed suite receipt and
fresh qualification are not claimed. Continue observing the same live run,
without restarting or editing source while it is active.

### Current528 completed qualification and receipt revalidation (2026-09-09)

The same current528 process completed normally: all 86 serial gates passed,
with no restarts, no failed gates, and no source edits during the run. The matrix
ran from `2026-09-09T09:52:58.620037+00:00` to
`2026-09-09T10:19:19.085296+00:00` (about 26 minutes 20 seconds).
Source, runtime, source-ROM, and isolated tested-ROM integrity checks all pass.
The post-run host check reports no running mGBA processes.

The final evidence is:

- `tmp/r534-deterministic-current528/suite-receipt.json`, SHA-256
  `01e0f45dff6ad9cce9f20adbab25b6edef5d4af7433d799b7537be83d4c3d770`.
- `tmp/r534-deterministic-current528/matrix/manifest.json`, SHA-256
  `226146a4aa5407ff85f4ddc1200e25bbd5fec62e779b8aa432749b383a834260`.
- `build/source-a/build-receipt.json` under that run, SHA-256
  `26c146cf57adbd0b6f3262535aa116cab5a71d2dab862dd446f666940d442575`.
- `build/source-b/build-receipt.json` under that run, SHA-256
  `0e7dbf959525f4c8a5282e983fda02ae3b12d7842514e8bd0528cff063cc77f5`.

Independent verification passed:

```sh
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/verify_suite_receipt.py \
  --receipt tmp/r534-deterministic-current528/suite-receipt.json
```

The recorded runtime environment uses the logical repository path
`/home/struktured/projects/penta-dragon-dx/tmp/mgba-cgb-latches-r454/build`;
use that same `LD_LIBRARY_PATH` value when verifying this receipt if `$PWD`
resolves through a different alias. The actual library SHA-256 remains
`20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`.
The source fingerprint remains
`68823c15258fb25be54467e8d5d33bbdd59b74960baa01b29d065d6fc7c50654`.

Fresh stage-speed ratios are 0.9985, 1.0066, 1.0000, 1.0000, 1.0038, and
1.0000 for stages 1-6; every strict target passes. Stage 7's matched-world-work
ratio is 0.9972086531751571 in both replays and also meets the strict target.
The ledger explicitly contains 19 accepted measurements, including bounded
boss speed/cadence differences and 9.9511% longer combined attract duration.
These are measurements, not 19 newly discovered defects; they remain visible
under the existing operator-reviewed policy, not silently called native parity.
The fresh title, stage-card, and Ted-arena captures were also visually sampled;
the Ted arena is nonblank. These samples supplement, not replace, the gates.

Current529 refreshes the source-only palette profile against the same source.
Its build receipt SHA-256 is
`cef91eb0c561747ed2d72bd13f1784c3c2c6d19c640eb6222c6feb058734a9bc`;
its verification-only palette receipt SHA-256 is
`0d79738aa475f760c5b3abfd1a7acea532a7bdf9d23b045f26216cd700fbdd0d`.
No approval was recorded.

The fresh `current528/prehardware-package/` directory contains a deterministic
IPS that reconstructs the exact candidate (271,995 bytes, SHA-256
`b7a4a99ef3db72cbfcc399c12f39d30c7c65b09bcf37455ec993116d616bb74f`).
The checked-in IPS was not changed. PREHARDWARE packaging revalidated the current
matrix and emitted a ROM-free ZIP, SHA-256
`fc5cfa62866f337c91d4e5c6b996473e26a400d34ea4dc62b9278d7f527eddfa`.
The ZIP contains only IPS, README, and checksums; four native 160x144 screenshots
are alongside it. ZIP integrity and the absence of ROM/save/state entries were
checked independently. The package remains explicitly not for publication.
No published receipt, approval, Git index, hardware device, or deployment was
changed. Hardware qualification and audience approval remain separate blockers
to final release, not things inferred from this emulator pass.

The final, post-matrix regression rerun passes all 281 tests in 232.180 seconds
against the same source fingerprint, including the final source-build environment
isolation change. MiSTer transport in those unit tests is mocked; no hardware
contact occurred. The final strict read-only Stop check passes (`{}`, exit 0).
The source fingerprint, source-only palette verification, and pinned ROM were
checked again after documentation updates and still agree. The generated ROMs,
receipts, captures, IPS, and PREHARDWARE archive remain in ignored scratch storage.

### Pre-stream and hardware-handoff audit; current530 refresh (2026-09-09)

The post-qualification handoff audit found two concrete tool defects. The live
profile's inventory omitted five registered gates: gameplay movement stress,
low-health Scene-0B publication, the Pocket visual-incident control, and both
current pickup-state/host-palette checks. Its no-emulator contract check failed.
Those explicit inventory entries are now present; both the default and exact
r534 contract checks register all 86 required gates.

The live verifier also gains `--verify-manifest`: a read-only validation of an
existing complete, current full matrix. It checks exact ordered coverage, source
and runtime identities, intact source/tested-ROM bytes, and stable evidence
throughout validation. It accepts neither partial nor selected-pass evidence,
does not run an emulator, and does not write/relabel a playtest receipt. Unit
controls reject omissions, altered ordering, stale identities, changed ROMs,
non-integer return codes, and ambiguous CLI combinations.

The local-only MiSTer preflight had accepted current528 after the tool source
changed, because it only checked stability within the historical matrix. It now
requires current source/runtime identities, exact source/tested-ROM SHA-256
identity, and input stability through IPS verification. The same preflight is
repeated at physical checkpoints before core/ROM queries. A direct negative
control confirms current528 is now rejected as stale. The shared reservation
guard remains unchanged. Its actual check reports missing
`MISTER_RESERVATION_ID` and `MISTER_RESERVATION_CHECKER`; no MiSTer connection
was attempted. Deployment permission was requested separately, not inferred.

The generated MiSTer launch sidecar now belongs beside this project's deployed
ROM (`/media/fat/games/GBC/penta_dragon_dx_launch.mgl`), not system `/tmp`.
That path change is covered by an offline contract test but still awaits actual
physical validation. The stream documentation distinguishes the current pinned
r534 source profile from older expanded-Ted commands and makes clear that a
changed audience palette requires a newly established candidate identity.

The regression run passed 289 tests in 192.788 seconds. After the final launch-
sidecar path change, all 20 focused handoff/source-profile/suite tests passed in
0.074 seconds. MiSTer transport in those tests is mocked. The strict read-only
Stop check passed (`{}`, exit 0) during the audit. No emulator or device was
launched by the contract/preflight checks.

The fresh `tmp/r534-deterministic-current530/` run has now started through the
same serial single-flight suite, with two independent traced source builds and
the complete 86-gate matrix. Its source fingerprint is
`8c2b65e7b1d82591e1ec9393de842db191fd381056cd63922b5175faf33c2f7f`.
The host process precheck found no mGBA process. Its requested final receipt is
`tmp/r534-deterministic-current530/suite-receipt.json`, leaving the published
receipt untouched. This is an active run, not a completed pass. Continue the
same process and keep source unchanged until it finishes, then independently
verify the suite and the new read-only live/hardware-preflight paths.

### Completed current530 handoff verification (2026-09-09)

The run described above has finished successfully. Its serial matrix ran from
10:39:47 UTC through 11:10:52 UTC and passed all 86 gates. Both independent
original-source builds reproduce the exact pinned r534 candidate. Independent
suite-receipt verification and `verify_live_regression.py --verify-manifest`
both pass against current source fingerprint
`8c2b65e7b1d82591e1ec9393de842db191fd381056cd63922b5175faf33c2f7f`.
The local-only MiSTer release-input preflight also passes all 86 gates and
verifies candidate MD5 `1bd65503ff407e44114dc206087e92f2`; it makes no device
connection and does not acquire a reservation or deploy anything.

Retained current530 SHA-256 identities:

- suite receipt: `274a76a68dbab579b012f2e0d0a494c547055aa8387b2da83824b3e9a2ab13bd`
- matrix manifest: `18eb324cf78f99246e7c61a7ce753df8e3af344630fd1307a297fdb2a3070abe`
- source-a build receipt: `f07a0d5b840e905f44a250b5f6b5d0d776851ae858065847bd2a6df9fbbd9680`
- source-b build receipt: `54ddfc956c8c6e0ea1a40202979fffb4c3efab2e2531a4ec044821aa29e05b8c`

Current531's source-only palette proof independently revalidates both
constructions against the same current source and palette. Its build receipt
SHA-256 is `0f22e9733eec024c80ae11ebead8685895a9d38e2fb0a1f6691ff28aa302a9f8`;
its verification-only receipt SHA-256 is
`ec3228da500061b2645b0e350cc847ae4444c1dd444a3ef0a95f916ff2612592`.
Audience approval, release qualification, and historical-evidence consumption
are all explicitly false.

The current530 PREHARDWARE ZIP passes independent archive-integrity checking
and contains only the IPS, README, and checksums, with no ROM/save/state entry.
Its SHA-256 is
`fc5cfa62866f337c91d4e5c6b996473e26a400d34ea4dc62b9278d7f527eddfa`.
No published package or receipt was replaced. All generated artifacts remain
in ignored repository scratch storage.

The strict read-only Stage-1 Stop check returns `{}` (exit 0), including the
main speed manifest check. The reported Stop failure does not reproduce with
the current pinned evidence. The trusted hook definition remains unchanged;
the read-only check disables emulator fallback, not validation. A host process
check found no mGBA emulator or unfinished source-proof process. Physical
hardware qualification and explicit audience approval are still pending.

The final offline regression rerun passes all 290 tests in 175.727 seconds.
MiSTer deployment output in that test run comes from mocked transport; no
device was contacted. The real, local-only reservation check still fails closed
because `MISTER_RESERVATION_ID` and `MISTER_RESERVATION_CHECKER` are missing.
After the audit update, all 834 source inputs retain the current530 fingerprint,
and the pinned candidate plus both independent source-build ROMs retain the
exact r534 SHA-256 above.

### Exact-candidate Ted operator-review capture, current532 (2026-09-09)

The completion audit found that known-deviation item 6 still requires explicit
operator ratification of Ted's stabilized whip/orb plane. Its linked v8 clip
binds DX SHA-256
`dbf336126f4559c3b47aec033946835e6195e7bbcc706fadb7a457579012a97a`,
not current r534. Neither the passing Ted readiness receipt nor general palette
source verification supplies that human decision.

A fresh comparison now lives at
`/mnt/data/tmp/penta-r534-ted-review-current532/index.html`, with
`og-vs-dx.mp4`, `contact-sheet.png`, and `receipt.json` alongside it. Large frame
sequences stay in `/mnt/data/tmp/`, outside Git. The existing checked-in
single-flight capture workflow ran OG and DX serially, using current530's
qualified Ted states:

- DX state SHA-256: `bf1c884f9032970d88d5ce39043f86a37d5bb577b96d631b6a95238d1f525311`
- OG state SHA-256: `8d0c6304acbc5585f1ec2642877d9e45e6fb4f3cc573957dc23eafeb84b1b1f1`

Both state identities match the current530 cadence evidence. The capture uses
the same pinned CGB-latch runtime, exact r534 ROM, and original cartridge hashes
documented above. It contains 3,600 native frames from each game, without
repeating a shorter source window. Independent video inspection reports
1280x620, 60 fps, 60.000 seconds, and 3,600 encoded frames. The comparison is
explicitly not phase-synchronized and makes no timing claim.

All 3,600 DX frames pass rendered containment, including 747 expansion frames
and zero violations. The 3,620-frame trace reports zero geometry violations,
zero absent-crown frames, and zero maximum screen jump. The contact sheet was
visually inspected and is nonblank; this static sample does not prove the
animation choice is acceptable. The operator decision remains pending.

Independent SHA-256 checks match the capture receipt:

- video: `147408610b6b40f110d59afde39635263b3d85f0cbb695eac60a9983ac167c27`
- contact sheet: `2b0698436e8f1f1f90e8a646d86c988159f0dacb9c78a16fe17404a0ce900542`
- receipt: `0e2487ced9904e0795014d644cab09949c4c0b3403b30acc2c589a8b27b1882e`

The post-capture host check found no mGBA emulator. No ROM/source tool, staged
deviation policy, approval record, hardware device, or published release was
changed. This provides exact-candidate review material, not a new hardware or
audience qualification.

### Headed START-menu regression and transition flashes (2026-09-09)

The operator reproduced a failure on the exact r534 source-a ROM in the guarded
headed session (PID 2031378). The loaded library was independently read from
that process's mappings and is the same corrected r454 libmgba used for the
matrix; this is not the earlier uncorrected-library blank-arena failure.

Reported sequence: START to open the item menu, exit, and remain stationary.
Red/green cells persist across the upper-left floor and walls until movement.
The operator reopened the menu only to capture the failure; a second opening
is not required to trigger it. mGBA's F12 captures are:

- `tmp/r534-deterministic-current530/build/source-a/candidate-0.png`
- `tmp/r534-deterministic-current530/build/source-a/candidate-1.png`
- both SHA-256: `86a5d9dc9d9aa86e5b5e885d9a17744a10e41d358cc4254ba3eeff0e16381601`

The latter screenshot was visually inspected. It shows the item menu below the
corrupted upper-left background. Actual tested ROM SHA-256 remains
`727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b`.
The active gate's tested provenance is now `FAILED_HEADED_TEST`; the trusted
Stop command and hook implementation remain unchanged. The historical rc11
incident record is preserved as a separate older incident.

Two additional operator reports remain open: a yellow/frozen initial dungeon
presentation before loading finishes, and a brief apparently DMG-colored title
after START confirmation. Neither has yet been reproduced frame-by-frame.
The existing start-route gate checks progress/nonwhite coverage, not exact
transition color continuity, and the stage-card color probe confirms the title
with A. Those passes therefore do not establish the reported START path.

The natural full-background menu probe previously used fixed SELECT pulses
after a long stationary wait. It now exposes an explicit `--menu-key start`
route and binds that button in the report. The full release and live inventories
now both require `stage1_start_menu_stationary`, with no movement argument,
blank SRAM, and a retained final state. A synthetic upper-left red/green raster
control verifies that the independent pre-menu background comparison rejects
the observed kind of artifact; it never treats the bad operator screenshot as
a clean baseline. This is new coverage, not a repaired ROM or demonstrated
emulator reproduction yet. The active human session must be preserved/closed
before serial automated reproduction can begin.

Offline validation: all 14 natural-menu unit tests passed. The accompanying
live-roster test correctly failed its old 86-gate count; after updating that
explicit expectation to 87, all five live-manifest tests and both new regression
controls passed together (7 tests, 11.990 seconds). The read-only live inventory
check registers all 87 gates. A direct strict Stop check now returns a blocking
decision for `FAILED_HEADED_TEST`, as intended, without launching an emulator.

Follow-up static inspection corrected the new route's close input before any
emulator execution. Native fixed-bank `$1D94` tests B and branches to the close
tail at `$1DC2`; the SELECT test at `$1DBC` also falls into that tail. START at
`$1DB8` instead branches to the item-use path at `$1DCF`. The new matrix route
therefore explicitly uses `--menu-key start --close-key b`, not START twice.
The diagnostic CLI can also select SELECT or START separately at the second
edge, with both requested inputs bound in its report. Six focused roster/input
tests pass after that correction. Actual reproduction is still pending the
single-flight slot occupied by the operator's preserved headed session.

### Outgoing-title flash confirmed from retained frames (2026-09-09)

Read-only reanalysis of current530's existing stage-card captures reproduces
the title-color report even on its A-confirm route. In all four DX replays
(`run-1`, `run-2`, and both `blank-sram-run-*` directories), frame 194 is the
colored title; frame 195 has LCD disabled; frames 196 through 212 display the
same outgoing title geometry with zero chromatic pixels and two visible colors.
The scene byte has already changed from `$01` to `$00`, but the title remains
visible for those 17 monochrome frames. Frame 196 SHA-256 is identical in all
four captures:
`6244ac855a1a3b419bc357148e2abae68aebcaf2713f49485a6c85ec35151b39`.
The colored and monochrome images were both visually inspected.

The existing stage-card gate excluded this outgoing-title interval from its
color checks. Its new `title_exit_color_integrity` check follows exact captured
title tile geometry across the scene change until a replacement map appears,
requires consecutive coverage, permits uniform fade/blank frames, and rejects
a nonuniform outgoing title that loses all chroma. It deliberately claims no
timing or general palette-fidelity proof. The check is wired into all four DX
replays of the existing full-suite `stage_card_stability` gate and retained in
its new `title_exit` receipt field.

Seven stage-card/dealias unit tests pass, including monochrome, missing-frame,
missing-baseline, and missing-replacement controls. Applying the new oracle to
all four old exact-r534 captures fails each one for frames 196-212. This is a
negative-control reanalysis, not a new playtest or a rewritten historical
receipt. The source points to the old-title scene-transition cleanup as a
candidate cause: the r366/r367 service rearms attribute cleanup as soon as the
scene changes, before the outgoing title disappears. A repair is not yet
implemented or verified. The yellow initial-load report remains separately
open; it must not be conflated with this confirmed monochrome-title interval.

### Operator-state reproduction and partial close repair (2026-09-09)

The preceding pending-session/START-route notes are superseded by actual live
reproduction. The owned headed session was saved into unused slot 9, copied
with its SRAM and screenshot into `tmp/r534-headed-menu-incident-current533/`,
then closed by its exact PID 2031378. A host process check confirmed no mGBA
process remained before automation resumed. No hardware deployment occurred.
The preserved `operator.ss9` SHA-256 is
`dd15cb653f5208a3c5597e861ff5942f1c9189a2b5302f72063cc094504621bd`.

The attempted blank-SRAM START/B route in current534 did **not** open a menu
(`first_window=none`); it cannot qualify this incident. The real operator
capture instead identifies scene `$02`, Stage 1, room `$01`. Its B-close
replay in `tmp/r534-operator-menu-close-current536/` reproduces 47 incorrect
visible background attributes throughout all 150 stationary frames 90–239.
All 61 movement-recovery frames 300–360 are clean. Menu ownership and hardware
Window are both released throughout the bad stationary interval. The actual
bad and recovered screenshots were visually inspected.

The independent room-01 oracle uses the canonical global LUT with only the
four already-reviewed contextual wall IDs `$24/$27/$30/$33` selecting BG6;
those fixed overrides are authenticated against the ROM's room-01 semantic
page. Applying the room-05 global table unchanged would falsely report these
wall tiles, so the discarded current535 diagnostic is not the reproduction.
The bad captured map is never used as a clean baseline.

`build_stage1_menu_close_trial_r535.py` produces a deliberately experimental
overlay from exact r534. It adds close-time invalidation of both physical-map
cache keys only for scene `$02`/stage `$02`, behind the existing SVBK1 gate;
all other scenes retain their original branch, including the separate `$0B`
repair. Its helper's actual instruction bytes are exercised for all 65,536
scene/stage pairs by a unit test. The isolated trial is
`tmp/menu-close-r535-trial-current537/candidate.gb`, SHA-256
`6fa78acd3dfd109fd420ab638693f9b62c4cbb016bfc9d9e5d9b41729003816a`.

The current538 replay passes all 150 stationary frames without movement,
but retains **four bad immediate-close frames 61–64** before the redraw is
published at frame 65. Thus the persistent defect is repaired in this focused
trial, but the close presentation is not yet fully repaired. This trial is
not a release candidate, does not repair the title/load flashes, and does not
replace the rejected r534 pin. Cross-build replay changed only the four
serialized ROM-CRC bytes: CPU, stack, mapper, WRAM and VRAM are byte-identical
to the preserved operator state. This is not a cold-boot qualification.

The full/live 87-gate inventories now require
`stage1_captured_menu_stationary` instead of the ineffective START-only route.
It runs `verify_stage1_captured_menu.py --operator-fixture --close-key b`,
authenticates the exact preserved fixture, records any CRC-only retargeting,
retains all 360 screenshots plus six keyframe states and their hashes, and
fails on any stationary mismatch. Movement recovery cannot excuse a failure.
Immediate-close bad frames are reported separately rather than silently
counted as clean. The title-exit check remains in the existing stage-card gate.
Missing operator fixture data blocks the gate; it does not skip this coverage.

### Rendered-pixel close gate and scoped passing trial (2026-09-09)

The immediate-close check is now mandatory too, not merely diagnostic. A
second trial repairing the six menu-owned attribute rows before closing
(`current540`, replay `current541`) eliminated every sampled attribute error,
but its frame 61 PNG still contained 568 wrong pixels in the upper-left
32×40 region. Frame-end VRAM was clean while that already-rendered frame was
not. That trial is therefore rejected by the new rendered-pixel check.

The pixel expectation is reconstructed from the exact operator state's tile
and art geometry, the independently contextualized room-01 LUT, and the ROM's
canonical Stage-1 palette. Neither the captured bad attributes nor its bad
screenshot supplies expected colors. The fixed camera must stay at SCX `$0C`,
SCY `$08`; the checked 32×40 incident region has no native sprite. Full visible
attribute coverage remains separate and mandatory. A synthetic one-red-pixel
control proves that clean frame-end memory cannot conceal a bad rendered
close frame. Read-only reanalysis rejects all 179 closed pre-movement frames
of r534 and the single lingering frame of current540.

The scoped trial now repairs the visible map's six menu-owned rows using
the current contextual C600 lookup, waits for the next VBlank before hiding
the menu, and invalidates both physical-map cache keys so subsequent map
publication cannot reuse the menu attributes. The direct visible-map repair
is restricted to room `$01` with LCD enabled; other rooms retain only the
cache invalidation. All polling/writes are on the close path, not the normal
frame loop. This remains an experiment pending broader timing/hazard/cold-boot
qualification, not a general repair claim for every room.

Reproducible scoped build:

```sh
PYTHONDONTWRITEBYTECODE=1 python scripts/diagnostics/build_stage1_menu_close_trial_r535.py \
  tmp/stage4-cache-key-r534/candidate.gb --repair-visible --wait-reveal \
  --output tmp/menu-close-r535-room01-trial-current546
```

Its SHA-256 is
`79ae6aeb6cc436d251508d5b2a110357c1c0b52759d8f6b0714178987547586c`.
The current547 replay passes with 178 checked closed-menu rendered frames,
zero bad pixels, zero immediate-close attribute errors, and zero errors over
all 150 stationary frames. The finished verifier was then run through the
actual `build_gates()` suite command on both ROMs, serially:

- `tmp/r534-menu-negative-current548/artifacts/stage1-captured-menu-stationary/receipt.json`:
  FAIL, 150 stationary bad frames, 179 rendered bad frames, exact r534 tested-ROM
  hash retained.
- `tmp/r535-menu-positive-current549/artifacts/stage1-captured-menu-stationary/receipt.json`:
  PASS, zero stationary or rendered errors, exact scoped-trial tested-ROM hash
  retained. CPU/stack/mapper/game/video state differs from the operator capture
  only in serialized ROM-CRC metadata.

The finished receipt also binds the verifier and guard hashes, exact isolated
tested-ROM path/hash, and all screenshot/state hashes. The live inventory
contract passes with 87 gates. Forty-five focused unit tests passed across the
captured-menu, actual helper branches, natural-menu raster, full/live roster,
stage-card/title, dealias, and headed-launch contracts.

The title-only diagnostic `tmp/title-exit-defer-trial-current542/` was rejected:
skipping the old-title rearm leaf did not remove the 17 monochrome frames in
any of current543's four DX routes. That leaf is not a sufficient root-cause
repair; deferred publication/attribute cleanup also requires investigation.
The yellow initial-load report remains open pending clarification of which
presentation the operator means. No title/load fix or full-suite qualification
is claimed. The readiness hook and r534 pin remain unchanged and failed.

### Title writer trace, late clear, and combined trial (2026-09-09)

Continuing after the readiness Stop rejection found a second, earlier title
attribute clear. The optional `PENTA_TITLE_TRACE=1` stage-card observer uses
nonempty half-open watchpoint ranges. The old D880 watchpoint and the first
diagnostic used equal start/end addresses, observing nothing; local mGBA
source confirms the end is exclusive. Corrected current551 observes:

- frame 194: bank13 PC `$53CF` disables LCD; `$53D8` clears both attribute
  maps before the native outgoing-title fade finishes;
- frame 195: bank13 `$6F01` restores LCD, exposing the neutralized old title;
- frame 196: `$6EA3` rearms DF08 and the generic cleaner clears again.

The first writer belongs to `build_levelsel_rom_transition()`, not the old
Nightfall cleanup leaf. Skipping the leaf alone could not repair it.

The current552 control preserves the outgoing title by skipping both early
clears while retaining the **new-title entry** rearm. Its current553 replay
removes the monochrome flash, but leaks Nightfall attributes into all 45
selector frames and 163 splash frames. It is rejected, not promoted.

The current554 trial moves the selector clear to fixed `$3B42`, after the
native `$408E` routine has retired the outgoing title tiles. An exact-return
bank31 dispatcher recognizes only `$3B47`, preserves other dispatch stack
layouts, performs the original save-present clear with the LCD safely off,
and restores the native DCFD branch condition/bank-1 continuation. The source
builder preserves the existing title-entry rearm. Current555 passes the
outgoing-title check and has zero nonneutral selector/splash attribute frames.
The outgoing colored title, intervening blank/loading frames, and clean
selector were visually inspected.

`build_menu_title_trial_r535.py` composes the disjoint menu and title overlays
from exact r534, rejecting overlapping byte ownership. Combined experimental
ROM: `tmp/menu-title-r535-trial-current556/candidate.gb`, SHA-256
`4f19c05227258db33e0432627443dc9a43207f055ea8c51add6615aa0df4a104`.
Its inherited dungeon map-flip/palette handoff remains unchanged. Current557
passed every runtime stage-card check but correctly failed unrecognized
static identity. Only after those runtime results and exact-composition tests
was this exact hash added to the handoff component's recognition list; this
does not recognize arbitrary mutations or confer release readiness.

Fresh combined evidence:

- `tmp/menu-title-r535-stage-card-current559/receipt.json`: complete stage-card
  PASS, including all four DX replays, stock timing control, preserved title
  colors, neutral selector/splash attributes, and atomic gameplay handoff.
- `tmp/menu-title-r535-menu-replay-current558/receipt.json`: captured-menu
  PASS, zero immediate or stationary attribute errors and zero wrong pixels
  across all 178 closed pre-movement incident-region frames.

Five new construction/recognition tests pass, including all 65,536 possible
dispatcher return addresses and mutation rejection at checksum, fixed hook,
bank31 dispatcher, and LUT bytes. Four inherited-profile tests also pass.
These are focused experimental passes, not the full release matrix or a new
headed human approval. The old r534 pin stays `FAILED_HEADED_TEST`. The yellow
freeze report remains unresolved: the operator was asked whether it concerns
the STAGE card or the already-visible dungeon, and no answer is recorded yet.

The actual selected release matrix then passed all three requested gates in
`tmp/menu-title-r535-selected-current560/manifest.json`: captured menu (2.1s),
stage-card/title stability (19.3s), and natural game-start routes including
cold/warm reset and blank/saved SRAM (113.8s). Its status is `selected-pass`,
not a full-matrix pass. It records zero failures, intact source/tested ROMs,
intact source inputs, source fingerprint
`3f19b2d8177bd34c4443ab1d077be9beaa9c705a3679f576517c101cda44d783`
over 839 inputs, and the correct patched mGBA library hash
`20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`.
The combined candidate remains experimental pending the remaining gates,
clarification/reproduction of the yellow freeze, and exact headed retesting.

### Broader containment controls and latest scoped experiment (2026-09-09)

Current561 rejected the earlier `4f19c052...` combined trial on title/attract
visuals: removing the old-title cleanup for every exit leaked attributes and
prevented the complete title/demo inventory. GAME START after attract passed;
the opening integrity gate initially blocked before launch because the new
ROM had no exact publisher-profile binding. These results supersede any
impression that the earlier three-gate pass was broad qualification.

The intermediate scene-zero-only fix (`951e770e...`, current562/current563)
restored the demo and passed opening integrity after an exact publisher
binding, but still leaked attributes into the banners and missed the unchanged
stock timing limit by one frame. The native title animation itself briefly
uses scene zero, so that scene is not sufficient evidence of GAME START.

The latest experiment uses the selector entry's existing `DF4C=$A0` marker
to defer only actual GAME START cleanup. All idle/attract/story exits retain
the original old-title rearm, and new-title entry rearming remains unchanged.
An exact `$76DC` caller capability routes the conditional rearm through the
bank31 dispatcher, alongside the exact `$3B47` late-clear capability; other
callers retain their original stack and dispatch path. The late clear uses
eight bounded 256-byte page loops, reducing its LCD-off duration without
changing any test threshold. The unused live bank13 pad is left unchanged.

Latest experimental ROM:
`tmp/menu-title-r535-entry-scoped-trial-current564/candidate.gb`, SHA-256
`2db9f03cd772e75367a219a73610007c2446655cfb7a27873ddaae3a62c816cd`.
It is reproducibly built by `build_menu_title_trial_r535.py` from exact r534.
The publisher/semantic profile binds this exact ROM hash plus the unchanged
publication instructions and semantic-helper bytes. Mutation controls reject
unknown ROMs; no generic matching fallback was introduced.

`tmp/menu-title-r535-entry-scoped-gates-current565/manifest.json` passes all
five selected gates:

- title visual receipts, including cold/returned banners and demo miniboss;
- captured stationary menu regression, including immediate rendered pixels;
- full title/stage-card stability, including all four DX routes;
- GAME START after attract;
- opening-to-Stage-1 integrity at matched room/camera.

The stock timing lag is 7 frames against the unchanged maximum of 10. The
manifest is `selected-pass`, with zero failures, intact source/tested ROMs and
source inputs, and fingerprint
`5aba0d88e6afb8b9a7198547951a7fe3000ea58cea9d79f92f115616b05e7129`
over 839 inputs. Seven construction/profile tests pass, including exhaustive
caller dispatch and old-scene/selector-marker branches. Four inherited-profile
tests and the 87-gate live inventory contract also pass.

This supersedes the earlier experimental ROMs but does not replace the failed
r534 readiness pin. Full release qualification, exact headed human retesting,
and clarification/reproduction of the separately reported yellow loading
freeze remain outstanding. No Pocket or MiSTer deployment has occurred.

### Speed qualification rejects the experimental replacement (2026-09-09)

The exact `2db9f03c...` five-visual-gate trial is **not** ready. The full
existing main-speed command was run unchanged in
`tmp/menu-title-r535-main-speed-current566/manifest.json`: 2,800 frames,
stages 1/3/4/5/6, the named 95% floors for stages 1/3/4/5, and the strict 1%
upper bound (stage 6 also keeps its strict 99% lower bound). Stage 1 measured
676 loops versus original 667, ratio 1.0135, and failed the upper bound.
Stages 3/4/5/6 passed at approximately 0.997/0.999/0.984/0.993, with matching
route coverage. No threshold was relaxed.

A further experiment moves the title-specific dispatcher from the common
bank31 entry to the pre-existing unknown-caller fallback at `$6D5A`.
Known room, dirty-map and menu dispatch paths retain their original title-
overlay bytes. This candidate is
`tmp/menu-title-r535-cold-dispatch-trial-current567/candidate.gb`, SHA-256
`69ff940ace8e73e82aa5331dde39282d191814c4ca1b814afb19a13fbb6dc197`.
Its focused Stage-1 speed replay in
`tmp/menu-title-r535-cold-stage1-speed-current568/manifest.json` still fails:
675 loops versus 667, ratio 1.0120, with identical route coverage. It has not
replaced the earlier five-gate visual receipt and is not promoted.

Eight current construction/profile tests pass, including exact known-dispatch
byte preservation and all 65,536 fallback caller values. These static passes
do not override the measured cadence failure. The requested regression is
implemented and reproducibly rejects the operator's r534 incident, but a
release-safe replacement still requires resolving cadence, the reported
yellow loading behavior, the remaining release gates, and headed retesting.
The readiness pin continues to record the failed r534 human test honestly.

### Read-only cadence controls isolate the title overlay (2026-09-09)

Three fresh serial guarded Stage-1 replays enable the existing read-only
`STAGE_SPEED_CAMERA_TRACE=1` observer, without changing ROM bytes, input,
the 120-frame settling period, CPU measurement anchor, 2,800-frame window,
or the strict 1% upper bound:

- `tmp/menu-title-r535-cadence-trace-current569/manifest.json`: combined
  `69ff940a...` trial reproduces the failure, 675/667 loops (1.0120).
- `tmp/r534-cadence-control-current570/manifest.json`: unchanged pinned
  r534 passes, 666/667 loops (0.9985).
- `tmp/menu-only-r535-cadence-control-current571/manifest.json`: the
  room-01 menu-only trial `79ae6aeb...` also passes, 666/667 loops (0.9985).

All three retain exact route coverage (horizontal travel 56, vertical 0).
The combined trial's additional loops occur across the gameplay window,
not solely at the initial boundary: its seven successive 400-frame bins
contain 97/93/95/99/97/97/97 loops, versus stock
95/93/95/95/96/97/96. This rules out simply counting the title transition
inside the timed window; it does not by itself distinguish ongoing title
hook costs from persistent state/timing effects established on entry.

These controls isolate the observed cadence regression to the added title
overlay (or its interaction with the menu overlay), rather than the menu
fix alone. They are diagnostic evidence, not full release qualification.
No candidate, readiness pin, test threshold, or failed headed-test record
was changed. The separate yellow-loading report still needs clarification.

### Local title rearm is another rejected control (2026-09-09)

`build_title_local_rearm_trial_r535.py` makes a bounded experimental overlay
on exact `69ff940a...`: the old-scene test again runs locally in bank 13 and
conditionally calls a nine-byte selector-marker guard in the retired early
clear body at `$53D1`. Both paths through the pinned replacement `$53C2`
entry already jump to `$6F01`; the live generic-cleaner pad stays untouched.
New-title rearming, late cleanup, and menu repair stay unchanged. Three unit
tests pass, including execution of the actual wrapper/helper bytes for all
old-scene/marker combinations and four new-scene boundary values.

The output `tmp/menu-title-r535-local-rearm-trial-current572/candidate.gb`
has SHA-256
`d1d8e82631e81be0d2b3fbe583e5ffd2bc58278926dd7ea3bdd6a34375a67590`.
It is **rejected**: the unchanged Stage-1 speed replay in
`tmp/menu-title-r535-local-rearm-speed-current573/manifest.json` measures
685/667 loops, ratio approximately 1.0270, with exact route coverage. Removing
the unconditional title-rearm bank switch does not resolve the failure.
This is not evidence for relaxing the speed bound, nor proof of a particular
timing/state cause. No visual qualification was attempted for this failing
control, no component-recognition whitelist was extended for it, and it
does not replace any candidate or headed-test provenance.

### Tile retirement passes focused visuals and main speed (2026-09-09)

The newer experiment avoids deferred cleanup and title-rearm dispatch entirely.
`build_title_tile_retire_trial_r535.py` composes the room-01 menu repair with
one changed immediate in the original bank13 selector clear: `$53D0` changes
from `01` to `00`, selecting the BG tile plane instead of the attribute plane.
The same original instructions retire the outgoing title geometry before its
attributes are cleared by the untouched scene cleanup. Loop length, LCD writes,
selector marker, register results, and continuation are unchanged. This is
an early plain-background transition through the original fade, not the
earlier experiment that held the colored title until late cleanup.

Experimental output: `tmp/menu-title-r535-tile-retire-trial-current574/candidate.gb`.
SHA-256: `681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3`.
Its initial stage-card run (`current575`) passed every runtime check but failed
the then-unknown whole-ROM component identity. After adding this exact hash
to the unchanged handoff/publisher component contracts, mutation controls
continue to reject unknown bytes. No generic profile fallback was added.

`tmp/menu-title-r535-tile-retire-gates-current577/manifest.json` is
`selected-pass` for all five selected gates: title visual receipts, captured
stationary menu, stage-card stability, GAME START after attract, and opening
to Stage 1. Source/tested ROM hashes and source inputs remained intact;
the captured source fingerprint is
`f3c92e6f2ddff78f9e49b33c257d2e30e2328f27fbb42325253a3c0549e55474`
over 841 inputs. All four title-exit replays show replacement geometry at
frame 195 with no monochrome outgoing-title frames. Inspected images show
the blue plain background followed by the native fade's white background.
The menu receipt passes immediate closed-frame pixels and every stationary
attribute check without movement.

`tmp/menu-title-r535-tile-retire-speed-current576/manifest.json` passes
Stage 1 at 666/667 loops. Its DX per-loop trace is byte-identical to unchanged
r534's `current570` trace, SHA-256
`7dad13ca6c3f71c2de845049035b475e3b3f177ede7846c6846e89d27b021b0e`.
The complete existing main-speed command also passes in
`tmp/menu-title-r535-tile-retire-main-speed-current578/manifest.json`:

- Stage 1: 666/667, ratio 0.9985;
- Stage 3: 699/699, ratio 1.0000;
- Stage 4: 764/764, ratio 1.0000;
- Stage 5: 793/790, ratio 1.0038;
- Stage 6: 756/756, ratio 1.0000.

Every stage meets the strict 1% target with exact route coverage; none needs
the existing named slowdown exception. Fifty focused unit tests pass across
the captured menu, menu repair, previous combined experiment, local-rearm
control, tile-retirement construction/component binding, stage-card, roster,
and natural-menu raster modules. The 87-gate live roster contract also passes.

These are focused experimental receipts, not full release qualification.
The original-only replacement build, full 87-gate matrix, other required
speed receipts, separate yellow-loading reproduction, and fresh exact-ROM
headed human test remain outstanding. No readiness pin, failed r534 human
test record, or deployment has changed. Earlier failed title experiments
remain rejected and must not be confused with this newer output.

### Original-source reconstruction and interrupted full attempts (2026-09-10)

The exact `681b4668...` output was reconstructed from the original cartridge:
`tmp/r535-original-base-current584/build-receipt.json` records two identical
syscall-audited 105-step r534 source builds, without retained candidate or
historical evidence inputs. Applying the checked tile-retirement/menu builder
twice to that newly generated base produced identical outputs in
`tmp/r535-original-replacement-a-current585/` and
`tmp/r535-original-replacement-b-current586/`, matching the experimental ROM.
These source receipts describe their captured tool snapshot; subsequent probe
changes require fresh source qualification before any READY claim.

The first full attempt, `tmp/menu-title-r535-tile-retire-full-current579/`,
found two verifier identity integration gaps. The unchanged bank-20 menu LUT
was not recognized under the new ROM hash; every captured menu page itself
reported zero palette mismatches. The hazard probe's Python recognizer knew
the new publisher name but its Lua recognizer did not, so initialization
stopped at the `PENTA_PUBLICATION_MATCHES == 1` assertion. The full verifier
PID 4018352 was interrupted (exit 130); the host process check was clear.
Its partial manifest is not passing evidence.

Closed-set inherited profile bindings now include only the exact
`681b4668...` output where the underlying LUT, publisher, observer, arena-data,
boss-entry and hazard-control bytes remain unchanged. No generic fallback
was added. `test_title_tile_retire_trial_r535.py` now has eight passing tests,
including execution of the real Lua publisher-initialization prefix with a
read-only ROM stub, rejection of an unknown name and mutated publisher,
current boot-derived hazard-route selection, inherited tables/observer ABIs,
and exact hazard-negative-control rejection of unrelated edits. The four
older r527 inherited-profile tests also pass.

`tmp/r535-inherited-profile-gates-current583/manifest.json` passes all six
selected gates: menu icons, current hazard-state capture, current hazard-menu
replay, hazard mutations, exact-destination mutation, and low-health flicker.
The hazard-menu replay completed in 68.4 seconds after the recognition fix.

A fresh full attempt, `tmp/r535-original-replacement-full-current587/`,
passed its first 21 gates, including the six-stage main-speed matrix. It was
then interrupted deliberately after the rendered loading defect below was
confirmed. Exact verifier PID 103286 exited 130. The first post-interruption
check found its owned emulator PID 185453 still under orphaned xvfb launcher
PID 185428. Only that exact launcher was terminated; the subsequent host
check reported no mGBA processes. This attempt also remains partial and must
not be represented as a full matrix pass.

### Rendered stage-card loading regression now rejects the trial (2026-09-10)

Raw screenshots reveal an additional real loading defect, present in both
the pinned r534 and `681b4668...`: the STAGE-01 tilemap stays unchanged while
its glyph patterns are replaced by incoming dungeon graphics. The older
handoff checks compare tile IDs, attributes and palettes, so they incorrectly
describe the changed raster as the same complete card. For example, the
historical r534 `current530` frame 0495 visibly contains the same garbled
colored graphics as the new trial. This may explain the user's exposed-load
report, but the user has not yet confirmed whether that was the stage card
or an already-visible dungeon.

`stage_card_raster_integrity()` in `verify_stage_card_stability.py` is now a
required check on all four DX routes. Its reference is the first three
identical nonuniform complete-card rasters in the early card interval, not
the late/corrupted tail. It checks every consecutive raster until dungeon
replacement. Global palette remaps and uniform blank fades are permitted;
splitting a reference color into different colors at different pixel
positions is rejected, catching glyph/background changes even with identical
tile IDs. It does not admit a stable corrupted tail as a new reference.
Six new synthetic controls cover intact/blank retirement, palette-only
changes, a single damaged glyph pixel, partial background retirement, late
baseline poisoning, and missing frames/baselines. All 12 stage-card tests pass.

`tmp/r535-stage-card-raster-negative-current588/receipt.json` now correctly
fails all four DX routes. Each uses reference frame 341, checks 167 frames,
and rejects frames 488 through 507 (20 frames) before dungeon frame 508.
Every older check still passes, demonstrating the specific prior blind spot.
Consequently `681b4668...` is **not release-ready**, despite its earlier
menu/title/speed and inherited-profile passes.

The bounded read-only trace in
`tmp/r535-stage-load-writer-trace-current589/run-1/stage-load-writes.tsv`
records the relevant order:

- Frame 476: native BGP `40` is overwritten with `E4` at fixed PC `$10E1`.
- Frame 480: native BGP `00` is likewise overwritten with `E4` at `$10E1`.
- Frame 487: bank 7, PC `$0D47`, replaces background pattern byte `$9000`.
- Frame 493: the same writer replaces the visible letter pattern at `$96E0`.
- Frame 502: BGP finally becomes `00` through bank 18 PC `$0A11`.
- Frame 507: bank 13 publishes the completed dungeon map at `$7459/$7464`.

The source's `build_native_dmg_fade_fixed_service()` normalizes active-play
fades using FFC1/FFE4, without excluding the still-active STAGE-card scene.
This is a concrete fade-ownership lead, not a completed loading fix. Do not
silence the new regression by skipping these frames or accepting their
garbled raster as a baseline. Any retirement change must preserve an intact
card or a legitimate blank fade through graphics reuse, then atomically
reveal the complete dungeon with its correct palette. No replacement pin,
successful human playtest record, or deployment has been written.

### Cold stage-card retirement trial (2026-09-10)

The additional read-only stack trace in `current590` identifies native
bank-1 return `$4146` after the complete STAGE-card wait/fade. The next
five bytes set `HL=$DC85, B=$28` before native loader work. New experimental
builder `scripts/diagnostics/build_stage_card_blank_trial_r535.py` replaces
only this setup with a bank-31 call, extends only the dispatch's unknown-
caller fallback for exact return `$414B`, and replays the original setup.
The known menu/map dispatch paths are unchanged. Native four-step fades,
the 100-tick card wait, and the global `$10D5` normalizer are untouched.

The helper requires scene `$18` and selected Stage 1 (`FFBA=0`). It must
not require `FFB7=2`: the following native `$4F7E` call initializes that
mode, so the initial `current591` experiment did no retirement and remained
a negative control. With the correct cold-entry guard, `current593` used a
white blank and passed the independent glyph oracle on all four routes.
The final trial uses black instead to avoid a bright loading flash:

- `tmp/r535-stage-card-black-trial-current595/candidate.gb`
- SHA-256 `fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576`
- MD5 `fde78c0cc42689edc5dc1ed5a95ded9f`

The helper preserves DE/BCPS, acquires a fresh VBlank with interrupts
disabled, sets all eight BG0 bytes to zero, then restores BCPS and the
native enabled-interrupt calling convention. The existing atomic VBlank
map publisher restores the exact Stage-1 BG0 before revealing the completed
dungeon. Captures show the reviewed card through frame 481, actual uniform
black from 482 through 508, and the complete correctly colored dungeon at
509. This adds one loading frame, not a change to the native card wait.

`verify_stage_card_stability.py` now distinguishes visible-card palette
ownership from terminal retirement: the visible card must retain its
reviewed colored palette, then may transition once to a verified all-black
160x144 raster until dungeon replacement. Palette metadata alone cannot
claim a blank; even one visible pixel fails. A returning card, third palette,
monochrome lettering, missing frame/replacement, or black from the start
fails. The independent glyph oracle still checks every visible card frame.
Reevaluating `current588` with both current predicates still rejects its 20
garbled frames; `current597` passes the entire updated four-route gate.
No corrupt baseline or sampled-frame exception was introduced.

The exact `fe14b0e3...` component identity was added to the unchanged atomic
handoff and physical-publisher recognition sets, retaining their byte
checks. The initial five-gate `current598` attempt passed title visuals,
captured-menu stationary return, stage-card stability and after-attract
GAME START, but its opening route stopped at the then-missing publisher
identity. This partial manifest remains failed, not relabeled.

Original-source construction `current600` was denied sandbox ptrace and
produced no successful build receipt. The host-audited retry `current601`
double-built r534 from the original cartridge with all 105 construction
steps. Applying the independent menu/title and loading builders twice gives
`tmp/r535-loading-source-final-a-current603/candidate.gb` and
`tmp/r535-loading-source-final-b-current605/candidate.gb`, both exactly
`fe14b0e3...`; no retained candidate supplied the base for these builds.

Strict six-stage speed receipt `current599` reports Stage 1 667/667,
Stage 2 759/754, Stage 3 699/699, Stage 4 767/764, Stage 5 773/790,
and Stage 6 759/756. Stage 5 is 2.15% below stock, so the no-exceptions
one-percent trial is **failed**. This is within the previously configured
Stage-5 0.95 floor, but is not an all-stages one-percent target pass.
Do not hide that target miss or overwrite the strict negative receipt.

The pin and `FAILED_HEADED_TEST` operator record still name r534. Permission
to change the pin for an experimental mGBA preview has been requested;
there is no response yet. No full 87-gate pass, replacement human approval,
READY claim, or hardware deployment is asserted for this loading trial.

`tmp/r535-source-menu-title-loading-gates-current606/manifest.json` is a
fresh **selected-pass** on the original-source `current603` ROM: title visual
receipts, captured-menu stationary return, stage-card stability,
GAME START after attract, and opening-to-Stage-1 integrity all pass. Its
source fingerprint and the `current601` original-build fingerprint were
rechecked against current source and match. This is five selected gates,
not a full matrix pass. The stage-card group has 28 passing unit tests;
the r535 trial group has 29 (overlapping the stage-card group), captured-menu
has seven, and the full/live manifest roster tests have five.

The full-frame natural-menu oracle's 14 synthetic/roster tests also pass
(132.7 seconds; no emulator launch). `current607` is a separate passing
main-speed manifest using the **unchanged** existing policy: targets
0/2/3/4/5, 2,800 frames, tolerance 0.01, accepted Stage 1/3/4/5 floors 0.95,
compiler bank 16 `$6C80..$7232`. It reproduces `current599`'s exact counts:
Stage 5 is explicitly `target=MISS, PASS` under its preexisting floor.
The no-exceptions `current599` failure is retained. No tolerance or policy
configuration was relaxed to replace that negative receipt.

Separate configured Stage-2 receipt `current608` passes at 759/754
(1.00663), including the strict one-percent target. All emulator-backed
runs in this follow-up completed normally and were serialized. The final
read-only process check found no running mGBA process. The experimental
preview pin decision remains unanswered; the rejected r534 pin, Stop hook,
and failed human-play record have not been changed.

### Full-matrix integration follow-up (2026-09-10)

While the preview-pin choice remained unanswered, automated qualification
continued without changing the pin. The remaining unchanged-component
recognizers now accept exact `fe14b0e3...` alongside its `681b4668...` parent:
arena data, boss latches, low-health observer ABI, menu/hazard tables, current
hazard fixture selection and exact negative mutations. The loading-builder
unit group now has 11 passing tests, including actual standalone Lua
initialization and rejection of unknown identities/opcode mutations.
The combined r535 unit group has 33 passing tests.

`current609` refreshed the original-source double build. `current611` and
`current613` reconstructed identical final ROMs. Full attempt `current614`
passed its first 19 gates, then was deliberately stopped to synchronize two
consumers still requiring the superseded never-blank Stage-card contract.
Exact owned verifier PID 889753 exited 130; the mandatory host census
reported no mGBA processes. This attempt remains partial, not a full pass.

`verify_stage1_reported_regressions_ready.py` and
`verify_pocket_visual_receipts.py` now require the visible glyph-integrity,
outgoing-title, and actual terminal-black-raster checks. The full matrix
continues to require the separate captured-menu stationary gate. Unit
controls check that either a missing or false new assertion fails both
receipt consumers; no legacy receipt is accepted merely because its old
palette/attribute checks pass. Nineteen stage-card tests, seven aggregate
tests, the aggregate mutation self-test, and 16 readiness-wiring tests pass.

The readiness checker SHA was legitimately updated in
`.codex/stage1-ready-gate.json` from `e87c4d59...` to
`2f1c88bb1846b9ecd0e5da1dd9d790b993d2f96d3eb27fc94d930dd06df7a694`
to bind this stronger checker. The hook definition and script were not
changed. The candidate pin and `FAILED_HEADED_TEST` human record remain
exact r534; this tool-identity update does not approve a ROM or bypass the
Stop gate.

After refreshing original-source construction again in `current615`,
`tmp/r535-final-contract-rom-a-current617/candidate.gb` and
`tmp/r535-final-contract-rom-b-current619/candidate.gb` both reproduce
`fe14b0e3...`. A fresh complete 87-gate attempt is running under
`tmp/r535-full-final-contract-current620/`; its final status must be read
from its manifest, not inferred from this start record.

### Completed full run and bounded final-boss controls (2026-09-10)

`current620` completed normally from 04:44:53 to 05:10:57 UTC: **77 passed,
3 failed, 7 blocked**. Failed gates were expansion ownership, all-nine boss
geometry, and boss publication cadence. Four Ted-dependent gates and three
boss-gallery gates were blocked by those failures. All other executed gates
passed, including the reported-issue visual tests, six-stage speed policy,
movement stress, hazard menus and mutations, pickup forms/art, room/wall
integrity, low health, later-stage soaks, death/game-over, title reel,
opening/ending, scroll, sound, palettes and IPS roundtrip. The manifest is
failed and has not been relabeled or resumed.

The ownership failure was an outdated expected bank-31 image. The audit now
independently reconstructs both r535 menu-close and shared loading-retirement
owners through their authenticated builders, including every padding byte
in banks 21 through 31. It never copies expectations from the tested ROM or
accepts an arbitrary candidate bank hash. Two new unit tests preserve r534
recognition and reject helper, other-bank, and padding mutations.
`tmp/r535-loading-ownership-audit-current630/report.json` passes the complete
static Ted integration contract for exact `fe14b0e3...`, with ownership mode
`reconstructed-r535-loading-retirement`. This separate pass does not change
the failed full manifest or qualify its blocked dependent gates.

The final-boss geometry failure is one tile-LUT mismatch at frame 334:
map `$9800`, row 9, column 15, tile `$1B`, palette 0 versus expected 1,
SCX `$15`, SCY `$05`. The next frame restores palette 1 on the same physical
map; it therefore does not meet the existing hidden-staging/map-flip
exception, which has not been widened. Publication cadence is 1.2035 against
the unchanged 1.20 phase ceiling at warmup 60 / observation 600 frames.
These failures remain blocking. No rendered-raster diagnosis of the single
geometry sample has yet established whether it was visible during scanout.

A diagnostic private-entry alternative,
`scripts/diagnostics/build_stage_card_private_trial_r535.py`, places the same
69-byte black-retirement body at bank 20 `$6C80..$6CC4`, with the neighboring
live `$6CDF` contextual trampoline protected. Only the native loader setup
and erased private cave change; bank 31 remains byte-identical to the
menu/title parent. Its source requires exact `681b4668...` and four unit
tests pass. The first build attempt correctly rejected an incorrectly named
neighbor address; after correcting the guard to the source-owned `$6CDF`,
the diagnostic ROM in `current621` is
`f2339ff5161ab6e80a948ab37cb4205b8cd53f372cb50c4436219457d2e825e3`.
It is not a qualified replacement or a proven fix for the boss failures.

`current622` retargets the failed final-boss state to the private trial by
changing only serialized CRC offsets 4/5/6/7. CPU, stack, mapper, WRAM and
VRAM are unchanged. Source state SHA is
`7b1ce77b84f11e3aa1dd051cb50c2fd256a5d4a63ea655ac34ab4b48e24baf5e`;
private retarget SHA is
`51972881993dca2d0dcea1621bf3030cb937d5586cb8324700d84ce689e7c0e0`.
The initial retarget attempt lacked its output directory and launched no
emulator; the corrected CRC-only replay is retained separately.

The original shared trial (`current620`), private trial (`current623`), and
exact r534 with the same CRC-only-retargeted machine state (`current625`)
all produce the **identical** geometry trace SHA
`a10de878a8f94f635d2238601d8729c93149e566cb63b0fd0bde6ab7cbc1dfa8`.
Thus the replay mismatch is not caused by a difference in the new helper's
boss execution; it is also reproducible in r534 at this machine-state phase.
The older r534 `current530` generated state passed, so this does not establish
that all r534 entry phases fail or that the new entry route is qualified.

Private-trial state generation `current626` initially took an incompatible
legacy-fixture fallback because its exact synchronous-entry identity was
missing. Adding only `f2339ff5...` to the generator's closed inherited set,
while retaining the `$E0 $72` latch-byte guard, enables the current cold
route. `current627` generates a fresh candidate-bound final-boss state, but
`current628` still has the same one geometry mismatch and `current629`
still fails cadence at 1.2035. Relocating the helper alone is not a solution.
No geometry exception, timing bound, input window, or failed receipt has
been relaxed or overwritten.

Source changes since the full run mean its source fingerprint and older
original-build snapshots are historical, not current READY evidence. No
new pin or successful human-play record has been written. The reported
menu/title/loading fixes retain their targeted evidence, but hardware
readiness remains blocked by final-boss qualification and outstanding human
playtest confirmation. The last host census found no emulator running.

### r535 headed review and pending final-boss diagnosis (2026-09-10)

After explicit operator approval, the candidate pin was changed to
`tmp/r535-final-contract-rom-a-current617/candidate.gb`, SHA-256
`fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576`.
The guarded headed launch is recorded in
`tmp/headed-launch-receipts/1789034347697780505-1571653-fe14b0e3c392.json`.
The operator reported that the red/green bleed appeared fixed (with "I
think") and that the title "stays same color". These are partial human
observations, not a loading, final-boss, or full-release pass. The old failed
headed provenance and remaining stale evidence have not been relabeled as
successful; the Stop hook remains enabled and blocks readiness.

README status was updated locally. The requested merge, tag, and push have
not been performed: the full-suite receipt is stale and final-boss geometry
and publication cadence remain unresolved. A read-only host census still
finds the operator's exact candidate running as PID 1571648; the single-flight
check returns 75. No second emulator was launched and no playtest process
was terminated while permission to close it was pending.

Offline inspection ties the failed physical cell `$992F` to the existing
bank-20 `$6200` Penta seam helper. That helper reads the tile and writes its
LUT attribute without an explicit VRAM-access wait. A timing-related access
failure is a hypothesis, not an established cause. The retained full-run
trace still has SHA-256
`a10de878a8f94f635d2238601d8729c93149e566cb63b0fd0bde6ab7cbc1dfa8`.

The geometry probe now has optional, default-disabled capture bounds for
seam-write timing, screenshots, and savestates around the failing frame.
The instrumented script parses with both installed Lua 5.3 and 5.4 libraries
without execution. Runtime behavior, trace equivalence, and raster evidence
still require a guarded replay once the emulator slot is free. No ROM fix,
geometry exception, cadence ceiling, or successful test receipt is claimed
from this instrumentation or syntax check.

### r536 final-boss VRAM repair and targeted results

The command approval gate subsequently approved graceful termination of the
exact owned headed PID 1571648 after checking its full command line. A fresh
host census confirmed no mGBA process before the first guarded diagnostic.
The ROM, saves, and prior receipts were not deleted or replaced.

`current631..current635` retain successive diagnostic replays. The original
geometry trace remains byte-identical to `current620`. Early timing files
were empty because the instrumentation used an unsupported `getRegister`
method; those files are not evidence of an absence of writes. The corrected
probe uses the emulator's `readRegister` API and masks 8-bit registers to
their documented width. Diagnostics are optional and disabled by default.

The decisive `current635` trace identifies the per-frame **bank-13** seam
repair, not the bank-20 post-publication helper initially suspected:

- At frame 333, PC `$5737`, STAT is `$C3` (pixel transfer), and the read from
  `$992F` returns `$FF` rather than tile `$1B`.
- PC `$573C` consequently reads `C6FF=0`. By the attribute write at `$5744`,
  STAT is `$C0` (HBlank), so palette 0 really overwrites the previous 1.
- Frame 334's sample records the mismatch; the next per-frame repair reads
  the tile in VBlank and restores palette 1. No hidden-map exception applies.

`scripts/diagnostics/build_penta_seam_vram_trial_r536.py` requires exact
`fe14b0e3...` and changes only bank 13 `$5734..$5744`, an erased 34-byte cave
at bank 20 `$6250`, and the global checksum. The original scene-14 predicate
and bank-13 `$5745` VBK-reset/lava-dispatch tail remain untouched. Two stacked
mapper return addresses enter the new bank-20 helper and return through that
existing tail without fetching a return instruction from an unmapped bank.
Independent STAT mode waits immediately precede the VRAM tile read and
attribute write; the active C600 LUT still determines the palette. C, DE,
and interrupt state are not changed by the new helper.

The diagnostic candidate in `tmp/r536-penta-seam-vram-current636/candidate.gb`
has SHA-256
`b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350`
and MD5 `d178b431bdbca10d6bd739e91e0535f6`. It is not a human-reviewed or
release-qualified replacement. The Stage-1 pin and failed historical headed
record have not been relabeled as a passing r536 test.

Targeted evidence:

- `current637`: the failed Penta state was retargeted by changing only
  serialized CRC offsets 4, 5, 6, and 7; all machine/game memory is unchanged.
- `current638`: the original 360-frame Penta geometry gate passes with zero
  contract or raw LUT mismatches.
- `current639`: the unchanged 60-frame warmup / 600-frame cadence window
  passes at DX/OG 1.1632 against the unchanged 1.20 phase ceiling. The tighter
  speed target is still **MISS**, not timing parity.
- `current640/641`: CRC-only retargeted states for all nine bosses pass the
  existing strict geometry contracts, without altering their exceptions.
- `current643`: a supplemental 3,600-frame Penta replay has zero mismatches.
  Its large trace is under `/mnt/data/tmp/penta-r536-seam-long.jXIOsk/`.
  The new read/write instruction boundaries each have 3,607 observations and
  zero mode-3 observations. Mode 2 observations are not VRAM violations:
  mode 2 locks OAM, while mode 3 locks VRAM.

Exact-hash observer/data profiles admit only this specific candidate while
retaining their opcode checks. Bank-20 ownership independently replays the
authenticated r534/r535/r536 builders, including all surrounding padding;
the integration verifier also checks the new visible-seam entry and helper.
The initial owner test caught an incomplete reconstruction that omitted
r535 menu code; reconstruction was corrected rather than exempting bytes.
All 48 r535/r536 unit tests pass, including candidate mutation rejection,
mapper ABI, both waits, and actual Lua publisher-profile negative controls.

The full regression matrix is running under
`tmp/r536-full-regression-current644/`; no full-suite result is claimed yet.
An independent original-source parent double-build is also running under
`tmp/r536-original-parent-current645/`. Merge, tag, and push remain pending.

That parent double-build subsequently completed: both original-source runs
reproduce exact r534 through all 105 construction steps, without historical
evidence consumption. Independent `verify_receipt` validation passes against
current source fingerprint
`124293a9cf73a976107a4cae465666628b0a876d926d364d18394c92df086b2a`,
also used by the running full matrix. Applying the authenticated title/menu,
black-card, and seam builders twice to this freshly reconstructed parent
produces `current648` and `current651`, both byte-identical to tested
`b93ebc46...`. Their intermediate receipts are retained in `current646/647`
and `current649/650`. This is fresh reproducibility evidence, not a passing
deterministic-suite ledger or human review of the new candidate.

### r536 complete matrix and static-contract follow-up

`current644` finished on 2026-09-10 at 11:41:33 UTC with **86 passed, one
failed, zero blocked**. Source fingerprints before and after both equal
`124293a9cf73a976107a4cae465666628b0a876d926d364d18394c92df086b2a`.
All boss runtime gates pass with freshly generated states: geometry,
determinism, semantic cadence, speed, trajectory pairing, publication
cadence, and material/silhouette galleries. Fresh Penta publication cadence
is 1.1810 against the unchanged 1.20 ceiling (the tighter target remains
MISS). The earlier retained-state ratio 1.1632 is a separate measurement.
Title/menu, seven-stage, ending, and live-palette checks also pass.

The sole failure, `boss_atomic_attr_contract`, required the old bank-13
`$572C` fragment verbatim, including the unsafe instructions deliberately
replaced by r536. Only after the full matrix finished, the verifier was
updated to reconstruct the new stub within that fragment and independently
authenticate the full bank-20 helper/ownership via `visible_seam_matches`.
The original scene predicate and continuation remain exact requirements.
New tests accept both authenticated parent and repair, and reject mutations
in the predicate, stub, continuation, helper, and surrounding padding.
All **49** r535/r536 unit tests pass. Fresh selected-gate run `current652`
passes `boss_atomic_attr_contract` and `ted_expanded_integration` against the
unchanged b93ebc46 candidate. It is not a full-matrix run.

The failed `current644` manifest has not been edited or resumed under changed
sources. Its passing runtime evidence and the later static checks are kept
distinct. The new verifier source invalidates whole-checkout freshness for
release qualification. No READY, deterministic-suite pass, new human test,
merge, tag, or push is claimed. Publishing still needs the pending choice
about including existing uncommitted candidate-source work; the index also
contains pre-existing staged edits that have not been swept into a commit.

A completely fresh full matrix was subsequently started as `current653`
against corrected source fingerprint
`e2606e1948b0b2f7f2c40468efb557990d0305d773fe40ee19827e2c9865c9ae`.
The earlier `current644` failure remains immutable. Fresh original-source
double-build `current655` and independent receipt verification pass with
that same fingerprint. Attempt `current654` failed because the sandbox
denied the required ptrace provenance check; its log is retained, and the
approved host retry uses the separate `current655` directory. No emulator
was used by either source-build attempt.

Overlay chains `current656/657/658` and `current659/660/661` both reproduce
exact b93ebc46 from that fresh original-source parent. These build receipts
remain source evidence, not a deterministic-suite ledger or human approval.
The r535 pin and historical failed headed record remain unchanged pending
the requested decision about pinning and reviewing r536.

`current653` completed on 2026-09-10 at **12:21:28 UTC** with status
`emulator-pass`: **87 passed, zero failed, zero blocked**. Its source
fingerprint before and after is the same e2606e19 value above (844 inputs).
The final manifest SHA-256 is
`92e7c18b711c2ea3b153ac1d1cde28fffea0c7ff3e1427abca7a8debeeb9d4ac`.
The original trial, isolated tested ROM, and both final source rebuilds
(`current658`, `current661`) all hash to exact b93ebc46. The corrected static
ownership gates pass within this full run, as do all boss geometry, speed,
trajectory, and cadence gates. Penta publication cadence again measures
1.1810 against the unchanged 1.20 ceiling, with the tighter target still MISS.
All earlier failed manifests remain unchanged.

This closes the requested final-boss automated regression failures. It does
not substitute for a full deterministic-suite release ledger, audience
approval, exact-r536 headed human review, or the pending reservation-backed
MiSTer hardware sweep. The pin/provenance and Git publishing decisions remain
pending; no commit, merge, tag, push, or READY claim has been made.

### Approved r536 headed launch

The command approval gate subsequently approved pinning and launching exact
r536 for human review. Only `candidate.path` and `candidate.sha256` changed
in `.codex/stage1-ready-gate.json`; the hook definition and failed historical
headed provenance were not changed or bypassed. Host census showed no
emulator before the guarded launch. The running exact process is PID 4168556,
owned by launch session 40857, with the canonical `current636/candidate.gb`
path and b93ebc46 SHA above.

Launch receipt:
`tmp/headed-launch-receipts/1789044275041347815-4168655-b93ebc46ed4a.json`,
timestamp 2026-09-10 12:44:35 UTC. Its gate snapshot SHA is
`5811e7039e76a807053236177a93cdd4b7d3aab008f6f0a8e535885e45c7f444`.
The visible mGBA game window reports PENTADRAGON at 60 fps. Its initial
dialog warns that the ROM is in a temporary directory; the project requires
this retained repository-local scratch location. The warning capture is
`tmp/r536-headed-error-current662.png`. This is not a game crash or a passing
human review. Source fingerprint remains e2606e19 after the candidate-pin
update, so the fresh full-regression source binding is unchanged.

Exact-r536 human feedback is now pending on the launched game. No successful
headed status, release-ledger pass, merge, tag, push, or READY claim is made.

The warning window disappeared during acknowledgement (`xdotool` reported
BadWindow on the disappearing target); a subsequent window census and
`tmp/r536-headed-game-current663.png` capture confirm the game is visible
and running with no warning dialog. No input was sent to the game itself.
The launcher remains open for human review; do not start another emulator
while PID 4168556 owns the single-flight slot.
