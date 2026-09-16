#!/usr/bin/env python3
"""Extend the translated Stage-1 hazard row through column 14."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BANK = 19
BASE_SHA256 = "d0cfccbdbcc1d5cb6a81a564cd190ef306a4b6b8a98a76a43b8d00813c4f3787"
ROW0_REPAIR_ADDR = 0x62C7
SPAN_IMMEDIATE_ADDR = ROW0_REPAIR_ADDR + 13


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return BANK * BANK_SIZE + address - 0x4000


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit("base is not exact tagged/no-bypass r97")
    rom = bytearray(source)

    front_offset = bank_offset(ROW0_REPAIR_ADDR)
    expected_front = bytes.fromhex(
        "CD 88 6C D2 F6 61 1B 1B 7D F6 04 6F 0E 0A C3 99 6D"
    )
    actual_front = bytes(rom[front_offset:front_offset + len(expected_front)])
    if actual_front != expected_front:
        raise AssertionError(
            "row-0 repair front changed: expected "
            f"{expected_front.hex(' ')}, got {actual_front.hex(' ')}"
        )

    span_offset = bank_offset(SPAN_IMMEDIATE_ADDR)
    if rom[span_offset] != 0x0A:
        raise AssertionError(
            f"expected ten-cell span at 0x{span_offset:05X}, "
            f"got ${rom[span_offset]:02X}"
        )
    rom[span_offset] = 0x0B

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    changed = [
        index for index, pair in enumerate(zip(source, rom))
        if pair[0] != pair[1]
    ]
    if (
        span_offset not in changed
        or not set(changed).issubset({0x014E, 0x014F, span_offset})
    ):
        raise AssertionError(
            f"unexpected changed offsets: {[f'0x{x:05X}' for x in changed]}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "schema": "penta-stage1-hazard-endpoint-r98-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "patch": {
            "bank": BANK,
            "address": f"0x{SPAN_IMMEDIATE_ADDR:04X}",
            "rom_offset": f"0x{span_offset:05X}",
            "before": "0x0A",
            "after": "0x0B",
            "meaning": "publish translated hazard columns 4 through 14 inclusive",
        },
        "changed_offsets": [f"0x{x:05X}" for x in changed],
        "global_checksum": f"0x{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
