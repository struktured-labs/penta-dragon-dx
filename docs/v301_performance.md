# v3.01 Performance Characteristics

> **Dungeon release compromise (approved 2026-08-27; r120 measured
> 2026-08-28).** The strict ±2% target remains visible in every receipt, while
> individually named dungeon stages may ship at a fail-closed floor of
> **0.95**. Exact r120 (`029a413b…`) measures Stage 1 **0.988**, Stage 2
> **0.988**, Stage 3 **0.976**, Stage 4 **0.990**, Stage 5 **0.962**, Stage 6
> **0.992**, and Stage 7 **0.974** on the 2,800-frame right route. Only Stages
> 3/5/7 currently consume their named 0.95 exceptions; 1/2/4/6 meet the strict
> target. A separate bounded Stage-7 patrol measures **0.924** and is retained
> as an explicit movement-stress debt with a fail-closed 0.92 floor; it does
> not replace the normal-route release measurement.
> Deterministic replay, scene continuity, cold/warm GAME START, terrain,
> menu/item hazards, low-health flicker, and mutation controls remain mandatory.
> This exception changes throughput only; optimization continues after release.

> **2026-08-28 optimization boundary.** On that Stage-7 patrol, an
> ABI-preserving control which skips the complete attribute compiler and
> publication reaches **0.996** (778/781), proving the color plane owns the
> remaining movement tax. It is visually invalid and cannot ship. Complete
> active-LCD GDMA (**0.951**), asynchronous HBlank DMA (**0.949**), and the
> dormant row-precomputed atomic copier (**0.835**) all fail the same patrol;
> none is promoted. This receipt-backed rejection prevents a faster-looking
> architecture from reintroducing partial planes, trails, or hazard artifacts.

> **2026-08-28 follow-up controls.** Removing later-dungeon room identity from
> the two-byte content cache reduced publications but regressed the Stage-7
> patrol to **0.919**, so it is rejected. Palette-service phase variants
> reached at best **774/790 = 0.9797** on Stage 5 but moved Stage 2 to 0.963
> and Stage 7 to 0.959; they are also rejected. A Stage-2 sparse pickup writer
> reached **747/754 = 0.991**, then correctly failed the 8,000-frame active-map
> gate with 38 displayed semantic mismatches: the old two-row capture envelope
> omitted valid pickups in packed rows 2/3. A complete four-row compile avoids
> that omission but measures only **738/754 = 0.979**. None of these controls
> is deployed; exact r120 remains the release baseline.

> **Current release policy (verified 2026-08-23).** The arena-loop instrument
> still exposes a strict ±2% target. Ted deterministically measures 307 DX
> iterations versus 314 stock iterations over 1800 arena frames: ratio
> **0.9777**, or **2.23%** slower. Per the operator-approved performance
> compromise, Ted has a narrow fail-closed exception floor of **0.975**;
> results below it still fail. Crystal Dragon retains its separate 0.95 floor
> for the intentional ghost effect. Both misses remain explicit in receipts.

> **⚠️ CORRECTION (verified 2026-06-07).** The cycle estimates in the
> "v3.01 colorize handler" table below describe the **attr_computation +
> GDMA** path, which **is NOT what ships**. `build_v301_gdma.py` writes
> the GDMA routine (bank13:0x6D80) and the 1024-byte `attr_computation`
> routine (bank13:0x7100) into ROM but **never CALLs either** — scanning
> the built ROM for `CD 80 6D` / `CD 00 71` finds nothing (both dead code).
>
> What actually ships every VBlank: `cond_pal` (cached, ~200T) + attr-cleaner
> (only first 32 frames post-boot) + ungated `bg_sweep` (1 row, ~600T) +
> OBJ colorizer (~300T). Plus, during the game's own tilemap copy, the
> inline tile+attr hook at bank1:0x42A7. (This banner originally described
> it as "tile phase then attr phase, each with its own STAT mode-0 wait —
> a dual STAT-wait per group"; **that is no longer true of the shipping
> ROM** — see the second correction below.)
>
> **=> The real modded cost is far below the 53K T / 76% figure.** The
> 53K T analysis is retained below for the (disabled) GDMA design only.

> **⚠️ SECOND CORRECTION (verified 2026-08-16, static disassembly).** The
> banner above used to name the inline hook's *second (attr-phase) STAT-wait
> per group* as the dominant cost and the main GB-speed-parity lever. **That
> wait is not in the shipping ROM.** `LDH A,[FF41]` sites in `0x42A0-0x4380`:
> vanilla **12**, DX **4**. Both use the same two-poll idiom (wait until
> mode==3, then wait until mode!=3) for a *single* HBlank sync; the DX atomic
> path writes tiles and attributes inside that one window. It is already fused.
>
> The measured cost driver is **cells per HBlank window**: vanilla and the DX
> stock path write **4** cells/window (tile only); the DX atomic path writes
> **3** (tile+attr), because ~55T/window goes to `LDH [FF4F]` (VBK→1), the
> `LD A,L; SUB 3; LD L,A` rewind, and `LDH [FF4F]` (VBK→0). A 24×24 map needs
> ~192 windows instead of ~144: **+33% HBlank windows**, charged only on
> frames taking the atomic path.
>
> Measured slowdown (`gameplay_speed_parity`, main-loop hits at `0x016C` per
> 600 frames) scales with map-publish frequency, as that model predicts:
>
> | stage | vanilla | DX | ratio |
> |-------|---------|-----|-------|
> | 1 | 141 | 133 | 0.943 |
> | 5 | 164 | 154 | 0.939 |
> | 7 | 167 | 142 | **0.850** (gate failure) |
>
> **Instrument warning (refined 2026-08-16).** Use `gameplay_speed_parity`
> for speed claims — it boots both ROMs from power-on through identical
> scripted input, so it has no pairing confound. `boss_publication_cadence`
> compares OG and DX from *different* save-state files whose landing phases
> differ (historically OG frame 77 vs DX frame 120), and is
> window-dependent (+2.16% @1800 vs +4.43% @3600 on one unchanged ROM,
> `tmp/boss-2pct/no-de-cadence/`). Its "impossible" speedups (angela −24%,
> cameo −22%, ted −14.5%) turned out to be *directionally real* — a new
> arena-loop-rate instrument (`verify_boss_speed_parity.py`, anchored at
> bank2:$406F) independently measures DX arenas 7–17% faster than OG on
> fresh pairs — but the magnitudes remain untrustworthy for both
> instruments. Direction only. See
> `docs/FINDINGS_2026_08_16_boss_speed_instrumentation.md`.

How efficient is the v3.01 colorization pipeline? Hard cycle counts +
qualitative observations.

## Frame budget recap

- CGB single-speed mode: **70,224 T-cycles per frame** (at 60 Hz)
- VBlank period: ~4,560 T-cycles (10 scanlines × 456T)
- Active rendering period: ~65,664 T-cycles per frame

## v3.01 colorize handler cycle estimate (DISABLED attr_comp+GDMA path — NOT shipping)

> This table is for the attr_comp+GDMA design that is compiled into ROM
> but never called. See the correction banner at the top. Kept for
> reference if that path is ever re-wired.

Per-call (each VBlank, during gameplay i.e. FFC1=1):

| Component                         | Estimated T-cycles      |
|-----------------------------------|--------------------------|
| FF99 save / set (entry)           | ~30T                     |
| VBK save / set                    | ~24T                     |
| cond_pal call (palette update)    | ~200T (cached path)      |
| bg_sweep call (1 row + viewport)  | ~600T                    |
| FFC1 gate + OAM DMA + OBJ shadow  | ~300T                    |
| **attr_computation (24 rows × ~2000T)** | **~50,000T**       |
| GDMA transfer (1024 bytes, mode 0)| ~2,048T (CPU halted)     |
| DF03=1 / cleanup / FF99 restore   | ~50T                     |
| **TOTAL per VBlank (gameplay)**   | **~53,000T**             |

On title screen (FFC1=0): only cond_pal + bg_sweep ≈ **~800T**.
Negligible overhead.

The 53K T figure means our handler uses **~76% of one frame's CPU
budget** (53K / 70K). That's high but fits within the frame. There's
~17K T left for the game's main loop logic, AI, scroll, etc.

## Vs vanilla and v3.00 (estimates)

| Version | VBlank handler total | Frame budget used | Notes |
|---------|----------------------|-------------------|-------|
| Vanilla DMG | ~3,000T          | 4%                | Plus main game loop |
| v3.00    | ~40,000T            | 57%               | Dual STAT wait per tile-copy group |
| v3.01    | ~53,000T            | 76%               | Vanilla-speed tile + full attr GDMA |

v3.01 uses MORE total T than v3.00 because v3.01 builds the full 1024-byte
attr buffer every frame. v3.00 wrote attrs inline during tile copy (half
as much work — only visible attrs). The trade-off: v3.01 has zero scroll
tearing (correct attr coverage), v3.00 had visible scroll-edge artifacts.

## Why mGBA headless benchmarks don't show the overhead

In offscreen/headless mode, mGBA emulates each Game Boy frame at fixed
CPU cost regardless of what the game does inside that frame. Running
all three variants for 60 seconds wallclock reaches the same emulated-
frame count (~2564 frames). The internal CPU load is invisible to the
emulator throughput.

Hard cycle measurement would require:
1. Instrumenting mGBA itself to dump per-VBlank-handler cycle counts, or
2. Running on real CGB hardware with profiling, or
3. Inserting cycle-counting breadcrumbs (write LY at handler entry /
   exit, compare scanline progression).

## Empirical "is it efficient enough" evidence

The strongest practical efficiency evidence is **the game runs correctly
at full speed with all behaviors intact**:

| Metric                        | Vanilla   | v3.01     |
|-------------------------------|-----------|-----------|
| Title→gameplay (FFC1=0→1) frame | ~338     | ~338      | ✓ same speed |
| Scroll tearing (palette changes/sec) | 1.50 | **0.00**  | ✓ better than vanilla |
| Phantom D887 transitions      | 18        | 3 (≤27)   | ✓ well under threshold |
| BG palette distinct words     | 0 (DMG)   | 21        | ✓ CGB-native |
| Title color non-white pixels  | 0%        | 8.5%      | ✓ colors active |
| Mini-boss palette load        | 0         | yes       | ✓ confirmed |

The 76%-of-frame-budget figure is conservative — if main-loop logic
were starved we'd see game slowdown, missed inputs, or stutter. None
observed. Scroll tearing dropping from 1.50/s to 0/s means we're
actually keeping VRAM attrs in better sync than vanilla.

## What "perfect bg colorization with O(1)ish speed" means here

The user's framing:
- **O(1)** per frame: attr_computation is fixed cost (24×24 tiles processed
  every frame, no scaling with game complexity). ✓
- **Equivalent to gb game speed**: vanilla tile-copy is preserved (single
  STAT wait per group, inline hook is byte-exact equivalent). Attr work
  is additive but stays within frame budget. ✓
- **Perfect**: scroll tearing eliminated (0/s vs vanilla 1.50/s), all
  visible tiles correctly colored. ✓

## Could it be made faster?

Possible optimizations (not implemented):
1. **Dirty-rect attr update**: only write attrs for tiles that changed
   since last frame. Compare current 0xC1A0 buffer to a previous snapshot,
   skip unchanged tiles. Could cut ~80-95% of attr work in steady state.
2. **Hardware HDMA instead of CPU loop**: program HDMA to copy tiles ROM
   → WRAM bank 2 attr buffer via a lookup table. Would eliminate CPU
   loop entirely. Requires bg_table in CGB-friendly format.
3. **Pre-computed attrs in ROM**: per-room attr tables loaded once at
   room change. Trades ROM space for runtime work.

**Updated 2026-08-16:** option 2 (HDMA) is no longer optional-nice-to-have —
it is the leading candidate for closing the remaining gap. Driving the
attribute plane with HDMA from the already-computed buffer removes the VBK
switch, the HL rewind, and the `POP AF` chain from the HBlank window, letting
the CPU run vanilla's byte-identical 4-wide tile loop. `gameplay_speed_parity`
currently **fails** on Stage 7 (ratio 0.850), so "not needed for current
production performance" no longer holds.

## What's NOT yet measured

- Per-DI window cycle count on real CGB hardware (vs mGBA estimates)
- Effect on Timer ISR audio (it gets ~50K T less per frame to work in)
- MiSTer FPGA hardware verification — emulator only so far
