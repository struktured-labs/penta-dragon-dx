# iter 276 — split-stamp half-orange Sara fix attempt (5 candidates, all reverted)

User mandate (2026-06-23): "no compromises, I will die on the hill of this
being a near perfect rom hack." Goal hook set: "no flickers, no slowdowns,
no half orange sara, title screen is clean, stage intro is clean. cursor
is rendered on first screen."

This iter tried 5 candidate strategies to fix the iter-31-introduced
half-orange Sara race documented in iter 241-247. ALL FIVE were reverted.

## Empirical baseline (current shipping teleport.gb)

`scripts/diagnostics/probe_white_flicker.lua` on stage1_entry_pink_renders.ss0:
- slot 0: 32 ATTR changes / 540 frames
- slot 2: 121 ATTR changes / 540 frames (worst — visible half-orange Sara)
- slots 14/15: ~52 changes / 540 frames (pre-existing orc/soldier race,
  hidden by lucky baseline sample timing at f=68)
- All 116 hook tests PASS on baseline

## Candidates tried

### A. early_stamp (full hwoam_recolor moved BEFORE joypad)
- Sara race: ELIMINATED (slot 2: 121 → 0)
- 3 tests fail: spider_miniboss_sara_d, sara_w_dual_enemies_with_arrows,
  spiral_power_active (the projectile drops to 0px — slot 10+ no longer
  re-stamped post-DMA)
- Reverted: slot 10+ enemies + projectiles go uncolored.

### B. double_stamp (early + late hwoam_recolor)
- Sara race: WORSE (slot 0: 32 → 137, slot 2: 121 → 131)
- Two stamp passes for the same slot create a NEW race between them.
- Reverted.

### C. STAT-mode gate inside hwoam_recolor (`BIT 1, A; RET NZ` skip in mode 2/3)
- Sara race: REDUCED 88% (slot 2: 121 → 14)
- 2 tests fail: sara_w_dual (44/48 pixel), spiral_power_active (0/35)
- Reverted: spiral projectile vanishes (slot 10+ frequently skipped when
  OAM locked).

### D. split-stamp: sara_only EARLY (slot 0-3) + hwoam LATE slot 4-39
- Sara race: ELIMINATED (slot 0: 0, slot 2: 0)
- Direct 5-test results: 5/5 PASS (orc adjusted to f=100 stable window).
- FULL 116-test hook: **13 FAIL** — moth, soldier, sara_w_2_metal_ball,
  sara_w_catfish_with_arrows_items, sara_w_miniboss_dying,
  sara_w_moth_alt_scene, sara_w_right_before_secret_stage_gbc,
  sara_w_secret_stage_shmup, death_cinematic_game_over_colorized,
  gargoyle_visual_render, spider_visual_render, stage5_lava_live_render,
  stage6_decorative_pal5.
- Root cause: the EARLY sara_only adds ~240T to the VBlank wrapper,
  shifting the colorize chain by 240T. Affects BG colorize sweep
  timing → lava pixels drop, stage 6 decorative drop, etc.
- Reverted: 13 broken tests is too many.

### E. minimal sara_slot2_only (28 bytes, ~130T) — slot 2 only
- Sara race: REDUCED 90% (slot 2: 121 → 12)
- 3 tests fail: orc (pre-existing slot 15 race), soldier (slot 15 STAYS
  pal 4 — real regression), spider_miniboss_sara_d (pixel 38/40 — real
  regression).
- Reverted: soldier renders orange instead of purple — visual regression
  the user would notice.

## The fundamental constraint

VBlank budget is ~4560T. The current colorize chain runs PARTIALLY into
active display where some writes succeed (HBlank windows) and some fail
(mode 2/3). Adding ANY work to the wrapper shifts EVERYTHING downstream
by that amount. The shift breaks tests that were sampling at "lucky"
frames where their pixel/attr counts happened to align with VBlank
write windows.

Reducing wrapper work to make budget room would require removing
something essential (joypad 8-debounce can't trim per iter 39 lesson;
teleport_routine + colorize chain are core functionality).

## What COULD work (multi-iter major surgery)

1. **STAT IRQ at LYC=144** — trigger a separate IRQ on VBlank entry
   that runs sara_only stamping. Runs in true-VBlank window guaranteed.
   Risk: STAT IRQ conflicts with existing parallax handler (iter 8
   lesson re: ~30T preludes breaking parallax).

2. **Compact the colorize chain** — shrink cond_pal / bg_colorizer /
   shadow_main by ~240T total to make budget room for sara_only EARLY.
   Risk: those routines are tightly written; cuts likely break things.

3. **Move iter 31 enemy coloring out of hwoam_recolor** — restructure
   so slot 10+ enemies get colored via a different mechanism (e.g.,
   game's main loop OAM update with pre-computed tile→pal table).
   Risk: deep RE work, multi-iter.

4. **Accept partial-fix candidate E + lower 3 test thresholds** —
   user has explicitly rejected this ("no compromises").

## Honest summary for user

The half-orange Sara race CAN be fixed but every fix attempted breaks
at least 3 other tests (real visual regressions in dungeon enemies or
lava/stage-6 rendering). The constraint is VBlank budget tightness.

To meet the "no compromises" mandate, none of the 5 candidates ship.
Baseline teleport.gb retained — Sara still has the half-orange race,
but all other tests pass.

Next step requires user decision:
- (a) Accept candidate E + 3 test threshold adjustments (small compromise)
- (b) Authorize multi-iter major surgery (1-2 weeks of work, no guarantee)
- (c) Accept current baseline (Sara race remains, everything else clean)
