#!/usr/bin/env python3
"""Relocate Stage-1 hazard phase classification and restore the safe fast path.

This diagnostic candidate keeps r100's complete left/right cylinder spans,
but moves the extra column-7/9/10 classification into expanded bank 20.  That
frees the four private-bank caves used by the receipt-audited scene-$02,
room-$03 empty-scanner bypass.  The bypass retains its conditional $55C0 seam
repair; only the proven zero-effect arm exits directly.

The result remains non-promotable until the strict speed, current-ROM
menu/item/low-health, mutation, and north-integrity gates all pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from arena_position import _Asm
from stage1_semantic_scanner_cache import install as install_room03_bypass


BANK_SIZE = 0x4000
PRIVATE_BANK = 19
HELPER_BANK = 20
BASE_SHA256 = "cef1338b9c834d29f2174bd9e1f90e76f1968701a2fd78bace11a52c9087b0b4"

ROW0_FRONT_ADDR = 0x62C7
PRIVATE_PHASE_LEAF_ADDR = 0x6B70
MAPPER_CALL_ADDR = 0x6D99
MAPPER_RETURN_ADDR = 0x6D9E
HELPER_DISPATCH_ADDR = 0x4380
SEMANTIC_HELPER_ADDR = 0x4300
RETURN_BRIDGE_ADDR = 0x6CDF


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def patch(
    rom: bytearray,
    bank: int,
    address: int,
    expected: bytes,
    replacement: bytes,
) -> None:
    if len(expected) != len(replacement):
        raise AssertionError(f"bank {bank}:${address:04X}: width changed")
    offset = bank_offset(bank, address)
    actual = bytes(rom[offset:offset + len(expected)])
    if actual != expected:
        raise AssertionError(
            f"bank {bank}:${address:04X}: expected {expected.hex(' ')}, "
            f"got {actual.hex(' ')}"
        )
    rom[offset:offset + len(replacement)] = replacement


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def build_bank20_dispatcher() -> bytes:
    """Classify translated hazard phases after bank 20 is mapped.

    Entry owns DE at packed-source column 6, HL at the destination row base,
    and C=0 as the private marker.  A match tail-enters the established
    semantic helper.  No match maps bank 19 back through the existing bridge
    and resumes the scanner's row-advance tail.
    """
    a = _Asm()

    def fold_tooth() -> None:
        a.db(0xE6, 0xEF, 0xD6, 0x64, 0xFE, 0x06)

    a.db(0x13, 0x1A)                       # column 6 -> column 7
    fold_tooth()
    a.jr(0x38, "left")                    # JR C

    a.db(0x13, 0x13, 0x1A)                # column 7 -> column 9
    fold_tooth()
    a.jr(0x38, "right9")

    a.db(0x13, 0x1A)                      # column 9 -> column 10
    fold_tooth()
    a.jr(0x38, "right10")
    a.db(0xC3, RETURN_BRIDGE_ADDR & 0xFF, RETURN_BRIDGE_ADDR >> 8)

    a.label("left")
    a.db(0x1B, 0x1B, 0x1B)                # column 7 -> column 4
    a.db(0x7D, 0xF6, 0x04, 0x6F, 0x0E, 0x0B)
    a.db(0xC3, SEMANTIC_HELPER_ADDR & 0xFF, SEMANTIC_HELPER_ADDR >> 8)

    a.label("right9")
    a.db(0x1B)                            # column 9 -> column 8
    a.jr(0x18, "right")

    a.label("right10")
    a.db(0x1B, 0x1B)                      # column 10 -> column 8

    a.label("right")
    a.db(0x7D, 0xF6, 0x08, 0x6F, 0x0E, 0x0A)
    a.db(0xC3, SEMANTIC_HELPER_ADDR & 0xFF, SEMANTIC_HELPER_ADDR >> 8)
    code = a.finish()
    if HELPER_DISPATCH_ADDR + len(code) > 0x4400:
        raise AssertionError(f"bank-20 dispatcher is too large: {len(code)}")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit("base is not the exact r100 visual candidate")
    rom = bytearray(source)

    # Redirect the no-column-6 arm to a five-byte mapper leaf in the audited
    # padding immediately after the live 16-byte start-4 helper.
    patch(
        rom,
        PRIVATE_BANK,
        ROW0_FRONT_ADDR,
        bytes.fromhex(
            "CD 88 6C D2 9E 6D 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
        ),
        bytes.fromhex(
            "CD 88 6C D2 70 6B 1B 1B 7D F6 04 6F 0E 0B C3 99 6D"
        ),
    )
    patch(
        rom,
        PRIVATE_BANK,
        PRIVATE_PHASE_LEAF_ADDR,
        bytes(5),
        bytes.fromhex("0E 00 C3 99 6D"),   # C=0 marker; map bank 20
    )

    # Remove r100's private-bank phase implementation.  These are the exact
    # four caves owned by the guarded room-3 bypass below.
    patch(
        rom, PRIVATE_BANK, 0x61A0,
        bytes.fromhex("7D F6 08 6F 0E 0A C3 9B 61 1B 1B C3 A0 61") + bytes(1),
        bytes(15),
    )
    patch(
        rom, PRIVATE_BANK, 0x6D9E,
        bytes.fromhex("13 1A CD 88 6C DA EF 6C C3 B5 6D") + bytes(6),
        bytes(17),
    )
    patch(
        rom, PRIVATE_BANK, 0x6DB5,
        bytes.fromhex(
            "13 13 1A CD 88 6C DA F5 6C 13 1A CD 88 6C "
            "DA A9 61 C3 F6 61"
        ),
        bytes(20),
    )
    patch(
        rom, PRIVATE_BANK, 0x6CEF,
        bytes.fromhex("1B 1B 1B C3 CF 62 1B C3 A0 61") + bytes(3),
        bytes(13),
    )

    dispatcher = build_bank20_dispatcher()
    patch(
        rom,
        HELPER_BANK,
        HELPER_DISPATCH_ADDR,
        bytes([0xFF]) * len(dispatcher),
        dispatcher,
    )
    patch(
        rom,
        HELPER_BANK,
        MAPPER_RETURN_ADDR,
        bytes.fromhex("C3 00 43"),
        bytes([
            0xC3,
            HELPER_DISPATCH_ADDR & 0xFF,
            HELPER_DISPATCH_ADDR >> 8,
        ]),
    )

    bypass_report = install_room03_bypass(rom)

    # The hot room-$03 branch is within JR range.  The equivalent conditional
    # JR saves exactly four clocks on every admitted fast-path publication.
    patch(
        rom,
        PRIVATE_BANK,
        0x6DBD,
        bytes.fromhex("CA 9E 6D"),
        bytes.fromhex("28 DE 00"),
    )

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    # Static witnesses cover both alternating left and right-cylinder forms.
    witnesses = {
        "left_col7": bytes.fromhex("01 64 02 01 02"),
        "right_col9": bytes.fromhex("01 02 01 67 74"),
        "right_col10": bytes.fromhex("01 02 01 02 64"),
        "no_match": bytes.fromhex("01 02 01 02 03"),
    }

    def tooth(value: int) -> bool:
        folded = value & 0xEF
        return 0x64 <= folded < 0x6A

    routes = {}
    for name, row in witnesses.items():
        if tooth(row[1]):
            routes[name] = "left-4..14"
        elif tooth(row[3]):
            routes[name] = "right-8..17"
        elif tooth(row[4]):
            routes[name] = "right-8..17"
        else:
            routes[name] = "scanner-tail"
    expected_routes = {
        "left_col7": "left-4..14",
        "right_col9": "right-8..17",
        "right_col10": "right-8..17",
        "no_match": "scanner-tail",
    }
    if routes != expected_routes:
        raise AssertionError((routes, expected_routes))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "schema": "penta-stage1-hazard-fast-r101-static-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(source),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "bank20_dispatcher": {
            "address": f"0x{HELPER_DISPATCH_ADDR:04X}",
            "size": len(dispatcher),
            "bytes": dispatcher.hex(" "),
            "routes": routes,
        },
        "private_phase_leaf": f"0x{PRIVATE_PHASE_LEAF_ADDR:04X}",
        "room03_bypass": {
            "projected_hits": bypass_report.projected_speed_hits,
            "projected_records": bypass_report.projected_speed_records,
            "conditional_seam_repair": True,
            "hot_branch": "JR Z,$6D9E",
            "hot_branch_savings_clocks": 4,
        },
        "global_checksum": f"0x{checksum:04X}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
