#!/usr/bin/env python3
"""Admit the fully proved low-nibble camera domain on exact r273."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
OLD_HELPER_SHA256 = (
    "5da2866e88a520bd67fd18b984a1cf4b6c7f6c1cb8bf93402d6fadd64f8afebd"
)
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def viewport(scx: int, scy: int) -> set[tuple[int, int]]:
    first_column, first_row = scx // 8, scy // 8
    columns = 20 + bool(scx & 7)
    rows = 18 + bool(scy & 7)
    return {
        (first_row + row, first_column + column)
        for row in range(rows) for column in range(columns)
    }


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r273 base: {digest(base)}")
    helper_offset = 22 * 0x4000 + HELPER_ADDR - 0x4000
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != OLD_HELPER_SHA256:
        raise AssertionError("r273 helper changed")
    helper = bytearray(old_helper)
    addresses: list[int] = []
    for register in (0x43, 0x42):
        old = bytes((0xF0, register, 0xE6, 0xF3))
        new = bytes((0xF0, register, 0xE6, 0xF0))
        positions = [index for index in range(len(helper))
                     if helper.startswith(old, index)]
        if len(positions) != 2 or helper.count(new):
            raise AssertionError((register, positions, helper.count(new)))
        for position in positions:
            helper[position + 3] = 0xF0
            addresses.append(HELPER_ADDR + position + 3)

    cells = set().union(*(viewport(scx, scy)
                          for scx in range(16) for scy in range(16)))
    if max(row for row, _column in cells) != 19:
        raise AssertionError("visible row union exceeds r273 crop")
    if max(column for _row, column in cells) != 21:
        raise AssertionError("visible column union exceeds r273 crop")

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    allowed = {0x014D, 0x014E, 0x014F}
    allowed.update(helper_offset + address - HELPER_ADDR for address in addresses)
    if any(index not in allowed for index in changed):
        raise AssertionError("change escaped camera masks/checksums")

    receipt: dict[str, object] = {
        "schema": "penta-stage7-r274-low-nibble-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "helper_old_sha256": digest(old_helper),
        "helper_new_sha256": digest(helper),
        "changed_bytes_including_checksums": len(changed),
        "patched_immediates": [f"bank22:${address:04X} F3->F0"
                               for address in sorted(addresses)],
        "camera_proof": {
            "admitted_values_per_axis": list(range(16)),
            "rejected_values_per_axis": 240,
            "visible_rows": list(range(20)),
            "visible_columns": list(range(22)),
            "maximum_visible_row": 19,
            "maximum_visible_column": 21,
            "crop_exposures": 0,
        },
        "contracts": {
            "exact_r273_base": True,
            "entry_and_both_post_service_masks_changed_identically": True,
            "all_256_low_nibble_camera_pairs_inside_r273_crop": True,
            "all_high_nibble_values_rejected": True,
            "r273_compiler_transport_ffc1_and_menu_repairs_byte_exact": True,
        },
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path,
                        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "tmp/stage7-r274-low-nibble/candidate.gb")
    parser.add_argument("--receipt", type=Path,
                        default=ROOT / "tmp/stage7-r274-low-nibble/build-receipt.json")
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
