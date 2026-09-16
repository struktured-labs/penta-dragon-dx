#!/usr/bin/env python3
"""Remove only the rejected room-03 scanner bypass from tagged r95."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BANK = 19
BASE_SHA256 = "ba0df8b9165afc722b5d4df91ce77412d1f237ae8dec8ba367503024f620e476"


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return BANK * BANK_SIZE + address - 0x4000


def global_checksum(rom: bytes | bytearray) -> int:
    return (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    if digest(original) != BASE_SHA256:
        raise SystemExit("base is not exact tagged r95")
    rom = bytearray(original)

    patches = (
        (
            0x6BE3,
            bytes.fromhex("F3 AF E0 4F C3 B5 6D 00 00 00"),
            bytes.fromhex("F3 AF E0 4F CD B7 61 C3 50 6C"),
            "restore unconditional complete scanner call",
        ),
        (
            0x6DB5,
            bytes.fromhex(
                "CB 58 20 07 F0 BD FE 03 CA 9E 6D "
                "CD B7 61 C3 50 6C 00 00 00"
            ),
            bytes(20),
            "remove scene02/room03 bypass dispatcher",
        ),
        (
            0x61A0,
            bytes.fromhex(
                "FA 21 C3 CD 88 6C C9 CD C0 55 C3 50 6C 00 00"
            ),
            bytes(15),
            "remove first bypass classifier",
        ),
        (
            0x6D9E,
            bytes.fromhex(
                "CD A0 61 DA A7 61 CD EF 6C DA A7 61 "
                "E1 C3 50 6C 00"
            ),
            bytes(17),
            "remove bypass repair decision",
        ),
        (
            0x6CEF,
            bytes.fromhex("FA 5A C3 FE 01 37 C8 CD 88 6C C9") + bytes(2),
            bytes(13),
            "remove second bypass classifier",
        ),
    )

    patch_receipts = []
    for address, expected, replacement, label in patches:
        offset = bank_offset(address)
        actual = bytes(rom[offset:offset + len(expected)])
        if actual != expected:
            raise AssertionError(
                f"{label} ${address:04X}: expected {expected.hex(' ')}, "
                f"got {actual.hex(' ')}"
            )
        rom[offset:offset + len(replacement)] = replacement
        patch_receipts.append({
            "label": label,
            "bank": BANK,
            "address": f"0x{address:04X}",
            "offset": f"0x{offset:05X}",
            "before": expected.hex(" "),
            "after": replacement.hex(" "),
        })

    # Fail closed: the normal helper calls the full scanner, while every cave
    # allocated exclusively to the rejected experiment is empty again.
    expected_after = {address: replacement for address, _, replacement, _ in patches}
    for address, expected in expected_after.items():
        offset = bank_offset(address)
        assert bytes(rom[offset:offset + len(expected)]) == expected
    assert bytes(rom[bank_offset(0x6BE3):bank_offset(0x6BED)]) == bytes.fromhex(
        "F3 AF E0 4F CD B7 61 C3 50 6C"
    )
    for address, expected, _, _ in patches:
        offset = bank_offset(address)
        assert bytes(rom[offset:offset + len(expected)]) != expected

    # Both generated postcopy callsites own the same mapper stack ABI. Each
    # CALL $DBF1 leaves one caller return; the Stage-1 guard and $10E2 use JPs.
    # Mapper $0847's CALL $0061 returns locally, then CALL $6C80 leaves exactly
    # one synthetic $084D frame. Bank19's dispatcher JPs to the row helper,
    # whose leading POP BC consumes that frame. Its final JP $0061 returns
    # through the original $DBF1 caller frame ($42FA pure / $4357 dirty).
    assert bytes(rom[0x42F7:0x42FA]) == bytes.fromhex("CD F1 DB")
    assert bytes(rom[0x4354:0x4357]) == bytes.fromhex("CD F1 DB")
    guard_source = BANK_SIZE * 13 + 0x5830 - 0x4000
    assert bytes(rom[guard_source:guard_source + 12]) == bytes.fromhex(
        "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
    )
    assert bytes(rom[0x10E2:0x10E7]) == bytes.fromhex("3E 13 C3 47 08")
    assert bytes(rom[0x0847:0x0850]) == bytes.fromhex(
        "CD 61 00 CD 80 6C C3 61 00"
    )
    assert bytes(rom[bank_offset(0x6C80):bank_offset(0x6C83)]) == bytes.fromhex(
        "C3 CE 6C"
    )
    assert bytes(rom[bank_offset(0x6CCE):bank_offset(0x6CD6)]) == bytes.fromhex(
        "F0 A5 E6 FE 67 C3 A7 6B"
    )
    assert rom[bank_offset(0x6BA7)] == 0xC1
    assert bytes(rom[bank_offset(0x6C50):bank_offset(0x6C58)]) == bytes.fromhex(
        "AF E0 A5 3E 01 C3 61 00"
    )

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_FORBIDDEN_PENDING_COORDINATION",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": digest(original),
        "output": str(args.output),
        "output_sha256": digest(rom),
        "tagged_ffa5_preserved": True,
        "room03_scanner_bypass_absent": True,
        "full_scanner_call": "bank19:$6BE7 CALL $61B7",
        "bypass_caves_zero": ["$61A0/15", "$6CEF/13", "$6D9E/17", "$6DB5/20"],
        "tagged_dispatcher_stack_contract": {
            "pure_call": "$42F7 CALL $DBF1; original return $42FA",
            "dirty_call": "$4354 CALL $DBF1; original return $4357",
            "common_guard": "$DBF1 Stage1 arm JP $10E2 (no frame)",
            "mapper": (
                "$0847 CALL $0061 consumes its local $084A frame; "
                "$084A CALL $6C80 creates one synthetic $084D frame"
            ),
            "bank19_route": (
                "$6C80 JP $6CCE; tagged dispatcher JP $6BA7; leading "
                "POP BC consumes the sole synthetic $084D frame"
            ),
            "return": (
                "$6C50 JP $0061; mapper RET consumes the original "
                "$42FA/$4357 caller frame"
            ),
            "verdict": "pure and dirty each own exactly one synthetic frame",
        },
        "patches": patch_receipts,
        "global_checksum": f"{checksum:04x}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
