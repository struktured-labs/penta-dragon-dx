#!/usr/bin/env python3
"""Extend r258's Stage-2 sparse window through live rows 4 and 5."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_runtime_sparse_r255 import (
    ATOMIC_DEST,
    Asm,
    BANK,
    MAPPER,
    SPECIAL_BLOB,
    bank_offset,
    checksum,
    map_jump,
)
from build_stage2_runtime_sparse_r256 import PROLOGUE
from build_stage2_runtime_unrolled_abi_r258 import install as install_r258
from build_stage2_runtime_unrolled_r257 import build_runtime
from build_stage2_runtime_sparse_r255 import build_special_runtime


BASE_SHA256 = "b27af6124eb21c3dc387a78c4ff126e451d07c1dd1507ec8d32330070bf9d3c9"
OLD_SPARSE_ENTRY = 0x4300
SPARSE_ENTRY = 0x5000
POSTCOMPILER = 0x4353


def build_sparse_helper() -> bytes:
    a = Asm(SPARSE_ENTRY)
    a.db(*PROLOGUE)
    a.db(
        0x11, 0xA8, 0xC1,                 # DE = packed row0,col8
        0xF0, ATOMIC_DEST, 0xE6, 0xFE,
        0x67, 0x2E, 0x08,                 # HL = exact map row0,col8
        0x06, 0xC6,                       # BC = C600 + tile ID
        0x3E, 0x01, 0xE0, 0x4F,           # VBK1
    )
    for row in range(6):
        for column in range(14):
            wait3 = f"r{row}_c{column}_wait3"
            wait0 = f"r{row}_c{column}_wait0"
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0x4F)
            a.label(wait3)
            a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
            a.jr(0x20, wait3)
            a.label(wait0)
            a.db(0xF0, 0x41, 0xE6, 0x03)
            a.jr(0x20, wait0)
            a.db(0x79, 0x22)
        if row != 5:
            a.db(0x7B, 0xC6, 0x0A, 0x5F)
            a.jr(0x30, f"src_ok_{row}")
            a.db(0x14)
            a.label(f"src_ok_{row}")
            a.db(0x7D, 0xC6, 0x12, 0x6F)
            a.jr(0x30, f"dst_ok_{row}")
            a.db(0x24)
            a.label(f"dst_ok_{row}")
    a.db(
        0xAF, 0xE0, 0x4F,
        0x3E, 0x01, 0xE0, 0x70,
    )
    map_jump(a, 1, POSTCOMPILER)
    return a.finish()


def r258_runtime_copy() -> bytes:
    """Recreate r258's 105-byte installed special-runtime source image."""

    old = build_runtime()
    map_tail = bytes.fromhex("01 00 4C C5 3E 15 C3 61 00")
    if not old.endswith(map_tail):
        raise AssertionError("r257 runtime mapper tail changed")
    active = old[:-len(map_tail)] + b"\xC5" + map_tail
    length = len(build_special_runtime())
    return active + bytes(length - len(active))


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong r258 base: {digest}")
    rom = bytearray(base)

    old_runtime = r258_runtime_copy()
    runtime_off = bank_offset(BANK, SPECIAL_BLOB)
    if rom[runtime_off:runtime_off + len(old_runtime)] != old_runtime:
        raise AssertionError("r258 special-runtime preimage changed")
    old_target = bytes((0x01, 0x00, 0x43, 0xC5, 0x3E, BANK, 0xC3, 0x61, 0x00))
    new_target = bytes((0x01, 0x00, 0x50, 0xC5, 0x3E, BANK, 0xC3, 0x61, 0x00))
    count = old_runtime.count(old_target)
    if count != 1:
        raise AssertionError(f"expected one sparse target, found {count}")
    new_runtime = old_runtime.replace(old_target, new_target, 1)
    rom[runtime_off:runtime_off + len(new_runtime)] = new_runtime

    sparse = build_sparse_helper()
    sparse_off = bank_offset(BANK, SPARSE_ENTRY)
    if rom[sparse_off:sparse_off + len(sparse)] != bytes([0xFF]) * len(sparse):
        raise AssertionError("six-row sparse-helper cave is not erased")
    rom[sparse_off:sparse_off + len(sparse)] = sparse
    checksum(rom)

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage2-runtime-window6-r259-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "sparse_helper_range": (
            f"bank{BANK}:${SPARSE_ENTRY:04X}-${SPARSE_ENTRY + len(sparse) - 1:04X}"
        ),
        "source_window": "packed rows 0..5, columns 8..21",
        "destination_window": "exact physical map rows 0..5, columns 8..21",
        "cells_per_publication": 84,
        "reason": "r258 display receipt observed rare pickups at rows 4 and 5",
        "unrolled_full_row_abi_unchanged": True,
        "required_first_gate": "Stage2 8000-frame display semantic equality",
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-abi-r258/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage2-runtime-window6-r259/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-runtime-window6-r259/build-receipt.json"),
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
