# Title-menu cursor fix attempts — consolidated summary

## The bug
User reported (2026-06-22) that the title-menu cursor is invisible.
Tile 0x73 is rendered as pal 0 (white) on the title screen, but the
pixels are also white (BG pal 0 indices 1-3 = various whites). So
the cursor blends into the white background.

Desired fix: render tile 0x73 as pal 1 (red, fully loaded on title)
so the cursor shows as a red triangle.

## All attempts

### iter 233 — global bg_table[0x73] = 1 (REVERTED)
Modified `build_v301_gdma._bg_table()` to set `table[0x73] = 1`.

Result: broke `stage6_decorative_pal5` test. Stage 6 BG uses tile
0x73 in lavender decorative walls. With pal 1 routing, lavender
pixels dropped 7822 → 5554.

Lesson: tile 0x73 is shared between title-cursor (needs pal 1) and
stage 6 walls (needs pal 5 lavender). A GLOBAL bg_table change
breaks one scene to fix the other. Need per-scene override.

### iter 234 — splash table `[0x2C:0x80] = 1` (REVERTED)
Modified the splash table (used at D880=0x18/0x1B/0x16) to route
letters to pal 1.

Result: broke `stage6_decorative_pal5` indirectly. WRAM 0xDA00 is
shared across scenes via savestate captures. If a savestate captures
the splash state, subsequent test runs see splash bytes leak into
non-splash tests.

Lesson: WRAM 0xDA00 is savestate-cached. Per-scene tables need to
RELOAD on scene transitions, not just inherit from savestate.

### iter 238 — title_override called per-frame (REVERTED)
12-byte routine at bank13:0x7FCD that writes `0xDA73 = 1` only when
D880=0x1C. Wired via CALL from the teleport routine.

Result: broke 14 regression tests due to ~27T per-frame CALL overhead.

Lesson: per-frame CALL additions to the teleport routine break
many tests via VBlank budget overrun.

### iter 240 / iter 263 — inline scene_detect post-copy (REVERTED, 4 failures identified)
Added 12 bytes to scene_detect's post-copy path. Cursor write fires
only when DF23=0x1C (title menu scene). Cost: +36T per scene CHANGE
on non-title scenes (skips the write but reads + compares + jumps).

Iter 263 captured the 4 failing tests:
- `orc` #0000B5: 22 → 8
- `sara_w_dual_enemies_with_arrows` #FF42A5: 60 → 44
- `spider_miniboss_sara_d` #00A500: 50 → 37
- `spiral_power_active` #0000B5: 44 → 0

Iter 264 follow-up split the 4 into:
- **Recovers** by f=300: orc (41), spiral_power_active (66)
- **Permanent**: sara_w_dual (0), spider_miniboss_sara_d (worsens to 25)

The "permanent" pair are CRAM-load timing failures: palette_loader's
write of OBP-2 pink-red and OBP-1 green misses its LCD-mode window
permanently with the +36T shift.

Lesson: ANY addition to scene_detect post-copy creates a +36T
shift on scene transitions. This breaks BOTH the OAM render
catch-up (recoverable) AND the CRAM palette load timing
(non-recoverable).

### iter 250's apparent fix — actually a duplicate (CLEANUP iter 255)
Iter 250 added `spider_miniboss_sara_w` thinking it was a new test.
Turned out to be a duplicate (existed since iter 32 with a different
savestate). Iter 255 removed the dup + added duplicate-detection
to the hook verifier.

Not a real cursor-fix attempt — just noise in the timeline.

## What works vs what doesn't

| Approach | Cost | Status |
|---|---|---|
| Global bg_table[0x73] = pal 1 | 0T | ✗ Breaks stage 6 (shared tile ID) |
| Splash table letter remap | 0T runtime | ✗ Breaks via WRAM 0xDA00 savestate cache leak |
| Per-frame CALL title_override | ~27T/frame | ✗ Breaks 14 tests via VBlank overrun |
| Inline scene_detect post-copy | ~36T per scene change | ✗ Breaks 4 tests (2 CRAM-permanent) |
| STAT IRQ stub extension | ~52T per HBlank × 144 lines | EXPECTED FAIL via iter-8 lesson |
| Title-menu native tile change | 0T | NOT TRIED (requires deep RE) |

## Current best-known approach

NONE of the attempted approaches work without breaking existing tests.

The remaining options require substantial work:

### Option A: title-menu native tile change
Find the title menu's tile-placement code path. Change which tile ID
it writes for the cursor (e.g., from 0x73 to 0x80 which is already
pal 1). No bg_table changes, no per-frame cost.

Risk: requires reverse-engineering the title menu's BG-write
sequence. Tile 0x73's font role may be elsewhere (the menu uses
0x73 for the cursor + other 0x70-range tiles for items).

### Option B: re-baseline the 4 failing tests
Update `orc`, `sara_w_dual_enemies_with_arrows`,
`spider_miniboss_sara_d`, and `spiral_power_active` to sample at
f=300 instead of f=68. orc + spiral recover by then. The two
"permanent" ones would still need either:
- Threshold reduction (loses regression sensitivity)
- Different sample frame (might not help either)
- Test removal (loses coverage)

### Option C: defer indefinitely
Accept the cursor bug as known-unfixed with documented constraints.
Five attempts have failed; the cost of further attempts likely
outweighs the benefit (cursor is annoying but not game-breaking).

## Recommendation

**Option C (defer)** for the autonomous loop. Future user-driven
attempts could pursue Option A if a clear title-menu code path
is identified.
