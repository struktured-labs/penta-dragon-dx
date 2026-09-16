#!/usr/bin/env python3
"""Restore r207's conservative Stage-1 key on the exact r210 handoff ROM.

This is an isolated hardware-qualification candidate.  It retains r210's
atomic STAGE-card palette handoff while removing the r208/r209 phase-key
runtime and its expansion-bank decider.  The source and replacement bytes are
both exact-hash bound; no other ROM byte may change except header checksums.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_later_gdma_upper_bound import update_checksums


R210_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
R207_SHA256 = "5c9da704f682281c0e4c17ace71c43254e2821157d8672bb6019338c6aaa9636"
RUNTIME_OFFSETS = (0x37C96, 0x43C96)
RUNTIME_LENGTH = 41
PRIVATE_OFFSET = 21 * 0x4000 + 0x100
PRIVATE_LENGTH = 63


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("r207", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    reference = args.r207.read_bytes()
    if digest(source) != R210_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {digest(source)}")
    if digest(reference) != R207_SHA256:
        raise SystemExit(f"unqualified exact r207 reference: {digest(reference)}")

    rom = bytearray(source)
    changed_regions: list[dict[str, object]] = []
    for offset in RUNTIME_OFFSETS:
        before = bytes(rom[offset:offset + RUNTIME_LENGTH])
        after = reference[offset:offset + RUNTIME_LENGTH]
        if before == after:
            raise SystemExit(f"r209 runtime is unexpectedly absent at 0x{offset:X}")
        rom[offset:offset + RUNTIME_LENGTH] = after
        changed_regions.append({
            "offset": f"0x{offset:X}",
            "length": RUNTIME_LENGTH,
            "before_sha256": digest(before),
            "after_sha256": digest(after),
        })

    private_before = bytes(rom[PRIVATE_OFFSET:PRIVATE_OFFSET + PRIVATE_LENGTH])
    private_after = reference[PRIVATE_OFFSET:PRIVATE_OFFSET + PRIVATE_LENGTH]
    if private_after != bytes([0xFF]) * PRIVATE_LENGTH:
        raise SystemExit("r207 split-key cave is not erased")
    if private_before == private_after:
        raise SystemExit("r209 split-key helper is unexpectedly absent")
    rom[PRIVATE_OFFSET:PRIVATE_OFFSET + PRIVATE_LENGTH] = private_after
    changed_regions.append({
        "offset": f"0x{PRIVATE_OFFSET:X}",
        "length": PRIVATE_LENGTH,
        "before_sha256": digest(private_before),
        "after_sha256": digest(private_after),
    })

    update_checksums(rom)
    candidate = bytes(rom)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    receipt = {
        "schema": "penta-stage1-visual-safe-key-r227-v1",
        "status": "STATIC_PASS_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "r207_reference_sha256": digest(reference),
        "candidate_sha256": digest(candidate),
        "preserved": [
            "r210 atomic Stage-card palette handoff",
            "all non-Stage-1-key payload bytes",
        ],
        "removed": [
            "r208 phase/content XOR key",
            "r209 split phase/content private decider",
        ],
        "changed_regions": changed_regions,
        "required_gates": [
            "stationary menu/item/low-health hazard",
            "Stage-card temporal stability",
            "pickup/no-bleed",
            "Stage-1 speed",
            "Pocket physical confirmation",
        ],
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
