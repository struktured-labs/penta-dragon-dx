#!/usr/bin/env python3
"""Build an exact-r210 Stage-5 stable-prelude candidate at the later-stage hook.

r214 intercepted the prelude before scene detection and changed title/level-
select cadence.  This revision leaves the entire entry and scene detector byte
exact.  It replaces only the later-stage BG0-repair CALL, where A is already
the live FFBA stage selector and the scene cache has already been reconciled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
HOOK_ADDR = 0x6E93
FRONT_ADDR = 0x570E
GUARD_ADDR = 0x6ED3

OLD_HOOK = bytes.fromhex("CD B8 69")
OLD_FRONT = bytes(16)
OLD_GUARD = bytes.fromhex(
    "18 00 18 00 18 00 18 00 18 00 18 00 18 00 18 00 "
    "18 00 18 00 18 00 18 00 00 00 00 00 00 00 00 00 00"
)

# A is FFBA at this hook.  Stage 5 enters the guard.  Every other later stage
# executes the displaced BG0 repair and resumes at the original continuation.
NEW_FRONT = bytes.fromhex(
    "FE 04 20 03 C3 D3 6E CD B8 69 C3 96 6E 00 00 00"
)

# The Stage-5 guard runs only after scene_detect has reconciled DF0D.  Stable
# frames may return directly to the VBlank wrapper when:
#   DF02=$5A  current dungeon/lava table is installed
#   DF4C!=$0C no BG0 palette repair phase is due
#   DF4F!=$A6 no room-publication promotion is due
#   LCDC.5=0  the item window is closed
# Any failure calls the exact displaced helper and rejoins at $6E96.
NEW_GUARD = bytes.fromhex(
    "FA 02 DF FE 5A 20 13 "
    "FA 4C DF FE 0C 28 0C "
    "FA 4F DF FE A6 28 05 "
    "F0 40 E6 20 C8 "
    "CD B8 69 C3 96 6E 00"
)


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
    if source_sha != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {source_sha}")
    if len(NEW_FRONT) != len(OLD_FRONT) or len(NEW_GUARD) != len(OLD_GUARD):
        raise SystemExit("candidate fragments changed their audited widths")
    require(source, HOOK_ADDR, OLD_HOOK, "later-stage BG0 CALL")
    require(source, FRONT_ADDR, OLD_FRONT, "arena-fragment unreachable tail")
    require(source, GUARD_ADDR, OLD_GUARD, "unreachable prelude pad")
    if source[offset(0x570D)] != 0xC9:
        raise SystemExit("front cave lost its RET predecessor")
    if source[offset(0x571E):offset(0x5720)] != bytes.fromhex("01 05"):
        raise SystemExit("front cave live-data boundary moved")
    if source[offset(0x6ED0):offset(0x6ED3)] != bytes.fromhex("C3 F4 6E"):
        raise SystemExit("guard cave lost its unconditional-JP predecessor")

    rom = bytearray(source)
    rom[offset(HOOK_ADDR):offset(HOOK_ADDR) + 3] = bytes.fromhex("C3 0E 57")
    rom[offset(FRONT_ADDR):offset(FRONT_ADDR) + 16] = NEW_FRONT
    rom[offset(GUARD_ADDR):offset(GUARD_ADDR) + 33] = NEW_GUARD
    update_checksums(rom)
    candidate = bytes(rom)

    changed = [i for i, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    for address, width in ((HOOK_ADDR, 3), (FRONT_ADDR, 16), (GUARD_ADDR, 33)):
        allowed.update(range(offset(address), offset(address) + width))
    if set(changed) - allowed:
        raise SystemExit("candidate changed bytes outside the audited fragments")

    receipt = {
        "schema": "penta-stage5-stable-prelude-r215-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(candidate),
        "r214_rejected": "pre-scene hook changed level-select cadence",
        "entry_and_scene_detect_byte_exact": True,
        "hook_contract": "A=FFBA after OR A; JP helper retains prelude caller frame",
        "stable_contract": [
            "FFBA == $04",
            "DF02 == $5A",
            "DF4C != $0C",
            "DF4F != $A6",
            "LCDC.5 == 0",
        ],
        "failure_path": "CALL $69B8; JP $6E96",
        "required_gates": [
            "Stage 5 strict speed >=0.99 and scroll 18/18",
            "Stage 5 lava/pickup semantic equality",
            "Stage 5 room transitions",
            "Stage 5 menu/window open-close",
            "guard mutation controls",
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
