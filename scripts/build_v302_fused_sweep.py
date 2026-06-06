#!/usr/bin/env python3
"""Penta Dragon DX v3.02 — v3.00 inline hook + fused (2-pass) BG sweep.

Identical to v3.00 in every way EXCEPT the per-frame bg_sweep is replaced
with the fused variant from optimize_bg_sweep.py, which folds the palette
lookup into the attr-write pass (3 passes -> 2). The fused sweep is proven
byte-equivalent to the original (run `python scripts/optimize_bg_sweep.py`)
and is ~34% cheaper per call (~1936 T-cycles/frame returned to the game's
main loop -> higher effective frame rate, most visible while scrolling).

No DI window, no FF99 write, same two VBK toggles -> outside the
phantom-sound danger zone (strictly less work in the same VBlank context).

CANDIDATE. MUST pass the five probes in scripts/probes/ before promotion:
    cp rom/working/penta_dragon_dx_FIXED.gb rom/working/penta_dragon_dx_FIXED.vNN.backup.gb
    cp rom/working/penta_dragon_dx_v302_fused_sweep.gb rom/working/penta_dragon_dx_FIXED.gb
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v300_inline_hook import build_v300
from optimize_bg_sweep import create_bg_sweep_viewport_gated_fast


def build_v302():
    return build_v300(
        output_path=Path("rom/working/penta_dragon_dx_v302_fused_sweep.gb"),
        sweep_fn=create_bg_sweep_viewport_gated_fast,
    )


if __name__ == "__main__":
    build_v302()
