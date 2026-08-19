#!/usr/bin/env python3
"""Relocate v78's live bank-13 $4CE4-$4CF1 allocations.

This hash-locked native-route candidate restores the stock list records,
moves the six-byte later-stage BG0 source table into generated-code padding,
and routes the cutscene bank switch through the unused fixed serial vector.
It retains the existing bank-6 story writer and stale-state landing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


QUALIFIED_NATIVE_ROUTE_SHA256 = (
    "4ad82a01f4d883b088cc86155645cfc261c4ba788f2beb6aeb4de151c6d9e3d3"
)
BANK13 = 13 * 0x4000
CHECKSUM_BYTES = {0x014E, 0x014F}

LIVE_RECORD_ADDR = 0x4CE4
LIVE_RECORD_DX = bytes.fromhex("20 00 30 00 18 00 00 00 00 3E 06 CD 61 00")
LATER_TABLE = LIVE_RECORD_DX[:6]
LATER_TABLE_ADDR = 0x7BAC

SERIAL_VECTOR_ADDR = 0x0058
SERIAL_VECTOR_STOCK = bytes.fromhex("D9 7D FB 7D FD ED BF FF")
STORY_FIXED_BRIDGE = bytes.fromhex("3E 06 CD 61 00 C3 C3 4C")

SELECTOR_PATTERN = bytes.fromhex("7B C6 E3 6F 26 4C 5E")
SELECTOR_REPLACEMENT = bytes.fromhex("7B C6 AB 6F 26 7B 5E")
STORY_CALL_PATTERN = bytes.fromhex("C4 ED 4C")
STORY_CALL_REPLACEMENT = bytes.fromhex("C4 58 00")


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def one_bank13_offset(data: bytes, pattern: bytes) -> int:
    start, end = BANK13, BANK13 + 0x4000
    hits = [
        index for index in range(start, end - len(pattern) + 1)
        if data[index:index + len(pattern)] == pattern
    ]
    if len(hits) != 1:
        raise ValueError(
            f"expected one active-bank13 {pattern.hex().upper()} hit, got {hits}"
        )
    return hits[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    if sha256(original) != QUALIFIED_NATIVE_ROUTE_SHA256:
        parser.error("base ROM is not the qualified v78 native-route isolation")
    patched = bytearray(original)

    live_offset = BANK13 + LIVE_RECORD_ADDR - 0x4000
    if original[live_offset:live_offset + len(LIVE_RECORD_DX)] != LIVE_RECORD_DX:
        parser.error("qualified bank13:$4CE4-$4CF1 bytes do not match")
    patched[live_offset:live_offset + len(LIVE_RECORD_DX)] = bytes(len(LIVE_RECORD_DX))

    table_offset = BANK13 + LATER_TABLE_ADDR - 0x4000
    if original[table_offset:table_offset + len(LATER_TABLE)] != bytes(len(LATER_TABLE)):
        parser.error("bank13:$7BAC-$7BB1 relocation slot is not zero padding")
    patched[table_offset:table_offset + len(LATER_TABLE)] = LATER_TABLE

    if original[SERIAL_VECTOR_ADDR:SERIAL_VECTOR_ADDR + 8] != SERIAL_VECTOR_STOCK:
        parser.error("fixed serial vector does not match the qualified stock bytes")
    patched[SERIAL_VECTOR_ADDR:SERIAL_VECTOR_ADDR + 8] = STORY_FIXED_BRIDGE

    selector_offset = one_bank13_offset(original, SELECTOR_PATTERN)
    patched[selector_offset:selector_offset + len(SELECTOR_PATTERN)] = SELECTOR_REPLACEMENT
    story_call_offset = one_bank13_offset(original, STORY_CALL_PATTERN)
    patched[story_call_offset:story_call_offset + len(STORY_CALL_PATTERN)] = STORY_CALL_REPLACEMENT

    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = (
        set(range(live_offset, live_offset + len(LIVE_RECORD_DX)))
        | set(range(table_offset, table_offset + len(LATER_TABLE)))
        | set(range(SERIAL_VECTOR_ADDR, SERIAL_VECTOR_ADDR + 8))
        | set(range(selector_offset, selector_offset + len(SELECTOR_PATTERN)))
        | set(range(story_call_offset, story_call_offset + len(STORY_CALL_PATTERN)))
        | CHECKSUM_BYTES
    )
    if not changed <= allowed:
        raise AssertionError(f"relocation escaped allowed bytes: {changed - allowed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-v78-cave-collision-relocation-v1",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "restored_live_records": "bank13:$4CE4-$4CF1",
        "later_table": "bank13:$7BAC-$7BB1",
        "story_fixed_bridge": "fixed:$0058-$005F",
        "selector_file_offset": f"0x{selector_offset:06X}",
        "story_call_file_offset": f"0x{story_call_offset:06X}",
        "serial_interrupt_ie_mask": "disabled; qualified gameplay IE=$07",
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
