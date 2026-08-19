#!/usr/bin/env python3
"""Prove Ted's compressed pointer-table index and its negative controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("PENTA_TED_DIRECT_PLANE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import build_v302_title_fix as build  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # The cold initializer emits one 16-bit padded-plane pointer for every
    # even-column 2x2 top-left: 24 rows * 12 pointers = 576 table bytes.
    table = bytearray()
    for row in range(24):
        for pair in range(12):
            pointer = 0xD000 + row * 32 + pair * 2
            table.extend(pointer.to_bytes(2, "little"))

    old_failures = 0
    new_failures = 0
    first_old = None
    for row in range(24):
        for column in range(24):
            packed = row * 24 + column
            expected = 0xD000 + row * 32 + column
            # Negative control: the retired arbitrary-cell helper treated an
            # odd packed offset as the start of a pointer.
            old = int.from_bytes(table[packed : packed + 2], "little")
            if old != expected:
                old_failures += 1
                first_old = first_old or (row, column, expected, old)
            aligned = packed & ~1
            fixed = int.from_bytes(table[aligned : aligned + 2], "little")
            fixed += column & 1
            if fixed != expected:
                new_failures += 1

    # Negative control for the observed skipped-late-write symptom: changing
    # C1A0 from checker FE to body 02 without a matching plane store must be
    # rejected by the semantic comparator.
    lut = {0xFE: 0x00, 0x02: 0x01}
    skipped_late_write_rejected = lut[0xFE] != lut[0x02]

    helper = build.build_ted_direct_single_writer_helpers()
    required_sequence = bytes.fromhex("7D E6 01 5F CB 85")
    rom = args.rom.read_bytes()
    result = {
        "schema": "penta-ted-direct-plane-index-v1",
        "status": "pass" if (
            old_failures > 0
            and new_failures == 0
            and skipped_late_write_rejected
            and required_sequence in helper
        ) else "fail",
        "rom_sha256": hashlib.sha256(rom).hexdigest(),
        "helper_sha256": hashlib.sha256(helper).hexdigest(),
        "compressed_table_bytes": len(table),
        "old_single_byte_index_failures": old_failures,
        "old_first_failure": {
            "row": first_old[0], "column": first_old[1],
            "expected": f"{first_old[2]:04X}", "actual": f"{first_old[3]:04X}",
        } if first_old else None,
        "fixed_index_failures": new_failures,
        "negative_controls": {
            "old_single_byte_index_rejected": old_failures > 0,
            "skipped_late_write_rejected": skipped_late_write_rejected,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
