# #14 Sara hidden behind black ceiling overhangs (sara-overhang-priority)

Parent: release-lock `db09de8d1b4293401f587fcce77689d8c13799eb009f13001487786c3accdcb8`
(main `86237fff`). Candidate:
`ffc29f4e29f2c2f9995f132c08676624ad92a206b822b3afdf835be3ad072feb`
(131 bytes differ from the parent, all in the runs below plus the header checksum).

## Symptom

Sara is drawn on top of the black ceiling overhangs (pre-secret corridor of
Stage 1, issue #14 comments) on EverDrive GB hardware and in mGBA. On the
original cartridge she walks *under* them: the overhang hides her.

## Root cause

The original game gives Sara's four 8x8 OBJ quadrants OBJ-to-BG priority
(OAM attribute bit 7) whenever the map block under a quadrant is an overhang
block:

* bank 1 `$5096` walks the four quadrant map pointers `DC10..DC17` through a
  block-range test (`$50DF`, `[FFA0,FFA1)`) and stores one flag per quadrant
  at `FFC2..FFC5`;
* the OBJ emitter (bank 0D/10 `$7B42`, executed from its WRAM copy at
  `$DA42`) calls bank 0 `$1188`, which sets bit 7 for slots 0..3 whose flag is
  non-zero.

DX reused `FFC4` for its map publisher (r353), so r365/r368 reduced `$1188`
to `RES 7,A / RET` and r381 removed the `FFC4` stores. Sara never gets BG
priority again. The earlier #14 spike (WRAM `$DB40` helper) restored it but
changed per-frame timing, which broke the attract demo (Gargoyle segment) and
Sara's doorway landing, so #14 was deferred at the release lock.

## Fix (cycle-identical to the parent)

1. **Bank 1 `$5096..$50F8` quadrant flags.** Same prologue/epilogue. Each
   quadrant CALLs one shared range test at `$50D7` (the old inline test, folded
   with `LD A,[HL+]`) and stores the flag to `FFC2`/`FFC3`/`FFC5` exactly as
   before, plus a private copy `T[q]` at WRAM `$C0C0+q` (OAM-page tail; OAM DMA
   copies only `$C000..$C09F`; no other reference; WRAM bank 0 so SVBK cannot
   hide it). `FFC4` stays with the DX publisher. Per quadrant every compare
   outcome costs exactly the parent's T-cycles (below 148, above 184, inside
   208; 144/180/204 for the `FFC4` quadrant), using `PUSH AF/POP AF` pads.
2. **Bank 0 `$11A0..$11C2`** (dead `POP HL/RET` + the flash helper `$11A2`,
   which had exactly two callers): one fused flash + priority helper. Flash
   semantics are identical to `$11A2` (slot to `FFDD`, counter `$ABC0+slot`,
   bit 4); it also returns `A = T[slot]` for slots 0..3 and 0 otherwise.
3. **Emitter call sites** bank 0D/10 `$7B42` (and so WRAM `$DA42`):
   `CALL 11A2 / CALL 1188 / AND F8 / OR C` becomes
   `CALL 11A0 / RRCA / AND 80 / OR B / OR C / NOP`. Same 9 bytes; the flash
   and no-flash paths both cost the parent's 260/240 T-cycles. Only bit 0 of
   `T` can reach bit 7, so stale or foreign values cannot set other bits.

No bank switch, trampoline or new bank is needed: the fixed-bank dead code
and the folded range test fund the work.

## Evidence

* Attract demo lockstep, frames 0..26000, parent vs candidate: scene, RNG
  (`FFD1`/`FFD4`), WRAM `$C000..$DEFF` (masking only Sara's OAM bit 7, `T` and
  the 9 call-site bytes), HRAM and CRAM identical on every sample. A fixed-PC
  cycle log (89,417 events at `$0040/$0048/$0050/$12CB`) is identical apart
  from 9 interrupt-entry latency samples of 8..24 cycles (an IRQ landing
  inside a modified instruction run) with no cumulative drift. The candidate
  sets the priority bit on ~170 demo frames (Sara under overhangs).
* `verify_stage7_state_patrol.py` (4000 frames, tolerance 0.02, all seeds)
  passes; every per-seed result equals the parent's except the helper
  telemetry label (`central_x_entry_11a2` -> `central_x_entry_11a0`, same
  count), PC samples and one `first_inactive_state` PC inside the emitter.
* New gate `sara_overhang_priority` (`verify_sara_overhang_priority.py`):
  stock and candidate cold boots with the same input recipe; at frames 1240,
  1260 and 1300 Sara (world 1240/1356, camera `$0C08`) must have priority set
  on all four entries and a fully black 16x16 footprint (hidden), and at
  frame 1200 (open floor) priority clear and visible. Stock passes (reference);
  the parent fails (priority never set, 192 visible footprint pixels at
  frame 1260); the candidate passes.
* `probe_stage_speed.lua` authenticates the new helper and call site
  (`same(0xDA41, ...)`, `same(0x11A0, ...)`) and samples them as
  `central_x_entry_11a0`, which `verify_stage_speed_matrix.py` adds to the
  existing helper entries; the telemetry contract itself is unchanged.
* Full deterministic suite: see `docs/release/verification/latest.json`.

Emulator evidence; hardware confirmation on the EverDrive is separate.
