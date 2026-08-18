# FINDINGS 2026-08-18 — the parked-share denominator artifact

**TL;DR.** Every `iterations-per-scene-frame` speed rate measured on a
banked-writer candidate was inflated in the DX-faster direction by the share
of frames the candidate parked SVBK≠0/1 at frame-callback time, because the
probes' banked-writer guard returned **before** the `scene_frames` increment.
Ted's "+22.46% faster" and the Shalamar cache lineage's "-1.74%, gate
passed" were both this artifact. The fix (sticky scene accounting,
`0b24b03`) is validated by a bit-exact null control and by cross-instrument
agreement. The honest numbers: **Ted ≈ +1.0–1.7% (green)**; **Shalamar
v60c ≈ +12% over OG (gate missed by ~10 points)**. Pre-cache "arenas run
faster" receipts audit clean and stand.

## The mechanism

Both boss speed probes' frame callbacks contained:

```lua
local svbk = emu:read8(0xFF70) & 0x07
if BANKED_WRITER and svbk ~= 0 and svbk ~= 1 then return end   -- guard
...
scene_frames = scene_frames + 1                                 -- never reached
```

The guard exists because D880 (banked WRAM) is unreadable while a candidate
parks SVBK on 2/3 across a frame boundary. But the early return also skipped
the `scene_frames` increment, so parked frames vanished from the rate
denominator while the loop-head breakpoint (unaffected) kept counting
iterations. Rate inflation factor: `1/(1-S)` where
`S = 1 - dx_scene_frames/og_scene_frames` (OG is never banked, so its
denominator is full).

Measured parked shares: Ted compiler candidates (v51+) park **~18-20%** of
Ted-arena frames; the Shalamar cache lineage parks **4-13%** from v56c
onward (the fusion moved work into SVBK-parked frame boundaries — v53-v55b
park 0%).

The **fix** (`0b24b03`, both probes + the cadence probe for hygiene): when
the guard fires, carry the last known in-scene state and keep counting
`scene_frames`; report `parked_frames` in every completion record.
`verify_boss_publication_cadence.py` never read `scene_frames` (its metric
is copy-to-copy frame gaps on raw indices), so **cadence gates were never
contaminated**.

## Audit formula for any historical receipt

```
S = 1 - dx_scene_frames / og_scene_frames      # per receipt
S > ~1%  ->  the published rate is invalid; re-derive on the common
             denominator: corrected = og_hits/og_sf vs dx_hits/og_sf
```

## Audit results (all 21 speed-parity receipts on disk)

**Clean (S=0): the pre-cache doctrine stands.** `all9-1800` and
`fresh6-7200` (Aug-12 checkpoint) show S=0.0% on every boss — shalamar
-7.5/-10.6, ted -14.7/-17.1, cameo -16.4/-17.0, angela -20.6 are
denominator-honest. "Arenas run direction-faster pre-cache" survives,
magnitudes still direction-only pending matched-span re-measurement.

**Ted (compiler lineage, v51+): always green, never fast.** S≈18-19.5%;
corrected +0.48% (v52c), +1.13% (v51@3600), +1.46% (v62b) — converging with
the trajectory instrument's +1.663% matched-span. Every "ted 14-22% faster"
receipt since v51 was the artifact.

**Shalamar cache lineage: the gate green was false.** FPI framing
(positive = DX slower than OG); "measured" = fresh runs on the fixed probe
(`tmp/rebaseline-shalamar/`, parity/matched-span):

| build | S | reported | corrected (fpi) | measured (fpi) |
|---|---|---|---|---|
| v55b | 0% | +27.68% (deficit) | +38.3% | +38.3% / +40.3% |
| v56c | 7.9% | +3.52% | +12.56% | — |
| v58b | 4.0% | +4.20% | +8.74% | **+8.74% / +8.25%** |
| v59 | 7.8% | +4.57% | +13.71% | — |
| v60b | 14.2% | -3.52% | +12.56% | — |
| v60c | 11-12.7% | **-1.74% / -0.35%** | +12.0-12.6% | **+12.0% / +13.0%** |

In runtime-fraction terms: the v56c piggyback removed **~18.6% of runtime**
(a much larger win than the mixed-framing record showed); v58b is the
lineage minimum (-21.4% vs v55b); everything after v58b gave back ~3% of
runtime while the broken meter reported improvement — a Goodhart loop: the
fusion's SVBK parking was simultaneously the intervention and the meter's
corruption, so iterations that parked more were rewarded. The meter equally
**punished un-parking** (~1:1), so rejected changes that reduced SVBK
residency may be discarded wins — re-audit the rejected pile with the same
formula.

## Controls that make this trustworthy

1. **Null (v55b, S=0):** fixed probe reproduces the original receipt
   bit-for-bit (+27.68% deficit, og 224 / dx 162 over 1199) — sticky
   accounting is a no-op where it must be. Window-matched to the original
   receipt (overhead varies ~0.2pp per window doubling; never compare across
   windows).
2. **Cross-instrument:** parity (corrected denominator) vs trajectory
   matched-span agree per pair — Ted +1.65/+1.663 (0.013pp), v58b
   +8.74/+8.25 (346-transition span), v60c +12.0/+13.0 (13-transition span;
   that fixture pair diverges almost immediately, so parity is the reliable
   number there).
3. **Numerator:** FFCD — the game's own mod-4 per-iteration counter, logged
   per sample — advances +1 mod 4 across all 967 samples on both sides.
   Zero missed iterations; the loop-head breakpoint count is validated by a
   game-owned construction.
4. **Correction validated across S = 0 → 19.5%**, so the v60c verdict
   (S=11%) is interpolation, not extrapolation: bit-exact at S=0 (null),
   0.49pp cross-instrument at S=4% (v58b), 0.2-1.2pp against the trajectory
   instrument at S=18.3-19.5% (Ted v51/v52c/v62b). Good enough for a
   10-point verdict; re-tighten (fresh well-paired fixtures, both
   instruments) before trusting any margin within ~2pp of the gate.

## Conventions (adopted)

- **Deficit vs FPI framing:** `slowdown = 1 - dx/og` (deficit, the gate's
  historical convention) vs `og/dx - 1` (fpi, the trajectory instrument's).
  They diverge with magnitude (27.68% deficit == +38.3% fpi) and mixing them
  briefly looked like a 12pp cross-check failure. Parity receipts now
  publish both (`50ae6e4`). Never mix framings in one table.
- **Runtime fraction** is the composable unit for cross-build comparisons;
  percentage points at different baselines do not add.
- **fpt vs fpi:** frames-per-transition (player-facing fight duration) vs
  frames-per-iteration (engine headroom). Ted's fpt is -0.4% (fight
  marginally shorter on DX — entirely from its ~0.5-0.7s-shorter holds, a
  quantified fidelity item likely identical to the pending whip-hold
  deviation). Gate fidelity on fpt with deviations named; track fpi as
  margin (it moves smoothly; fpt is flat until the frame budget cliff).

## Ted trajectory findings (arm-4 traces, v63)

- OG/DX Ted fixtures pair for the full window (234/351 transitions) — the
  matched-span number is magnitude-valid.
- The phase schedule is **mixed**: a per-iteration monotonic ramp
  (DD85 ascending / DD87 descending) plus two long **condition-anchored
  holds** (~300 frames each). DX's holds resolve ~10% sooner (543 vs 613
  frames total), which is why DX ends +2 transitions ahead despite fewer
  iterations — measured, benign for the metric, and the source of the
  fpt/hold fidelity item above.
- Progression-only (holds excluded) Ted cost: **+2.72%** fpi — the
  undiluted loop cost; blended +1.66-1.91%.

## Open items

1. `r` = current-generation cache-off vs OG (codex's builder artifact;
   byte-diff-confined recipe). Feasibility threshold: **r <= 1.02** or the
   cache cannot reach the gate alone. Same artifact yields the attribution
   number and the aligner's arm-3a fixture.
2. The v58b->v59 diff read (~3-5 points sitting in a known regression that
   also doubled parked share).
3. Rejected-pile re-audit (formula above; no new tooling).
4. Attract-timing +30.5% — check whether that receipt is
   scene-frames-denominated before classifying.
5. Regenerate Shalamar OG/DX state pairs (the v60c pair is weakly pairable:
   13 matched transitions).

## Instruments added/changed this session

- `verify_boss_trajectory_pairing.py` + `probe_boss_trajectory_pairing.lua`
  (`be98cae`): iteration-indexed phase-vector pairing; matched-span
  frames-per-iteration; paired/unpairable/static-vector classification;
  `--dx-warmup` offset-search control; per-capture private runtime dirs
  (battery-RAM leak found by the a/b replay check on first live contact).
- Sticky scene accounting + `parked_frames` in
  `probe_boss_speed_parity.lua`, `probe_boss_trajectory_pairing.lua`,
  `probe_boss_publication_cadence.lua` (`0b24b03`, `32620ab`).
- `slowdown_percent_fpi` in parity receipts (`50ae6e4`).
