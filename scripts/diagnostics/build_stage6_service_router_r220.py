#!/usr/bin/env python3
"""Build an exact-r210 Stage-6-only inactive-service router.

Only D880=$07 returns early.  Every other scene executes the original
death->title pair and glyph call in their original relative order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000


def off(address: int) -> int:
    return BANK13 + address - 0x4000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def checksums(rom: bytearray) -> None:
    value = 0
    for byte in rom[0x134:0x14D]:
        value = (value - byte - 1) & 0xFF
    rom[0x14D] = value
    total = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = total.to_bytes(2, "big")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()
    source = args.base.read_bytes()
    if sha(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {sha(source)}")

    regions = {
        0x6F20: bytes.fromhex("CD 00 71 CD 60 6A"),
        0x6F82: bytes.fromhex("CD A7 6D"),
        0x570E: bytes(16),
        0x6ED3: bytes.fromhex(
            "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
            "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
        ),
    }
    for address, expected in regions.items():
        actual = source[off(address):off(address) + len(expected)]
        if actual != expected:
            raise SystemExit(f"preimage moved at bank13:${address:04X}")
    if source[off(0x570D)] != 0xC9 or source[off(0x571E):off(0x5720)] != bytes.fromhex("01 05"):
        raise SystemExit("front cave ownership changed")
    if source[off(0x6ED0):off(0x6ED3)] != bytes.fromhex("C3 F4 6E"):
        raise SystemExit("prelude cave ownership changed")

    pair = bytes.fromhex("FA 80 D8 FE 07 C8 CD 00 71 C3 60 6A") + bytes(4)
    glyph = bytes.fromhex("FA 80 D8 FE 07 C8 C3 A7 6D") + bytes(24)
    assert len(pair) == 16 and len(glyph) == 33
    rom = bytearray(source)
    rom[off(0x6F20):off(0x6F26)] = bytes.fromhex("CD 0E 57 00 00 00")
    rom[off(0x6F82):off(0x6F85)] = bytes.fromhex("CD D3 6E")
    rom[off(0x570E):off(0x571E)] = pair
    rom[off(0x6ED3):off(0x6EF4)] = glyph
    checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-stage6-service-router-r220-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "only_early_return_scene": "$07 (Stage 6)",
        "all_other_scenes": "CALL death; JP title; later JP glyph",
        "renderer_palette_map_code_untouched": True,
        "required_gates": [
            "Stage 6 >=0.99",
            "Penta state generator no worse than exact r210",
            "title/opening/death/story/ending",
            "seven-stage matrix",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
