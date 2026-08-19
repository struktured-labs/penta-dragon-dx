#!/usr/bin/env python3
"""Relocate the qualified v72 arena $9C00 cache away from the IE save byte."""

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


QUALIFIED_V72_SHA256 = (
    "c2782a829fd6f759c4a96d7b94ff7d7abeb88fbc1ce24695b7f1f896309eb53e"
)
OLD_HELPER_SHA256 = (
    "a7013293a1aec7aaa24c818ef7ecc8eb848be2c88793c56f93cdd9b7bec144fc"
)
OLD_HELPER_LENGTH = 322
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
    args = parser.parse_args()

    original = args.base.read_bytes()
    if sha256(original) != QUALIFIED_V72_SHA256:
        parser.error("base is not the qualified v72 ROM")
    offset = HELPER_BANK * 0x4000 + HELPER_ENTRY - 0x4000
    old_helper = original[offset:offset + OLD_HELPER_LENGTH]
    if sha256(old_helper) != OLD_HELPER_SHA256:
        parser.error("v72 arena helper does not match the qualified source")
    if original[
        offset + OLD_HELPER_LENGTH:offset + HELPER_CAPACITY
    ] != bytes([0xFF]) * (HELPER_CAPACITY - OLD_HELPER_LENGTH):
        parser.error("arena helper tail is not free")

    helper = build_helper()
    if len(helper) != 327:
        parser.error(f"unexpected relocated helper length: {len(helper)}")
    selector = bytes.fromhex("7A FE 9C 2E 53 20 02 2E 5C 26 DF")
    if selector not in helper:
        parser.error("relocated $9800/$9C00 selector is absent")

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
        parser.error("cache relocation changed bytes outside the helper/checksum")

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
        "old_helper_length": OLD_HELPER_LENGTH,
        "new_helper_length": len(helper),
        "cache_9800": "DF53-DF56",
        "cache_9c00": "DF5C-DF5F",
        "conflicting_ie_save": "DF5A",
        "global_checksum": f"{checksum:04X}",
        "changed_bytes": len(changed),
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
