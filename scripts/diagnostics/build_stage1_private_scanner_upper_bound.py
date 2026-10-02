#!/usr/bin/env python3
"""Build a non-promotable r100 private-scanner upper-bound control.

The caller retains its DI/VBK preamble, CALL/return frame, transition repair,
and common postcopy handoff.  Only the 24-row scanner body is omitted.  This
ROM is a timing attribution control and must never be promoted or deployed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BANK = 19
BASE_SHA256 = "cef1338b9c834d29f2174bd9e1f90e76f1968701a2fd78bace11a52c9087b0b4"
CALL_ADDR = 0x6BE7
LEAF_ADDR = 0x6B6F
REPAIR_ADDR = 0x55C0


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def offset(address: int) -> int:
    return BANK * BANK_SIZE + address - 0x4000


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit("base is not exact visual-safe r100")
    rom = bytearray(source)

    call_off = offset(CALL_ADDR)
    if rom[call_off:call_off + 3] != bytes.fromhex("CD B7 61"):
        raise AssertionError("scanner CALL preimage changed")
    leaf_off = offset(LEAF_ADDR)
    if rom[leaf_off:leaf_off + 3] != bytes(3):
        raise AssertionError("diagnostic leaf preimage is not zero")

    # CALL still creates $6BEA above the saved completed-map base. $55C0's
    # opening POP BC / POP DE / PUSH BC therefore observes exactly the normal
    # scanner-tail stack and its RET lands at the unchanged common JP $6C50.
    rom[call_off:call_off + 3] = bytes([
        0xCD, LEAF_ADDR & 0xFF, LEAF_ADDR >> 8,
    ])
    rom[leaf_off:leaf_off + 3] = bytes([
        0xC3, REPAIR_ADDR & 0xFF, REPAIR_ADDR >> 8,
    ])

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    receipt = {
        "schema": "penta-stage1-private-scanner-upper-bound-v1",
        "status": "NON_PROMOTABLE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "output_sha256": digest(rom),
        "patch": {
            "caller": "bank19:$6BE7 CALL $6B6F",
            "leaf": "bank19:$6B6F JP $55C0",
            "scanner_body": "omitted",
            "call_frame_retained": True,
            "transition_repair_retained": True,
            "common_handoff_retained": True,
        },
        "global_checksum": f"0x{checksum:04X}",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
