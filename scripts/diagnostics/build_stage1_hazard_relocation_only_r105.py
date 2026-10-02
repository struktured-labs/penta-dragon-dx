#!/usr/bin/env python3
"""Build r105: isolate r101's classifier relocation on visual-safe r100.

r101 combined two independent changes: a bank-20 relocation of the alternate
hazard-phase classifier and an explicitly rejected room-$03 scanner bypass.
This diagnostic applies only the relocation.  In particular, the normal
``CALL $61B7`` scanner entry and all of its temporal prepublication remain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_hazard_fast_r101 as r101


BASE_SHA256 = "cef1338b9c834d29f2174bd9e1f90e76f1968701a2fd78bace11a52c9087b0b4"


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


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

    r101.patch(
        rom, r101.PRIVATE_BANK, r101.ROW0_FRONT_ADDR,
        bytes.fromhex(
            "CD 88 6C D2 9E 6D 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
        ),
        bytes.fromhex(
            "CD 88 6C D2 70 6B 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
        ),
    )
    r101.patch(
        rom, r101.PRIVATE_BANK, r101.PRIVATE_PHASE_LEAF_ADDR,
        bytes(5), bytes.fromhex("0E 00 C3 99 6D"),
    )

    # Retire exactly the four r100 fragments subsumed by the relocated body.
    # None of these caves is repurposed for a scanner bypass in this control.
    retired = (
        (0x61A0,
         bytes.fromhex("7D F6 08 6F 0E 0A C3 9B 61 1B 1B C3 A0 61")
         + bytes(1)),
        (0x6D9E,
         bytes.fromhex("13 1A CD 88 6C DA EF 6C C3 B5 6D") + bytes(6)),
        (0x6DB5,
         bytes.fromhex(
             "13 13 1A CD 88 6C DA F5 6C 13 1A CD 88 6C "
             "DA A9 61 C3 F6 61"
         )),
        (0x6CEF,
         bytes.fromhex("1B 1B 1B C3 CF 62 1B C3 A0 61") + bytes(3)),
    )
    for address, expected in retired:
        r101.patch(
            rom, r101.PRIVATE_BANK, address, expected, bytes(len(expected))
        )

    dispatcher = r101.build_bank20_dispatcher()
    r101.patch(
        rom, r101.HELPER_BANK, r101.HELPER_DISPATCH_ADDR,
        bytes([0xFF]) * len(dispatcher), dispatcher,
    )
    r101.patch(
        rom, r101.HELPER_BANK, r101.MAPPER_RETURN_ADDR,
        bytes.fromhex("C3 00 43"),
        bytes([
            0xC3,
            r101.HELPER_DISPATCH_ADDR & 0xFF,
            r101.HELPER_DISPATCH_ADDR >> 8,
        ]),
    )

    rom[0x014D] = 0
    # Header bytes are unchanged from r100, so restore its exact checksum.
    rom[0x014D] = source[0x014D]
    checksum = r101.global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    receipt = {
        "schema": "penta-stage1-hazard-relocation-only-r105-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "relocated_classifier": {
            "bank": r101.HELPER_BANK,
            "address": f"0x{r101.HELPER_DISPATCH_ADDR:04X}",
            "size": len(dispatcher),
            "bytes": dispatcher.hex(" "),
        },
        "scanner_contract": {
            "entry_call_retained": "bank19:$6BE7 CALL $61B7",
            "room03_bypass_installed": False,
            "temporal_prepublication_retained": True,
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
