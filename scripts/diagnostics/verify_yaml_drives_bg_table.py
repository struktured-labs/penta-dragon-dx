#!/usr/bin/env python3
"""Regression guard: YAML-loaded bg_table must match frozen golden bytes.

Iter 278w (2026-06-30): bg_tile_categories.yaml became the single source
of truth for build_v301_gdma.py:_bg_table(). This script verifies that
the YAML loader produces bytes byte-identical to the v3.01 production
ROM's dungeon bg_table at bank13:0x7000.

If a YAML edit is intentional, run visual regression suite, then update
GOLDEN below.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from build_v301_gdma import _load_bg_table_yaml  # noqa: E402

# Frozen 256-byte dump from rom/working/penta_dragon_dx_v301.gb @ bank13:0x7000
# captured 2026-06-30 = output of _load_bg_table_yaml() at iter 278w commit.
# Pre-refactor _bg_table() produced identical bytes.
GOLDEN = bytes.fromhex(
    "00000000000000000000000000000000"
    "00000000060006060606060006000600"
    "00000000000606000000060606060600"
    "00000000060606060600060606060000"
    "00060600060606060606000000000000"
    "00000000060606060006000000000000"
    "00000000000000000000000000000000"
    "00000000000000000000000000000000"
    "01010101010101010101010101010101"
    "01010101010101010101010101010101"
    "01010101010101010101010101010101"
    "01010101010101010101010101010101"
    "01010101010101010101010101010101"
    "01010101010101010101010101010101"
    "00000000000000000000000000000000"
    "00000000000000000000000000000000"
)


def main() -> int:
    assert len(GOLDEN) == 256, f"GOLDEN length {len(GOLDEN)} != 256"
    actual = _load_bg_table_yaml()
    if actual == GOLDEN:
        print(f"[PASS] YAML loader produces 256 bytes matching GOLDEN")
        return 0
    print(f"[FAIL] YAML loader output DRIFTED from GOLDEN")
    print(f"  actual: {actual.hex()}")
    print(f"  golden: {GOLDEN.hex()}")
    diffs = 0
    for i, (a, g) in enumerate(zip(actual, GOLDEN)):
        if a != g:
            print(f"    tile 0x{i:02X}: got pal {a}, golden pal {g}")
            diffs += 1
    print(f"  Total drift: {diffs} tiles")
    print()
    print("  If intentional: verify visual regression suite, then update GOLDEN.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
