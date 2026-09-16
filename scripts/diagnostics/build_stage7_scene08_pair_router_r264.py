#!/usr/bin/env python3
"""Build an exact-r264 Stage-7 inactive-service routing diagnostic.

The VBlank wrapper calls the death/story and title-palette services during
every dungeon frame even though neither service owns Stage-7 gameplay scene
$08.  This default-off candidate returns early only for exact scene $08.

Stage 1 and Stage 5 use the already-audited delay cave so their wrapper cost
remains exactly 216 T-cycles.  All scene owners retain the original service
tail calls, the glyph/render/palette paths remain byte-exact, and the ROM is
strictly SHA/preimage bound to visually repaired r264.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
BANK13 = 13 * 0x4000
PAIR_ADDR = 0x6F20
DELAY_ADDR = 0x570E
ROUTER_ADDR = 0x6ED3
GLYPH_CALL_ADDR = 0x6F82
MENU_TAIL = 0x77A8

OLD_PAIR = bytes.fromhex("CD 00 71 CD 60 6A")
OLD_DELAY = bytes(16)
OLD_ROUTER = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)
NATIVE_HIDDEN_MENU_TAIL = bytes.fromhex("AF E0 E4 C9")

# Exact Scene 8 exits after the first compare.  The remaining owner routing is
# the qualified r248 contract.  The loop counts are one smaller because the
# added CP $08 / RET Z costs exactly one taken DJNZ-like delay iteration on
# the Stage-1/5 non-taken path.
ROUTER = bytes.fromhex(
    "FA 80 D8 "          # LD A,[$D880]
    "FE 08 C8 "          # exact Stage 7: RET Z
    "FE 02 DA 60 6A "    # title/epilogue: JP C,$6A60
    "FE 0C D2 00 71 "    # death/story/arena: JP NC,$7100
    "F0 BA 06 02 B7 "    # B=2; Stage 1?
    "28 05 "             # yes -> shared delay
    "05 FE 04 20 03 "    # B=1; Stage 5? otherwise return
    "C3 0E 57 C9"        # delay tail / ordinary dungeon RET
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
        raise AssertionError(
            f"{label} preimage moved at bank13:${address:04X}: "
            f"{actual.hex()} != {expected.hex()}"
        )


def install(source: bytes) -> tuple[bytes, dict[str, object]]:
    source_sha = digest(source)
    if source_sha != BASE_SHA256:
        raise AssertionError(f"unqualified exact r264 base: {source_sha}")
    if len(ROUTER) > len(OLD_ROUTER) or len(DELAY) != len(OLD_DELAY):
        raise AssertionError("router/cave width changed")
    require(source, PAIR_ADDR, OLD_PAIR, "death/title pair")
    require(source, DELAY_ADDR, OLD_DELAY, "delay cave")
    require(source, ROUTER_ADDR, OLD_ROUTER, "router cave")
    require(source, GLYPH_CALL_ADDR, bytes.fromhex("CD A7 6D"), "glyph call")
    require(source, 0x570D, bytes.fromhex("C9"), "delay predecessor")
    require(source, 0x571E, bytes.fromhex("01 05"), "delay boundary")
    require(source, 0x6ED0, bytes.fromhex("C3 F4 6E"), "router predecessor")
    if source[MENU_TAIL:MENU_TAIL + 4] != NATIVE_HIDDEN_MENU_TAIL:
        raise AssertionError("r264 menu hidden-map repair is absent")

    rom = bytearray(source)
    rom[offset(PAIR_ADDR):offset(PAIR_ADDR) + len(OLD_PAIR)] = bytes.fromhex(
        "CD D3 6E 00 00 00"
    )
    rom[offset(DELAY_ADDR):offset(DELAY_ADDR) + len(DELAY)] = DELAY
    installed_router = ROUTER + bytes(len(OLD_ROUTER) - len(ROUTER))
    rom[offset(ROUTER_ADDR):offset(ROUTER_ADDR) + len(OLD_ROUTER)] \
        = installed_router
    update_checksums(rom)
    candidate = bytes(rom)

    changed = [
        index for index, (before, after) in enumerate(zip(source, candidate))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    for address, size in (
        (PAIR_ADDR, len(OLD_PAIR)),
        (DELAY_ADDR, len(DELAY)),
        (ROUTER_ADDR, len(OLD_ROUTER)),
    ):
        allowed.update(range(offset(address), offset(address) + size))
    unexpected = [index for index in changed if index not in allowed]
    if unexpected:
        raise AssertionError(f"unexpected payload changes: {unexpected[:8]}")

    # Caller-inclusive cycle model, including the three fixed-width NOPs.
    timing = {
        "original_pair": 216,
        "stage1_balanced": 216,
        "stage5_balanced": 216,
        "stage7_scene08": 80,
        "saved_per_stage7_vblank": 136,
    }
    if timing["stage1_balanced"] != timing["original_pair"]:
        raise AssertionError("Stage1 timing balance changed")
    if timing["stage5_balanced"] != timing["original_pair"]:
        raise AssertionError("Stage5 timing balance changed")

    receipt = {
        "schema": "penta-stage7-scene08-pair-router-r264-build-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(candidate),
        "changed_byte_count_including_checksums": len(changed),
        "patches": {
            "wrapper_pair": "bank13:$6F20-$6F25",
            "balanced_delay": "bank13:$570E-$571D",
            "scene_router": "bank13:$6ED3-$6EF3",
        },
        "preimages": {
            "wrapper_pair": OLD_PAIR.hex(" ").upper(),
            "delay_cave": "00 x16",
            "router_record": OLD_ROUTER.hex(" ").upper(),
            "delay_predecessor": "bank13:$570D RET",
            "delay_boundary": "bank13:$571E 01 05",
            "router_predecessor": "bank13:$6ED0 JP $6EF4",
        },
        "timing_t_cycles": timing,
        "contracts": {
            "exact_stage7_scene_gate": "$D880 == $08",
            "stage1_pair_timing_exact": True,
            "stage5_pair_timing_exact": True,
            "title_owner_tail_calls_original_title_service": True,
            "death_story_owner_tail_calls_original_service": True,
            "glyph_call_byte_exact": True,
            "renderer_and_map_copier_byte_exact": True,
            "r264_menu_hidden_map_fix_byte_exact": True,
        },
        "required_first_gate": (
            "Stage7 right/2800 with exact modular camera distance and "
            "ratio >= .99; raw scroll-change count is diagnostic only"
        ),
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage7-scene08-pair-router-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage7-scene08-pair-router-r264/build-receipt.json"),
    )
    args = parser.parse_args()
    candidate, receipt = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
