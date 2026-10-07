# Explicit palette-test fixtures (#70)

The broad palette run initially produced55 failures and6 passes in this clean
worktree. The shared synthetic-state fixture unconditionally loaded an ignored
historical ROM, and the real-memory tests referenced two more ignored capture
directories. The current-ROM environment variable was ignored by those tests.
This was missing test input, not55 observed game defects.

The shared fixture now accepts `PENTA_TEST_STREAM_ROM` only for the exact
current126861... or historical46eb... identity. Without an override it builds
the current fixture from original cartridge/source in repository-local scratch.
Transaction tests use that same authenticated path rather than reopening a
hardcoded historical filename. Real device subprocesses remain forbidden by
the mocks. Historical capture assertions remain available for the legacy ROM.

For current-ROM real-memory checks, supply an explicit state manifest. It
requires three distinct Stage1 captures and at least one Stage2 capture,
validates every file hash, ROM CRC/title, state size and dungeon identity, then
runs the original ownership/alias assertions on the translated memory. These
synthetic MiSTer containers are parser inputs, never runnable device savestates.
Missing inputs fail explicitly; no automatic emulator launch or skip occurs.

## Reproduction

From this worktree, generate a manifest from a completed source suite:

```sh
python tests/palette_test_fixtures.py \
  --suite-root tmp/title-retry-source-suite-02 \
  --output tmp/palette-current-states-generated-01.json
PENTA_TEST_STREAM_ROM="$PWD/tmp/title-retry-source-suite-02/build/source-a/candidate.gb" \
PENTA_TEST_PALETTE_STATES="$PWD/tmp/palette-current-states-generated-01.json" \
uv run --no-project --with pytest --with pillow --with pyyaml python -m pytest -q \
  tests/test_title_retry_palette_candidate.py tests/test_palette_owned_transactions.py \
  tests/test_stage1_palette_ownership.py tests/test_stage2_palette_ownership.py \
  tests/test_palette_fixture_contract.py
```

Use a fresh output manifest name on repeat. Manifest generation records the
source run/matrix hashes and rejects incomplete suites or gate inventories.
The existing source-suite02 supplied Stage1 return captures6960/7080/7200 and
the exact Stage2 control state. It is reused authenticated evidence, not a fresh
emulator run. No ROM/state data or generated manifest belongs in Git.

Result:68 tests and35 subtests passed, no skips. Seven fixture-contract tests
also pass independently and reject changed hashes, wrong ROM/dungeon identity,
missing/duplicate samples and a missing manifest. An initial manifest-generator
attempt incorrectly expected matrix status `passed`; the authoritative matrix
uses `emulator-pass`. The corrected explicit status check generated the fixture
and the same68-test run passed with that generated manifest.

Follow-up inventory review added explicit rejection of duplicate result names
and duplicate selected-gate names, alongside empty, missing, extra, failed and
running entries. The expanded run passed76 tests plus35 subtests; a separate
fixture/card/repeat/Select-oracle run passed48 tests plus16 subtests. These
counts overlap and are not additional emulator integration gates.

Only tests and this audit changed for #70. The running source suite's bound
source fingerprint remained unchanged. No palette bridge deployment, hardware
acceptance, or issue closure is implied.
