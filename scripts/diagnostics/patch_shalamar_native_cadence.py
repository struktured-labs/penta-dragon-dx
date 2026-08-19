#!/usr/bin/env python3
"""Retain one content-selected native Shalamar copy class on cache-correct v76."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.arena_semantic_key import HELPER_BANK, HELPER_ENTRY, build_helper


CACHE_CORRECT_V76_SHA256 = (
    "a2d26927e54ca41b256803822ce473aab3992974729b86d4986e0190cb6fe49c"
)
HELPER_CAPACITY = 0x200


def sha256(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--class", dest="native_raw_nibble", type=lambda value: int(value, 0),
        choices=range(16), required=True,
        help="observed raw-key low nibble whose exact repeats retain native work",
    )
    args = parser.parse_args()

    original = args.base.read_bytes()
    if sha256(original) != CACHE_CORRECT_V76_SHA256:
        parser.error("base is not the cache-correct v76 ROM")

    offset = HELPER_BANK * 0x4000 + HELPER_ENTRY - 0x4000
    old_helper = build_helper()
    if original[offset:offset + len(old_helper)] != old_helper:
        parser.error("v76 helper is not source-exact")
    if original[offset + len(old_helper):offset + HELPER_CAPACITY] != (
        bytes([0xFF]) * (HELPER_CAPACITY - len(old_helper))
    ):
        parser.error("arena helper tail is not free")

    helper = build_helper(
        shalamar_native_exact_class=args.native_raw_nibble
    )
    if len(helper) != 343:
        parser.error(f"unexpected cadence helper length: {len(helper)}")

    patched = bytearray(original)
    patched[offset:offset + HELPER_CAPACITY] = (
        helper + bytes([0xFF]) * (HELPER_CAPACITY - len(helper))
    )
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = [
        index
        for index, (before, after) in enumerate(zip(original, patched, strict=True))
        if before != after
    ]
    allowed = set(range(offset, offset + HELPER_CAPACITY)) | {0x014E, 0x014F}
    if set(changed) - allowed:
        parser.error("cadence patch changed bytes outside helper/checksum")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "status": "PASS",
        "base": str(args.base),
        "base_sha256": sha256(original),
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "helper_bank": HELPER_BANK,
        "helper_entry": f"{HELPER_ENTRY:04X}",
        "old_helper_length": len(old_helper),
        "new_helper_length": len(helper),
        "shalamar_native_raw_low_nibble": args.native_raw_nibble,
        "policy": "sanitize and publish exact Shalamar repeats in the selected class",
        "global_checksum": f"{checksum:04X}",
        "changed_bytes": len(changed),
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
