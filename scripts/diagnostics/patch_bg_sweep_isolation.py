#!/usr/bin/env python3
"""Disable v78 native-route's legacy row sweep for attribution testing.

The native-route candidate already publishes a complete off-screen attribute
plane.  This hash-locked, non-release control changes the bank-13 BG sweep's
padding entry from NOP to RET so receipts can prove whether the legacy
18-frame row repair is redundant, slow, or actively racing that publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


QUALIFIED_BASES = {
    "4ad82a01f4d883b088cc86155645cfc261c4ba788f2beb6aeb4de151c6d9e3d3":
        "v78-native-map-route",
    "370690ba124d7a0e58534590bc48d223f328f3fe6a339513ef48d7febf49fb63":
        "v78-native-route-cave-relocated",
}
SWEEP_ENTRY_OFFSET = 13 * 0x4000 + (0x6CD0 - 0x4000)
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
    base_sha256 = sha256(original)
    base_variant = QUALIFIED_BASES.get(base_sha256)
    if base_variant is None:
        parser.error("base ROM is not a qualified v78 native-route isolation")
    if original[SWEEP_ENTRY_OFFSET] != 0x00:
        parser.error("bank-13 $6CD0 is not the qualified NOP entry")

    patched = bytearray(original)
    patched[SWEEP_ENTRY_OFFSET] = 0xC9
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = {SWEEP_ENTRY_OFFSET, *CHECKSUM_BYTES}
    if not changed <= allowed:
        raise AssertionError(f"BG-sweep isolation escaped allowed bytes: {changed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-bg-sweep-isolation-v1",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": base_sha256,
        "base_variant": base_variant,
        "output_sha256": sha256(patched),
        "entry_address": "bank13:$6CD0",
        "entry_file_offset": f"0x{SWEEP_ENTRY_OFFSET:06X}",
        "before": "00",
        "after": "C9",
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
