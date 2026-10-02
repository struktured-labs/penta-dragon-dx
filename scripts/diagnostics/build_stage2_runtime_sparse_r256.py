#!/usr/bin/env python3
"""Restore SVBK1 before r255's long Stage-2 sparse publication loop.

r255 correctly isolated the Stage-2 publisher from the qualified r231 bank-1
path, but entered its 56-cell HBlank writer while SVBK3 was still selected.
That made ordinary game-state reads alias staging WRAM at frame boundaries.

This narrow diagnostic inserts ``LD A,$01; LDH [$FF70],A`` at the bank-21
sparse-helper entry.  The existing helper is shifted intact by four bytes, so
all of its relative branches and semantics remain byte-identical.  ROM code is
not affected by SVBK, and the synthetic mapper frame has already been consumed
before this entry, so restoring the stack's WRAM bank here is safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_runtime_sparse_r255 import (
    BANK,
    SPARSE_ENTRY,
    bank_offset,
    build_sparse_helper,
    checksum,
)


BASE_SHA256 = "ee26f49e1e6780571a802000bd2a7f8eb4326fcc1c8515a92829cb2bb52f9eb7"
PROLOGUE = bytes((0x3E, 0x01, 0xE0, 0x70))  # LD A,$01; LDH [$FF70],A


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong r255 base: {digest}")

    rom = bytearray(base)
    old_helper = build_sparse_helper()
    off = bank_offset(BANK, SPARSE_ENTRY)
    old_end = off + len(old_helper)
    if rom[off:old_end] != old_helper:
        raise AssertionError("r255 sparse-helper preimage changed")
    if rom[old_end:old_end + len(PROLOGUE)] != bytes([0xFF]) * len(PROLOGUE):
        raise AssertionError("four-byte sparse-helper growth cave is not erased")

    new_helper = PROLOGUE + old_helper
    rom[off:off + len(new_helper)] = new_helper
    checksum(rom)

    # Fail closed on the defining isolation contracts.
    if rom[off:off + len(PROLOGUE)] != PROLOGUE:
        raise AssertionError("SVBK1 prologue not installed")
    if rom[off + len(PROLOGUE):off + len(new_helper)] != old_helper:
        raise AssertionError("shifted sparse helper is not byte-identical")
    if rom[0x42EC:0x435B] != base[0x42EC:0x435B]:
        raise AssertionError("bank-1 compiler/postcopy path changed")

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage2-runtime-sparse-r256-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "change": "restore SVBK1 at bank21:$4300 before the sparse HBlank loop",
        "prologue_hex": PROLOGUE.hex(" ").upper(),
        "shifted_helper_range": (
            f"bank{BANK}:${SPARSE_ENTRY + len(PROLOGUE):04X}-"
            f"${SPARSE_ENTRY + len(new_helper) - 1:04X}"
        ),
        "bank1_compiler_byte_exact": True,
        "required_first_gate": (
            "Stage2 trace must show SVBK1 at bank21:$4304 and zero "
            "non-DMA scene mismatches"
        ),
    }
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-sparse-r255/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage2-runtime-sparse-r256/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-runtime-sparse-r256/build-receipt.json"),
    )
    args = parser.parse_args()

    candidate, report = install(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
