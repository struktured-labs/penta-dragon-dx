#!/usr/bin/env python3
"""Build a correctness-only Stage-1 pickup-cache bypass on exact r120.

The production room-return scanner suppresses work with an eight-bit XOR key
derived from DC0E and two packed-source bytes.  This diagnostic preserves the
scanner and writer byte-for-byte but removes only the three-byte compare/JR-Z
suppression, forcing every scanner entry to rebuild its semantic pickup list.
It is an upper-bound experiment, not a promotable implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
PATCH_OFFSET = 0x4EEBE                 # bank19:$6EBE
PATCH_PREIMAGE = bytes.fromhex("BE 28 31")
PATCH_REPLACEMENT = bytes.fromhex("00 00 00")


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
    if rom[PATCH_OFFSET:PATCH_OFFSET + len(PATCH_PREIMAGE)] != PATCH_PREIMAGE:
        raise SystemExit("Stage-1 pickup key suppression preimage moved")
    rom[PATCH_OFFSET:PATCH_OFFSET + len(PATCH_REPLACEMENT)] = PATCH_REPLACEMENT
    update_checksums(rom)
    output = bytes(rom)

    report = {
        "schema": "penta-stage1-pickup-always-scan-r188-v1",
        "status": "CORRECTNESS_CONTROL_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "patch": "bank19:$6EBE CP [HL]; JR Z,+$31 -> NOP; NOP; NOP",
        "writer_changed": False,
        "semantic_classifier_changed": False,
        "cache_suppression_changed": True,
        "required_first_gate": "Stage-1 1200-frame rendered no-bleed route",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
