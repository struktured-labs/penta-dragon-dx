#!/usr/bin/env python3
"""Build an exact-r210 scene router for inactive VBlank services.

Ordinary dungeon scenes ($02-$0B) currently call the death/story dispatcher,
title-palette service, and footer-glyph service every VBlank even though none
owns those scenes.  This candidate preserves service order for their actual
owners and returns immediately for ordinary dungeon gameplay.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ALLOWED_BASES = {
    "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273": (
        "r210-pocket-visual-safe"
    ),
    "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c": (
        "r231-pocket-visual-qualified-xflip"
    ),
}
BANK13 = 13 * 0x4000
SERVICE_PAIR_ADDR = 0x6F20
GLYPH_CALL_ADDR = 0x6F82
SCENE_ROUTER_ADDR = 0x570E
GLYPH_ROUTER_ADDR = 0x6ED3

OLD_PAIR = bytes.fromhex("CD 00 71 CD 60 6A")
OLD_GLYPH = bytes.fromhex("CD A7 6D")
OLD_SCENE_CAVE = bytes(16)
OLD_GLYPH_CAVE = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)

# $00-$01: title/epilogue service.  $02-$0B: return.  $0C+: death,
# story, ending, and arena service.  This is the receipt-proven r195 routing
# contract rebased onto exact r210.
SCENE_ROUTER = bytes.fromhex(
    "FA 80 D8 FE 02 38 06 FE 0C D8 C3 00 71 C3 60 6A"
)

# Subtracting two maps dungeon $02-$0B to $00-$09 (RET C after CP $0A).
# Title underflow and scene $0C+ tail-call the unchanged glyph service.
GLYPH_ROUTER = bytes.fromhex("FA 80 D8 D6 02 FE 0A D8 C3 A7 6D") + bytes(22)


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
    source_sha = digest(source)
    if source_sha not in ALLOWED_BASES:
        raise SystemExit(f"unqualified router base: {source_sha}")
    if len(SCENE_ROUTER) != 16 or len(GLYPH_ROUTER) != 33:
        raise SystemExit("router widths changed")
    require(source, SERVICE_PAIR_ADDR, OLD_PAIR, "death/title call pair")
    require(source, GLYPH_CALL_ADDR, OLD_GLYPH, "glyph call")
    require(source, SCENE_ROUTER_ADDR, OLD_SCENE_CAVE, "scene-router cave")
    require(source, GLYPH_ROUTER_ADDR, OLD_GLYPH_CAVE, "glyph-router cave")
    if source[offset(0x570D)] != 0xC9:
        raise SystemExit("scene-router cave lost RET predecessor")
    if source[offset(0x571E):offset(0x5720)] != bytes.fromhex("01 05"):
        raise SystemExit("scene-router live-data boundary moved")
    if source[offset(0x6ED0):offset(0x6ED3)] != bytes.fromhex("C3 F4 6E"):
        raise SystemExit("glyph-router cave lost unconditional-JP predecessor")

    rom = bytearray(source)
    rom[offset(SERVICE_PAIR_ADDR):offset(SERVICE_PAIR_ADDR) + 6] = bytes.fromhex(
        "CD 0E 57 00 00 00"
    )
    rom[offset(GLYPH_CALL_ADDR):offset(GLYPH_CALL_ADDR) + 3] = bytes.fromhex(
        "CD D3 6E"
    )
    rom[offset(SCENE_ROUTER_ADDR):offset(SCENE_ROUTER_ADDR) + 16] = SCENE_ROUTER
    rom[offset(GLYPH_ROUTER_ADDR):offset(GLYPH_ROUTER_ADDR) + 33] = GLYPH_ROUTER
    update_checksums(rom)
    candidate = bytes(rom)

    receipt = {
        "schema": "penta-gameplay-service-router-r217-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "base_profile": ALLOWED_BASES[source_sha],
        "candidate_sha256": digest(candidate),
        "routing": {
            "$00-$01": ["title palette", "footer glyph"],
            "$02-$0B": [],
            "$0C-$FF": ["death/story/arena", "footer glyph"],
        },
        "service_implementations_byte_exact": True,
        "palette_renderer_map_copier_untouched": True,
        "required_gates": [
            "Stage 6 strict speed >=0.99",
            "Stage 3 attribution",
            "title visual/footer glyph",
            "opening-to-Stage-1",
            "death/game-over",
            "story and ending glyph/font",
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
