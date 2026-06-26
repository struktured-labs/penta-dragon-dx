# iter 278q — mGBA setBreakpoint protect FFD0/FFC0 forces (attempted, reverted)

## Summary

After iter 278o's diagnosis that the iter 278n inline sara_stamp failure
was due to game's main-loop FFD0=0 write racing the test's external
FFD0=1 force, attempted to use mGBA Lua `setBreakpoint(addr, callback)`
to re-force FFD0=1 (and FFC0=N) immediately after each game-side write
to the same address.

## Implementation

Build side (same as iter 278n + 35 NOPs):
- Inline sara_stamp slot 0-3 inside hwoam_recolor (race-free shadow OAM read)
- Colorizer at slot 4-39 (HL=0xFE13, B=36)
- 35 NOPs to balance runtime delta

Test side:
- `emu:setBreakpoint(0x0BA1, fn)` — fires after game's LDH [FFD0],A at 0x0B9F
- `emu:setBreakpoint(0x7ACB / 0x7AE8 / 0x7B18, fn)` — fires after game's
  LDH [FFC0],A at the 3 bank1 write sites
- Callbacks re-force the test value when in test phase

## Result — Partial mechanism works, then crashes

First run (FFD0 protection only): 8 fails → 5 fails. OBP-2 jet form
LOADS correctly. setBreakpoint mechanism is SOUND for FFD0.

Second run (FFD0 + FFC0 protection): mGBA Lua appears to crash/timeout
on FFC0 setBreakpoints. The standalone FFC0/FFD0 tests produce NO
output files (no CRAM dump), suggesting mGBA process died before
writing results. The fresh-boot harness reports "[RETRY] had 1 failure(s)"
because output files are missing.

Hypothesis: mGBA Lua's setBreakpoint may not be stable when many
breakpoints fire many times per frame. The 3 FFC0 breakpoints might
each fire multiple times per frame, hitting some internal limit.

## Why this matters

The setBreakpoint mechanism for FFD0 alone showed the approach is
viable. The OBP-2 witch persistence (5 distinct iterations' root cause)
was eliminated. But extending to FFC0/FFBE/FFBF triggers mGBA Lua
issues.

A more robust implementation would require:
1. Single breakpoint that conditionally handles all state forces
2. Or memory-write hooks (if mGBA supports them) instead of PC breakpoints
3. Or game-side ROM patch to skip the overwrites during a test mode

All require deeper investigation than the autonomous loop can complete
in a single iteration.

## Build state after revert

Restored to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening (ship-clean, component 4 FIXED)
- iter 278l: cursor visible as 'A' character (component 3 FIXED)
- iter 278e: 75% Sara race reduction (components 1+2 partial)
- 170 byte-verifier locks pass
- All 116 BG regression tests pass
- Fresh-boot all expectations pass

## /goal final status

| Component | State | Commit |
|---|---|---|
| 1. White flicker | 75% reduction | iter 278e (`0c04648`) |
| 2. Orange Sara | 75% reduction | iter 278e (`0c04648`) |
| 3. Title cursor | FIXED — 'A' character at title menu | iter 278l (`fe596c2`) |
| 4. Stage intro colors | FIXED — letters render red | iter 278p (`2d94d67`) |

Components 3 and 4 fully shipped this session. Components 1 and 2
require deeper RE work (game-side FFD0 overwrite path patch, or
robust memory-write hook mechanism) that exceeds autonomous-loop
iteration scope.
