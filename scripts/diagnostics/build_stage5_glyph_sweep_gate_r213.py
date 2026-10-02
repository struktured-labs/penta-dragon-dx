#!/usr/bin/env python3
"""Build an exact-r210 glyph-on-sweep attribution candidate.

The footer/native-9 helper is transition work, but the wrapper calls it every
dungeon VBlank.  This same-width diagnostic runs it on the existing full BG
sweep arm and skips it on the steady fast-OBJ arm.  It preserves the helper,
all colorizer calls, joypad timing before the renderer, and wrapper teardown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
BRANCH_ADDR = 0x6F78
SEQUENCE_ADDR = 0x6F7A
OLD_BRANCH = bytes.fromhex("28 05")
OLD_SEQUENCE = bytes.fromhex("CD 00 6E 18 03 CD 00 6B CD A7 6D")
NEW_BRANCH = bytes.fromhex("28 08")
NEW_SEQUENCE = bytes.fromhex("CD 00 6E CD A7 6D 18 03 CD 00 6B")


def offset(address: int) -> int:
    return BANK13 + address - 0x4000


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {digest(source)}")
    if source[offset(BRANCH_ADDR):offset(BRANCH_ADDR) + 2] != OLD_BRANCH:
        raise SystemExit("BG-sweep branch preimage moved")
    if source[offset(SEQUENCE_ADDR):offset(SEQUENCE_ADDR) + len(OLD_SEQUENCE)] != OLD_SEQUENCE:
        raise SystemExit("render/glyph sequence preimage moved")

    rom = bytearray(source)
    rom[offset(BRANCH_ADDR):offset(BRANCH_ADDR) + 2] = NEW_BRANCH
    rom[offset(SEQUENCE_ADDR):offset(SEQUENCE_ADDR) + len(NEW_SEQUENCE)] = NEW_SEQUENCE
    update_checksums(rom)
    candidate = bytes(rom)
    receipt = {
        "schema": "penta-stage5-glyph-sweep-gate-r213-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "same_width": True,
        "full_sweep_path": ["full BG colorizer", "glyph service"],
        "steady_path": ["fast OBJ colorizer"],
        "glyph_helper_preserved": True,
        "required_gates": [
            "Stage 5 speed",
            "title visual/footer glyph",
            "opening-to-Stage-1",
            "death/game-over",
            "ending glyph/font",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
