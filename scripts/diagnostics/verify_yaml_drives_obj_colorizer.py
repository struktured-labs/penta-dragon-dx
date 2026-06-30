#!/usr/bin/env python3
"""Regression guard: YAML-loaded obj_colorizer must match the frozen
golden bytes AND the legacy `create_tile_based_colorizer` codegen.

Iter 278x (2026-06-30): the `obj_colorizer:` block in
`palettes/bg_tile_categories.yaml` is now the single source of truth for
the OBJ tile-based colorizer baked into v3.01 at bank13:0x6A10. This
script asserts byte-identity across three addresses (legacy 0x4000,
relocated 0x6B27 from iter 278e, and production 0x6A10), plus a
byte-for-byte match against the frozen `obj_colorizer_v301_0x6A10.bin`
golden capture.

If a YAML edit is intentional, run the full BG hook + fresh-boot, then
regenerate the golden capture with `bg_experiment.create_tile_based_colorizer`
and update both the golden file and this verifier as needed.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from bg_experiment import (  # noqa: E402
    create_tile_based_colorizer,
    create_tile_based_colorizer_from_yaml,
)

GOLDEN_PATH = (
    REPO_ROOT / "palettes" / "golden" / "obj_colorizer_v301_0x6A10.bin"
)
PRODUCTION_ADDR = 0x6A10
ADDRS = [0x4000, 0x6B27, 0x6A10]


def main() -> int:
    failures = 0
    for addr in ADDRS:
        legacy = create_tile_based_colorizer(addr)
        yaml_b = create_tile_based_colorizer_from_yaml(addr)
        if legacy != yaml_b:
            print(
                f"[FAIL] addr 0x{addr:04X}: YAML loader drifted from legacy codegen"
            )
            for i, (a, b) in enumerate(zip(legacy, yaml_b)):
                if a != b:
                    print(f"    @ {i}: legacy=0x{a:02X} yaml=0x{b:02X}")
            failures += 1
        else:
            print(
                f"[PASS] addr 0x{addr:04X}: YAML == legacy ({len(legacy)} bytes)"
            )

    # Golden bin match at production base
    if GOLDEN_PATH.exists():
        golden = GOLDEN_PATH.read_bytes()
        actual = create_tile_based_colorizer_from_yaml(PRODUCTION_ADDR)
        if actual == golden:
            print(
                f"[PASS] production 0x{PRODUCTION_ADDR:04X}: YAML matches "
                f"GOLDEN ({len(golden)} bytes) at {GOLDEN_PATH.name}"
            )
        else:
            print(
                f"[FAIL] production 0x{PRODUCTION_ADDR:04X}: YAML DRIFTED from GOLDEN"
            )
            print(f"  actual: {actual.hex()}")
            print(f"  golden: {golden.hex()}")
            failures += 1
    else:
        print(f"[FAIL] missing golden capture at {GOLDEN_PATH}")
        failures += 1

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
