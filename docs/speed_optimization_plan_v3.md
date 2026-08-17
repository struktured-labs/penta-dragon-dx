# Speed Optimization Plan v3 — closing the dungeon ~6%

> **Status**: measurement phase (2026-08-16). Supersedes the *analysis* in
> `speed_optimization_plan_v2.md` (whose VBlank-chain gating work shipped,
> but whose cost model predates the current builder) and the stale
> "second STAT wait" lever in older notes — that wait does not exist in
> the shipping ROM. Companion measurement record:
> `docs/FINDINGS_2026_08_16_boss_speed_instrumentation.md`.

## The problem, precisely

`gameplay_speed_parity` (main-loop hits at `$016C` per 600 frames,
input-identical boot — the confound-free instrument):

| stage | vanilla | DX | ratio | scroll changes (OG/DX) |
|---|---|---|---|---|
| 1 | 141 | 133 | 0.943 | 15/15 (clean) |
| 5 | 164 | 154 | 0.939 | 18/18 (clean) |
| 7 | 167 | 142 | 0.850 (**gate fail**) | 62/103 (**diverged**) |

Honest read: **the dungeon runs ~6% slow** (stages 1/5, matched scroll).
Stage 7's 15% is direction-real but magnitude-suspect: the scroll-count
mismatch (62 vs 103) shows the two runs diverged onto different route
coverage, so part of that figure is route divergence, not pure CPU cost.

Boss arenas are NOT part of this problem — measured 2026-08-16, five of
nine run *faster* than vanilla (see the findings doc). This plan is about
the dungeon copier only.

## Root-cause model (statically verified)

The shipping inline copier at bank1:`$42A7` has two paths:

| path | window body | cells/window |
|---|---|---|
| vanilla / DX stock (`$432D`) | `LD A,[DE]; INC DE; LD [HL+],A` ×4 | 4 (tile only) |
| DX atomic (`$42D1`) | 3 tile stores → VBK=1 → rewind HL (−3) → `POP AF; LD [HL+],A` ×3 → VBK=0 | 3 (tile+attr) |

The atomic body spends ~55T per window on `LDH [FF4F]` ×2 + the
`LD A,L; SUB 3; LD L,A` rewind + POP staging. A 24-cell row therefore
needs **8 windows instead of 6 (+33%)** whenever the atomic path runs.
Slowdown should scale with publication frequency — consistent with
stage 1/5 ≈ 6% and stage 7 (heavy scroll) worst.

## Step 0 COMPLETE (stages 1/5/7 measured 2026-08-16/17)

Receipts: `tmp/boss-speed-parity/window-count-stage1.json`,
`…-stage57.json`. The probe's main-loop counter reproduced the parity
receipts (141/133, 164/153-vs-154, 167/142 exact) — instrument
cross-validated on all three stages.

| per PLAY FRAME | st1 OG | st1 DX | st5 OG | st5 DX | st7 OG | st7 DX |
|---|---|---|---|---|---|---|
| true windows (final-wait exits) | 35.4 | 33.4 | 40.8 | 37.9 | 41.4 | 37.4 |
| DX atomic-path share | — | 16.3% | — | 8.4% | — | **32.5%** |
| poll iterations | 330.7 | 347.5 | 384.2 | 388.4 | 392.6 | 412.1 |
| main-loop ratio | 0.943 | | 0.933 | | **0.850** | |

**Per LOOP ITERATION** (the load-independent view):

| per iteration | st1 | st5 | st7 |
|---|---|---|---|
| windows OG → DX | 150.6 → 150.7 | 149.3 → 148.6 | 148.7 → **158.0** |
| polls OG → DX | 1407 → 1568 (+11%) | 1406 → 1523 (+8%) | 1410 → **1741 (+23%)** |

Three conclusions:

1. **In stages 1/5 the copier does IDENTICAL work per iteration** —
   window count is a consequence of the loop rate, not a cause. The
   per-iteration cost driver is **longer waits** (+8–11% polls/iter),
   consistent with ISR interference making passes miss HBlank windows
   (miss one → burn a whole extra scanline polling). OG's poll/iter is a
   flat ~1407 across all stages — a clean baseline constant.
2. **Stage 7 is the atomic-share stage** (32.5% vs 8–16%): it alone shows
   more windows per iteration (+6%) and much longer waits (+23%). Option 1
   (golf the atomic window back to 4 cells) is therefore a *Stage-7 lever*
   (maybe 3–5% there) but near-noise for stages 1/5 (≤1%).
3. **Ledger for stages 1/5**: copier extra waits ≈1% of frame + colorize
   ISR ≈2% ≈ 3% direct tax vs 5.7–6.7% observed loop deficit. The gap is
   plausibly quantization amplification — the loop runs ~4.2 frames/iter,
   and a small CPU tax that pushes a pass past its last usable HBlank
   costs a whole extra line/frame, not a proportional slice. (Testable:
   instrument per-pass duration distribution; a bimodal shift with the
   same mean-tax would confirm.)

**Fix ranking after step 0**: the copier is NOT the primary dungeon lever.
(a) Shrink the colorize ISR (~2%, all stages) — cheapest real win;
(b) Option 1 golf for Stage 7's atomic share; (c) publication reduction
only if (a)+(b) fall short. The verification bar section applies to all.

## Step 0 results, first pass (Stage 1 only — superseded by the table above)

Receipt: `tmp/boss-speed-parity/window-count-stage1.json`. The probe's
main-loop counter reproduced the parity receipt exactly (og=141, dx=133) —
instrument cross-validated.

| metric (per play frame) | OG | DX (Aug-12) |
|---|---|---|
| true windows (final-wait exits) | 35.4 | 33.4 |
| — of which atomic body `$42DF` | — | 5.4 (**16%**) |
| — stock body `$433B` | — | 27.9 |
| poll iterations (wait time) | 330.7 | 347.5 (**+5.1%** ≈ ~1% of frame) |

**The root-cause model below is falsified for dungeon gameplay**: the
steady scroll copy runs the stock 4-wide path; the atomic 3-cell path is a
minority (Stage-1 pickup/packed-map commits). The copier's wait overhead
explains only **~1%** of the 5.7% Stage-1 slowdown. Revised ledger:

- ~1% copier waits (measured above)
- ~2% colorize VBlank ISR (+3 scanlines, measured in the boss findings doc)
- remainder distributed: per-group `RST 18` WRAM-helper dispatch in the DX
  stock twin, mid-frame services, cond_pal/bg_sweep/OBJ path costs

**Consequence for the options:** Option 1 (cycle-golf the atomic window)
recovers ≤1% and is deprioritized unless stages 5/7 show the atomic share
ballooning under heavy scroll. The productive hunt order becomes: (a) the
distributed per-frame service costs (ISR + RST dispatch), then (b)
Option 3-style publication reduction. Stage 5/7 data will confirm.

Structural notes from the counters (useful for any later golf): the DX
stock twin skips the mode-3 re-wait for subsequent groups (flow enters the
HBlank wait at `$4335` directly, 88186 arrivals vs 77902 first-wait polls),
so it is already leaner per group than vanilla's dual-wait — another reason
the old "second STAT wait" story misled: the shipped code is better than
the docs said, not worse.

## Step 0 — window-count probe (method)

Before touching the builder, split the ~6% into *per-window overhead* vs
*window count* empirically, and confirm which path actually runs during
dungeon gameplay:

- `scripts/diagnostics/probe_window_count.lua` (new): breakpoints on every
  STAT-poll site and on each wait's fall-through (first store) in
  bank1:`$42A0–$4380`, addresses supplied by the driver from a static scan
  of the exact ROM under test. Counters per address; per-frame totals.
- Outputs per stage/ROM: window acquisitions, poll iterations (≈ time
  spent waiting), atomic-vs-stock path share, publications.
- Decision rule:
  - If DX window count ≈ +33% and poll iterations dominate the delta →
    **Option 1 (cycle-golf) is sufficient in principle**; target = 4
    cells/window.
  - If window count is near vanilla but waits are longer → the overhead
    is elsewhere (re-measure before choosing).
  - If the stock path (not atomic) dominates in dungeon → the model is
    wrong; stop and re-derive.

## The fix options, ranked

### Option 1 — cycle-golf the atomic window body back to 4 cells (FIRST CHOICE)

Recover ~30T of the ~55T overhead so 4 tiles + 4 attrs fit the worst-case
window: candidates include keeping a dedicated attr pointer instead of the
HL rewind, hoisting one VBK toggle out of the window (enter with VBK
pre-set), and restaging the POP chain. Smallest possible change; no
architectural risk; directly removes the +33% window count.
Risks: worst-case mode-0 window length is the binding constraint —
must be validated against shortest-window timing (SCX fine-scroll and
sprite-heavy lines shorten mode 0), on mGBA *and* MiSTer. Any change here
re-runs the full 30-gate matrix.

### Option 2 — HDMA the attribute plane (bigger ceiling, fiddlier)

Let HBlank DMA deliver attrs while the CPU runs vanilla's byte-identical
4-wide tile loop. **Hardware caveats (this corrects an earlier, glossier
pitch of the same idea):**
- HDMA's destination honors the **current VBK** at transfer time; the CPU
  writes tiles with VBK=0 in the same windows. Sequencing per HBlank must
  be: HDMA slice fires first (VBK must be 1 at HBlank start) → CPU sets
  VBK=0, writes tiles, sets VBK=1 before the window closes.
- HDMA copies contiguous 16-byte slices; tilemap rows are 32-wide with 24
  used → requires a 32-wide staging buffer in WRAM (the extra 8 bytes per
  row must carry current VRAM contents to avoid clobbering).
- HDMA steals ~8 M-cycles/HBlank from the CPU window — budget that into
  the 4-wide tile loop's fit.
- Historical note: the old "GDMA is a non-goal" rejection was of the
  50,000T full-buffer *recompute* design, not of DMA over a sparse
  precomputed buffer. Different design; re-opened.

### Option 3 — dirty-cell / incremental publication (structural)

Only republish cells that changed (scroll edge columns + animated tiles)
instead of full rows. Largest win; same machinery family as the Ted
incremental-cell work. Cost: a real project with its own flicker-risk
class (the v297–v299 stale-attr races were exactly this shape). Only if
Options 1–2 fall short.

### Option 4 — CGB double-speed (REJECTED)

KEY1 doubles CPU throughput per window, but also doubles the Timer ISR
rate that drives the sound engine (tempo, D887 discipline) and costs
~2050T + CPU STOP per switch. Touching the sound engine's clock is the
highest-risk move in this codebase. Not pursued.

## Verification bar for any chosen option

1. `verify_stage_speed_matrix.py` stages 1/5/7 — target ≥ 0.99 on 1/5;
   stage 7 re-measured with attention to the scroll-divergence artifact.
2. Full 30-gate release matrix (`verify_release_candidate.py`).
3. The golden check: headed mGBA, Stage 1, zero orange flicker, 5 s.
4. MiSTer hardware pass (reservation-gated) before any release claim —
   mode-0 window margins are exactly the thing emulators are most
   forgiving about.
