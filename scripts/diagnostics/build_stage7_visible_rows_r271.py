#!/usr/bin/env python3
"""Crop r269's Stage-7 hidden-map work to the exact visible row union.

The admitted primary publisher masks SCY to 00..0F.  Across that complete
domain a 160-pixel CGB viewport can touch only tile rows 0..19.  Rows 20..23
cannot become visible before the next guarded publication.  This diagnostic
therefore compiles/transfers 20 padded attribute rows, stages the ten odd tile
rows 1..19, and executes twenty two-block tile HDMAs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit_stage7_dual_plane_hdma_r264 as audit  # noqa: E402


BASE_SHA256 = "4abe94ee1d782c66c1ee79f5c45c5a0875f66ee384c60161db712bff17b87711"
R265_SHA256 = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
HELPER_BANK = 22
HELPER_ADDR = 0x6C80
HELPER_SIZE = 1459
R269_HELPER_SHA256 = (
    "bc81f4d6197304ddfdcb39265b5a234d5fb06ae86895c75fcc2f466354befebd"
)
VISIBLE_ROWS = 20
ATTR_BLOCKS = VISIBLE_ROWS * 2
ATTR_HDMA_COMMAND = 0x80 | (ATTR_BLOCKS - 1)
ATTR_GDMA_COMMAND = ATTR_BLOCKS - 1


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


def visible_row_union() -> set[int]:
    rows: set[int] = set()
    for scy in range(16):
        first = scy // 8
        count = 18 + bool(scy & 7)
        rows.update(range(first, first + count))
    return rows


def install(base: bytes, r265: bytes) -> tuple[bytes, dict[str, object]]:
    if digest(base) != BASE_SHA256:
        raise AssertionError(f"wrong exact r269 base: {digest(base)}")
    if digest(r265) != R265_SHA256:
        raise AssertionError(f"wrong exact r265 comparison: {digest(r265)}")
    if visible_row_union() != set(range(VISIBLE_ROWS)):
        raise AssertionError("low-nibble SCY visible-row union changed")

    stock_helper, labels = audit.build_helper()
    if digest(stock_helper) != audit.sha256(stock_helper):
        raise AssertionError("audit helper digest disagreement")
    helper_offset = bank_offset(HELPER_BANK, HELPER_ADDR)
    old_helper = base[helper_offset:helper_offset + HELPER_SIZE]
    if digest(old_helper) != R269_HELPER_SHA256:
        raise AssertionError("r269 helper changed")

    # r269 differs from the audited helper only at the two exact FFC1 guards.
    reverted = bytearray(old_helper)
    for position in (0x0F, 0x569):
        if reverted[position:position + 5] != bytes.fromhex("F0 C1 FE 02 D2"):
            raise AssertionError(f"r269 FFC1 guard moved: {position:#x}")
        reverted[position:position + 5] = bytes.fromhex("F0 C1 FE 01 C2")
    if bytes(reverted) != stock_helper:
        raise AssertionError("r269 helper differs beyond its FFC1 guards")

    helper = bytearray(old_helper)
    changes: list[dict[str, object]] = []

    def patch(address: int, old: bytes, new: bytes, reason: str) -> None:
        if len(old) != len(new):
            raise AssertionError("in-place patch changed width")
        position = address - HELPER_ADDR
        if helper[position:position + len(old)] != old:
            raise AssertionError(f"preimage moved at ${address:04X}")
        helper[position:position + len(new)] = new
        changes.append({
            "address": f"bank22:${address:04X}",
            "old": old.hex(" ").upper(),
            "new": new.hex(" ").upper(),
            "reason": reason,
        })

    # Attribute compiler row counter: 24 -> 20.
    patch(0x6CF5, b"\x18", bytes((VISIBLE_ROWS,)),
          "compile only the exact visible row union 0..19")

    # Rows 21 and 23 are the final two unrolled odd staging records.  Jump to
    # the unchanged VBK0/SVBK1 cleanup immediately before phase1_service.
    row21 = 0xC1A0 + 21 * 24
    row21_entry = stock_helper.find(
        bytes((0x11, row21 & 0xFF, row21 >> 8))
    ) + HELPER_ADDR
    cleanup = bytes.fromhex("AF E0 4F 3C E0 70 FB 00 F3")
    cleanup_positions = [
        index for index in range(len(stock_helper))
        if stock_helper.startswith(cleanup, index)
    ]
    phase1_cleanup = labels["phase1_service"] - 6
    if row21_entry != 0x705A or cleanup_positions[0] + HELPER_ADDR != phase1_cleanup:
        raise AssertionError((row21_entry, cleanup_positions, phase1_cleanup))
    patch(
        row21_entry,
        bytes((0x11, row21 & 0xFF, row21 >> 8)),
        bytes((0xC3, phase1_cleanup & 0xFF, phase1_cleanup >> 8)),
        "skip unreachable odd rows 21/23 and retain exact phase cleanup",
    )

    # One 40-block attribute transfer covers 20 complete padded 32-byte rows.
    patch(0x712F, b"\xAF", bytes((ATTR_HDMA_COMMAND,)),
          "LCD-on attribute HBlank DMA: 48 -> 40 blocks")
    patch(0x713C, b"\x2F", bytes((ATTR_GDMA_COMMAND,)),
          "LCD-off attribute GDMA: 48 -> 40 blocks")

    # Descriptor loop: rows 0..19 only. Each command remains exact $81.
    patch(0x715C, b"\x18", bytes((VISIBLE_ROWS,)),
          "tile descriptor count: 24 -> 20 visible rows")

    rom = bytearray(base)
    rom[helper_offset:helper_offset + HELPER_SIZE] = helper
    update_checksums(rom)
    candidate = bytes(rom)
    changed_indices = [
        index for index, (before, after) in enumerate(zip(base, candidate))
        if before != after
    ]
    allowed = {0x014D, 0x014E, 0x014F}
    for change in changes:
        address = int(str(change["address"]).split("$")[1], 16)
        allowed.update(range(
            helper_offset + address - HELPER_ADDR,
            helper_offset + address - HELPER_ADDR
            + len(bytes.fromhex(str(change["new"]))),
        ))
    if any(index not in allowed for index in changed_indices):
        raise AssertionError("change escaped visible-row patches/checksums")

    receipt: dict[str, object] = {
        "schema": "penta-stage7-visible-rows-r271-build-v1",
        "status": "STATIC_PASS_SPEED_DIAGNOSTIC_ONLY",
        "promotable": False,
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "helper_old_sha256": digest(old_helper),
        "helper_new_sha256": digest(helper),
        "changed_bytes_from_r269_including_checksums": len(changed_indices),
        "patches": changes,
        "viewport_proof": {
            "admitted_scy": [f"${value:02X}" for value in range(16)],
            "visible_row_union": [f"${value:02X}" for value in range(20)],
            "maximum_visible_row": 19,
            "cropped_rows": [20, 21, 22, 23],
            "rows_per_plane": VISIBLE_ROWS,
            "blocks_per_plane": ATTR_BLOCKS,
            "attribute_hdma_command": f"${ATTR_HDMA_COMMAND:02X}",
            "attribute_gdma_command": f"${ATTR_GDMA_COMMAND:02X}",
            "tile_hdma_commands": VISIBLE_ROWS,
            "tile_blocks": VISIBLE_ROWS * 2,
        },
        "conservative_savings_per_fast_publication_t": {
            "four_attribute_compile_rows": 4 * 1012,
            "two_odd_tile_staging_rows": 2 * 656 - 16,
            "eight_attribute_hblank_blocks_wall": 8 * 456,
            "eight_tile_hblank_blocks_wall": 8 * 456,
            "four_tile_intercommand_setups_minimum": 4 * 200,
        },
        "contracts": {
            "exact_r269_base": True,
            "all_potentially_visible_rows_compiled_and_transferred": True,
            "complete_32_byte_padded_width_retained": True,
            "primary_publisher_scy_low_nibble_proof_inherited": True,
            "ffc1_00_01_transition_guard_byte_exact": True,
            "all_other_guards_and_r265_menu_repairs_byte_exact": True,
            "helper_labels_and_length_unchanged": True,
        },
        "required_first_gate": "Stage7 target6/patrol/2800 strict 0.99 speed",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-transition-state-r269/candidate.gb",
    )
    parser.add_argument(
        "--r265", type=Path,
        default=ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-visible-rows-r271/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-visible-rows-r271/build-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(
        arguments.base.read_bytes(), arguments.r265.read_bytes()
    )
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
