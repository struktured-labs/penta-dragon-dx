#!/usr/bin/env python3
"""Build a cycle-balanced dungeon VBlank service router on exact r231.

The stock wrapper calls the death/story service and title-palette service in
every dungeon VBlank even though both immediately reject normal gameplay.
This diagnostic keeps their exact owner routes, fast-returns in later dungeon
stages, and spends the saved cycles in Stage 1/5 so their qualified timing is
unchanged.  The footer-glyph call and all rendering code remain byte-exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c"
BANK13 = 13 * 0x4000
PAIR_ADDR = 0x6F20
DELAY_ADDR = 0x570E
ROUTER_ADDR = 0x6ED3
GLYPH_CALL_ADDR = 0x6F82

OLD_PAIR = bytes.fromhex("CD 00 71 CD 60 6A")
OLD_DELAY = bytes(16)
OLD_ROUTER = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)

# $00-$01 tail-call the title service; $0C+ tail-call death/story.  Ordinary
# dungeon scenes return immediately except exact Stage 1/5 scene IDs, whose
# delay loops restore the original 216-T-cycle pair cost.
ROUTER = bytes.fromhex(
    "FA 80 D8 FE 02 DA 60 6A FE 0C D2 00 71 F0 BA B7 "
    "28 05 FE 04 28 06 C9 06 03 C3 0E 57 06 02 C3 0E 57"
)
DELAY = bytes.fromhex("05 20 FD 00 00 00 C9") + bytes(9)


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
        raise SystemExit(f"unqualified base: {digest(source)}")
    if len(ROUTER) != 33 or len(DELAY) != 16:
        raise SystemExit("router/cave width changed")
    require(source, PAIR_ADDR, OLD_PAIR, "death/title pair")
    require(source, DELAY_ADDR, OLD_DELAY, "delay cave")
    require(source, ROUTER_ADDR, OLD_ROUTER, "router cave")
    require(source, GLYPH_CALL_ADDR, bytes.fromhex("CD A7 6D"), "glyph call")
    require(source, 0x570D, bytes.fromhex("C9"), "delay predecessor")
    require(source, 0x571E, bytes.fromhex("01 05"), "delay boundary")
    require(source, 0x6ED0, bytes.fromhex("C3 F4 6E"), "router predecessor")

    rom = bytearray(source)
    rom[offset(PAIR_ADDR):offset(PAIR_ADDR) + 6] = bytes.fromhex(
        "CD D3 6E 00 00 00"
    )
    rom[offset(DELAY_ADDR):offset(DELAY_ADDR) + 16] = DELAY
    rom[offset(ROUTER_ADDR):offset(ROUTER_ADDR) + 33] = ROUTER
    update_checksums(rom)
    candidate = bytes(rom)

    changed = [
        index for index, (before, after) in enumerate(zip(source, candidate))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    for address, size in ((PAIR_ADDR, 6), (DELAY_ADDR, 16), (ROUTER_ADDR, 33)):
        allowed.update(range(offset(address), offset(address) + size))
    if any(index not in allowed for index in changed):
        raise SystemExit("candidate changed bytes outside asserted regions")

    receipt = {
        "schema": "penta-stage15-balanced-router-r248-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "timing_t_cycles": {
            "original_pair": 216,
            "stage1_balanced": 216,
            "stage5_balanced": 216,
            "other_dungeon_fast": 148,
            "saved_per_later_dungeon_vblank": 68,
        },
        "contracts": {
            "stage1_and_stage5_pair_timing_exact": True,
            "title_owner_tail_calls_original_title_service": True,
            "death_story_owner_tail_calls_original_service": True,
            "footer_glyph_call_byte_exact": True,
            "palette_renderer_byte_exact": True,
            "map_copier_byte_exact": True,
        },
        "required_gates": [
            "strict deterministic all-stage speed matrix at <=2 percent",
            "qualified seven-incident visual suite",
            "title/opening/death/story owner-route receipts",
            "Pocket hardware test under a fresh hash-qualified filename",
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
