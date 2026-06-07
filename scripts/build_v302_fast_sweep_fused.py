#!/usr/bin/env python3
"""v3.02 fast-sweep (fused): build_v301_fast_sweep + the fused 2-pass bg_sweep.

Same N-calls-per-frame strategy as build_v301_fast_sweep.py, but each
bg_sweep call uses the fused 2-pass implementation from optimize_bg_sweep.py
(~34% fewer cycles per call, proven byte-equivalent — including the
gate-stripped form this path uses). Because each call is cheaper, you fit
~1.5x more rows per frame in the same CPU budget: roughly,

    N fused calls  ~=  (N * 3692/5628)  original calls  in cycle cost,

so e.g. N=9 fused costs about what N=6 original did. Use it to reach full
18-row viewport coverage in fewer frames, or to keep current coverage while
handing cycles back to the game's main loop (higher effective frame rate).

Usage:  python scripts/build_v302_fast_sweep_fused.py [N]    (default N=6)

CANDIDATE. Verify with the five probes before promotion (see CLAUDE.md).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v301_fast_sweep import build
from optimize_bg_sweep import create_bg_sweep_viewport_gated_fast


def build_fused(n_calls: int):
    return build(n_calls, sweep_fn=create_bg_sweep_viewport_gated_fast, tag="_fused")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    build_fused(n)
