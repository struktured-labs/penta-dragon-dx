#!/usr/bin/env python3
"""Build a non-promotable four-row Stage-2 attribute upper bound."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"


def checksum(rom: bytearray) -> None:
    header = 0
    for byte in rom[0x0134:0x014D]:
        header = (header - byte - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong r120 base: {digest}")
    rom = bytearray(source)
    patches = {
        0x4310: (0x18, 0x04),  # compile four complete packed rows
        0x4341: (0x2F, 0x07),  # LCD-off GDMA: eight 16-byte blocks
        0x4345: (0xAF, 0x87),  # rendered HBlank DMA: eight blocks
    }
    for offset, (old, new) in patches.items():
        if rom[offset] != old:
            raise SystemExit(
                f"preimage moved at ${offset:04X}: {rom[offset]:02X} != {old:02X}"
            )
        rom[offset] = new
    checksum(rom)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    report = {
        "schema": "penta-stage2-row4-upper-bound-v1",
        "status": "non-promotable-control",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "scope_warning": "compiler change is global; run Stage 2 only",
        "compiled_rows": 4,
        "dma_blocks": 8,
        "changed_offsets": [f"0x{offset:04X}" for offset in patches],
        "required_gates": [
            "Stage 2 strict speed >= .98 with exact scroll",
            "Stage 2 8000-frame active-map semantic equality",
            "production implementation must add an exact Stage-2 scene gate",
        ],
    }
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
