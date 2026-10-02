#!/usr/bin/env python3
"""Build an exact-r120 row-precomputed copier attribution ROM.

This installs the dormant row-precomputed tile/attribute copier over the
current postcomputed full-plane publisher. It is intentionally not a release
candidate: Stage-1's later selective postcopy is absent. The control answers
one question only—whether row-local atomic publication can remove Stage 7's
movement tax without weakening its attribute semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v301_gdma import (  # noqa: E402
    create_inline_tile_copy_row_precomputed_attrs,
)


BASE_SHA256 = "029a413b4ef5c0d3fdb6d9d39902821e8b0d9f35a36bed20ab82973f2ab10742"
INLINE_START = 0x42A7
INLINE_END = 0x436E
DECISION_HELPER = 0x3485


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    rom[0x014D] = value
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    digest = sha256(source)
    if digest != BASE_SHA256:
        raise SystemExit(f"wrong exact r120 base: {digest}")
    rom = bytearray(source)
    if rom[0x0030:0x0033] != bytes.fromhex("C3 5A 43"):
        raise SystemExit("RST $30 title entry preimage changed")
    if rom[INLINE_START:INLINE_START + 10] != bytes.fromhex(
        "2E 00 7C E0 A5 16 FF CD 85 34"
    ):
        raise SystemExit("postcomputed copier preimage changed")

    copier = create_inline_tile_copy_row_precomputed_attrs(
        DECISION_HELPER,
        current_decision_abi=True,
    )
    capacity = INLINE_END - INLINE_START
    if len(copier) > capacity:
        raise SystemExit(f"row copier does not fit: {len(copier)}/{capacity}")
    rom[INLINE_START:INLINE_END] = copier + bytes(capacity - len(copier))
    # $42A5 is the established H=$98 entry immediately before INLINE_START.
    rom[0x0030:0x0033] = bytes.fromhex("C3 A5 42")
    update_checksums(rom)
    output = bytes(rom)
    receipt = {
        "status": "PASS_STATIC_STAGE7_ONLY",
        "promotable": False,
        "base_sha256": digest,
        "candidate_sha256": sha256(output),
        "inline": f"{len(copier)}/{capacity} bytes at $42A7",
        "decision_abi": "D=$FF before current $3485 helper",
        "title_entry": "RST $30 -> $42A5 (H=$98 then row copier)",
        "known_missing_release_contract": "Stage-1 selective postcopy",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
