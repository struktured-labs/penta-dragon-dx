#!/usr/bin/env python3
"""Use the exact unrolled row compiler behind r256's Stage-2 dispatcher.

r256 fixed the long sparse writer's WRAM-bank ownership, but its compact
counter-based full-row compiler still differs substantially from the qualified
r231 helper during Stage-2 loading.  This attribution candidate keeps r256's
Stage-1-safe dispatch and sparse path, while routing full-row calls to an exact
unrolled helper in expansion ROM.  The helper restores ROM bank 1 through the
native mapper instead of returning in bank 21.
"""

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
    ROW_RUNTIME,
    SPECIAL_BLOB,
    bank_offset,
    build_special_runtime,
    checksum,
    copy_loop,
    map_jump,
    original_row_helper,
)


BASE_SHA256 = "3ca7c592935133a3a153e412b9c9b25421d3c8fbd2c4542283e43a8af909d6f5"
FULL_HELPER = 0x4C00


def build_runtime() -> bytes:
    # This is r255's dispatcher with only the full_row implementation changed.
    from build_stage2_runtime_sparse_r255 import (
        ATOMIC_DEST,
        RESTORE_ENTRY,
        ROW_COUNT,
        ROW_READY,
        SPARSE_ENTRY,
        STAGE,
    )

    a = Asm(ROW_RUNTIME)
    a.db(0xF0, STAGE, 0xFE, 0x01)
    a.jr(0x20, "restore")
    a.db(
        0xFA, ROW_READY & 0xFF, ROW_READY >> 8,
        0x4F,
        0xF0, ATOMIC_DEST,
        0xCB, 0x57,
    )
    a.jr(0x20, "map_9c")
    a.db(0x79, 0xCB, 0x41)
    a.jr(0x20, "sparse")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC1, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("map_9c")
    a.db(0x79, 0xCB, 0x49)
    a.jr(0x20, "sparse")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC9, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("sparse")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x18)
    a.jr(0x20, "full_row")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "full_row")
    a.db(0xC1)
    map_jump(a, BANK, SPARSE_ENTRY)

    a.label("restore")
    map_jump(a, BANK, RESTORE_ENTRY)

    a.label("full_row")
    # Preserve the CALL $D400 return below the mapper's synthetic frame.
    map_jump(a, BANK, FULL_HELPER)
    return a.finish()


def build_full_helper() -> bytes:
    stock = original_row_helper()
    if stock[-1] != 0xC9:
        raise AssertionError("original row helper no longer ends in RET")
    # The mapper's RET consumes the original CALL $D400 return in SVBK3 and
    # resumes the qualified bank-1 compiler at $4329.
    return stock[:-1] + bytes((0x3E, 0x01, 0xC3, MAPPER & 0xFF, MAPPER >> 8))


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong r256 base: {digest}")
    rom = bytearray(base)

    old_runtime = build_special_runtime()
    new_runtime = build_runtime()
    if len(new_runtime) > len(old_runtime):
        raise AssertionError("replacement runtime unexpectedly grew")
    special_off = bank_offset(BANK, SPECIAL_BLOB)
    if rom[special_off:special_off + len(old_runtime)] != old_runtime:
        raise AssertionError("r256 special-runtime preimage changed")
    # Keep the rare-entry copy length byte-identical by padding to the old
    # installed length. Any fallthrough into padding remains fail-closed.
    padded_runtime = new_runtime + bytes(len(old_runtime) - len(new_runtime))
    rom[special_off:special_off + len(padded_runtime)] = padded_runtime

    full = build_full_helper()
    full_off = bank_offset(BANK, FULL_HELPER)
    if rom[full_off:full_off + len(full)] != bytes([0xFF]) * len(full):
        raise AssertionError("full-row ROM helper cave is not erased")
    rom[full_off:full_off + len(full)] = full
    checksum(rom)

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage2-runtime-unrolled-r257-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "runtime_copy_length_unchanged": len(old_runtime),
        "active_runtime_size": len(new_runtime),
        "full_helper_range": (
            f"bank{BANK}:${FULL_HELPER:04X}-${FULL_HELPER + len(full) - 1:04X}"
        ),
        "unrolled_cells": 24,
        "row_body_byte_exact": full[:-5] == original_row_helper()[:-1],
        "bank1_compiler_byte_exact_to_r256": (
            candidate[0x42EC:0x435B] == base[0x42EC:0x435B]
        ),
        "required_first_gate": "Stage2 800-frame exact-scene speed attribution",
    }
    if not report["row_body_byte_exact"] or not report["bank1_compiler_byte_exact_to_r256"]:
        raise AssertionError("static isolation contract failed")
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-sparse-r256/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-r257/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-r257/build-receipt.json"),
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
