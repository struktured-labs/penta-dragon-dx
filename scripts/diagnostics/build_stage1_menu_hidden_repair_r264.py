#!/usr/bin/env python3
"""Restore the native menu-close handoff on the exact r263 candidate.

The expanded menu-close tail forced a complete $9C00 publication while
$9C00 could already be the displayed BG map.  The semantic hazard writer then
painted 42 cells into visible VRAM over several HBlanks, producing hardware-
visible yellow trails and red/green wall artifacts even though the completed
map was byte-exact.  This isolated diagnostic restores the original native
tail so the normal double-buffered VBlank path performs the next publication
against the hidden map.

This builder is deliberately SHA- and preimage-bound.  It is not production
integration by itself; emulator receipts must prove zero semantic writes to
the active map, exact menu/item recovery, Stage-1 geometry, and speed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "ce860a51b1f3daa783c08244ff02d2dbf957aa19cd04d23a7c04be2c8392e8bd"
MENU_CLOSE_TAIL = 0x77A8
FORCED_VISIBLE_REPAIR = bytes.fromhex("CD A0 42 C9")
NATIVE_HIDDEN_HANDOFF = bytes.fromhex("AF E0 E4 C9")


def checksum(rom: bytearray) -> None:
    value = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E] = value >> 8
    rom[0x14F] = value & 0xFF


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong exact r263 base: {digest}")
    if base[MENU_CLOSE_TAIL:MENU_CLOSE_TAIL + 4] != FORCED_VISIBLE_REPAIR:
        raise AssertionError("menu-close forced-repair preimage changed")

    rom = bytearray(base)
    rom[MENU_CLOSE_TAIL:MENU_CLOSE_TAIL + 4] = NATIVE_HIDDEN_HANDOFF
    checksum(rom)
    candidate = bytes(rom)

    changed = [
        index for index, (old, new) in enumerate(zip(base, candidate))
        if old != new
    ]
    payload_changes = [index for index in changed if index not in (0x14E, 0x14F)]
    expected_payload = list(range(MENU_CLOSE_TAIL, MENU_CLOSE_TAIL + 3))
    if payload_changes != expected_payload:
        raise AssertionError(
            f"unexpected payload changes: {[hex(index) for index in payload_changes]}"
        )
    if candidate[MENU_CLOSE_TAIL:MENU_CLOSE_TAIL + 4] != NATIVE_HIDDEN_HANDOFF:
        raise AssertionError("native menu-close tail installation changed")

    report = {
        "schema": "penta-stage1-menu-hidden-repair-r264-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "changed_byte_count_including_checksums": len(changed),
        "payload_changed_offsets": [f"0x{index:05X}" for index in payload_changes],
        "old_tail": FORCED_VISIBLE_REPAIR.hex(" ").upper(),
        "new_tail": NATIVE_HIDDEN_HANDOFF.hex(" ").upper(),
        "old_behavior": "CALL $42A0; RET (can publish semantic attrs to visible $9C00)",
        "new_behavior": "XOR A; LDH [$FFE4],A; RET (native hidden-map handoff)",
        "required_first_gates": [
            "zero semantic hazard attribute writes to the active BG map",
            "menu item-use and close recovery with exact visible attributes",
            "low-health hazard stability",
            "Stage-1 entrance/wall geometry exact against OG",
            "Stage-1 and all-stage speed matrix",
        ],
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-isolated-entry-r263/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/build-receipt.json"),
    )
    args = parser.parse_args()

    candidate, receipt = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
