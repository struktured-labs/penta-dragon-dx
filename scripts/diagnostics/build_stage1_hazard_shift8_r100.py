#!/usr/bin/env python3
"""Color both phases of the second translated Stage-1 hazard cylinder."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BANK = 19
BASE_SHA256 = "4f97fea4e8b1672e9c6b2d4bd90cc8eda09e561f2ad56b70550ff9fcc3f61961"
TAIL_ADDR = 0x6DB5
PHASE7_ADDR = 0x6D9E
PUBLISHER_ADDR = 0x61A0
LEAVES_ADDR = 0x6CEF


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
        raise SystemExit("base is not exact alternating-phase r99")
    rom = bytearray(source)

    tail_offset = bank_offset(TAIL_ADDR)
    tail_before = bytes.fromhex(
        "13 1A CD 88 6C D2 F6 61 1B 1B 1B C3 CF 62"
    ) + bytes(6)
    tail_after = bytes.fromhex(
        "13 13 1A CD 88 6C DA F5 6C 13 1A CD 88 6C "
        "DA A9 61 C3 F6 61"
    )
    if bytes(rom[tail_offset:tail_offset + 20]) != tail_before:
        raise AssertionError("row phase-tail preimage changed")

    publisher_offset = bank_offset(PUBLISHER_ADDR)
    publisher = bytes.fromhex(
        "7D F6 08 6F 0E 0A C3 9B 61 1B 1B C3 A0 61"
    )
    if bytes(rom[publisher_offset:publisher_offset + 15]) != bytes(15):
        raise AssertionError("shift-8 publisher cave is not empty")

    leaves_offset = bank_offset(LEAVES_ADDR)
    leaves = bytes.fromhex("1B 1B 1B C3 CF 62 1B C3 A0 61")
    if bytes(rom[leaves_offset:leaves_offset + 13]) != bytes(13):
        raise AssertionError("shift-8 leaf cave is not empty")

    phase7_offset = bank_offset(PHASE7_ADDR)
    phase7 = bytes.fromhex("13 1A CD 88 6C DA EF 6C C3 B5 6D")
    if bytes(rom[phase7_offset:phase7_offset + 17]) != bytes(17):
        raise AssertionError("column-7 classifier cave is not empty")

    front_offset = bank_offset(0x62C7)
    front_before = bytes.fromhex(
        "CD 88 6C D2 B5 6D 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
    )
    front_after = bytes.fromhex(
        "CD 88 6C D2 9E 6D 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
    )
    if bytes(rom[front_offset:front_offset + len(front_before)]) != front_before:
        raise AssertionError("column-6 classifier front changed")

    # Bank 20's existing $61A0 return trampoline is required because the
    # publisher jumps into the established CALL $0061 at bank19:$619D.
    bank20_return = 20 * BANK_SIZE + PUBLISHER_ADDR - 0x4000
    if bytes(rom[bank20_return:bank20_return + 3]) != bytes.fromhex("C3 00 43"):
        raise AssertionError("bank-20 semantic return trampoline changed")

    rom[tail_offset:tail_offset + 20] = tail_after
    rom[publisher_offset:publisher_offset + len(publisher)] = publisher
    rom[leaves_offset:leaves_offset + len(leaves)] = leaves
    rom[phase7_offset:phase7_offset + len(phase7)] = phase7
    rom[front_offset:front_offset + len(front_after)] = front_after

    # Captured current-ROM phases always expose a tooth at column 9 or 10.
    witnesses = (
        bytes.fromhex("01 67 74 02 64 67 74 02 5F 04"),
        bytes.fromhex("01 65 66 75 01 65 66 75 66 04"),
        bytes.fromhex("01 02 64 67 74 02 64 67 5F 04"),
    )
    admitted = [
        ((row[1] & 0xEF) in range(0x64, 0x6A))
        or ((row[2] & 0xEF) in range(0x64, 0x6A))
        for row in witnesses
    ]
    if admitted != [True, True, True]:
        raise AssertionError("shift-8 phase witnesses are not admitted")

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    changed = [
        index for index, pair in enumerate(zip(source, rom))
        if pair[0] != pair[1]
    ]
    allowed = {
        0x014E, 0x014F,
        *range(tail_offset, tail_offset + 20),
        *range(publisher_offset, publisher_offset + len(publisher)),
        *range(leaves_offset, leaves_offset + len(leaves)),
        *range(phase7_offset, phase7_offset + len(phase7)),
        *range(front_offset + 4, front_offset + 6),
    }
    if not set(changed).issubset(allowed):
        raise AssertionError(
            f"unexpected changed offsets: {[f'0x{x:05X}' for x in changed]}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "schema": "penta-stage1-hazard-shift8-r100-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "tail": {"address": f"0x{TAIL_ADDR:04X}", "bytes": tail_after.hex(" ")},
        "publisher": {
            "address": f"0x{PUBLISHER_ADDR:04X}",
            "bytes": publisher.hex(" "),
            "span": "columns 8 through 17 inclusive",
        },
        "leaves": {"address": f"0x{LEAVES_ADDR:04X}", "bytes": leaves.hex(" ")},
        "phase7": {"address": f"0x{PHASE7_ADDR:04X}", "bytes": phase7.hex(" ")},
        "witnesses": [row.hex(" ") for row in witnesses],
        "changed_offsets": [f"0x{x:05X}" for x in changed],
        "global_checksum": f"0x{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
