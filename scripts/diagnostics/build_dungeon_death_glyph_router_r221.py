#!/usr/bin/env python3
"""Build exact-r210 dungeon routing for death and glyph only.

The title-service CALL remains byte-exact at $6F23 for every scene.  This keeps
arena service order/timing closer to the accepted ROM while ordinary dungeon
scenes skip only the death dispatcher and footer-glyph service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000


def off(a: int) -> int:
    return BANK13 + a - 0x4000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def fix_checksums(rom: bytearray) -> None:
    h = 0
    for byte in rom[0x134:0x14D]:
        h = (h - byte - 1) & 0xFF
    rom[0x14D] = h
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

    old_guard = bytes.fromhex(
        "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
        "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
    )
    checks = (
        (0x6F20, bytes.fromhex("CD 00 71 CD 60 6A")),
        (0x6F82, bytes.fromhex("CD A7 6D")),
        (0x570E, bytes(16)),
        (0x6ED3, old_guard),
    )
    for address, expected in checks:
        if source[off(address):off(address) + len(expected)] != expected:
            raise SystemExit(f"preimage moved at bank13:${address:04X}")

    # D880-2 in $00-$09 means ordinary dungeon $02-$0B: RET C.  Title
    # underflow and scene $0C+ tail-call the original owner.
    death_router = bytes.fromhex("FA 80 D8 D6 02 FE 0A D8 C3 00 71") + bytes(5)
    glyph_router = bytes.fromhex("FA 80 D8 D6 02 FE 0A D8 C3 A7 6D") + bytes(22)
    assert len(death_router) == 16 and len(glyph_router) == 33

    rom = bytearray(source)
    rom[off(0x6F20):off(0x6F23)] = bytes.fromhex("CD 0E 57")
    # $6F23-$6F25 remains the exact CALL $6A60 title service.
    rom[off(0x6F82):off(0x6F85)] = bytes.fromhex("CD D3 6E")
    rom[off(0x570E):off(0x571E)] = death_router
    rom[off(0x6ED3):off(0x6EF4)] = glyph_router
    fix_checksums(rom)
    candidate = bytes(rom)

    report = {
        "schema": "penta-dungeon-death-glyph-router-r221-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "title_call_6f23_byte_exact": candidate[off(0x6F23):off(0x6F26)].hex(),
        "dungeon_skips": ["death/story dispatcher", "footer glyph"],
        "dungeon_retains": ["title palette service"],
        "other_scenes": "tail-call original death/glyph owners",
        "required_gates": [
            "Stage 6 >=0.99",
            "Penta no worse than r210",
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
