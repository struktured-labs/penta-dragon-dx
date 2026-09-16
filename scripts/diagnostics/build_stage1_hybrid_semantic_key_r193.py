#!/usr/bin/env python3
"""Build an exact-width hybrid Stage-1 semantic key on exact r120.

The rendered-clean r74 key supplied the missing packed-source discriminator,
while the current DF7C room/pickup key is required by the newer hazard/menu
work.  This candidate combines SCY, DC02, packed cell C1BB, and DF7C in the
same 41-byte runtime slot.  It removes the unsafe DCFD always-dirty shortcut
and the redundant far packed sample, changing no publisher or scanner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
R120_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4FFAFDDC3DC0F04247FA02DCA847"
    "FA7CDFA8B9C812C9C3B9DA"
)
HYBRID_RUNTIME = bytes.fromhex(
    "FA80D8E6F7FE02201D16DF7CEECB5F1A4F"
    "F04247FA02DCA847FABB C1A847FA7CDFA8"
    "B9C812C9C3B9DA".replace(" ", "")
)


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
    if len(HYBRID_RUNTIME) != RUNTIME_LENGTH:
        raise SystemExit(f"hybrid runtime is {len(HYBRID_RUNTIME)}, expected 41")
    rom = bytearray(source)
    for offset in RUNTIME_OFFSETS:
        if rom[offset:offset + RUNTIME_LENGTH] != R120_RUNTIME:
            raise SystemExit(f"Stage-1 runtime preimage moved at ${offset:06X}")
        rom[offset:offset + RUNTIME_LENGTH] = HYBRID_RUNTIME
    update_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage1-hybrid-semantic-key-r193-v1",
        "status": "ATTRIBUTION_CANDIDATE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(candidate),
        "key_features": ["SCY", "DC02", "C1BB", "DF7C"],
        "runtime_copies": [f"${offset:06X}" for offset in RUNTIME_OFFSETS],
        "forced_dirty_dcfD_removed": True,
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
