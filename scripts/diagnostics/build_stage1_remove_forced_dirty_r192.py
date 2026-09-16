#!/usr/bin/env python3
"""Remove only Stage-1's forced-dirty DCFD branch on exact r120.

The current runtime forces every DCFD=0 publication through the full 24-row
attribute compiler.  On horizontal streaming that compiler repeatedly paints
the semantic plane at a stale origin, producing detached pickup rectangles and
wall flashes.  This attribution candidate retains the current SCY/DC02/DF7C
per-map key and all hazard/postcopy code, but lets DCFD=0 use that same key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
PATCH_OFFSETS = (0x37CA7, 0x43CA7)
PATCH_PREIMAGE = bytes.fromhex("FA FD DC 3D C0")
PATCH_REPLACEMENT = bytes.fromhex("00 00 00 00 00")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest != BASE_SHA256:
        raise SystemExit(f"unqualified exact r120 base: {digest}")
    rom = bytearray(source)
    for offset in PATCH_OFFSETS:
        if rom[offset:offset + 5] != PATCH_PREIMAGE:
            raise SystemExit(f"forced-dirty preimage moved at ${offset:06X}")
        rom[offset:offset + 5] = PATCH_REPLACEMENT
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-remove-forced-dirty-r192-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(candidate),
        "runtime_offsets": [f"${offset:06X}" for offset in PATCH_OFFSETS],
        "current_scy_dc02_df7c_key_preserved": True,
        "hazard_scanner_changed": False,
        "copier_changed": False,
        "palette_table_changed": False,
        "required_gates": [
            "Stage-1 rendered no-bleed",
            "current hazard menu/item",
            "low-health hazard determinism",
            "attract pickup palettes",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
