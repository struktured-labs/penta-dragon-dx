# v3.01 production vs teleport — hook test baseline (iter 44, 2026-06-19)

A representative 20-test sample comparing pass/fail on `penta_dragon_dx_v301.gb`
vs `penta_dragon_dx_teleport.gb`. Run via
`scripts/diagnostics/compare_v301_vs_teleport.sh` (parallelized in-line for
iter 44 to keep runtime under 5 min).

## Sample results (20 tests)

|                                  | v3.01 | teleport |
|----------------------------------|:-----:|:--------:|
| **BG-table base-coverage**       |       |          |
| dungeon_uses_dungeon_table       |  ✓    |  ✓       |
| dungeon_table_spikes_metallic    |  ✓    |  ✓       |
| title_menu_uses_dungeon_table    |  ✓    |  ✓       |
| **Teleport-routine-only (expected v3.01 fail)** |       |          |
| banner_bg_table_palettes         |  ✗    |  ✓       |
| splash_bg_table_all_pal0         |  ✗    |  ✓       |
| lava_stage5_override             |  ✗    |  ✓       |
| shalamar_arena_content           |  ✗    |  ✓       |
| **Arena dispatch (built into v3.01)** |       |          |
| shalamar_arena_dispatch          |  ✓    |  ✓       |
| **Sara form / dungeon OBJ (slots 0-9)** |       |          |
| sara_w_alone                     |  ✓    |  ✓       |
| sara_d_alone                     |  ✓    |  ✓       |
| gargoyle_miniboss                |  ✓    |  ✓       |
| moth                             |  ✓    |  ✓       |
| mage                             |  ✓    |  ✓       |
| sara_w_item_pickup_scene         |  ✓    |  ✓       |
| sara_w_in_spider_miniboss_live   |  ✓    |  ✓       |
| **Slot-10+ OBJ (needs iter 31 hwoam_recolor)** |       |          |
| orc                              |  ✗    |  ✓       |
| soldier                          |  ✗    |  ✓       |
| catfish                          |  ✗    |  ✓       |
| spider_miniboss_sara_d           |  ✗    |  ✓       |
| hornets                          |  ✗    |  ✓       |

**v3.01: 11/20 pass (55%)** — teleport: 20/20 pass.

## What the 9 v3.01 failures tell us

Three categories:

1. **Teleport-routine-only (4 tests)** — banner_bg_table_palettes,
   splash_bg_table_all_pal0, lava_stage5_override, shalamar_arena_content.
   These tests verify per-scene overrides that live in
   `build_v301_teleport.py`'s teleport routine (banner_override,
   cutscene_override, lava_override, per-arena bg_tables). v3.01 production
   doesn't have any of this — by design, those features were added on top
   of v3.01 for the wip-color-sweep branch's exploratory work.

2. **Iter 31 slot-10+ OBJ (5 tests)** — orc, soldier, catfish,
   spider_miniboss_sara_d, hornets. These need `hwoam_recolor` (iter 31)
   to re-stamp HW OAM slots 10+ post-DMA. Iter 43 verified that a partial
   v3.01 backport (hwoam_recolor + STAT-IRQ stub) regresses Sara odd slots
   due to wrapper timing shift.

3. **No "regular bug" failures** — every v3.01 fail is one of the two
   classes above; nothing else.

## Implications for production deployment

- **v3.01 is correct for what it covers** — Sara form colorization, BG
  dispatch via scene_detect (when applied), dungeon-table base content,
  arena dispatch math, gargoyle/moth/mage slot-0-9 colorization. The
  shipped FIXED.gb is byte-identical to v3.01.

- **The "iter 31 win" only reaches MiSTer if** the teleport-stack feature
  set replaces v3.01 entirely (one-step gold-standard promotion) OR a
  zero-cycle-timing-shift backport is found (multi-iter). Iter 34 + iter
  43 confirmed both partial backports are infeasible.

- **Banner / splash / lava / per-arena bg_table fixes** are similarly
  teleport-only. Reaching MiSTer requires the same gold-standard
  promotion or sentence-by-sentence backport.

## Future work

- Full 65-test matrix (vs the 20-test sample here) — bash script has
  `set -e` removed for iter 44 but still slow sequentially. Could be
  parallelized via `xargs -P` to run in ~5 min total.
- Re-test on real CGB hardware (MiSTer) — the iter 43 finding of "Lua
  catches transient pal-4 read where LCD renders correctly" suggests
  some failures may be test-rig artifacts rather than real bugs.
