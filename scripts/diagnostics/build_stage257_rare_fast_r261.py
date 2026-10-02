#!/usr/bin/env python3
"""Remove the unnecessary Stage-5/7 D400 copy from r260 scene entry."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_runtime_sparse_r255 import (
    Asm,
    BANK,
    MAPPER,
    ORIGINAL_BLOB,
    RARE_ENTRY,
    ROW_READY,
    ROW_RUNTIME,
    ROW_TEMP,
    SCENE_FLAG,
    SPECIAL_BLOB,
    bank_offset,
    build_rare_entry,
    build_special_runtime,
    checksum,
    copy_loop,
    original_row_helper,
)


BASE_SHA256 = "799b288c6adf2939672685121127c7f60fc0ff2eb00e3f1eb27f8b7d12d7bff7"


def build_rare_entry_fast(special_length: int) -> bytes:
    a = Asm(RARE_ENTRY)
    a.db(0xFA, SCENE_FLAG & 0xFF, SCENE_FLAG >> 8, 0xB7)
    a.jr(0x20, "runtime_ready")

    # Stage 2 only: install the special dispatcher and reset its private state.
    a.db(0x3E, 0x03, 0xE0, 0x70)
    copy_loop(a, SPECIAL_BLOB, ROW_RUNTIME, special_length, "copy_special")
    a.db(
        0xAF,
        0xEA, ROW_TEMP & 0xFF, ROW_TEMP >> 8,
        0xEA, ROW_READY & 0xFF, ROW_READY >> 8,
    )

    a.label("runtime_ready")
    # Stage 5/7 cold starts already own the original helper. If Stage 2's
    # dispatcher survives an unusual direct transition, its non-Stage-2 arm
    # restores the original helper on the first real compiler call.
    a.db(
        0x3E, 0x01, 0xE0, 0x70,
        0x21, 0xAE, 0xC6, 0x3E, 0x02, 0x22, 0x77,
        0x2E, 0xBE, 0x22, 0x77,
        0x2E, 0xC6, 0x22, 0x77,
        0x2E, 0xD6, 0x22, 0x77,
        0x3E, 0x0D, 0xC3, MAPPER & 0xFF, MAPPER >> 8,
    )
    return a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong qualified-r260 base: {digest}")
    rom = bytearray(base)

    special_length = len(build_special_runtime())
    old = build_rare_entry(special_length)
    new = build_rare_entry_fast(special_length)
    if len(new) > len(old):
        raise AssertionError("fast rare entry unexpectedly grew")
    off = bank_offset(BANK, RARE_ENTRY)
    if rom[off:off + len(old)] != old:
        raise AssertionError("r260 rare-entry preimage changed")
    rom[off:off + len(old)] = new + bytes(len(old) - len(new))
    checksum(rom)

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage257-rare-fast-r261-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "old_rare_entry_size": len(old),
        "new_rare_entry_size": len(new),
        "stage2_special_install_preserved": True,
        "stage5_stage7_lut_bytes_preserved": True,
        "removed_transition_work": "SVBK3 copy of 121-byte original D400 helper",
        "fail_closed_restore": (
            "surviving Stage2 dispatcher restores original D400 on first "
            "non-Stage2 compiler call"
        ),
        "required_first_gate": "Stage5 2800-frame exact-scroll speed",
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-hdma6-r260/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage257-rare-fast-r261/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage257-rare-fast-r261/build-receipt.json"),
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
