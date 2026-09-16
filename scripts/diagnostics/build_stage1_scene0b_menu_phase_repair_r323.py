#!/usr/bin/env python3
"""Build r323: repair stale Scene-$0B runtime only while the menu is live.

The real low-health menu capture proves that converting DAD7 from its legacy
JP route to the current CALL route while the native menu is *closing* prevents
the following SELECT-open transition.  r323 leaves the legacy route intact
until the ordinary menu flag (FFE4) is set again, then performs the exact r313
repair and cache invalidation under DI.  The r320 atomic publisher is retained.

This is a controlled live experiment and remains non-promotable until every
visual and input gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_return_r321 as r321


ROOT = r321.ROOT
TMP = r321.TMP
BASE = r321.BASE
BASE_RECEIPT = r321.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-menu-phase-repair-r323/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-menu-phase-repair-r323/build-receipt.json"

REPAIR_ADDR = r321.r313.HANDLER_LABELS["repair"]
RESUME_ADDR = r321.r313.HANDLER_LABELS["resume"]
REPAIR_SIZE = RESUME_ADDR - REPAIR_ADDR
CAVE_ADDR = 0x6E50


def offset(address: int) -> int:
    return r321.bank_offset(r321.HANDLER_BANK, address)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    r321.validate_preimages(source, receipt_bytes)
    r313_handler = r321.HANDLER
    local_repair = REPAIR_ADDR - r321.HANDLER_ADDR
    repair = r313_handler[local_repair:local_repair + REPAIR_SIZE]
    if len(repair) != 24 or repair != bytes.fromhex(
        "F3 3E C4 EA DE DA 3E 13 EA DF DA 3E 00 EA E0 DA 3E FF EA 53 DF EA 57 DF"
    ):
        raise AssertionError("r313 repair stream drifted")
    # Test FFE4 only at the admitted stale-runtime repair site.  The no-menu
    # branch uses r313's untouched resume ABI and changes no game state.
    cave = bytes.fromhex("F0 E4 FE 01 C2") + RESUME_ADDR.to_bytes(2, "little") + repair + bytes((0xC3,)) + RESUME_ADDR.to_bytes(2, "little")
    if len(cave) != 34:
        raise AssertionError("r323 cave width changed")
    rom = bytearray(source)
    handler_offset = r321.handler_offset()
    rom[handler_offset:handler_offset + len(r313_handler)] = r313_handler
    repair_offset = offset(REPAIR_ADDR)
    rom[repair_offset:repair_offset + REPAIR_SIZE] = bytes((0xC3,)) + CAVE_ADDR.to_bytes(2, "little") + bytes(REPAIR_SIZE - 3)
    cave_offset = offset(CAVE_ADDR)
    if rom[cave_offset:cave_offset + len(cave)] != bytes([0xFF]) * len(cave):
        raise AssertionError("r323 cave preimage is not erased")
    rom[cave_offset:cave_offset + len(cave)] = cave
    r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r321.functional_offsets(source, candidate)
    allowed = set(range(handler_offset, handler_offset + len(r313_handler))) | set(range(cave_offset, cave_offset + len(cave)))
    if not changed <= allowed:
        raise AssertionError("r323 functional delta escaped handler/cave")
    if candidate[r321.r320.PRIMARY_ADDR:r321.r320.PRIMARY_END] != r321.r320.NEW_PRIMARY:
        raise AssertionError("r323 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r323 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-menu-phase-repair-r323-build-v1",
        "status": "STATIC_PASS_EXPERIMENT_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "stale_repair_gate": "FFE4 == 01 only",
            "no_menu_behavior": "exact r313 resume; legacy DAD7 remains live",
            "repair_behavior": "exact r313 DI/current-gateway/cache sequence",
            "cave": f"bank31:${CAVE_ADDR:04X}-${CAVE_ADDR + len(cave) - 1:04X}",
        },
        "functional_changed_bytes_from_r320": len(changed),
        "required_live_gates": ["menu round-trip", "visual frames", "north", "hazard", "speed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
