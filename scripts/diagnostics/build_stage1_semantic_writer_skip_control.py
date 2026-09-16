#!/usr/bin/env python3
"""Build a non-promotable upper bound that skips semantic row writes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_SHA256 = "cef1338b9c834d29f2174bd9e1f90e76f1968701a2fd78bace11a52c9087b0b4"
BANK_SIZE = 0x4000
BANK = 20
ENTRY = 0x4300


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != EXPECTED_SHA256:
        raise SystemExit("base is not exact r100")
    rom = bytearray(source)
    offset = BANK * BANK_SIZE + ENTRY - 0x4000
    expected = bytes.fromhex("F0 40 CB")
    replacement = bytes.fromhex("C3 DF 6C")
    if bytes(rom[offset:offset + 3]) != expected:
        raise AssertionError("semantic helper entry preimage changed")
    rom[offset:offset + 3] = replacement
    value = global_checksum(rom)
    rom[0x014E] = value >> 8
    rom[0x014F] = value & 0xFF

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "schema": "penta-stage1-semantic-writer-skip-control-v1",
        "status": "NON_PROMOTABLE_VISUALLY_INVALID",
        "promotable": False,
        "purpose": "upper bound for semantic row-writer cost",
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "patch": {
            "bank": BANK,
            "address": f"0x{ENTRY:04X}",
            "before": expected.hex(" "),
            "after": replacement.hex(" "),
        },
        "global_checksum": f"0x{value:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
