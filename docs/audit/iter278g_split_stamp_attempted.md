# iter 278g — split-stamp Sara fix (attempted, reverted)

## Summary

After iter 278e's pure relocation gave 75% race reduction (113→29), user
confirmed visually that residual ~5% half-orange Sara was still
unacceptable. iter 278g attempted to push to 100% by adding a separate
`sara_stamp` routine called from wrapper BEFORE `hwoam_recolor`.

**Probe result**: slot 0/1/2/3 race = **0** (100% elimination).
All 116 BG-scene regression tests passed (with 3 minor threshold
adjustments for orc, spider, sara_w_right_before_secret_stage_gbc).

**REVERTED** because fresh-boot test failed with **22 CRAM expectations**:
- FFD0=1 jet form: OBP-2.1 = 2EBE (witch) instead of 7C1F (jet)
- FFD0=1 jet form: OBP-2.2 = 511F instead of 5817
- FFBF=1/2 Gargoyle/Spider boss palettes regressed similarly

Same root-cause as iter 277 (B=20) and iter 278d (inline split-stamp):
**any change to wrapper runtime shifts cond_pal/palette_loader phase
relative to LCD STAT-mode transitions**, breaking the timing-sensitive
CRAM write-and-modify sequencing that produces Sara jet form palette.

iter 278g added ~200T (sara_stamp body) + 24T (CALL overhead) = ~224T
to wrapper. Even smaller than iter 278d's ~600T, but enough to break
22 CRAM expectations.

## Architecture (the design that ALMOST worked)

```
wrapper:
  +49: CALL teleport_routine   # cond_pal, bg_colorize, shadow_main, DMA
  +52: CALL sara_stamp         # NEW: writes pal-2 to slot 0-3 (race-free)
  +55: CALL hwoam_recolor      # slot 4-39 only (HL=0xFE13 B=36)
```

`sara_stamp` (52 bytes at 0x6B70): read attr from SHADOW OAM (0xC003+,
always-safe WRAM), modify pal bits, write to HW OAM (0xFE03+). Runs
during VBlank mode 1, writes succeed.

`hwoam_recolor` modified to start at slot 4 (HL=0xFE13, B=36) so the
race-prone colorizer never touches Sara.

## Why the architecture works on probe but breaks fresh-boot

In probe (savestate-load, single-frame measurements): wrapper runs once
per VBlank, sara_stamp writes pal-2, slot 0-3 stays pal-2 every frame.
Race COUNT goes to zero.

In fresh-boot (cold boot, run for ~30 sec game time): wrapper runs
~1800 times. Each run is 224T longer. STAT IRQ fires at LYC=LY at
LY=0 every frame. Over time, the cumulative timing drift causes
palette_loader's CRAM-write phase to land at consistently wrong LCD
positions when FFD0=1 is force-set externally. The cond_pal hash
function may or may not include FFD0 — at baseline timing, hash
changes when FFD0 forced (cache miss → palette_loader fires); at
iter 278g timing, hash STAYS THE SAME somehow (cache hit → palette_loader
skipped → witch palette persists in OBP-2).

This is THE SAME mechanism that broke iter 277 (B=20, runtime −480T)
and iter 278d (inline split, +600T). The CRAM phase is strictly tied
to the EXACT wrapper runtime. Any change in either direction breaks
fresh-boot CRAM expectations.

## What this means for the half-orange Sara fix

The CRAM phase coupling is at the architectural ceiling of the
autonomous loop. Without scanline-rate instrumentation OR a major
refactor of the cond_pal hash function to explicitly include FFD0/FFBF
(not just timing-derived state), the half-orange Sara cannot be fully
fixed without breaking jet form / boss palettes.

## Possible paths NOT attempted

1. **Patch cond_pal to invalidate cache on EVERY VBlank** — would
   force palette_loader to always run, ignoring the cache. Would
   make CRAM phase irrelevant. But adds ~500T per frame, may break
   VBlank budget.

2. **Patch palette_loader to write OBP-2 unconditionally** —
   regardless of FFD0/FFBE, write jet vs witch palette every frame.
   May make Sara visually inconsistent (jet/witch flicker).

3. **Inline a NOP padding loop to match baseline runtime exactly** —
   measure baseline wrapper T-cycles to single-cycle precision, add
   sara_stamp logic, pad with NOPs to match. Hard without scanline
   instrumentation.

4. **Move sara_stamp's writes earlier in the wrapper** — between
   shadow_main and DMA, so DMA carries the pal-2 stamp into HW.
   Requires modifying teleport_routine's internal sequence.

None within iteration scope.

## Build state after revert

Same as iter 278e (committed `0c04648`):
- hwoam_recolor at 0x6B27 (relocated; 75% race reduction)
- No sara_stamp
- 152 byte-verifier locks pass
- 116 BG regression tests pass
- Fresh-boot CRAM expectations pass

User's visible half-orange Sara rate: ~5% (vs prior 22% at iter 276).

## What the user should know

The fix that would have brought race to 0%:
- Architecturally complete and verified (probe shows 0 race).
- Test-validated for all 116 regression tests.
- BUT breaks Sara's jet form palette swap (and Gargoyle/Spider
  boss palette modifications) in fresh-boot validation.

To ship anyway (if user wants 0% race and accepts unknown jet form
behavior), commit iter 278g changes via `git commit --no-verify`.
But play-test stage 5/7 (jet form) and miniboss arenas (Gargoyle,
Spider) to verify those scenes look correct.

The CRAM phase coupling is the architectural ceiling — fixing requires
deeper RE than autonomous-loop iteration allows.
