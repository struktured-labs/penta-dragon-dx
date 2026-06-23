# iter 263 — iter 240 cursor fix: 4 failing tests identified

## Context
Iter 240 attempted to fix the title-menu cursor visibility bug by adding
12 inline bytes to scene_detect's post-copy path: after the dungeon
table copies to WRAM 0xDA00, if DF23=0x1C (title menu), overwrite
0xDA73 = 1 (pal 1 red) so the cursor tile renders visibly.

The hook reported "4 regression tests failed" but the .fail files were
auto-cleared before the test names could be captured. Iter 263 re-ran
the same fix outside the hook (full xargs sweep with persistent logs)
to identify which 4 tests fail.

## The 4 failing tests

All 4 are PIXEL-COUNT failures (timing shift drops render counts below
threshold). All other 116 tests pass.

| Test | Color | Threshold | Iter 263 count | Baseline | Loss |
|---|---|---|---|---|---|
| `orc` | #0000B5 (dark-blue body) | 16 | 8 | 22 | 64% |
| `sara_w_dual_enemies_with_arrows` | #FF42A5 (Sara W pink-red) | 48 | 44 | 60 | 27% |
| `spider_miniboss_sara_d` | #00A500 (Sara D green) | 40 | 37 | 50 | 26% |
| `spiral_power_active` | #0000B5 (spiral dark-blue) | 35 | 0 | 44 | **100%** |

## Root cause

The cursor fix adds 12 bytes to scene_detect (post-copy):
```
LD A, [DF23]   ; 16T
CP 0x1C         ; 8T
JR NZ, +5       ; 12T (taken on non-title)
LD A, 1         ; (unreached on non-title)
LD [0xDA73], A  ; (unreached on non-title)
RET             ; 16T
```

On non-title scenes (the test scenarios): +52T per scene CHANGE.
On title scenes: +52T per scene CHANGE (rare).

The savestate-load triggers ONE scene change at f=0 (from uninit to
captured scene). That +52T delay shifts when colorize+DMA completes
relative to the test runner's sample frames (f=60-68). Some sprite
pixels haven't fully rendered by sample time → counts drop.

`spiral_power_active` dropping to 0 is the most severe: the dark-blue
projectile sprite isn't being drawn AT ALL at the sample frame. That
suggests the timing shift caused the projectile's OAM update to
miss its VBlank write window.

## Why the simple lower-thresholds fix doesn't work

For the first 3 tests, lowering thresholds would lose regression
sensitivity but keep coverage. For `spiral_power_active` though, dropping
the threshold from 35 to 0 removes ALL regression coverage on the
spiral-power projectile — that's basically deleting the test.

## Reverted

Iter 263's scene_detect change has been reverted. The cursor fix is
unworkable in its current form.

## Constraints for any future cursor fix attempt

1. Must NOT shift scene_detect's post-copy T-cost (any addition there
   causes timing failures on the 4 listed tests).
2. The fix needs to happen OUTSIDE the per-VBlank colorize chain.
   Options:
   - Modify the dungeon table ROM source so 0xDA73 is set in the
     table itself. Iter 233 tried this — broke stage 6 because tile
     0x73 is used there too. Requires per-scene table strategy.
   - Add a separate routine called from the title-menu's OWN code
     path (not the VBlank colorize chain). This requires
     reverse-engineering where the title-menu's render loop is.
   - Add the cursor write to the COLD-BOOT initialization only.
     But cold-boot copy fires once and 0xDA73 stays at dungeon value
     after subsequent scene transitions, so this wouldn't survive.

## Net result

- 0 ROM changes committed (cursor still missing, but no regressions)
- 4 specific test failure modes documented for next attempt
- Empirical evidence that scene_detect post-copy timing is hard to
  modify without breaking pixel-count thresholds

The cursor bug remains UNRESOLVED but now has measurable constraints.
