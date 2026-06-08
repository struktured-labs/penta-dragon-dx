# Findings — arena GDMA destabilization isolation (2026-06-07)

The WIP arena position-GDMA (branch `wip-arena-gdma-position`) KILLS the color
alternation (0 ATTR-FLIPs vs 134) but DESTABILIZES the boss arena (D880
collapses 0x0C → 0x01 within ~170 frames). Parallel isolation (headless
stability probe = % of 300 frames the arena stays D880==0x0C after teleport):

| variant                                   | in-arena stability |
|-------------------------------------------|--------------------|
| noop (teleport tail change only, no work) | 100%  → wiring is innocent |
| nogdma (expander on entry, no per-frame)  | 32%   → expander hurts (long FF70=2 window) |
| noexp (per-frame GDMA only, 576B)         | 7%    → GDMA is the main destabilizer |
| v0 full (expander + GDMA)                 | 7%    |
| GDMA size sweep 16B / 128B / 288B / 576B  | 6% / 6% / 7% / 7%  → SIZE-INDEPENDENT |

## Conclusion
Per-frame general-mode GDMA is fatal to the arena **regardless of transfer
size**. Even a 16-byte GDMA collapses it, but zero GDMA is 100% stable → the
cause is the GDMA *operation*, not CPU-halt duration. Leading explanation:
**HDMA-engine conflict** — the boss arena uses HBlank-HDMA for its scroll-shake
"bob" (probe_boss_coord showed FF42/FF43 oscillating), and a general-mode GDMA
terminates the arena's in-flight HDMA every frame.

The teleport tail wiring (CALL colorize; CALL arena_wrapper; RET) is fine
(noop=100%). The expander's long non-DI FF70=2 window is a secondary issue
(nogdma=32%), DI-chunkable — but moot if GDMA can't be used.

## Pivot
GDMA delivery is a dead end for the arena. The remaining path to TRUE
zero-alternation that AVOIDS HDMA: a **position-based bg_sweep**. The existing
bg_sweep already writes attrs via CPU stores (no HDMA) and coexists with the
arena. Make it (a) cover more rows/frame to keep up with animation, and (b)
write position-band attrs (not bg_table[tile]) in arena scenes. No HDMA, no
GDMA, no per-frame VBK/FF70 dance → should not destabilize.

Fallback: ship the data-driven tile-ID tables already on `main` (alternation
reduced from the original rainbow, but not zero).
