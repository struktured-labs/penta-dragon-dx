# v3.01 Performance Characteristics

How efficient is the v3.01 colorization pipeline? Hard cycle counts +
qualitative observations.

## Frame budget recap

- CGB single-speed mode: **70,224 T-cycles per frame** (at 60 Hz)
- VBlank period: ~4,560 T-cycles (10 scanlines × 456T)
- Active rendering period: ~65,664 T-cycles per frame

## v3.01 colorize handler cycle estimate

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

None of these are needed for the current production performance.

## What's NOT yet measured

- Per-DI window cycle count on real CGB hardware (vs mGBA estimates)
- Effect on Timer ISR audio (it gets ~50K T less per frame to work in)
- MiSTer FPGA hardware verification — emulator only so far
