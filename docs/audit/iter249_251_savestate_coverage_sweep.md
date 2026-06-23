# iter 249-251 — Savestate coverage sweep

## Goal
Pivoted from iter 244-248's fruitless fix-attempts at the stage-entry
OAM transient. Switched to regression-suite expansion using
previously-untested savestates.

## Inventory at start of iter 249
- 105 .ss0 files in save_states_for_claude/
- 66 unique savestates referenced by 114 YAML tests
- **39 untested savestates** (37% gap)

## Approach
Built `scripts/diagnostics/probe_savestate_inspect.lua` — quick mGBA
probe that dumps D880, FFBE, FFBF, FFBA, FFC1 + first 12 OAM slot
attrs at f=68 and f=300. Bulk-probed all 39 untested savestates to
identify their game state and stability.

State distribution of untested savestates (sampled at f=70):
| D880 | Count | Notes |
|---|---|---|
| 0x00 | 5 | boot/post-load (no game) |
| 0x01 | 13 | cold-boot title-related |
| 0x02 | 7 | normal dungeon |
| 0x0A | 3 | mini-boss arena |
| 0x0B | 2 | transition |
| 0x18 | 1 | splash |
| 0x38, 0xBF | 2 | corrupted/fringe |

## Tests added (iter 249-251)

### iter 249: `sara_w_2_soldier`
- savestate: `level1_sara_w_2_soldier.ss0`
- D880=0x02 (dungeon), FFBE=0x00 (Sara W), FFBF=0x00
- Asserts: slot 0-3 = pal 2 (Sara W tile 0x24-0x27), slot 8-11 = pal 6 (soldier humanoid)
- Coverage gap: 2-soldier dungeon scene (distinct from existing
  `sara_w_pulsing_bg_with_enemies` which has different soldier-spawn state)
- 5/5 stable

### iter 250: `spider_miniboss_sara_w`
- savestate: `v2.26_level1_sara_w_spider_mini_boss.ss0`
- D880=0x0A (Spider arena), FFBE=0x00 (Sara W), FFBF=0x02 (Spider)
- Asserts: slot 0-3 = pal 2 (Sara W tile 0x2C-0x2F alt-anim), slot 4-11 = pal 7 (Spider)
- Coverage gap: existing `spider_miniboss_sara_d` covers Sara Dragon
  variant only. This adds Sara WITCH variant — catches FFBE=0 form
  handling regressions under FFBF=2 boss mode.
- Also exercises Sara's 0x2C-0x2F tile range (different from 0x20-0x27 used elsewhere).
- 5/5 stable

### iter 251: `orc_mid_transition`
- savestate: `level1_sara_w_orc.2.ss0`
- D880=0x0B (transition scene), FFBE=0x00, FFBF=0x00
- Asserts: slot 0-3 = pal 2 (Sara W tile 0x20-0x23), slot 4-7 = pal 5 (Orc tile 0x50-0x53)
- Coverage gap: existing `orc` test uses D880=0x02 (pure dungeon).
  This adds D880=0x0B coverage (mini-boss transition window where
  FFBF has cleared but D880 hasn't returned to dungeon).
- 5/5 stable

## Candidates considered + rejected

### `level1_sara_w_spike_hazard.ss0`
- D880=0xBF (out-of-spec scene byte)
- hwoam_recolor skips (gate is D880 < 0x0C), HW OAM stays at savestate-captured pal 1
- Fringe state, not representative of normal gameplay. Skipped.

### `level1_sara_w_spier_miniboss.ss0`
- D880=0x0B (transition), FFBF=0x02 (Spider mid-fight)
- Sara slot 0-3 show pal 1 (Sara DRAGON colors) despite FFBE=0 (Sara WITCH)
- Unusual palette mismatch — likely savestate captured mid-form-transition
- Needs deeper investigation before encoding as a test. Skipped.

### `sara_w_special_spiral_weapon_activated_level1_v_2.31.ss0`
- D880=0x38, FFBE=0x70, FFBF=0x06, FFBA=0x7E — all corrupt
- Likely produced by an old freeze bug or stack corruption
- Not usable. Skipped.

### `level1_stage_??_title_screen.ss0`
- D880=0x18 at f68, D880=0x09 at f300 — unstable transition
- Would need to sample at a SPECIFIC frame, hard to encode reliably. Skipped.

### `level1_sara_w_healpotion1_poison_cure_slow_cure.ss0`
- D880=0x02, Sara W slot 0-3 = pal 2 (tile 0x24-0x27)
- Coverage redundant with `sara_w_2_soldier` (also tile 0x24-0x27). Skipped.

### `level1_sara_w_square.ss0`
- D880=0x02, Sara W slot 0-3 = pal 2 (tile 0x20-0x23 in flipped order)
- Coverage redundant with `sara_w_alone`. Skipped (marginal value).

### autoplay_v7_* savestates
- D880=0x01 (cold-boot title state)
- No visible OAM. Not useful for color-regression tests.

## Net result
- 117 YAML tests (was 114) — 3 new
- 36 untested savestates remaining (was 39)
- Coverage expanded for: Sara W spider miniboss variant, Sara W soldier dungeon,
  orc in transition scene
- All additions verified 5/5 stable + pass hook validation

## Tools added
- `scripts/diagnostics/probe_savestate_inspect.lua` — reusable single-state inspector
- `tmp/untested_states.csv` — comprehensive state table for the 39 untested
  savestates (not checked in; regenerable via the batch probe loop in
  this audit's history)

## Notes for future expansion
The marginal value of additional savestate-based tests is diminishing.
The 36 remaining untested savestates split as:
- ~18 cold-boot title states (D880=0x00/0x01) — likely no useful OAM coverage
- ~5 dungeon states that duplicate existing tile-range coverage
- ~5 transition or fringe states (corrupted or unstable)
- ~8 require deeper investigation (e.g., secret-stage entry, the
  cluster of spier/spider variants)

Higher-value future expansion targets:
- Cross-stage BG palette histograms (per-stage CRAM verification at
  cold boot via fresh_boot.py extension)
- Animation-frame-specific tests (e.g., Sara teleport mid-animation)
- Stage-transition timing tests (catch DF1F-gate state corruption)
