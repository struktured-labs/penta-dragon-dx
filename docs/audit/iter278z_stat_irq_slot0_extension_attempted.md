# iter 278z — STAT IRQ slot-0 extension (attempted, reverted)

## Hypothesis

Fresh-boot probe baseline showed slot 1 = 78% pal-2 (because existing
STAT IRQ stub at 0xDB50 explicitly stamps slot 1) but slot 0 only at
12% pal-2. Theory: extending the stub to also stamp slot 0 would
bring slot 0 to ~78% pal-2 too.

## Implementation

Added 4 instructions to `build_stat_irq_wram_stub()`:
```
LD A, [0xFE03]    ; slot 0 attr
AND 0xF8
OR B              ; B = pal-2 or pal-1 from FFBE
LD [0xFE03], A
```

+44T per STAT IRQ fire (was 44T baseline → now 88T total).

Relocated STAT_STUB_ROM_ADDR from 0x53F2 (36-byte budget) to 0x6A70
(144-byte free run in bank 13) to fit the extension. Verified bytes
serialize correctly to bank13:0x6A70.

## Result — infrastructure-blocked validation

Sara fresh-boot probe (`tmp/probe_fresh_boot_sara2.lua`) consistently
fails to produce output after iter 278z build. mGBA-qt runs but doesn't
write the counts file. Same probe runs cleanly on prior iter 278p+y
baseline.

This MIGHT mean:
- iter 278z's +44T STAT IRQ overhead breaks the test infrastructure
  (parallax timing → mGBA-headless crashes mid-script?)
- OR an unrelated environment issue (Xvfb display slot exhaustion has
  been documented this session; was partially cleaned but may persist)

## Decision

Reverted to iter 278p+y baseline. The infrastructure issue prevents
clean validation of iter 278z, and the +44T addition is borderline at
iter 8's documented 30T parallax-break threshold. Even if game still
runs, iter 278z2 should:

1. Diagnose Xvfb infrastructure (kill all leftover display servers,
   restart fresh)
2. Re-run baseline probe to confirm reproducibility
3. Then re-attempt iter 278z with smaller delta (e.g., replace existing
   slot 1 stamp with slot 0 stamp — same cycle cost, just different slot)

## Build state after revert

iter 278y baseline (commit `73868bd`):
- iter 278w: bg_table = function of YAML
- iter 278x: OBJ colorizer = function of YAML + Phase 3 drift cleanups
- iter 278y: stale-fallback cleanup → KeyError on missing YAML key

All YAML-driven verifiers PASS.
All 170 byte-verifier locks PASS.
All hook tests (116 BG + fresh-boot CRAM) PASS.

## /goal status

Components 1 (white flicker) + 2 (no orange in Sara): empirical baseline
shows slots 0/2/3 only at 12-39% pal-2 on fresh boot. **The bug is real
and persistent.** 13th distinct attempt to address it (counting
iter 277/278d/g/h/n/o/q/r/s/s2/t/v/z) blocked on infrastructure +
architectural ceiling.

Future iters should focus on validating that infrastructure is sane
BEFORE pushing more sara_stamp attempts — wasting cycles on
unverifiable attempts is the path that produced 13 reverts.

Components 3 (cursor) + 4 (stage intro) remain SHIPPED.
