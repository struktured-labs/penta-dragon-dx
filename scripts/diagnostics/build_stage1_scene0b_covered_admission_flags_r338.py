#!/usr/bin/env python3
"""Build r338: preserve r335's exact post-copy flag ABI after the cover."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_covered_admission_r337 as r337

ROOT = r337.ROOT
TMP = r337.TMP
BASE = r337.BASE
BASE_RECEIPT = r337.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-covered-admission-flags-r338/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-covered-admission-flags-r338/build-receipt.json"


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    candidate, parent = r337.build(source, receipt_bytes)
    rom = bytearray(candidate)
    cave_offset = r337.r335.r331.o(r337.r335.r331.CAVE_ADDR)
    chunks = r337.r335.selected(source)
    r335_size = 1 + 14 * len(chunks) + r337.r335.r331.REPAIR_SIZE + 3
    r337_extra = 12 + 3
    cave_size = r335_size + r337_extra
    cave = bytearray(rom[cave_offset:cave_offset + cave_size])
    tail_size = r337.r335.r331.REPAIR_SIZE + 3
    insertion = len(cave) - tail_size
    if cave[insertion - 3:insertion] != bytes.fromhex("F1 E0 40"):
        raise AssertionError("r338 uncover sequence changed")
    # CP A recreates the exact Z=1,N=1,H=0,C=0 flags left by r335's final
    # DEC-B copy iteration, without changing the restored LCDC value in A.
    extended = cave[:insertion] + bytes((0xBF,)) + cave[insertion:]
    if rom[cave_offset + cave_size] != 0xFF:
        raise AssertionError("r338 flag-contract extension preimage changed")
    rom[cave_offset:cave_offset + len(extended)] = extended
    r337.r335.r331.r325.r324.r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    sha = hashlib.sha256(candidate).hexdigest()
    return candidate, {
        "schema": "penta-stage1-scene0b-covered-admission-flags-r338-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base_r337": parent["candidate_sha256"],
        "patch": {
            "window_cover": "retained",
            "post_copy_flags": "CP A => Z/N/H/C 1/1/0/0 before r313 repair",
        },
        "required_live_gates": parent["required_live_gates"],
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
