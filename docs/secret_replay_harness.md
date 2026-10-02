# Secret-area diagnostic replay

Use `scripts/diagnostics/run_secret_entry_probe.py` and its adjacent
`probe_secret_entry.lua` for new investigations, not the historical copies in
ignored `tmp/`. These are diagnostic tools, not release acceptance gates.

Set `ENTRY_ROM` explicitly. Supply `cold` or a savestate belonging to that exact
ROM, followed by a fresh output basename. The launcher verifies the state's
ROM CRC/header and refuses retargeting. It always invokes the single-flight
wrapper; status75 means occupied, not permission to bypass or retry blindly.

Example, using an existing exact-ROM state:

```sh
ENTRY_ROM=tmp/secret-alias-chunk-trial-01/candidate.gb \
ENTRY_FRAMES=120 ENTRY_KEYS=1 ENTRY_PULSE_A=1 ENTRY_CAPTURE_EVERY=30 \
uv run --with pillow --with pyyaml python scripts/diagnostics/run_secret_entry_probe.py \
  tmp/secret-alias-chunk-lowhealth-return-01/frame-0960.ss0 my-new-replay
```

Optional native capture uses `ENTRY_NATIVE_TAP` pointing to the built native
capture library. For restored-state captures also set `ENTRY_NATIVE_START_GATE`
to an initialization marker inside the new output directory. The tap must
support that startup protocol; completeness does not establish audio fidelity.
Large capture files go under `/mnt/data/tmp/`, falling back to repository
`tmp/` when unavailable. ROMs/states/screenshots remain ignored scratch data.

The current diagnostic runtime expects the local corrected core library under
`tmp/mgba-cgb-latches-r454/build`; retain core/library identities when interpreting
results. The launcher records probe, runner and single-flight wrapper hashes.

Health telemetry reads physical bank1 `DCBB`, independently of mapped SVBK.
`DCDC` is not health. Explicit `ENTRY_*` assistance can alter health, inventory,
position or encounter setup and is recorded in the receipt. Do not claim a
natural playthrough from assisted fixtures. Empty `inputs.tsv` is not proof of
delivered input; native capture provides a separate input timeline.

Timeouts write an incomplete receipt and run the read-only process check.
Inspect that result before any subsequent emulator command. Existing captures
and old broken telemetry are retained as controls; never rewrite their receipts.
