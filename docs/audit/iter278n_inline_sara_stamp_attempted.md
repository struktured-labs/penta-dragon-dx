# iter 278n — INLINE sara_stamp + NOP runtime balance (attempted, reverted)

## Summary

After iter 278g (separate CALL sara_stamp, +24T → broke 22 CRAM) and
iter 278h (sara_stamp + FFA9 cache invalidate → wrapper overran VBlank
4764T > 4560T), attempted a tighter architecture:

**Inline sara_stamp INSIDE hwoam_recolor** (no CALL/RET overhead),
replacing the first 4 colorizer iterations to balance cycle delta.
Plus NOP padding to compensate for sara_stamp body being faster than
the colorizer per-slot path.

**REVERTED** because CRAM phase still broke at every tested NOP count.

## Architecture (what was implemented)

```
hwoam_recolor at 0x6B27:
  ; Scope check + D/E setup (unchanged ~96T)
  LD A,[D880]; CP 0x0C; RET NC          ; scope gate
  ; D = Sara form palette setup           ; existing
  ; E = boss slot setup                   ; existing
  ; NEW: inline sara_stamp for slot 0-3
  LD BC, 0xC003       ; shadow OAM attr base (WRAM, race-free)
  LD HL, 0xFE03       ; HW OAM attr base
  ; ×4 unrolled (13 bytes each):
  LD A,[BC]; AND F8; OR D; LD [HL],A
  INC HL × 4; INC BC × 4
  ; NOP padding (tested 0, 20, 35) to balance runtime delta
  NOP × N
  ; Tail-call colorizer for slot 4-39
  LD B, 36
  JP colorizer_loop_start
```

The colorizer's first 4 iterations are SKIPPED via HL=FE13 (slot 4 attr)
+ B=36. Slot 0-3 get unconditional Sara palette stamp from SHADOW OAM,
which is WRAM and immune to LCD mode locks.

## Test results

| NOPs | net delta vs iter 278e | fresh-boot CRAM fails |
|---|---|---|
| 0  | -160T to -240T (estimated) | 8 |
| 20 | -80T to -160T | 6 |
| 35 | -20T to -100T | 6 |

The failures consistently include:
- OBP-2.1 = 2EBE (witch idx 1, NOT jet 7C1F)
- OBP-2.2 = 511F (witch idx 2, NOT jet 5817)
- OBP-3.0 = 0000 (transparent, NOT 7F00)
- Spider boss palette (some idx)
- SpiralProjectile / TurboProjectile pixel counts below threshold

These are the SAME failures as iter 277 (B=20, -480T) and iter 278g
(+24T CALL). They share root cause: cond_pal's hash check at FFA9
does NOT register a cache miss when the fresh-boot test externally
forces FFD0=1, so palette_loader's jet-form branch never fires for
OBP-2/OBP-3.

## Why NOPs can't fix it

cond_pal cache invalidation depends on the timing of when the cond_pal
hash function reads FFD0 (vs when the test writes FFD0). The wrapper's
total runtime determines this phase. Adding/removing N×4T NOPs shifts
the phase but the SET of "correct phase" values is narrow — likely a
single specific value with ±5T tolerance.

NOP padding at 20-NOP / 35-NOP increments missed the window. A finer
search (1-NOP increments) would take ~50 iterations × 15 min each =
~12 hours. Not feasible in the autonomous loop.

The deeper architectural issue: cond_pal hash function must EXPLICITLY
include FFD0 in its hash inputs (not just rely on phase coincidence)
to be deterministically invalidated when FFD0 changes. That's a
deeper refactor of the colorizer routine.

## What this means for /goal "no orange in Sara"

The architectural ceiling is confirmed: 75% reduction via pure
relocation (iter 278e, committed) is the ONLY ship-clean improvement
available in the autonomous loop. Any logic addition to the wrapper
shifts CRAM-write phase relative to cond_pal cache invalidation,
breaking fresh-boot test expectations.

A genuine 100% fix requires either:
1. **Refactor cond_pal hash** to deterministically include FFD0/FFBF
   in the hash computation (so external forces always invalidate cache).
2. **Replace test mechanism** so external FFD0 force triggers cache
   invalidation via FFA9 write (changing the test, not the build).
3. **Scanline-precise NOP search** to find the exact phase-preserving
   NOP count (10-12 hour search at current iteration speed).

None are autonomous-loop achievable without user-explicit deep-RE
authorization or test-spec change approval.

## Build state after revert

Same as iter 278m (committed `4e9cbff`):
- iter 278e (75% Sara race reduction via 0x7F40 → 0x6B27 relocation)
- iter 278l (cursor tile 1-byte patch)
- 167 byte-verifier locks pass
- All 116 BG regression tests pass
- Fresh-boot all expectations pass
