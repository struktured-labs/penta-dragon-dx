# Release packaging

## Deterministic source receipt

Before packaging or committing release-sensitive source, run:

```bash
python3 scripts/diagnostics/run_deterministic_suite.py \
  --expanded-ted \
  --menu-icon-colors
```

The command refuses to start while any mGBA process is active, builds twice
under the suite's repository-local `tmp/` output, requires byte-identical
candidates, and runs the current 78-gate expanded matrix serially. Only a
complete pass writes the ROM-free,
source-fingerprint-bound receipt at
`docs/release/verification/latest.json`.

Before presenting a build for headed play or a livestream, run the dedicated
full live profile:

```bash
python3 scripts/diagnostics/verify_live_regression.py \
  tmp/menu-icons-candidate-r5/penta-dragon-dx-menu-icons-r5.gb \
  --output tmp/penta-live-regression
```

Its `manifest.json` is the hash-bound receipt for the exact candidate. The
profile is ROM-aware: the 512 KiB expanded stream candidate requires the same
78 gates as the release matrix, while the legacy profile currently requires
86. It includes separate natural-attract and live-gameplay pickup gates, both
GAME START paths, Stage 1 traversal/copy/bleed, speed, spikes, bonus gameplay,
ordinary and low-health flicker, all-nine matched-work boss timing and its
phase-shift null, the complete spotlight roster, and every story/ending route.
A subprocess exit code without the exact profile-aware manifest is rejected.

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

`scripts/build_release_bundle.py` creates a deterministic, ROM-free archive
from the checked-in IPS and a successful full release-matrix manifest. It
independently rebuilds and applies the IPS before packaging, checks all native
screenshots, and rejects ROMs, save files, or savestates in the archive.

Until both the audience palette decision and the reservation-backed MiSTer
sweep are bound to the same ROM hash, the only permitted output name contains
`PREHARDWARE` and its readme says not to publish it:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest tmp/penta-release-candidate/manifest.json
```

Final mode is deliberately stricter:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest /path/to/emulator-manifest.json \
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
  --output /path/to/palette-approval.json \
  --confirm "AUDIENCE APPROVED" \
  --notes "Final colors selected during the Twitch stream" \
  --expanded-ted \
  --menu-icon-colors
```

Romhacking.net stopped accepting new database submissions in August 2024, so
the practical current database target is Romhack Plaza. Plaza accepts IPS
patches and ZIP archives, forbids ROM files, recommends a separate
`readme.txt`, and requires at least one native-resolution screenshot (three or
more are preferred):

- https://community.romhackplaza.org/help/terms/
- https://romhackplaza.org/news/many-new-things-on-the-plaza/

The packager emits four 160x144 PNGs beside the ZIP for the submission form.
It does not upload anything.
