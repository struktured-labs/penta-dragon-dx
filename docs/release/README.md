# Release packaging

## Game Over/restart successor (issues #7–#10)

The repaired candidate is SHA-256
`c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d`.
Use the separate `--restart-source` profile for its publication receipt:

```bash
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
.venv/bin/python scripts/diagnostics/run_deterministic_suite.py \
  --restart-source --output tmp/restart-deterministic-FRESH-ATTEMPT
```

It builds original cartridge → r536 → Game Over row guard → death cleanup/title
rearm twice, authenticates every parent and patch, and runs all 90 gates. The
three restart routes include blank-SRAM and saved-game spike deaths and compare
two complete restart cycles. The hazard routes use a deterministic HP-zero
stimulus after walking, not movement-only collision qualification.

The 2026-09-16 publication run passed all 90 gates with two byte-identical
builds; the full unit sweep passed 1,195 tests. Its checked-in receipt is
[`verification/latest.json`](verification/latest.json). Retained local evidence
is under `tmp/restart-publication-suite-20260916-03/`; generated ROMs and
captures are not published in Git.

Do not substitute an older r536 receipt for this successor. The checked-in IPS
and existing palette-lab approval profile still target the r536 parent; the new
successor is built by `scripts/build_restart_candidate.py`, not that older IPS.
Hardware replay, audience approval, and release packaging remain separate from
source publication. The historical r536 commands below document the parent.

## Deterministic source receipt

For the pinned r536 profile, before packaging or committing release-sensitive
source, run with the documented CGB-latch runtime:

```bash
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/run_deterministic_suite.py \
  --r536-source --output tmp/r536-deterministic-FRESH-ATTEMPT
```

The command refuses to start while any mGBA process is active, builds twice
under the suite's repository-local `tmp/` output, requires byte-identical
candidates, and runs the current 90-gate expanded matrix serially. The r536
profile requires a fresh output and rejects legacy flags and resume. Each of
its two independent source builds retains traced factory/construction evidence;
no historical-input bundle or retained factory ROM is required. Only a
complete pass writes the ROM-free,
source-fingerprint-bound receipt at
`docs/release/verification/latest.json`.

Use `--receipt tmp/r536-deterministic-FRESH-ATTEMPT/suite-receipt.json` to keep
the proof in scratch storage without replacing the published receipt. The r536
receipt records canonical source-build and matrix paths; its verifier requires
those retained artifacts even when the receipt itself is copied elsewhere.
It rechecks both constructions, current source/runtime identities, actual
tested-ROM bytes, full gate order, and the complete nested exception ledger.
The ledger uses current Stage-7 world-position evidence and reports observed
speed/cadence exceptions rather than requiring historical slowdowns to recur.
The legacy `--expanded-ted --menu-icon-colors` profile remains available for its
older candidate and retains its prior ledger contract.

Before presenting a build for headed play or a livestream, run the dedicated
full live profile:

```bash
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/verify_live_regression.py \
  tmp/r536-penta-seam-vram-current636/candidate.gb \
  --output tmp/r536-live-regression-FRESH-ATTEMPT
```

Its `manifest.json` is the hash-bound receipt for the exact candidate. The
profile is ROM-aware and requires the complete applicable release roster
(currently 90 gates). It includes separate natural-attract and
live-gameplay pickup gates, both
GAME START paths, Stage 1 traversal/copy/bleed, speed, spikes, bonus gameplay,
ordinary and low-health flicker, all-nine matched-work boss timing and its
phase-shift null, the complete spotlight roster, and every story/ending route.
A subprocess exit code without the exact profile-aware manifest is rejected.

For an already-qualified candidate, the pre-stream gate can independently
validate its existing complete matrix without launching another emulator or
writing/relabeling a playtest receipt:

```bash
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/verify_live_regression.py \
  tmp/r536-deterministic-FRESH-ATTEMPT/build/source-a/candidate.gb \
  --verify-manifest tmp/r536-deterministic-FRESH-ATTEMPT/matrix/manifest.json
```

This requires full-matrix status, the exact current ordered roster, current
source/runtime identities, and matching source/tested-ROM bytes. Selected,
stale, reordered, partial, or changed evidence fails. Use the same literal
runtime environment recorded by the matrix when repository paths have aliases.
`--check-contract` remains the no-emulator inventory-only check; it does not
qualify a ROM.

During the matrix, a random per-run token identifies only that run's emulator
descendants across `xvfb` sessions and PID namespaces. A foreign emulator is
confirmed across three 50 ms polls before the runner stops its own exact
groups. Guarded children also publish their host-visible namespace PID and
kernel start time before `exec`; forked children retain the same tokenized
single-flight lock descriptor. These validated identities preserve ownership
across environment rewriting, nested PID namespaces, and post-exec forks
without allowing stale PID reuse. A normally completed matrix is also rejected
if any token-owned mGBA process remains alive.

Install the repository hook once per clone:

```bash
scripts/install_git_hooks.sh
```

The pre-commit hook rechecks the dedicated live-profile inventory and emulator
single-flight policy, rejects a missing or stale full-suite receipt, and
rejects staged ROM/save/state files. It does not run mGBA during commit. This
means a source change cannot be committed against an old receipt, while the
emulator remains a deliberate serial pre-commit step instead of spawning from
inside Git.

After acquiring the shared MiSTer reservation, start the physical sweep with
the exact emulator manifest, ROM, and IPS that share one hash-qualified
candidate lineage:

```bash
python3 scripts/mister.py release_sweep_start \
  /path/to/emulator-manifest.json \
  /path/to/candidate.gb \
  /path/to/candidate.ips
```

The ROM and IPS arguments are optional only when the checked-in production
paths already match the emulator manifest. The preflight rejects a truncated
or reordered matrix, changed source/runtime identities, an IPS that does not
reconstruct the candidate, or any later change to the explicit local inputs.
Every hardware boundary revalidates the reservation before SSH or SCP.
At the `boss_arena` checkpoint, explicitly inspect Ted's whip/orb staging and
compare it with the hash-pinned side-by-side clip in
`docs/release/known_deviations.md`. Confirming that checkpoint ratifies the
documented stabilized presentation; do not seal `hardware-pass` if the native
alternation is preferred instead.

`scripts/build_release_bundle.py` creates a deterministic, ROM-free archive
from the checked-in IPS and a successful full release-matrix manifest. It
independently rebuilds and applies the IPS before packaging, checks all native
screenshots, and rejects ROMs, save files, or savestates in the archive.

Until both the audience palette decision and the reservation-backed MiSTer
sweep are bound to the same ROM hash, the only permitted output name contains
`PREHARDWARE` and its readme says not to publish it:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest tmp/r536-deterministic-FRESH-ATTEMPT/matrix/manifest.json \
  --rom tmp/r536-deterministic-FRESH-ATTEMPT/build/source-a/candidate.gb
```

Final mode is deliberately stricter:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest /path/to/emulator-manifest.json \
  --rom /path/to/exact-r536-candidate.gb \
  --hardware-manifest /path/to/mister-hardware-manifest.json \
  --palette-approval /path/to/audience-palette-approval.json \
  --final
```

The hardware manifest must use schema
`penta-dragon-dx-mister-release-v1`, report `hardware-pass`, bind the exact
ROM, IPS, and emulator-manifest hashes, and pass every required checkpoint.
The palette approval must use schema
`penta-dragon-dx-palette-approval-v1`, report `audience-approved`, and bind
the exact ROM and production palette-YAML hashes.

After the livestream vote, rebuild the candidate and matrix first, then record
the explicit approval. The recorder independently rebuilds the exact ROM from
the approved YAML using temporary outputs:

```bash
python3 scripts/record_palette_approval.py \
  --r536-source \
  --rom /path/to/exact-r536-candidate.gb \
  --source-output tmp/r536-palette-source-FRESH-ATTEMPT \
  --output /path/to/palette-approval.json \
  --confirm "AUDIENCE APPROVED" \
  --notes "Final colors selected during the audience review"
```

### Exact r536 source verification

For r536 emulator qualification, explicitly select the documented CGB-latch
runtime on the checked-in verifier command; do not rely on a login-shell
environment. See [the instrument audit](../audit/mgba_cgb_latches_r454.md).
The library SHA-256 must be
`20fa5ddaf77abed9cf55972616242a232181a04fb1d52bf3e38e58e7b809b4cf`.
The installed uncorrected library produces a blank Ted arena and cannot
substitute for that runtime. A runtime change requires a fresh full matrix,
not a resume or a combination of results from different libraries:

```bash
LD_LIBRARY_PATH="$PWD/tmp/mgba-cgb-latches-r454/build" \
PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/diagnostics/verify_release_candidate.py \
  tmp/r536-penta-seam-vram-current636/candidate.gb \
  --output tmp/r536-full-release-FRESH-ATTEMPT
```

The source-only entrypoint builds exact r536 directly from the
original cartridge and repository source, with no retained factory ROM or
historical-input bundle:

```bash
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/build_r536_candidate.py \
  --out-dir tmp/r536-original-source-FRESH-ATTEMPT
```

Use a fresh repository-local output directory. This requires filesystem tracing
permission, runs two traced factory builds and two identical 105-step in-memory
constructions, then revalidates both runs against current source, tools, and
inputs. The new entrypoint is included in the source fingerprint. ROMs, traces,
and receipts stay in ignored scratch storage. Success is source reconstruction,
not audience approval, hardware validation, or current-tree emulator
qualification.

The palette recorder has a distinct source-only r536 profile. To exercise
it without recording an approval:

```bash
TMPDIR="$PWD/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 scripts/record_palette_approval.py \
  --r536-source --verify-only \
  --rom tmp/r536-penta-seam-vram-current636/candidate.gb \
  --palettes palettes/penta_palettes_v097.yaml \
  --source-output tmp/r536-palette-original-source-FRESH-ATTEMPT
```

This writes a separate source-verification receipt, explicitly recording no
audience approval or release qualification. It rejects historical/legacy
profile flags and confirmation/output options in verification-only mode.
After an actual audience decision, the same profile can record approval only
with the existing exact confirmation phrase, a fresh approval `--output`, and
a fresh `--source-output` (omit `--verify-only`). No approval is implied by a
successful source build. Existing approval files are never overwritten by
this profile.

The final packager recognizes `r536-original-source-v1` and independently
revalidates its hash/path/fingerprint-bound reconstruction receipt, including
both traced factories and regenerated ROMs. The legacy expanded-Ted approval
profile cannot stand in for r536. Final mode still requires a separate
hash-bound hardware pass and explicit audience approval. For all profiles,
the packager now also requires the full emulator gate order and source/runtime
identities to match the current tree and selected runtime, not merely remain
stable within an older run. Use the same documented CGB-latch runtime when
validating/packaging its matrix. The deterministic-suite build entrypoint now
supports the same source-only profile; actual full emulator qualification and
real audience/hardware evidence remain separate requirements.

The earlier `r534-original-source-v1` profile remains available for historical
receipt verification. It does not qualify or approve r536.

The separate historical original-cartridge replay profile can verify that the
current palette sources reconstruct the exact pinned r534 ROM without recording
approval:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/record_palette_approval.py \
  --rom tmp/stage4-cache-key-r534/candidate.gb \
  --palettes palettes/penta_palettes_v097.yaml \
  --verify-only --r534-original-replay \
  --historical-input-manifest tmp/r534-lineage-inputs-current486.json \
  --replay-output tmp/r534-palette-source-current494
```

Choose a fresh repository-local output directory for each attempt. This
requires filesystem tracing permission and retains two traced builds, a
revalidated reconstruction receipt, and `palette-verification.json`. The
twenty-eight historical inputs are construction evidence, not fresh playtests.
This mode rejects approval confirmation/output options and legacy profile
flags. Its receipt explicitly records no audience approval or release
qualification; the final packager's existing approval policy is unchanged.

Romhacking.net stopped accepting new database submissions in August 2024, so
the practical current database target is Romhack Plaza. Plaza accepts IPS
patches and ZIP archives, forbids ROM files, recommends a separate
`readme.txt`, and requires at least one native-resolution screenshot (three or
more are preferred):

- https://community.romhackplaza.org/help/terms/
- https://romhackplaza.org/news/many-new-things-on-the-plaza/

The packager emits four 160x144 PNGs beside the ZIP for the submission form.
It does not upload anything.
