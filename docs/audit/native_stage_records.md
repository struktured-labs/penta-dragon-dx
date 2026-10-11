# #54 Native bank-1 stage records 7/8 (native-stage-records)

Parent: main `b8efcffe` build
`126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941`.
Candidate:
`050209058633e2723a25c4ad60f92e0a3d54d51dbdd27d449b23069d98323ed4`
(407 bytes differ from the parent, all listed below plus the header checksum).
Built by the final chain stage `scripts/diagnostics/build_native_stage_records.py`
(`build_stream_regression_candidate --native-stage-records`, stream source
profile v4).

## Symptom

Stage init `00:0C29 -> 01:7B91` copies the 29-byte record at
`01:7BB3 + 29*FFBA` to HRAM `$FF9B-$FFB7`. Record bytes 19..27 land in
`$FFAE-$FFB6`, the tile-animation/scroll parameters read by the VBlank routine
`00:086C` and by `01:4198`. On the cartridge they are zero for records 7 and 8.
Older DX builds (rc11, `ffc29f4e`) loaded helper code there, which drove the
animation path in those stages: the corrupted secret-area tiles of #23.

## Root cause

Two DX helpers had been placed in "asserted-zero caves" that are really record
bytes 19..27 of records 7 and 8:

* `01:7C91` Ted bank-16 trampoline tail `3E 10 21 00 40 E5 C3 61 00`
  (entered only by `JP $7C91` at `01:6FEC`);
* `01:7CAE` death final-publication return `C5 D5 CD 5C 43 D1 C1 AF C9`
  (entered only by `JP $7CAE` at fixed `00:0035`).

PR #63 (`clean-stage-headers`) fixed the HRAM values but not the table or the
loader: it left both helpers in place, rewrote the native loader
(`01:7B91-7BB2`: `CP 07 / JP NC 7C7E`) and fetched records 7/8 from a bank-63
mirror through a far stub written over record-7 bytes 0..17. The bank-1 table
stayed corrupt, and the live loader took 4104 cycles for records 7/8 instead of
the cartridge's 3304 (+800 cycles per stage load).

## Fix (cycle-identical to the parent)

1. Both nine-byte helpers move, byte for byte, into fixed bank 0 at
   `$00D0` / `$00D9`. `$00CF-$00FF` is unreferenced stock fill between the
   `RET` at `$00CE` and the entry point `$0100`. No stock or DX control
   transfer or pointer names it, and an attract read/exec watch (below) sees no
   access. Neither helper depends on its own bank, and both are entered with
   bank 1 mapped as before.
2. The two `JP nn` operands (`01:6FEC`, `00:0035`) are retargeted. `JP nn`
   costs 16 T-cycles for every target.
3. `01:7B91-01:7CB7` (native loader, index helper and all nine records) is
   restored to the exact cartridge bytes, so every record gets native loader
   timing again.
4. The retired bank-63 mirror, index, loader, wrapper and stub bytes go back to
   erased `$FF`; nothing references them.

Changed ranges (file offsets): `0036-0037`, `00D0-00E1`, header checksum
`014E-014F`, `6FED-6FEE`, `7B91-7BB1`, `7C7E-7C8F`, `7C91-7C98`, `7CAE-7CB6`,
bank 63 `FC000-FC9B1`, `FFC81-FFC86`.

## Evidence

* Loader contract (`verify_clean_stage_headers`, extended): for records 0..8
  the candidate equals the cartridge (HRAM `$FF9B-$FFB7`, AF/BC/DE/HL, bank,
  DC09, 3304 loader cycles). The parent has the right HRAM, but records 7/8 take
  4104 cycles.
* Attract lockstep, frames 0..26000, parent vs candidate: per-frame cycle
  counter, scene, RNG, PC, WRAM `$C000-$DEFF` + `$DF00` sums, HRAM and CRAM
  byte-identical, **with no masks**. The fixed-PC interrupt cycle log (89,472
  V/S/T/Q events) is byte-identical too.
* `verify_stage7_state_patrol` (stage 7, 9 seeds + base): PASS. Per-seed
  attr-events, lifecycle, camera and loop TSVs are byte-identical to the
  parent.
* Fill watch (`$00CF-$00FF` data-read watchpoint + per-address exec
  breakpoints, attract 0..26000): 0 reads and 0 executions on both parent and
  candidate.
* New gate `native_stage_records` (`verify_native_stage_records.py`,
  registered after `secret_boss_handoff`):
  static table + loader vs the cartridge, live loader probe for records 0..8
  (HRAM image, registers, bank, DC09, cycles), and a negative control with the
  played helper layout written back. Candidate PASS. Parent FAIL (static table,
  records 7/8 4104 != 3304 cycles). `ffc29f4e` FAIL (`$FFAE-$FFB6` =
  helper bytes).
* `playtest_header` gate adds a native-layout corruption control and
  `--require-native-timing-all-records`. `ted_expanded_integration` follows the
  relocated helpers (`native_stage_records_exact`).
* #23 secret-area replay: `ffc29f4e` has 6,544 map rotations, the candidate 0
  over 3,574 secret frames. The parent run is byte-identical to the candidate
  (trace and all 168 frames), so #23 was already resolved by #63 and stays
  resolved.
* Full deterministic suite: see `docs/release/verification/latest.json`.
