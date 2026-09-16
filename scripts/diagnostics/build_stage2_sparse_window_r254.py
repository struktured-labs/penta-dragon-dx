#!/usr/bin/env python3
"""Correct r253's Stage-2 sparse writer to the live-scrolling envelope.

The first static corpus missed vertical and far-right scroll phases.  The
8,000-frame display contract proves Stage-2 rare pickup tiles occupy packed
rows 0..3 and columns 8..21.  This replacement rewrites that complete 56-cell
window, including neutral cells so removed/moved pickups cannot trail.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_sparse_pickup_r113 import (
    ATOMIC_DEST,
    COMPILER_CONTINUATION,
    COMPILER_RESUME,
    HELPER_BANK,
    MARKER,
    POSTCOMPILER,
    STAGE,
    Asm,
    bank_offset,
    build_compiler_continuation as build_old_compiler,
    checksum,
    map_return,
)


BASE_SHA256 = "2750d602202dc754fb0e0d797b17f2b260e7a8f48e72e00eb4b0ec6c93099a15"


def build_compiler() -> bytes:
    a = Asm(COMPILER_CONTINUATION)
    a.db(0xF0, STAGE, 0xFE, 0x01)
    a.jr(0x20, "full")
    a.db(
        0xFA, MARKER & 0xFF, MARKER >> 8,
        0x4F,
        0xF0, ATOMIC_DEST,
        0xCB, 0x57,
    )
    a.jr(0x20, "map_9c")
    a.db(0x79, 0xCB, 0x47)
    a.jr(0x20, "sparse")
    a.db(0xCB, 0xC1)
    a.jr(0x18, "mark_full")
    a.label("map_9c")
    a.db(0x79, 0xCB, 0x4F)
    a.jr(0x20, "sparse")
    a.db(0xCB, 0xC9)
    a.label("mark_full")
    a.db(0x79, 0xEA, MARKER & 0xFF, MARKER >> 8)
    a.label("full")
    a.db(0xF3, 0x11, 0xA0, 0xC1, 0x21, 0x00, 0xD0)
    map_return(a, 1, COMPILER_RESUME)

    a.label("sparse")
    a.db(0xF0, 0x40, 0xCB, 0x7F)
    a.jr(0x28, "full")
    a.db(
        0xF3,
        0x11, 0xA8, 0xC1,                 # packed row 0, column 8
        0xF0, ATOMIC_DEST, 0xE6, 0xFE,
        0x67, 0x2E, 0x08,                 # physical map row 0, column 8
        0x06, 0xC6,
        0x3E, 0x01, 0xE0, 0x4F,
    )
    for row in range(4):
        for column in range(14):
            wait3 = f"r{row}_c{column}_wait3"
            wait0 = f"r{row}_c{column}_wait0"
            a.db(0x1A, 0x13, 0x4F, 0x0A, 0xF5)
            a.label(wait3)
            a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
            a.jr(0x20, wait3)
            a.label(wait0)
            a.db(0xF0, 0x41, 0xE6, 0x03)
            a.jr(0x20, wait0)
            a.db(0xF1, 0x22)
        if row != 3:
            # C1A0 has 24 cells/row: after cols 8..21, add 10.
            a.db(0x7B, 0xC6, 0x0A, 0x5F)
            a.jr(0x30, f"source_no_carry_{row}")
            a.db(0x14)
            a.label(f"source_no_carry_{row}")
            # VRAM has 32 cells/row: after cols 8..21, add 18.
            a.db(0x7D, 0xC6, 0x12, 0x6F)
            a.jr(0x30, f"dest_no_carry_{row}")
            a.db(0x24)
            a.label(f"dest_no_carry_{row}")
    a.db(0xAF, 0xE0, 0x4F)
    map_return(a, 1, POSTCOMPILER)
    return a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong r253 diagnostic base: {digest}")
    rom = bytearray(base)
    old = build_old_compiler()
    new = build_compiler()
    offset = bank_offset(HELPER_BANK, COMPILER_CONTINUATION)
    if rom[offset:offset + len(old)] != old:
        raise AssertionError("r253 sparse compiler preimage changed")
    if len(new) < len(old):
        raise AssertionError("unexpected compiler shrink")
    if rom[offset + len(old):offset + len(new)] != bytes([0xFF]) * (len(new) - len(old)):
        raise AssertionError("expanded compiler cave is not erased")
    rom[offset:offset + len(new)] = new
    checksum(rom)
    receipt = {
        "schema": "penta-stage2-sparse-window-r254-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "compiler_range": (
            f"bank{HELPER_BANK}:${COMPILER_CONTINUATION:04X}-"
            f"${COMPILER_CONTINUATION + len(new) - 1:04X}"
        ),
        "old_cells": 40,
        "new_cells": 56,
        "source_window": "rows 0..3, columns 8..21",
        "trail_policy": "rewrite all semantic and neutral cells",
        "live_failure_bound": (
            "r253 8000-frame mismatches were confined to this window"
        ),
    }
    return bytes(rom), receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
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
