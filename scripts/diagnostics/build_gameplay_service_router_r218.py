#!/usr/bin/env python3
"""Build exact-r210 dungeon-only VBlank service routing.

r217 omitted the title-service call in arena scenes.  Although semantically a
no-op there, that changed Penta Dragon's timing and added two attribute/OAM
phase mismatches.  r218 keeps the original death -> title pair and later glyph
call for every scene >= $0C.  Only ordinary dungeon scenes $02-$0B skip them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
PAIR_ADDR = 0x6F20
GLYPH_ADDR = 0x6F82
PAIR_ROUTER_ADDR = 0x6ED3
GLYPH_ROUTER_ADDR = 0x570E

OLD_PAIR = bytes.fromhex("CD 00 71 CD 60 6A")
OLD_GLYPH = bytes.fromhex("CD A7 6D")
OLD_PAIR_CAVE = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)
OLD_GLYPH_CAVE = bytes(16)

# Title family: title service. Dungeon family: RET. Scene $0C+: preserve the
# exact original death CALL followed by a tail-call to the title service.
PAIR_ROUTER = bytes.fromhex(
    "FA 80 D8 FE 02 38 09 FE 0C D8 "
    "CD 00 71 C3 60 6A C3 60 6A"
) + bytes(14)
GLYPH_ROUTER = bytes.fromhex("FA 80 D8 D6 02 FE 0A D8 C3 A7 6D") + bytes(5)


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


def require(source: bytes, address: int, expected: bytes, label: str) -> None:
    actual = source[offset(address):offset(address) + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{label} preimage moved at bank13:${address:04X}: "
            f"{actual.hex()} != {expected.hex()}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {digest(source)}")
    if len(PAIR_ROUTER) != 33 or len(GLYPH_ROUTER) != 16:
        raise SystemExit("router widths changed")
    require(source, PAIR_ADDR, OLD_PAIR, "death/title call pair")
    require(source, GLYPH_ADDR, OLD_GLYPH, "glyph call")
    require(source, PAIR_ROUTER_ADDR, OLD_PAIR_CAVE, "pair-router cave")
    require(source, GLYPH_ROUTER_ADDR, OLD_GLYPH_CAVE, "glyph-router cave")
    if source[offset(0x570D)] != 0xC9:
        raise SystemExit("glyph-router cave lost RET predecessor")
    if source[offset(0x571E):offset(0x5720)] != bytes.fromhex("01 05"):
        raise SystemExit("glyph-router live-data boundary moved")
    if source[offset(0x6ED0):offset(0x6ED3)] != bytes.fromhex("C3 F4 6E"):
        raise SystemExit("pair-router cave lost unconditional-JP predecessor")

    rom = bytearray(source)
    rom[offset(PAIR_ADDR):offset(PAIR_ADDR) + 6] = bytes.fromhex(
        "CD D3 6E 00 00 00"
    )
    rom[offset(GLYPH_ADDR):offset(GLYPH_ADDR) + 3] = bytes.fromhex("CD 0E 57")
    rom[offset(PAIR_ROUTER_ADDR):offset(PAIR_ROUTER_ADDR) + 33] = PAIR_ROUTER
    rom[offset(GLYPH_ROUTER_ADDR):offset(GLYPH_ROUTER_ADDR) + 16] = GLYPH_ROUTER
    update_checksums(rom)
    candidate = bytes(rom)

    receipt = {
        "schema": "penta-gameplay-service-router-r218-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "candidate_sha256": digest(candidate),
        "r217_rejected": "arena title-call omission added two Penta mismatches",
        "routing": {
            "$00-$01": ["title palette", "footer glyph"],
            "$02-$0B": [],
            "$0C-$FF": ["death/story/arena", "title palette", "footer glyph"],
        },
        "arena_service_order_preserved": "death -> title; glyph remains later",
        "required_gates": [
            "Stage 6 strict speed >=0.99",
            "Penta boss generation no worse than exact r210 control",
            "title/footer and opening",
            "death/game-over and story/ending",
            "all-stage speed matrix",
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
