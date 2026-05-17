# Penta Dragon DX colorization verification harnesses

Each script self-verifies one regression class from the v2.85-v3.00 arc.
Run all five before declaring a build good — per CLAUDE.md, the user's
eyes are the final judge, but no-probe regressions waste their time.

## The 5 probes

```bash
# Title-screen white bug (CGB BG palette never loaded on menus)
python3 scripts/probes/verify_title_color.py rom/working/penta_dragon_dx_FIXED.gb

# Phantom sound (extra D887 transitions vs vanilla baseline)
python3 scripts/probes/verify_phantom_d887.py rom/working/penta_dragon_dx_FIXED.gb --frames 600

# BG colorization (palette load + tile-attribute write during gameplay)
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_FIXED.gb

# Mini-boss OBJ colorization (forces DCB8=2 by default — pass --natural to
# exercise the spawn state machine instead)
python3 scripts/probes/verify_miniboss_color.py rom/working/penta_dragon_dx_FIXED.gb

# Scroll-tearing (palette + attr stability during sustained scroll)
python3 scripts/probes/verify_scroll_tearing.py rom/working/penta_dragon_dx_FIXED.gb
```

Exit code 0 = PASS, exit 1 = FAIL (bug present), exit 2 = harness error.

## Reference results (v3.00, commit 2c08deb)

| ROM       | Title | Phantom (10s) | BG color | Mini-boss | Scroll |
|-----------|-------|---------------|----------|-----------|--------|
| vanilla   | n/a   | ~12 (baseline)| FAIL     | n/a       | n/a (baseline) |
| v287      | PASS  | ~59 (FAIL 5×) | PASS     | PASS      | unknown |
| v289      | PASS  | ~59 (FAIL 5×) | FAIL@splash | unknown | unknown |
| v290      | FAIL  | ~6 (PASS)     | PASS     | unknown   | unknown |
| v294      | PASS  | ~2 (PASS)     | PASS     | unknown   | unknown |
| **v3.00** | **PASS** | **~4 (PASS)** | **PASS** | **PASS** | **PASS** |

Typical v3.00 gameplay-palette attr histogram (level 1 entry, post-settle):
`pal0~900, pal1~38, pal5~2, pal6~10-50, pal7~80`. The
`--pal6-min`/`--pal6-max`/`--pal1-min`/`--pal1-max` flags on
`verify_gameplay_palette.py` enforce envelopes around these values so a
future bg_table refactor that mis-routes a palette is caught even if
≥2 indices are still in use.

## Per-probe notes

**verify_phantom_d887.py** caches the vanilla baseline on disk
(`.phantom_d887_baseline.json`, keyed by ROM mtime+size). Use
`--rebaseline` to force a fresh measurement.

**verify_scroll_tearing.py** samples *both* BG palette RAM and the
VBK=1 attr histogram every frame during a 4-second scroll window. The
PASS/FAIL gate currently only checks palette stability (matches the
pre-v3.00 probe behavior); the attr-stability metric is logged for
diagnosis until a baseline envelope is established.

**verify_miniboss_color.py** force-writes `DCB8=2` at gameplay+300
frames by default for deterministic timing. Pass `--natural` to let
the game's section counter advance organically — slower (~12000 frame
budget), but catches regressions in the spawn state machine that the
forced path would mask.

## Lua probes (not auto-verified)

`*.lua` files in this directory are called by the Python probes via
mgba's `--script`. They are not standalone gates.
