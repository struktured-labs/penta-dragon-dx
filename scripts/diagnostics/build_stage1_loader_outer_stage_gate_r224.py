#!/usr/bin/env python3
"""Build exact-r210 FFBA-owned Stage-1 live-loader dispatch.

The wrapper currently gates on DCFD, which is nonzero in every live stage, and
the callee later rejects non-Stage-1 scenes.  This candidate gates the CALL on
FFBA==0 and moves the original DCFD live-route check into the callee.  The
attract route therefore remains rejected, while Stages 2-7 avoid the CALL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
BANK13 = 13 * 0x4000
WRAPPER_ADDR = 0x6F85
LOADER_ADDR = 0x6A0E
OLD_WRAPPER = bytes.fromhex("FA FD DC B7 C4 0E 6A")
NEW_WRAPPER = bytes.fromhex("F0 BA B7 CC 0E 6A 00")
OLD_LOADER_REGION = bytes.fromhex(
    "FA 5B DF E6 03 FE 03 C8 FA 80 D8 E6 F7 FE 02 C0 "
    "01 AA 6C C5 3E 13 C3 61 00 C9 00 00 00 00 00"
)
NEW_LOADER_REGION = bytes.fromhex(
    "FA FD DC B7 C8 "
    "FA 5B DF E6 03 FE 03 C8 "
    "FA 80 D8 E6 F7 FE 02 C0 "
    "01 AA 6C C5 3E 13 C3 61 00 00"
)


def off(a: int) -> int:
    return BANK13 + a - 0x4000


def sha(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def checksums(rom: bytearray) -> None:
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
    if len(OLD_WRAPPER) != len(NEW_WRAPPER):
        raise SystemExit("wrapper patch width changed")
    if len(OLD_LOADER_REGION) != len(NEW_LOADER_REGION):
        raise SystemExit("loader region width changed")
    if source[off(WRAPPER_ADDR):off(WRAPPER_ADDR) + len(OLD_WRAPPER)] != OLD_WRAPPER:
        raise SystemExit("wrapper loader-call preimage moved")
    if source[off(LOADER_ADDR):off(LOADER_ADDR) + len(OLD_LOADER_REGION)] != OLD_LOADER_REGION:
        raise SystemExit("loader region preimage moved")
    if source[off(LOADER_ADDR) + len(OLD_LOADER_REGION):off(LOADER_ADDR) + len(OLD_LOADER_REGION) + 3] != bytes.fromhex("EA 4E DF"):
        raise SystemExit("loader live boundary moved")

    rom = bytearray(source)
    rom[off(WRAPPER_ADDR):off(WRAPPER_ADDR) + 7] = NEW_WRAPPER
    rom[off(LOADER_ADDR):off(LOADER_ADDR) + len(NEW_LOADER_REGION)] = NEW_LOADER_REGION
    checksums(rom)
    candidate = bytes(rom)
    report = {
        "schema": "penta-stage1-loader-outer-stage-gate-r224-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": sha(source),
        "candidate_sha256": sha(candidate),
        "wrapper_contract": "CALL loader iff FFBA == 0",
        "loader_contract": "RET if DCFD == 0, phase rejected, or scene not Stage1/Gargoyle",
        "stage2_to_7": "no loader CALL",
        "attract": "FFBA0 CALL then DCFD0 RET before phase/scene/body",
        "stage1_live": "FFBA0 CALL, DCFD1, original phase+scene checks and body",
        "required_gates": [
            "Stage 6 >=0.99",
            "seven-stage speed matrix",
            "title and attract visual receipts",
            "opening and Stage1 hazard/menu/low-health receipts",
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
