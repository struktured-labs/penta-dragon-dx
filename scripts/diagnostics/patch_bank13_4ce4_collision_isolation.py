#!/usr/bin/env python3
"""Restore the live bank-13 $4CE4-$4CF1 stock list records.

The qualified v78 native-route ROM stores a six-byte palette-source table and
a five-byte story bank bridge in this zero-valued range.  Stock's pointer table
at bank13:$4C48 references these bytes as individual FF/list records during
gameplay.  This non-release control restores all fourteen bytes to prove the
cave collision's timing and terrain impact; it intentionally disables those
two DX data/code allocations until they are relocated.
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
START_ADDRESS = 0x4CE4
END_ADDRESS = 0x4CF2
EXPECTED_DX = bytes.fromhex("20 00 30 00 18 00 00 00 00 3E 06 CD 61 00")
EXPECTED_STOCK = bytes(len(EXPECTED_DX))
CHECKSUM_BYTES = {0x014E, 0x014F}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    if sha256(original) != QUALIFIED_NATIVE_ROUTE_SHA256:
        parser.error("base ROM is not the qualified v78 native-route isolation")
    offset = BANK13 + START_ADDRESS - 0x4000
    if original[offset:offset + len(EXPECTED_DX)] != EXPECTED_DX:
        parser.error("qualified bank13:$4CE4-$4CF1 bytes do not match")

    patched = bytearray(original)
    patched[offset:offset + len(EXPECTED_STOCK)] = EXPECTED_STOCK
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = set(range(offset, offset + len(EXPECTED_STOCK))) | CHECKSUM_BYTES
    if not changed <= allowed:
        raise AssertionError(f"collision isolation escaped allowed bytes: {changed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-bank13-4ce4-collision-isolation-v1",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "range": f"bank13:${START_ADDRESS:04X}-${END_ADDRESS - 1:04X}",
        "file_offset": f"0x{offset:06X}",
        "before": EXPECTED_DX.hex().upper(),
        "after": EXPECTED_STOCK.hex().upper(),
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
