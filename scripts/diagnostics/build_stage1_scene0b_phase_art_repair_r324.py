#!/usr/bin/env python3
"""Build r324: phase-safe Scene-$0B repair plus canonical wall-art restore.

r323 proved the menu transition survives when the legacy DAD7 route remains
active until FFE4 says the native menu is live.  Its first full replay then
reached the independent corrupted-walls gate and correctly failed on the
known noncanonical signed BG art.  r324 adds r315's audited 256-byte GDMA art
mirror only to that phase-safe repair branch.  r320's atomic presentation leaf
is unchanged.

This remains a non-promotable candidate until all live visual/input gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_return_r321 as r321
import build_stage1_scene0b_chr_restore_r315 as r315


ROOT = r321.ROOT
TMP = r321.TMP
BASE = r321.BASE
BASE_RECEIPT = r321.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-phase-art-repair-r324/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-phase-art-repair-r324/build-receipt.json"

REPAIR_ADDR = r321.r313.HANDLER_LABELS["repair"]
RESUME_ADDR = r321.r313.HANDLER_LABELS["resume"]
REPAIR_SIZE = RESUME_ADDR - REPAIR_ADDR
ART_HELPER_ADDR = 0x6E50
CAVE_ADDR = 0x6EA0
ART_PAYLOAD_ADDR = 0x7000


def offset(address: int) -> int:
    return r321.bank_offset(r321.HANDLER_BANK, address)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require_erased(rom: bytearray, address: int, width: int, label: str) -> None:
    region = rom[offset(address):offset(address) + width]
    if region != bytes([0xFF]) * width:
        raise AssertionError(f"r324 {label} cave preimage changed")


def construct(source: bytes) -> tuple[bytes, dict]:
    r321.source_preimages(source)
    handler = r321.HANDLER
    local_repair = REPAIR_ADDR - r321.HANDLER_ADDR
    repair = handler[local_repair:local_repair + REPAIR_SIZE]
    if repair != bytes.fromhex(
        "F3 3E C4 EA DE DA 3E 13 EA DF DA 3E 00 EA E0 DA 3E FF EA 53 DF EA 57 DF"
    ):
        raise AssertionError("r313 repair stream drifted")
    art_payload = source[r315.ART_SOURCE_OFFSET:r315.ART_SOURCE_OFFSET + r315.ART_BYTES]
    if digest(art_payload) != r315.ART_PAYLOAD_SHA256:
        raise AssertionError("canonical signed art source identity changed")
    # No-menu: exact r313 resume with no state change.  Menu live: DI,
    # restore the canonical signed art, require exact GDMA completion, then
    # execute r313's current-gateway/cache repair unchanged.
    cave = (
        bytes.fromhex("F0 E4 FE 01 C2") + RESUME_ADDR.to_bytes(2, "little")
        + bytes((0xF3, 0xCD)) + ART_HELPER_ADDR.to_bytes(2, "little")
        + bytes((0xC2,)) + RESUME_ADDR.to_bytes(2, "little")
        + repair + bytes((0xC3,)) + RESUME_ADDR.to_bytes(2, "little")
    )
    if len(cave) != 41:
        raise AssertionError("r324 cave width changed")
    rom = bytearray(source)
    handler_offset = r321.handler_offset()
    rom[handler_offset:handler_offset + len(handler)] = handler
    repair_offset = offset(REPAIR_ADDR)
    rom[repair_offset:repair_offset + REPAIR_SIZE] = bytes((0xC3,)) + CAVE_ADDR.to_bytes(2, "little") + bytes(REPAIR_SIZE - 3)
    require_erased(rom, ART_HELPER_ADDR, len(r315.LCD_OFF_CANCEL_ART_HELPER), "art helper")
    require_erased(rom, CAVE_ADDR, len(cave), "phase repair")
    require_erased(rom, ART_PAYLOAD_ADDR, len(art_payload), "art payload")
    rom[offset(ART_HELPER_ADDR):offset(ART_HELPER_ADDR) + len(r315.LCD_OFF_CANCEL_ART_HELPER)] = r315.LCD_OFF_CANCEL_ART_HELPER
    rom[offset(CAVE_ADDR):offset(CAVE_ADDR) + len(cave)] = cave
    rom[offset(ART_PAYLOAD_ADDR):offset(ART_PAYLOAD_ADDR) + len(art_payload)] = art_payload
    r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r321.functional_offsets(source, candidate)
    allowed = (
        set(range(handler_offset, handler_offset + len(handler)))
        | set(range(offset(ART_HELPER_ADDR), offset(ART_HELPER_ADDR) + len(r315.LCD_OFF_CANCEL_ART_HELPER)))
        | set(range(offset(CAVE_ADDR), offset(CAVE_ADDR) + len(cave)))
        | set(range(offset(ART_PAYLOAD_ADDR), offset(ART_PAYLOAD_ADDR) + len(art_payload)))
    )
    if not changed <= allowed:
        raise AssertionError("r324 functional delta escaped owned ranges")
    if candidate[r321.r320.PRIMARY_ADDR:r321.r320.PRIMARY_END] != r321.r320.NEW_PRIMARY:
        raise AssertionError("r324 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r324 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-phase-art-repair-r324-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "stale_repair_gate": "FFE4 == 01 only",
            "art_restore": f"bank31:${ART_HELPER_ADDR:04X} GDMA $7000->$9100 256 bytes",
            "canonical_art_sha256": r315.ART_PAYLOAD_SHA256,
            "phase_repair_cave": f"bank31:${CAVE_ADDR:04X}-${CAVE_ADDR + len(cave) - 1:04X}",
        },
        "functional_changed_bytes_from_r320": len(changed),
        "required_live_gates": ["menu round-trip", "wall/CHR oracle", "visual frames", "north", "hazard", "speed"],
    }


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    r321.validate_preimages(source, receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({"schema": "penta-stage1-scene0b-phase-art-repair-r324-build-v1",
                    "status": "STATIC_PASS_EXPERIMENT_LIVE_GATES_REQUIRED"})
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


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
