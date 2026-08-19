#!/usr/bin/env python3
"""NOP one qualified v78 native-route VBlank service call.

These are destructive-to-color, non-release performance controls.  Each
output changes exactly one fixed-width wrapper call plus the global checksum,
preserving the service's caller ABI while removing its runtime cost.
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
SERVICES = {
    "prelude": (
        0x6F6B, bytes.fromhex("C4 80 6E"), bytes.fromhex("00 00 00")
    ),
    "colorizer": (
        0x6F7E, bytes.fromhex("D4 00 6E"), bytes.fromhex("00 00 00")
    ),
    "palette": (
        0x6F31, bytes.fromhex("CD 90 6C"), bytes.fromhex("00 00 00")
    ),
    # Scene detection still runs during cold boot and loading; once it returns
    # exact Stage 4 ($05), reuse the existing CP/RET-Z slot to bypass only the
    # rest of the per-frame prelude. This is the lifecycle-safe profiler.
    "prelude-stage4-gate": (
        0x6E83, bytes.fromhex("FE 0A C8"), bytes.fromhex("FE 05 C8")
    ),
    # Replace the death/splash selector plus conditional colorizer call with
    # an equal-width Stage-4 gate. Other scenes still call the colorizer;
    # exact Stage 4 skips it and lands on the following glyph service.
    "colorizer-stage4-gate": (
        0x6F77,
        bytes.fromhex("D6 17 D6 01 CC 33 6A D4 00 6E"),
        bytes.fromhex("FE 05 28 03 CD 00 6E 00 00 00"),
    ),
}
CHECKSUM_BYTES = {0x014E, 0x014F}


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--service", choices=sorted(SERVICES), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    if sha256(original) != QUALIFIED_NATIVE_ROUTE_SHA256:
        parser.error("base ROM is not the qualified v78 native-route isolation")
    address, expected, replacement = SERVICES[args.service]
    offset = BANK13 + address - 0x4000
    if original[offset:offset + len(expected)] != expected:
        parser.error(
            f"{args.service} entry mismatch at bank13:${address:04X}: "
            f"expected {expected.hex().upper()}, got "
            f"{original[offset:offset + len(expected)].hex().upper()}"
        )

    patched = bytearray(original)
    if len(replacement) != len(expected):
        raise AssertionError("service isolation must preserve instruction width")
    patched[offset:offset + len(expected)] = replacement
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = set(range(offset, offset + len(expected))) | CHECKSUM_BYTES
    if not changed <= allowed:
        raise AssertionError(f"service isolation escaped allowed bytes: {changed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-v78-service-call-isolation-v2",
        "status": "PASS",
        "release_candidate": False,
        "service": args.service,
        "base_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "entry_address": f"bank13:${address:04X}",
        "entry_file_offset": f"0x{offset:06X}",
        "before": expected.hex().upper(),
        "after": replacement.hex().upper(),
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
