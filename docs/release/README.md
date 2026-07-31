# Release packaging

## Deterministic source receipt

Before packaging or committing release-sensitive source, run:

```bash
python3 scripts/diagnostics/run_deterministic_suite.py
```

The command refuses to start while any mGBA process is active, builds twice
under `/tmp`, requires byte-identical candidates, and runs the current
38-gate matrix serially. Only a complete pass writes the ROM-free,
source-fingerprint-bound receipt at
`docs/release/verification/latest.json`.

During the matrix, a random per-run token identifies only that run's emulator
descendants across `xvfb` sessions and PID namespaces. A foreign emulator is
confirmed across three 50 ms polls before the runner stops its own exact
groups. A normally completed matrix is also rejected if any token-owned mGBA
process remains alive.

Install the repository hook once per clone:

```bash
scripts/install_git_hooks.sh
```

The pre-commit hook rechecks the emulator single-flight policy, rejects a
missing or stale full-suite receipt, and rejects staged ROM/save/state files.
It does not run mGBA during commit.

`scripts/build_release_bundle.py` creates a deterministic, ROM-free archive
from the checked-in IPS and a successful full release-matrix manifest. It
independently rebuilds and applies the IPS before packaging, checks all native
screenshots, and rejects ROMs, save files, or savestates in the archive.

Until both the audience palette decision and the reservation-backed MiSTer
sweep are bound to the same ROM hash, the only permitted output name contains
`PREHARDWARE` and its readme says not to publish it:

```bash
python3 scripts/build_release_bundle.py \
  --emulator-manifest /tmp/penta-release-candidate/manifest.json
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
  --notes "Final colors selected during the Twitch stream"
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
