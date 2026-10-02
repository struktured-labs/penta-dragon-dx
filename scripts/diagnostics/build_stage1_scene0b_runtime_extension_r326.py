#!/usr/bin/env python3
"""Build r326: install the omitted resident-runtime extension before DAD7.

The r325 replay proves the menu/art paths are clean while legacy DAD7 still
bypasses physical semantic publication.  Replacing only DAD7's JP with the
new CALL is insufficient because old serialized runtimes can lack the
installer-owned DBF1-DBFC extension.  r326 writes the canonical 12 bytes under
the same SVBK1/scene/FFB7 admission, then executes r313's exact DAD7 repair.
The menu-art restore and r320 atomic publisher are retained from r325.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_art_phase_repair_r325 as r325
import build_stage1_scene0b_runtime_selfheal_r313 as r313


ROOT = r325.ROOT
TMP = r325.TMP
BASE = r325.BASE
BASE_RECEIPT = r325.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-runtime-extension-r326/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-runtime-extension-r326/build-receipt.json"

REPAIR_ADDR = r313.HANDLER_LABELS["repair"]
RESUME_ADDR = r313.HANDLER_LABELS["resume"]
REPAIR_SIZE = RESUME_ADDR - REPAIR_ADDR
CAVE_ADDR = 0x6F00
EXTENSION_ADDR = 0xDBF1
EXTENSION = bytes.fromhex("F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    base, base_receipt = r325.build(source, receipt_bytes)
    rom = bytearray(base)
    handler_offset = r325.r324.r321.handler_offset()
    repair_offset = r325.r324.offset(REPAIR_ADDR)
    handler = r313.HANDLER
    local = REPAIR_ADDR - r313.HANDLER_ADDR
    repair = handler[local:local + REPAIR_SIZE]
    if repair != bytes.fromhex("F3 3E C4 EA DE DA 3E 13 EA DF DA 3E 00 EA E0 DA 3E FF EA 53 DF EA 57 DF"):
        raise AssertionError("r313 repair stream drifted")
    extension_writes = b"".join(
        bytes((0x3E, value, 0xEA, (EXTENSION_ADDR + i) & 0xFF, (EXTENSION_ADDR + i) >> 8))
        for i, value in enumerate(EXTENSION)
    )
    cave = bytes((0xF3,)) + extension_writes + repair + bytes((0xC3,)) + RESUME_ADDR.to_bytes(2, "little")
    cave_offset = r325.r324.offset(CAVE_ADDR)
    if rom[cave_offset:cave_offset + len(cave)] != bytes([0xFF]) * len(cave):
        raise AssertionError("r326 runtime-extension cave preimage is not erased")
    rom[repair_offset:repair_offset + REPAIR_SIZE] = bytes((0xC3,)) + CAVE_ADDR.to_bytes(2, "little") + bytes(REPAIR_SIZE - 3)
    rom[cave_offset:cave_offset + len(cave)] = cave
    r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r325.r324.r321.functional_offsets(source, candidate)
    base_changed = r325.r324.r321.functional_offsets(source, base)
    extra = changed - base_changed
    allowed = set(range(repair_offset, repair_offset + REPAIR_SIZE)) | set(range(cave_offset, cave_offset + len(cave)))
    if not extra <= allowed:
        raise AssertionError("r326 functional delta escaped repair ownership")
    if candidate[r325.r324.r321.r320.PRIMARY_ADDR:r325.r324.r321.r320.PRIMARY_END] != r325.r324.r321.r320.NEW_PRIMARY:
        raise AssertionError("r326 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r326 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-runtime-extension-r326-build-v1",
        "status": "STATIC_PASS_EXPERIMENT_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base_r325": base_receipt["candidate_sha256"],
        "patch": {
            "r320_atomic_publisher": "unchanged",
            "r325_menu_art_restore": "retained",
            "runtime_extension": f"SVBK1:${EXTENSION_ADDR:04X}-${EXTENSION_ADDR + len(EXTENSION) - 1:04X}",
            "extension_bytes": EXTENSION.hex(" ").upper(),
            "ordering": "extension before exact r313 DAD7 gateway/cache repair",
        },
        "functional_changed_bytes_from_r320": len(changed),
        "required_live_gates": ["full scene0B gate", "hazard", "north", "speed"],
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
