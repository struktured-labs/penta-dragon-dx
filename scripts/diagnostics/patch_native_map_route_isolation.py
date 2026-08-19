#!/usr/bin/env python3
"""Restore v78's shared map entry to the native bank-1 selector.

This hash-locked diagnostic removes only the legacy bank-18 continuation
introduced at v34.  It retains v78's complete bank-1 tile copier and
post-copy attribute compiler, allowing speed and visual receipts to determine
whether the old detour is now redundant.  The output is not a release ROM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


QUALIFIED_V78_SHA256 = (
    "1e97384eed106bc8ec3697e5a66a80088cbb64c63b29c183853f67b2e1c0d5fe"
)
ENTRY_OFFSET = 0x4295
QUALIFIED_ENTRY = bytes.fromhex("CD 33 00 3E 01 BF D9 00 00 00 00")
NATIVE_ENTRY = bytes.fromhex("FA 0B DC 3C E6 01 EA 0B DC 28 05")
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
    if sha256(original) != QUALIFIED_V78_SHA256:
        parser.error("base ROM is not the qualified v78 candidate")
    if original[ENTRY_OFFSET:ENTRY_OFFSET + len(QUALIFIED_ENTRY)] != QUALIFIED_ENTRY:
        parser.error("v78 $4295 entry does not match the qualified bytes")

    patched = bytearray(original)
    patched[ENTRY_OFFSET:ENTRY_OFFSET + len(NATIVE_ENTRY)] = NATIVE_ENTRY
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = set(range(ENTRY_OFFSET, ENTRY_OFFSET + len(NATIVE_ENTRY))) | CHECKSUM_BYTES
    if not changed <= allowed:
        raise AssertionError(f"native-route isolation escaped allowed bytes: {changed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-native-map-route-isolation-v1",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "entry_address": "fixed:$4295",
        "entry_file_offset": f"0x{ENTRY_OFFSET:06X}",
        "before": QUALIFIED_ENTRY.hex().upper(),
        "after": NATIVE_ENTRY.hex().upper(),
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
