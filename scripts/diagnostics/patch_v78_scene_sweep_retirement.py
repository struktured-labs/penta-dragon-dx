#!/usr/bin/env python3
"""Retire the legacy BG row sweep only outside Stage 1 in relocated v78.

The relocated candidate already publishes complete later-stage attribute
planes.  This hash-locked candidate changes the room-repair scene branch so
only exact Stage 1 can enter its cold sweep; every other scene clears the
stale row budget.  The sweep implementation itself remains intact for the
Stage-1 cold path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


QUALIFIED_BASE_SHA256 = (
    "370690ba124d7a0e58534590bc48d223f328f3fe6a339513ef48d7febf49fb63"
)
BANK13 = 13 * 0x4000
BRANCH_ADDR = 0x6B90
BRANCH_OFFSET = BANK13 + BRANCH_ADDR - 0x4000
QUALIFIED_BRANCH = bytes.fromhex("FE 0A 30 09")
RETIRED_BRANCH = bytes.fromhex("C3 9D 6B 00")
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
    if sha256(original) != QUALIFIED_BASE_SHA256:
        parser.error("base ROM is not the qualified relocated v78 candidate")
    if original[
        BRANCH_OFFSET:BRANCH_OFFSET + len(QUALIFIED_BRANCH)
    ] != QUALIFIED_BRANCH:
        parser.error("bank-13 room-repair scene branch does not match")

    patched = bytearray(original)
    patched[
        BRANCH_OFFSET:BRANCH_OFFSET + len(RETIRED_BRANCH)
    ] = RETIRED_BRANCH
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")
    changed = {
        index for index, (before, after) in enumerate(zip(original, patched))
        if before != after
    }
    allowed = set(range(BRANCH_OFFSET, BRANCH_OFFSET + 4)) | CHECKSUM_BYTES
    if not changed <= allowed:
        raise AssertionError(
            f"scene-local sweep retirement escaped allowed bytes: {changed}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    receipt = {
        "schema": "penta-v78-scene-sweep-retirement-v1",
        "status": "PASS",
        "release_candidate": False,
        "base_sha256": sha256(original),
        "output_sha256": sha256(patched),
        "branch_address": "bank13:$6B90-$6B93",
        "before": QUALIFIED_BRANCH.hex(" ").upper(),
        "after": RETIRED_BRANCH.hex(" ").upper(),
        "stage1_sweep_preserved": True,
        "non_stage1_action": "clear DF4E and return",
        "changed_offsets": [f"0x{index:06X}" for index in sorted(changed)],
        "global_checksum": f"{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
