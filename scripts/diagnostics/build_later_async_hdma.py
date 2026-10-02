#!/usr/bin/env python3
"""Build an exact-r120 asynchronous HBlank-DMA experiment.

The complete attribute plane and the $AF 48-block HBlank transfer are kept.
Only the CPU busy-wait after HDMA5 is replaced with equal-width NOP padding.
The candidate is non-promotable until every-frame receipts prove that the
off-screen map is never displayed or republished before HDMA5 completes.
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
WAIT_START = 0x4348
WAIT_PREIMAGE = bytes.fromhex("F0 55 CB 7F 28 FA")


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
    if rom[WAIT_START:WAIT_START + len(WAIT_PREIMAGE)] != WAIT_PREIMAGE:
        raise SystemExit("HDMA wait-loop preimage changed")
    rom[WAIT_START:WAIT_START + len(WAIT_PREIMAGE)] = bytes(len(WAIT_PREIMAGE))
    update_checksums(rom)
    output = bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest,
        "base_profile": ALLOWED_BASES[digest],
        "candidate_sha256": sha256(output),
        "transfer": "$AF 48-block HBlank DMA preserved",
        "patch": "$4348-$434D completion busy-wait -> six NOPs",
        "required_negative_controls": [
            "fail on map display before HDMA5=$FF",
            "fail on a second publication while HDMA5 is active",
            "fail on any desired/rendered attribute mismatch",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
