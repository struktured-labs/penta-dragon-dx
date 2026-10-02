# VBlank cost prototypes (issue #49)

Status: **measurement tooling only.** The shipping build is unchanged. No
production input (build scripts, patches, ROM) was modified, and the variant
ROMs live only under `tmp/perf-proto/` (untracked).

## Background

On release-lock candidate `792319cb…` (seed 80, equal-start Stage 7) the VBlank
handler `$06D1 → RETI $081D` costs a mean of about 6060 cycle units per frame,
versus 2684 for stock. That extra is about 2.3% of a 140448-unit frame, and it
explains the about 2.4% Stage-7 throughput gap versus stock. Top costs:
- OAM DMA `$FF80`: 938 (inherited; stock 1480)
- `$6E80` chain: 1162
- bank-19 LCDC/attr helper via the `$0847` trampoline: 319 average (888 per
  call as a no-op)
- joypad: 448
- `0824/73FC` bank wrapper: about 440
- D880 dispatch stubs: about 100–136 each

## Prototypes (`patch_vblank_fastpaths.py`, preimage-guarded, input must be 792319cb)

| id | change | ROM SHA-256 |
|----|--------|-------------|
| P1 | bank0 `$082E` CALL `$73FC` → CALL `$7464` (skip JP hop) | 1e3e5066… |
| P2 | bank13 `$76EE` fast path for pending-LCDC request C4&$60==$40 (skips no-op bank-19 trampoline round trip) | 7bf1045f… |
| P3 | bank13 `$6EF4` INC HL/DEC HL/JP → JP `$572C` | 62d6878d… |
| P4 | bank13 `$6F82` inline D880 guard before CALL `$6DA7` | 858cc4b6… |
| all | P1+P2+P3+P4 | 2f03f163… |

## Deterministic savings (instruction-level profile, `probe_prof.lua`, seed 80)

Raw handler means are confounded by how often OAM DMA runs: `$FF80` runs only
on frames where the main loop finished, and P3 ran DMA on 1483 frames versus
2607. So the deterministic code saving is measured on the non-OAM path.

| variant | raw handler mean | non-OAM path (base 4595) |
|---------|------------------|---------------------------|
| base | 6063 | 4595 |
| P1 | 6047 | −36 |
| P2 | 5816 | −230 |
| P3 | 5694 | −54 |
| P4 | 5905 | −134 |
| all | 5555 | **−422** (≈0.3% of a frame) |

## Pixel identity

- **Free-running** (`probe_pixhash.lua`, per-frame screen FNV, cold boot):
  this is not a valid oracle. The cycle savings shift title and attract
  timing; for example, the first diff is at title frame 34–35, and attract
  gameplay starts at 6409–6436 versus 6408. As a result, frames diverge even
  though rendering is unchanged.
  - idle 9000f, frames identical: P1 5008, P2 5464, P3 3038, P4 3789,
    all 2859
  - title-only 5000f: P2 5000/5000; the others are 1359–1689
- **Lockstep** (`lock/probe_lockstep.lua`): a base savestate is taken every 60
  frames over idle 9000f and scripted game 5000f. Each state is replayed for 8
  frames in every variant, and the screen and OAM hashes are compared.
  Results: see below.

The harness check passes: record versus replay on base gives 0 screen and 0
OAM diffs (idle 1192 frames over 149 states, game 664 frames over 83 states).

| variant | idle screen / OAM diffs (of 1192) | game screen / OAM diffs (of 664) |
|---------|-----------------------------------|----------------------------------|
| P1 | 2 / 3 | 0 / 3 |
| P2 | 0 / 1 | 2 / 6 |
| P3 | 2 / 3 | 0 / 3 |
| P4 | 5 / 5 | 7 / 9 |
| all | 5 / 7 | 15 / 18 |

For every variant, the first frame after each loaded state is identical to
base. All diffs fall at window offset ≥2, mostly 5–8. About 40% of the
differing screens equal base's adjacent frame. That pattern fits cycle-timing
divergence: the trimmed VBlank lets an update land one frame differently. It
does not look like a rendering change. Strict identity is still not proven
beyond the first frame (`lock/ls_offsets.py`).

Note: an earlier lockstep attempt saved states with `saveStateFile(path, 2)`,
which writes all-zero files, so every load failed. Those `rep-*`/`st-*` outputs
are invalid. The fixed probe uses default flags (`st2-*`/`rep2-*`).

## Stage-7 v3 gate (equal-start, 9 seeds, floor 0.97)

| variant | ratio | usable seeds | status |
|---------|-------|--------------|--------|
| base (suite rl-suite-20261002-01) | 0.9817 | 9/9 | PASS |
| base (rerun, gate2 harness) | 0.9817 | 9/9 | PASS (bit-identical per seed) |
| P1 | 0.9749 | 9/9 | PASS |
| P2 | 0.9778 | 9/9 | PASS |
| P3 | 0.9691 | 9/9 | FAIL (below 0.97; settling half-cycle 26 > 24) |
| P4 | 0.9804 | 6/9 | FAIL (min 7 usable seeds) |
| all | 0.9753 | 9/9 | PASS |

**Noise:** rerunning the same ROM is fully deterministic. The base rerun
reproduces the suite run exactly, combined and per seed (0.981708…), so
same-ROM noise is 0. However, every variant runs faster in VBlank, yet the
variants land 0.9691–0.9804, all at or below base. A few hundred cycles of
timing shift sends enemy/contact evolution (and the usable leg/seed set) down a
different path, which moves the combined ratio by about ±1%. That swamps the
expected +0.3% gain. The gate can only detect throughput changes of a few
percent, and it does not reward these trims.

## Conclusion

- Deterministic VBlank savings from all four trims together come to 422 of the
  4595 non-OAM units per frame, about 0.3% of a frame. The gap versus stock is
  about 3300 units/frame (about 2.3%). These trims recover roughly 13% of that
  gap, and only in this best case.
- The Stage-7 v3 gate shows no measurable throughput gain. Timing-perturbation
  sensitivity (about ±1%) dominates, and two individual variants fail the gate.
- The rest of the excess is real DX colorization work: the `$6E80` chain
  (~1160) and the bank-13 per-frame palette/attr dispatch. Removing it means
  cutting or amortizing that work, which is a design change, not peephole
  trimming.
- **Recommendation:** do not ship these trims for performance. Keep this
  tooling for any future colorization-cost work. Accept the ~2.4% Stage-7 gap
  as inherent, or schedule a larger project to amortize the `$6E80` and
  dispatch work across frames.

## Reproduce

All scripts run from the repo root and write their outputs under `tmp/perf-proto/`:

    python3 scripts/probes/perf_vblank/patch_vblank_fastpaths.py <792319cb.gb> tmp/perf-proto/all/penta_dragon_dx_FIXED.gb [--only P1]
    bash scripts/probes/perf_vblank/run_all.sh      # free-running pix + run_perf.sh (profiles + Stage-7 v3 gates)
    bash scripts/probes/perf_vblank/lock/run_lock2.sh  # lockstep record/replay (fixed probe) + base gate rerun
    python3 scripts/probes/perf_vblank/gate_summary.py tmp/perf-proto/gm-*/logs/gameplay_movement_stress.log

`gate2.py` re-runs one gate from the `tmp/rl-suite-20261002-01` manifest against
another ROM. The env vars LD_LIBRARY_PATH=tmp/mgba-cgb-latches-r454/build and
.venv/bin first on PATH must be set, as for the suite.
