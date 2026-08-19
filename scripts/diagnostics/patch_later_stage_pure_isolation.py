#!/usr/bin/env python3
"""Build a hash-locked v78 diagnostic that bypasses atomic map publication.

This is a performance-isolation control, not a release patch.  Replacing the
RST $18 decision-vector entry with ``XOR A; RET`` forces every map publication
onto the pure stock-width tile path before any WRAM or banked helper can retain
an atomic decision.  This deliberately sacrifices attribute correctness so
the experiment can measure the atomic publisher's total throughput cost while
leaving every unrelated v78 byte intact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
QUALIFIED_BASES = {
    "1e97384eed106bc8ec3697e5a66a80088cbb64c63b29c183853f67b2e1c0d5fe":
        "v78",
    "4ad82a01f4d883b088cc86155645cfc261c4ba788f2beb6aeb4de151c6d9e3d3":
        "v78-native-map-route",
}
CHECKSUM_BYTES = {0x014E, 0x014F}
RST18_OFFSET = 0x0018
QUALIFIED_RST18 = bytes.fromhex("7A 3C CA D7 DA C3 80 DB")


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
        parser.error("base ROM is not a qualified v78 diagnostic base")
    patched = bytearray(original)
    if patched[RST18_OFFSET:RST18_OFFSET + len(QUALIFIED_RST18)] != QUALIFIED_RST18:
        parser.error("v78 RST $18 decision vector does not match the qualified bytes")
    expected = patched[RST18_OFFSET:RST18_OFFSET + 2]
    patched[RST18_OFFSET:RST18_OFFSET + 2] = bytes.fromhex("AF C9")
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = {
        RST18_OFFSET,
        RST18_OFFSET + 1,
        *CHECKSUM_BYTES,
    }
    if not changed <= allowed:
        raise AssertionError(
            f"pure isolation escaped its exact source/checksum bytes: {changed}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-map-publisher-pure-isolation-v2",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": base_sha256,
        "base_variant": base_variant,
        "output_sha256": sha256(patched),
        "source_address": "fixed:RST $18",
        "source_file_offset": f"0x{RST18_OFFSET:06X}",
        "before": expected.hex().upper(),
        "after": "AFC9",
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
