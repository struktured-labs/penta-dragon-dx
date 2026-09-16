#!/usr/bin/env python3
"""Recognize both alternating translated Stage-1 hazard phases."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BANK = 19
BASE_SHA256 = "7dab6d9e1bd08e6d136e92cdab7c7b657dcd44bddc41c77e46053158837cb1e5"
FRONT_ADDR = 0x62C7
TAIL_ADDR = 0x6DB5


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
        raise SystemExit("base is not exact Stage-1 endpoint r98")
    rom = bytearray(source)

    front_offset = bank_offset(FRONT_ADDR)
    front_before = bytes.fromhex(
        "CD 88 6C D2 F6 61 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
    )
    front_after = bytes.fromhex(
        "CD 88 6C D2 B5 6D 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
    )
    if bytes(rom[front_offset:front_offset + len(front_before)]) != front_before:
        raise AssertionError("translated-phase front preimage changed")

    tail_offset = bank_offset(TAIL_ADDR)
    tail = bytes.fromhex("13 1A CD 88 6C D2 F6 61 1B 1B 1B C3 CF 62")
    if bytes(rom[tail_offset:tail_offset + 20]) != bytes(20):
        raise AssertionError("translated-phase tail cave is not empty")

    rom[front_offset:front_offset + len(front_after)] = front_after
    rom[tail_offset:tail_offset + len(tail)] = tail

    # Receipt-proven alternating layouts: the first uses column 6, while the
    # second has a neutral column 6 and must be admitted by column 7.
    witnesses = (
        bytes.fromhex("26 27 64 02 74 67 64 02 74 67 64"),
        bytes.fromhex("26 27 01 75 66 65 01 75 66 65 01"),
    )
    admitted = [
        ((row[2] & 0xEF) in range(0x64, 0x6A))
        or ((row[3] & 0xEF) in range(0x64, 0x6A))
        for row in witnesses
    ]
    if admitted != [True, True]:
        raise AssertionError("alternating hazard witnesses are not admitted")

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    changed = [
        index for index, pair in enumerate(zip(source, rom))
        if pair[0] != pair[1]
    ]
    allowed = {
        0x014E, 0x014F,
        *(range(front_offset + 4, front_offset + 6)),
        *(range(tail_offset, tail_offset + len(tail))),
    }
    if not set(changed).issubset(allowed):
        raise AssertionError(
            f"unexpected changed offsets: {[f'0x{x:05X}' for x in changed]}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "schema": "penta-stage1-hazard-phase-r99-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "front_patch": {
            "bank": BANK,
            "address": f"0x{FRONT_ADDR:04X}",
            "before": front_before.hex(" "),
            "after": front_after.hex(" "),
        },
        "column7_tail": {
            "bank": BANK,
            "address": f"0x{TAIL_ADDR:04X}",
            "bytes": tail.hex(" "),
        },
        "witnesses": [row.hex(" ") for row in witnesses],
        "changed_offsets": [f"0x{x:05X}" for x in changed],
        "global_checksum": f"0x{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
