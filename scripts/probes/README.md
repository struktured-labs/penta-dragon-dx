# Penta Dragon DX colorization verification harnesses

Each script self-verifies one of the v2.90-era regressions. Run them on
any ROM build before declaring a fix complete.

## Usage

```bash
# Title-screen white bug (CGB BG palette never loaded on menus)
python3 scripts/probes/verify_title_color.py rom/working/penta_dragon_dx_FIXED.gb

# Phantom sound (extra D887 transitions vs vanilla)
python3 scripts/probes/verify_phantom_d887.py rom/working/penta_dragon_dx_FIXED.gb --frames 600

# BG colorization (palette load + tile-attribute write during gameplay)
python3 scripts/probes/verify_gameplay_palette.py rom/working/penta_dragon_dx_FIXED.gb
```

Exit code 0 = PASS, exit 1 = FAIL (bug present), exit 2 = harness error.

## Reference results (commit a1b8fb4)

| ROM       | Title | Phantom (30s) | BG color | Notes |
|-----------|-------|---------------|----------|-------|
| vanilla   | n/a   | 12 (baseline) | FAIL     | no colorization |
| v287      | PASS  | 59 FAIL (5×)  | PASS     | trampoline causes phantom |
| v289      | PASS  | 59 FAIL (5×)  | FAIL@splash | same |
| v290      | FAIL  | 6  PASS       | PASS     | no trampoline; title gated by FFC1=1 |
| v294 (current FIXED.gb) | **PASS** | **2 PASS** | **PASS** | v290 + cond_pal-before-FFC1 + bg_sweep without menu skip |

## Not yet automated

**Scroll tearing**: hard to reproduce in mgba (mid-frame LCD timing
artifact). Verify visually on hardware/mgba. The root cause was the same
FFC1 gate that caused the title bug, so v2.94 should fix it too, but
visual confirmation is needed.

**Mini-boss colors wrong**: would need to script reaching a mini-boss
fight (DCB8=2 or DCB8=5) and dump OBJ palette + sprite-attribute table.
Probably the same root cause as BG colorization (palette/attrs not
written on certain scenes) — verify after promoting v2.94.
