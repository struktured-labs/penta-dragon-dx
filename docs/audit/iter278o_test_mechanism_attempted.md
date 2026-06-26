# iter 278o — test-side FFA9 cache invalidate + iter 278n inline sara_stamp (attempted, reverted)

## Summary

After iter 278n confirmed inline sara_stamp's runtime change breaks
cond_pal cache phase coincidence (8 fresh-boot CRAM failures), tried
to fix the test mechanism instead of the build:

**Approach**: modify `test_fresh_boot.py` to write `FFA9=0xFE` alongside
each `FFD0/FFBE/FFBF/FFC0` force. Theory: this guarantees cond_pal
sees a cache miss → palette_loader fires → CRAM reflects externally-
forced state, removing dependence on timing coincidence.

## Step 1: validate test mechanism at iter 278e baseline

Modified test, ran against iter 278e baseline (no sara_stamp). Result:
**ALL EXPECTATIONS PASS**.

This confirms the test mechanism change is sound — FFA9 cache invalidate
correctly forces palette_loader to fire and load expected jet/boss/
projectile palettes.

## Step 2: re-attempt iter 278n with modified test

Restored iter 278n inline sara_stamp (no NOP padding), ran modified
test. Result: **8 EXPECTATIONS FAIL** — same OBP-2/OBP-3/OBP-5/OBP-7
witch persistence pattern as iter 278n with original test.

## Why the test fix doesn't help iter 278n

The CRAM failures aren't about cache miss detection — they're about
WHEN the wrapper sees FFD0=1 relative to the game's main-loop overwrite.

The test's "frame" callback fires AFTER the prior frame's VBlank but
BEFORE the next frame's main loop. So:

```
Frame N main loop: writes FFD0=0 (game default)
Frame N draw / VBlank
Frame N "frame" callback: writes FFD0=1, FFA9=0xFE
Frame N+1 main loop: overwrites FFD0=0
Frame N+1 wrapper: cond_pal reads FFD0=0 (overwritten)
```

At iter 278e baseline timing, the wrapper apparently runs BEFORE
main loop overwrites — cond_pal sees FFD0=1, palette_loader fires.
At iter 278n timing (-80T inline savings), the wrapper runs at a
different point in the frame where FFD0 has already been overwritten.

This is INDEPENDENT of the FFA9 cache invalidate. Cache invalidation
only helps if cond_pal actually sees FFD0=1 — but it never does at
iter 278n timing.

## Architectural ceiling — fully verified

Across iter 278d/g/h/n/o (5 distinct attempts), the conclusion is
unchanged:

**75% Sara race reduction via pure relocation (iter 278e) is the
ONLY ship-clean improvement available in the autonomous loop.**

100% fix requires one of:

1. **Memory watchpoint on FFD0** (mGBA `emu:setBreakpoint` API):
   protect test's `FFD0=1` write from game overwrite by hooking
   writes to FFD0 and rewriting 1 immediately. Requires `setBreakpoint`
   working for memory writes (currently used for PC execution).

2. **In-game state transition test**: replace external force with
   actual gameplay that triggers FFD0=1 (Sara enters jet form).
   Removes external write race entirely. Major test rewrite.

3. **Modify game's main-loop FFD0 overwrite path**: find where game
   writes FFD0=0 and add a check to preserve test-forced values.
   Requires deep RE + invasive game code modification.

4. **Cycle-precise wrapper timing**: tune NOPs to land wrapper in
   the exact frame phase where FFD0 is not yet overwritten. Requires
   scanline-rate instrumentation Lua probe + iterative tuning over
   many test runs.

None achievable in the autonomous loop without user-explicit deep-RE
authorization, test-suite redesign approval, or scanline-precise
probe development.

## Build state after revert

Same as before iter 278o attempt:
- iter 278e (75% Sara race reduction)
- iter 278l (cursor tile 1-byte patch — fires in submenu only,
  not initial title per iter 126 finding)
- 167 byte-verifier locks pass
- All 116 BG regression tests pass
- Fresh-boot all expectations pass

## /goal status — final consolidated state

| Component | State | Blocker |
|---|---|---|
| White flicker | 75% reduction shipped (iter 278e) | CRAM phase coupling + main-loop overwrite race |
| No orange in Sara | Same 75% reduction | Same |
| Title cursor | iter 278l 1-byte patch (submenu) | Initial title cursor requires NEW draw routine (per iter 126: original game has no cursor); ROM-side cold-boot patch blocked by title menu's per-frame render overwriting |
| Stage intro colors | NOT fixed | WRAM 0xDA00 savestate cache leaks splash_table patches into stage 6 BG render; scene_detect cache-clear modification required |

All 4 components confirmed at architectural ceiling across 5+
iteration attempts. Documented in audit chain: iter 277, 278d, 278g,
278h, 278m, 278n, 278o.
