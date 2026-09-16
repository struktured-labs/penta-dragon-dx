#!/usr/bin/env python3
"""Build an exact-r120 full-plane GDMA timing experiment.

The production publisher uses immediate GDMA only with LCD off and otherwise
uses HBlank DMA. This non-promotable control changes the LCD-on command to the
same complete 48-block GDMA. Attribute contents and destination are unchanged;
real-hardware display behavior still requires Pocket/MiSTer qualification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_BASES = {
    "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742": (
        "r120"
    ),
    "5bdd5c4124dcef74a75e467ff73c729af165e039ca2d5f803ddd5f19d9dcae08": (
        "r120-stage-bit0-phase"
    ),
}
DMA_SELECT = 0x4340
PREIMAGE = bytes.fromhex("3E 2F 28 02 3E AF E0 55")
REPLACEMENT = bytes.fromhex("3E 2F 28 02 3E 2F E0 55")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    rom[0x014D] = value
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest not in ALLOWED_BASES:
        raise SystemExit(f"unqualified exact base: {digest}")
    rom = bytearray(source)
    if rom[DMA_SELECT:DMA_SELECT + len(PREIMAGE)] != PREIMAGE:
        raise SystemExit("DMA selector preimage changed")
    rom[DMA_SELECT:DMA_SELECT + len(REPLACEMENT)] = REPLACEMENT
    update_checksums(rom)
    output = bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_AND_HARDWARE_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "base_profile": ALLOWED_BASES[digest],
        "candidate_sha256": sha256(output),
        "patch": "$4345 LCD-on HDMA5 command $AF -> $2F",
        "attribute_semantics_changed": False,
        "hardware_risk": "active-LCD GDMA display stall requires Pocket/MiSTer audit",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
