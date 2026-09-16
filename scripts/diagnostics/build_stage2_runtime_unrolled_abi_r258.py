#!/usr/bin/env python3
"""Preserve BC across r257's mapper hop to the unrolled row compiler."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage2_runtime_sparse_r255 import (
    BANK,
    SPECIAL_BLOB,
    bank_offset,
    build_special_runtime,
    checksum,
)
from build_stage2_runtime_unrolled_r257 import (
    FULL_HELPER,
    build_full_helper,
    build_runtime,
)


BASE_SHA256 = "a92f5783c68cfe1954189277e723af1611185aee829a3497cf006abddfd073a4"


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong rejected-r257 base: {digest}")
    rom = bytearray(base)

    copy_length = len(build_special_runtime())
    old_runtime_active = build_runtime()
    old_runtime = old_runtime_active + bytes(copy_length - len(old_runtime_active))
    special_off = bank_offset(BANK, SPECIAL_BLOB)
    if rom[special_off:special_off + copy_length] != old_runtime:
        raise AssertionError("r257 runtime preimage changed")

    # The full-row route is the final mapper jump in the active runtime.
    map_tail = bytes.fromhex("01 00 4C C5 3E 15 C3 61 00")
    if not old_runtime_active.endswith(map_tail):
        raise AssertionError("r257 full-row mapper tail changed")
    # PUSH BC places the row LUT register beneath the mapper's synthetic
    # return. The mapper consumes only its own frame; bank21:$4C00 restores BC.
    new_runtime_active = old_runtime_active[:-len(map_tail)] + b"\xC5" + map_tail
    if len(new_runtime_active) > copy_length:
        raise AssertionError("BC-safe runtime exceeds installed copy length")
    new_runtime = new_runtime_active + bytes(copy_length - len(new_runtime_active))
    rom[special_off:special_off + copy_length] = new_runtime

    old_full = build_full_helper()
    full_off = bank_offset(BANK, FULL_HELPER)
    if rom[full_off:full_off + len(old_full)] != old_full:
        raise AssertionError("r257 full-helper preimage changed")
    if rom[full_off + len(old_full)] != 0xFF:
        raise AssertionError("one-byte full-helper growth cave is not erased")
    new_full = b"\xC1" + old_full  # POP BC before the exact 24-cell body
    rom[full_off:full_off + len(new_full)] = new_full

    checksum(rom)
    candidate = bytes(rom)
    report = {
        "schema": "penta-stage2-runtime-unrolled-abi-r258-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "runtime_copy_length_unchanged": copy_length,
        "runtime_stack_contract": [
            "CALL $D400 return remains deepest frame in SVBK3",
            "PUSH BC saves exact C600 LUT register",
            "mapper RET consumes only synthetic bank21:$4C00 frame",
            "bank21:$4C00 POP BC restores LUT before first cell",
            "final mapper RET consumes original CALL $D400 return in bank1",
        ],
        "full_helper_range": (
            f"bank{BANK}:${FULL_HELPER:04X}-${FULL_HELPER + len(new_full) - 1:04X}"
        ),
        "row_body_byte_exact_after_pop": new_full[1:-5] == old_full[:-5],
        "required_first_gate": "Stage2 8000-frame display semantic equality",
    }
    if not report["row_body_byte_exact_after_pop"]:
        raise AssertionError("row body changed while adding BC preservation")
    return candidate, report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-r257/candidate.gb"),
    )
    parser.add_argument(
        "--output", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-abi-r258/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-runtime-unrolled-abi-r258/build-receipt.json"),
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
