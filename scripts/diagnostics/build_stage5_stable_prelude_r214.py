#!/usr/bin/env python3
"""Build an exact-r210, fail-closed Stage-5 stable-prelude candidate.

The release prelude must still run for scene changes, palette-phase repairs,
room-publication repairs, and the item window.  This diagnostic adds a narrow
Stage-5-only return when every one of those owners says the frame is already
settled.  Any disagreement runs the original prelude from immediately after
its displaced scene-detect call.

This is intentionally an isolated candidate.  It is not promotable until the
Stage-5 speed, lava, room-transition, and menu/window gates all pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000

ENTRY_ADDR = 0x6E80
FRONT_ADDR = 0x570E
NORMAL_FINISH_JUMP_ADDR = 0x6ED0
GUARD_ADDR = 0x6ED3
SLOW_ADDR = 0x6EF4

OLD_ENTRY = bytes.fromhex("CD 90 6F")
OLD_FRONT = bytes(16)
OLD_FINISH_JUMP = bytes.fromhex("C3 F4 6E")
OLD_GUARD = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)
OLD_SLOW = bytes.fromhex("23 2B C3 2C 57")

# Entry front: only D880=$06 (Stage 5) is eligible.  The other scenes tail to
# the exact slow path.  The five-byte finish leaf displaced from $6EF4 follows
# immediately and remains the target of the normal window-maintenance path.
NEW_FRONT = bytes.fromhex(
    "FA 80 D8 FE 06 C2 F4 6E C3 D3 6E "
    "23 2B C3 2C 57"
)

# Stage-5 settled contract:
#   DF0D=$06  scene detector already published the Stage-5 table
#   DF02=$5A  neutral/lava table cold-copy sentinel is valid
#   DF4C!=$0C no later-stage BG0 palette repair is due
#   DF4F!=$A6 no room-publication promotion is due
#   LCDC.5=0 item/window maintenance is inactive
# Every failing JR lands at $6EF4.  Window-on falls through to the same leaf.
NEW_GUARD = bytes.fromhex(
    "FA 0D DF FE 06 20 1A "
    "FA 02 DF FE 5A 20 13 "
    "FA 4C DF FE 0C 28 0C "
    "FA 4F DF FE A6 28 05 "
    "F0 40 E6 20 C8"
)

# CALL scene_detect; JR $6E83.  The five-byte form deliberately ends before
# $6EF9, preserving the original Stage-5 phase NOP targeted by JR $6E9B.
NEW_SLOW = bytes.fromhex("CD 90 6F 18 8A")


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


def assert_preimage(source: bytes, address: int, expected: bytes, name: str) -> None:
    actual = source[offset(address):offset(address) + len(expected)]
    if actual != expected:
        raise SystemExit(
            f"{name} preimage moved at bank13:${address:04X}: "
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
    if source_sha != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {source_sha}")
    if len(source) != 32 * 0x4000:
        raise SystemExit(f"expected 512 KiB ROM, got {len(source)} bytes")
    if len(NEW_FRONT) != len(OLD_FRONT) or len(NEW_GUARD) != len(OLD_GUARD):
        raise SystemExit("candidate fragments changed their audited widths")

    for address, expected, name in (
        (ENTRY_ADDR, OLD_ENTRY, "prelude entry"),
        (FRONT_ADDR, OLD_FRONT, "arena-fragment unreachable tail"),
        (NORMAL_FINISH_JUMP_ADDR, OLD_FINISH_JUMP, "normal finish jump"),
        (GUARD_ADDR, OLD_GUARD, "unreachable prelude pad"),
        (SLOW_ADDR, OLD_SLOW, "prelude finish leaf"),
    ):
        assert_preimage(source, address, expected, name)

    # The guard region is unreachable in r210: the sole preceding live branch
    # is the asserted unconditional JP at $6ED0.  The front cave is immediately
    # after an asserted RET at $570D and immediately before live data at $571E.
    if source[offset(0x570D)] != 0xC9:
        raise SystemExit("front cave lost its RET predecessor")
    if source[offset(0x571E):offset(0x5720)] != bytes.fromhex("01 05"):
        raise SystemExit("front cave live-data boundary moved")
    if source[offset(0x6E9B):offset(0x6E9D)] != bytes.fromhex("30 5C"):
        raise SystemExit("Stage-5 phase branch moved")
    if source[offset(0x6EF9)] != 0x00:
        raise SystemExit("Stage-5 phase NOP moved")

    rom = bytearray(source)
    rom[offset(ENTRY_ADDR):offset(ENTRY_ADDR) + 3] = bytes.fromhex("C3 0E 57")
    rom[offset(FRONT_ADDR):offset(FRONT_ADDR) + 16] = NEW_FRONT
    rom[
        offset(NORMAL_FINISH_JUMP_ADDR):offset(NORMAL_FINISH_JUMP_ADDR) + 3
    ] = bytes.fromhex("C3 19 57")
    rom[offset(GUARD_ADDR):offset(GUARD_ADDR) + len(NEW_GUARD)] = NEW_GUARD
    rom[offset(SLOW_ADDR):offset(SLOW_ADDR) + len(NEW_SLOW)] = NEW_SLOW
    update_checksums(rom)
    candidate = bytes(rom)

    changed = [i for i, (a, b) in enumerate(zip(source, candidate)) if a != b]
    payload_changed = [i for i in changed if i not in (0x014D, 0x014E, 0x014F)]
    expected_ranges = (
        range(offset(ENTRY_ADDR), offset(ENTRY_ADDR) + 3),
        range(offset(FRONT_ADDR), offset(FRONT_ADDR) + 16),
        range(offset(NORMAL_FINISH_JUMP_ADDR), offset(NORMAL_FINISH_JUMP_ADDR) + 3),
        range(offset(GUARD_ADDR), offset(GUARD_ADDR) + len(NEW_GUARD)),
        range(offset(SLOW_ADDR), offset(SLOW_ADDR) + len(NEW_SLOW)),
    )
    expected_payload = {value for values in expected_ranges for value in values}
    if set(payload_changed) - expected_payload:
        raise SystemExit("candidate changed bytes outside the audited fragments")

    receipt = {
        "schema": "penta-stage5-stable-prelude-r214-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(candidate),
        "guard": {
            "scene": "D880 == $06",
            "scene_cache": "DF0D == $06",
            "cold_table_sentinel": "DF02 == $5A",
            "palette_repair": "DF4C != $0C",
            "room_repair": "DF4F != $A6",
            "window": "LCDC.5 == 0",
        },
        "fail_closed_target": "CALL $6F90; JR $6E83",
        "phase_nop_6ef9_preserved": candidate[offset(0x6EF9)] == 0,
        "normal_finish_preserved": candidate[offset(0x5719):offset(0x571E)].hex(),
        "payload_changed_bytes": len(payload_changed),
        "required_gates": [
            "Stage 5 strict speed >= 0.99 with exact scroll",
            "Stage 5 lava semantic equality and no pickup trails",
            "Stage 5 room-transition repair",
            "Stage 5 menu/window open-close",
            "guard negative controls for DF0D/DF02/DF4C/DF4F/LCDC",
            "all-stage speed matrix before promotion",
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
