#!/usr/bin/env python3
"""Build r327: install the complete canonical DA8E-DAFF runtime segment.

The authenticated stale capture has a pre-r305 resident runtime.  The r326
extension-only repair showed that DBF1-DBFC alone cannot make its DAD7 CALL
path input-safe.  r327 mirrors the installer-owned canonical DA8E-DAFF block
into bank31 and copies it to SVBK1 while executing outside that destination,
then runs r313's scoped cache invalidation.  r325's menu-art restore and
r320's atomic presentation leaf remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_art_phase_repair_r325 as r325
import build_stage1_scene0b_runtime_selfheal_r313 as r313
import build_stage1_bank16_installer_mirror_r307 as r307


ROOT = r325.ROOT
TMP = r325.TMP
BASE = r325.BASE
BASE_RECEIPT = r325.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-full-runtime-r327/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-full-runtime-r327/build-receipt.json"

REPAIR_ADDR = r313.HANDLER_LABELS["repair"]
RESUME_ADDR = r313.HANDLER_LABELS["resume"]
REPAIR_SIZE = RESUME_ADDR - REPAIR_ADDR
CAVE_ADDR = 0x6F00
PAYLOAD_ADDR = 0x7100
RUNTIME_SOURCE_ADDR = 0x7C4D
RUNTIME_DEST_ADDR = 0xDA8E
RUNTIME_BYTES = 0x72


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    return r325.r324.r321.bank_offset(bank, address)


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    base, base_receipt = r325.build(source, receipt_bytes)
    runtime = source[bank_offset(r307.CANONICAL_BANK, RUNTIME_SOURCE_ADDR):bank_offset(r307.CANONICAL_BANK, RUNTIME_SOURCE_ADDR) + RUNTIME_BYTES]
    if len(runtime) != RUNTIME_BYTES or runtime[0x50:0x53] != bytes.fromhex("C4 13 00"):
        raise AssertionError("canonical r305 DAD7 runtime source drifted")
    handler = r313.HANDLER
    local = REPAIR_ADDR - r313.HANDLER_ADDR
    repair = handler[local:local + REPAIR_SIZE]
    if repair != bytes.fromhex("F3 3E C4 EA DE DA 3E 13 EA DF DA 3E 00 EA E0 DA 3E FF EA 53 DF EA 57 DF"):
        raise AssertionError("r313 repair stream drifted")
    # DI; HL=bank31 payload; DE=SVBK1 DA8E; B=72; [HL+]->[DE+]; then exact repair.
    copy_loop = bytes((0xF3, 0x21)) + PAYLOAD_ADDR.to_bytes(2, "little") + bytes((0x11,)) + RUNTIME_DEST_ADDR.to_bytes(2, "little") + bytes((0x06, RUNTIME_BYTES, 0x2A, 0x12, 0x13, 0x05, 0x20, 0xFA))
    cave = copy_loop + repair + bytes((0xC3,)) + RESUME_ADDR.to_bytes(2, "little")
    rom = bytearray(base)
    repair_offset = r325.r324.offset(REPAIR_ADDR)
    cave_offset = r325.r324.offset(CAVE_ADDR)
    payload_offset = r325.r324.offset(PAYLOAD_ADDR)
    for off, width, label in ((cave_offset, len(cave), "copy cave"), (payload_offset, len(runtime), "runtime payload")):
        if rom[off:off + width] != bytes([0xFF]) * width:
            raise AssertionError(f"r327 {label} preimage is not erased")
    rom[repair_offset:repair_offset + REPAIR_SIZE] = bytes((0xC3,)) + CAVE_ADDR.to_bytes(2, "little") + bytes(REPAIR_SIZE - 3)
    rom[cave_offset:cave_offset + len(cave)] = cave
    rom[payload_offset:payload_offset + len(runtime)] = runtime
    r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    changed = r325.r324.r321.functional_offsets(source, candidate)
    base_changed = r325.r324.r321.functional_offsets(source, base)
    extra = changed - base_changed
    allowed = set(range(repair_offset, repair_offset + REPAIR_SIZE)) | set(range(cave_offset, cave_offset + len(cave))) | set(range(payload_offset, payload_offset + len(runtime)))
    if not extra <= allowed:
        raise AssertionError("r327 functional delta escaped runtime ownership")
    checked = bytearray(candidate)
    r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r327 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-full-runtime-r327-build-v1",
        "status": "STATIC_PASS_EXPERIMENT_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base_r325": base_receipt["candidate_sha256"],
        "patch": {"runtime": "SVBK1:$DA8E-$DAFF canonical r305", "source": "bank13:$7C4D-$7CBE mirrored bank31:$7100", "copy": "DI loop while PC is bank31", "r320_atomic_publisher": "unchanged", "r325_menu_art_restore": "retained"},
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
