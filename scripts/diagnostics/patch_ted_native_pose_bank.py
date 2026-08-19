#!/usr/bin/env python3
"""Install the source-built Ted native-pose bank into an expanded candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from prototype_ted_expanded_bank import (
    BANK_SIZE,
    NATIVE_POSE_BANK,
    build_native_pose_bank,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_checksum(data: bytes | bytearray) -> int:
    value = 0
    for byte in data[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.candidate.read_bytes()
    if len(source) != 32 * BANK_SIZE:
        parser.error(f"expected a 512 KiB expanded ROM, got {len(source)} bytes")
    bank = build_native_pose_bank()
    if len(bank) != BANK_SIZE:
        raise AssertionError(f"native pose bank is {len(bank)} bytes")

    patched = bytearray(source)
    start = NATIVE_POSE_BANK * BANK_SIZE
    patched[start:start + BANK_SIZE] = bank
    patched[0x014D] = header_checksum(patched)
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = [
        offset
        for offset, (before, after) in enumerate(zip(source, patched, strict=True))
        if before != after
    ]
    allowed = set(range(start, start + BANK_SIZE)) | {0x014D, 0x014E, 0x014F}
    if set(changed) - allowed:
        raise AssertionError("native-pose patch escaped bank 17/checksums")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    report = {
        "status": "pass",
        "source": str(args.candidate),
        "source_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "bank": NATIVE_POSE_BANK,
        "bank_sha256": sha256(bank),
        "changed_bytes": len(changed),
        "checksums": {
            "header": f"{patched[0x014D]:02X}",
            "global": f"{checksum:04X}",
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
