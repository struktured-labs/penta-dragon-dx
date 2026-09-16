#!/usr/bin/env python3
"""Make r271's twentieth tile row conditional on the exact SCY domain."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "1eefb4bd7963928303ffe7dda9ff4875d6f438eda3721934b4fb439ae09e97e9"
HELPER_BANK = 22
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459
OLD_HELPER_SHA256 = (
    "b5720c19b184db7942ed333b1065402ca465dfd1e3b73d0ad49111758a157396"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return bank * 0x4000 + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def exposed_rows(scy: int) -> set[int]:
    first = scy // 8
    count = 18 + bool(scy & 7)
    return set(range(first, first + count))


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r271 base: {digest(base)}")
    domain = (0x00, 0x04, 0x08, 0x0C)
    row_counts = {scy: 20 if 19 in exposed_rows(scy) else 19 for scy in domain}
    if row_counts != {0x00: 19, 0x04: 19, 0x08: 19, 0x0C: 20}:
        raise AssertionError(row_counts)

    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != OLD_HELPER_SHA256:
        raise AssertionError("r271 helper changed")
    helper = bytearray(old_helper)

    def patch(address: int, old: bytes, new: bytes) -> None:
        if len(old) != len(new):
            raise AssertionError("patch width changed")
        position = address - HELPER_ADDR
        if helper[position:position + len(old)] != old:
            raise AssertionError(f"preimage moved at ${address:04X}")
        helper[position:position + len(new)] = new

    # r271's unconditional JP at $705A makes the following row-21 body dead.
    # Reuse that exact dead range for a no-stack phase-3 setup routine. It
    # chooses 20 descriptors only for SCY=0C, otherwise 19; then selects
    # SVBK2 immediately before returning by JP to the unchanged descriptor
    # setup. No CALL/RET/PUSH/POP executes after SVBK2 is selected.
    routine_address = 0x705D
    routine = bytes.fromhex(
        "F0 42 FE 0C 3E 14 28 01 3D E0 E0 3E 02 E0 70 C3 58 71"
    )
    dead_preimage = bytes(helper[
        routine_address - HELPER_ADDR:
        routine_address - HELPER_ADDR + len(routine)
    ])
    patch(routine_address, dead_preimage, routine)

    # Route phase3 setup to the dead-range routine while still in SVBK1.
    patch(0x7154, bytes.fromhex("3E 02 E0 70"), bytes.fromhex("C3 5D 70 00"))
    # The routine owns FFE0's descriptor count; retain instruction width.
    patch(0x715B, bytes.fromhex("3E 14 E0 E0"), bytes(4))

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    for address, length in (
        (routine_address, len(routine)), (0x7154, 4), (0x715B, 4),
    ):
        start = helper_offset + address - HELPER_ADDR
        allowed.update(range(start, start + length))
    if any(index not in allowed for index in changed):
        raise AssertionError("change escaped dynamic-row patches/checksums")

    receipt: dict[str, object] = {
        "schema": "penta-stage7-dynamic-last-row-r272-build-v1",
        "status": "STATIC_PASS_SPEED_DIAGNOSTIC_ONLY",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "helper_old_sha256": digest(old_helper),
        "helper_new_sha256": digest(helper),
        "changed_bytes_from_r271_including_checksums": len(changed),
        "routine": {
            "range": f"bank22:${routine_address:04X}-${routine_address + len(routine) - 1:04X}",
            "preimage_sha256": digest(dead_preimage),
            "sha256": digest(routine),
            "stack_operations": 0,
            "runs_before_svbk2_selection": True,
            "phase3_resume": "bank22:$7158",
        },
        "scy_truth_table": {
            f"${scy:02X}": {
                "visible_rows": sorted(exposed_rows(scy)),
                "tile_transfer_rows": row_counts[scy],
            }
            for scy in domain
        },
        "contracts": {
            "exact_r271_base": True,
            "only_scy_0c_transfers_row19": True,
            "every_potentially_visible_tile_row_transferred": True,
            "no_stack_operation_under_svbk2": True,
            "r271_attribute_crop_and_all_r269_guards_byte_exact": True,
            "r265_menu_repairs_byte_exact": True,
        },
        "required_first_gate": "Stage7 target6/patrol/2800 strict 0.99 speed",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-visible-rows-r271/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-dynamic-last-row-r272/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-dynamic-last-row-r272/build-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(arguments.base.read_bytes())
    for path, payload in (
        (arguments.output, candidate),
        (arguments.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
