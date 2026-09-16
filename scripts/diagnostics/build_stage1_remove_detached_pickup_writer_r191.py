#!/usr/bin/env python3
"""Disable the obsolete detached Stage-1 pickup writer on exact r120.

The room-expander hook still computes and publishes DF7C, which is consumed by
the current full attribute-plane decision runtime.  It then returns directly
instead of running the old metatile-coordinate 2x2 writer.  That writer uses a
fixed room origin and visibly paints pickup palettes into adjacent floor cells
during scrolling.  The tile-ID compiler remains the sole pickup attribute
owner; hazard scanning, map copying, palettes, and later stages are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
PATCH_OFFSET = 0x4EEC2              # bank19:$6EC2
PATCH_PREIMAGE = bytes.fromhex("CD 13 DA")
PATCH_REPLACEMENT = bytes.fromhex("C3 F2 6E")  # JP scanner restore/return


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
    if rom[PATCH_OFFSET:PATCH_OFFSET + 3] != PATCH_PREIMAGE:
        raise SystemExit("detached Stage-1 pickup writer preimage moved")
    rom[PATCH_OFFSET:PATCH_OFFSET + 3] = PATCH_REPLACEMENT
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-remove-detached-pickup-writer-r191-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(candidate),
        "patch": "bank19:$6EC2 CALL $DA13 -> JP $6EF2",
        "df7c_key_update_preserved": True,
        "full_tile_id_attribute_compiler_preserved": True,
        "hazard_scanner_changed": False,
        "copier_changed": False,
        "palette_table_changed": False,
        "required_gates": [
            "Stage-1 rendered no-bleed",
            "live pickup palettes",
            "current hazard menu/item",
            "low-health hazard determinism",
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
