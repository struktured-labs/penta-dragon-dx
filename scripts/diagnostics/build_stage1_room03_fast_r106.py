#!/usr/bin/env python3
"""Build r106: exact scene-$02/room-$03 private scanner upper bound.

This default-off diagnostic retains r100 byte-for-byte outside a guarded CALL
dispatcher. Ordinary room $03 unwinds the original return/saved-HL stack and
returns to the common handoff before either the scanner or $55C0 predicates.
Scene $0A and every other room tail-enter the byte-exact r100 scanner.
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
GATE_ADDR = 0x6B6F
ROOM_ADDR = 0x6B7A
SCANNER_ADDR = 0x61B7

GATE = bytes.fromhex("CB 58 28 07 C3 B7 61 00")
ROOM = bytes.fromhex("F0 BD FE 03 C2 B7 61 C1 D1 C5 C9")


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
    for address, payload in ((GATE_ADDR, GATE), (ROOM_ADDR, ROOM)):
        off = offset(address)
        if rom[off:off + len(payload)] != bytes(len(payload)):
            raise AssertionError(f"diagnostic cave ${address:04X} changed")
        rom[off:off + len(payload)] = payload
    rom[call_off:call_off + 3] = bytes([
        0xCD, GATE_ADDR & 0xFF, GATE_ADDR >> 8,
    ])

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    receipt = {
        "schema": "penta-stage1-room03-fast-r106-static-v1",
        "status": "NON_PROMOTABLE_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": digest(source),
        "output_sha256": digest(rom),
        "guard": {
            "entry": "bank19:$6B6F",
            "ordinary_scene": "B bit3 clear",
            "room": "FFBD == $03",
            "fast_exit": "POP BC; POP DE; PUSH BC; RET",
            "scene0A": "JP $61B7",
            "other_rooms": "JP $61B7",
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
