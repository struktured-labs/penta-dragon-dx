# Color Regression Tests

Snapshot of the regression suite as of iter 137 (2026-06-21).

## Quick stats
- **114 tests** across 70 with pixel guards, 45 with bg_table assertions, 48 with OAM assertions
- **110 pixel guards** total, all clustered at 1.22-1.36x ratio (max sensitivity per iter 137 sweep)
- Run via `scripts/hooks/pre-commit` (parallel, ~60-90s with up to 12 workers)
- Single-test invocation: `uv run python scripts/run_color_regression.py --rom rom/working/penta_dragon_dx_teleport.gb --test <name>`

## Test categories

| Category | Count | Purpose |
|----------|-------|---------|
| BG dispatch (`*_dispatch`, `*_uses_dungeon_table`, etc.) | 21 | Scene_detect routes D880 → correct bg_table |
| BG content (`*_arena_content`, `dungeon_table_*`) | 14 | bg_table tile→pal mappings inside the table |
| Lava override | 5 | `build_lava_override` fires for FFBA=4/6 only |
| Native scene captures | 13 | Real captured state (not framework `force_d880`) |
| Death cinematic (FFBA 1-6 + dispatch) | 7 | Multi-FFBA death CRAM verification |
| OBJ tests (Sara/enemies) | 35+ | OAM slot palette assertions per scene |
| Visual render (`*_visual_render`) | 4 | Pixel guards on mini-boss / SHMUP scenes |
| Title menu / splash | 5 | Title state CRAM verification |

## Key insights for future iters

### Pixel-guard ratio
All guards uniformly 1.22-1.36x of observed. A regression dropping a color count by 20-25% will fire a test immediately. Don't add new tests with looser ratios.

### Native-savestate vs force_d880
`force_d880` writes to RAM but doesn't redraw — same screenshot per savestate. `native` captures (via emu:saveStateFile flag 0x01 PNG, per iter 110) exercise the cold-boot DA00 copy with the real state byte captured in the save.

### Death-cycle pattern (iter 114)
Level-select with no save data → Sara dies repeatedly → natural D880 cycle 0x18→0x08→0x17→0x01→0x00→0x18. Use this to capture death/splash/banner savestates without needing in-game play.

### iter 83 NOT CAUGHT adversarial gaps (still partial)
- OBP-3/4/5 ROM-source corruption: not caught by existing tests (savestate CRAM persists)
- Need either: fresh-boot probe extension OR enemy-rendering scenes with FFBD-cycle force_load
- BG-pal-2 was added iter 118 (stage3_purple_pal2 closes that one)

### Filed for future
- Live-gameplay lava ROOM render (stage 7 entry doesn't include tiles 0x19/0x1A — needs path-finding)
- v3.01 hwoam_recolor backport (timing regression, needs MiSTer hardware verification)
- D880=0x15 intro cutscene capture (OPENING START menu route appears to dispatch through GAME START stack, not separate D880=0x15)

## Pre-commit hook details

`scripts/hooks/pre-commit` runs:
1. **YAML integrity** — every test in hook list has YAML entry
2. **iter-31/39/40 ROM byte checks** (11 checks) — teleport + v3.01 specific byte values
3. **Parallel regression run** — 114 tests with up to 12 workers
4. **Fresh-boot end-to-end test** — `scripts/diagnostics/test_fresh_boot.py` (10 guards across 4 phases)

If any fail, commit is blocked. Override via `git commit --no-verify` only when necessary; the hook is the canonical safety net.

## Adding new tests

```yaml
- name: "your_test_name"
  savestate: "level1_sara_w_*.ss0"  # path under save_states_for_claude/
  description: "What this catches + why"
  expected_boss_flag: 0    # or check_boss_flag: false to skip
  expectations:            # OAM slot/tile_range checks (optional)
    - slots: [0, 1, 2, 3]
      palette: 2
  bg_table_expectations:   # WRAM 0xDA00 checks (optional)
    - tile_range: [0x80, 0x80]
      palette: 1
  pixel_expectations:      # rendered screenshot checks (optional)
    - color: "FF42A5"
      min_pixels: 18       # ~80% of observed; verify 5/5 stable first
      description: "..."
```

Then add the test name to `scripts/hooks/pre-commit` TESTS array. Verify single-test passes before committing.
