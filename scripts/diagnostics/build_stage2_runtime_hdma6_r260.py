#!/usr/bin/env python3
"""Publish six Stage-2 semantic rows with one 12-block HBlank DMA.

The semantically complete r259 window proved that rows 0..5 are required, but
84 one-cell HBlank waits cost about four percent.  This candidate instead lets
the qualified row compiler build six complete 32-byte staging rows at D000,
then transfers the contiguous 192 bytes to the exact physical BG map with one
12-block HBlank DMA.  Neutral cells and row padding are published as zero, so
pickup movement/removal cannot leave trails.
"""

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
    RESTORE_ENTRY,
    ROW_COUNT,
    ROW_READY,
    ROW_RUNTIME,
    SPECIAL_BLOB,
    STAGE,
    bank_offset,
    build_special_runtime,
    checksum,
    map_jump,
)
from build_stage2_runtime_unrolled_r257 import (
    FULL_HELPER,
    build_runtime as build_r257_runtime,
)


BASE_SHA256 = "b27af6124eb21c3dc387a78c4ff126e451d07c1dd1507ec8d32330070bf9d3c9"
PUBLISH_ENTRY = 0x5800
POSTCOMPILER = 0x4353


def r258_runtime_copy() -> bytes:
    old = build_r257_runtime()
    map_tail = bytes.fromhex("01 00 4C C5 3E 15 C3 61 00")
    if not old.endswith(map_tail):
        raise AssertionError("r257 runtime mapper tail changed")
    active = old[:-len(map_tail)] + b"\xC5" + map_tail
    length = len(build_special_runtime())
    return active + bytes(length - len(active))


def build_runtime() -> bytes:
    a = Asm(ROW_RUNTIME)
    a.db(0xF0, STAGE, 0xFE, 0x01)
    a.jr(0x20, "restore")

    # C = physical-map readiness; FFA5 is exact tagged destination $99/$9D.
    a.db(
        0xFA, ROW_READY & 0xFF, ROW_READY >> 8,
        0x4F,
        0xF0, ATOMIC_DEST,
        0xCB, 0x57,
    )
    a.jr(0x20, "map_9c")
    a.db(0x79, 0xCB, 0x41)
    a.jr(0x20, "ready")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC1, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("map_9c")
    a.db(0x79, 0xCB, 0x49)
    a.jr(0x20, "ready")
    a.db(0xF0, ROW_COUNT, 0xFE, 0x01)
    a.jr(0x20, "full_row")
    a.db(0xCB, 0xC9, 0x79, 0xEA, ROW_READY & 0xFF, ROW_READY >> 8)
    a.jr(0x18, "full_row")

    a.label("ready")
    # Calls with FFE0=24..19 compile rows 0..5 normally.  The next call sees
    # 18, discards its row-call frame, and publishes those six staged rows.
    a.db(0xF0, ROW_COUNT, 0xFE, 0x12)
    a.jr(0x20, "full_row")
    a.db(0xC1)
    map_jump(a, BANK, PUBLISH_ENTRY)

    a.label("restore")
    map_jump(a, BANK, RESTORE_ENTRY)

    a.label("full_row")
    # Save exact BC=C600+tile below the mapper's synthetic return.  The
    # ABI-correct bank21:$4C00 helper restores BC before its unrolled body.
    a.db(0xC5)
    map_jump(a, BANK, FULL_HELPER)
    return a.finish()


def build_publisher() -> bytes:
    a = Asm(PUBLISH_ENTRY)
    # Source: SVBK3:D000, six contiguous 32-byte rows = 12 DMA blocks.
    # Destination: exact physical map from tagged FFA5 ($99/$9D -> $98/$9C).
    a.db(
        0x3E, 0x01, 0xE0, 0x4F,           # VBK1
        0x3E, 0xD0, 0xE0, 0x51,           # HDMA1 = D0
        0xAF, 0xE0, 0x52,                 # HDMA2 = 00
        0xF0, ATOMIC_DEST, 0xE6, 0xFE,
        0xE0, 0x53,                        # HDMA3 = 98/9C
        0xAF, 0xE0, 0x54,                 # HDMA4 = 00
        0x3E, 0x8B, 0xE0, 0x55,           # 12 HBlank blocks
    )
    a.label("wait")
    a.db(0xF0, 0x55, 0xCB, 0x7F)
    a.jr(0x28, "wait")
    a.db(
        0xAF, 0xE0, 0x4F,                 # VBK0
        0x3E, 0x01, 0xE0, 0x70,           # restore stack's SVBK1
    )
    map_jump(a, 1, POSTCOMPILER)
    return a.finish()


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    digest = hashlib.sha256(base).hexdigest()
    if digest != BASE_SHA256:
        raise AssertionError(f"wrong ABI-correct r258 base: {digest}")
    rom = bytearray(base)

    old_runtime = r258_runtime_copy()
    runtime_off = bank_offset(BANK, SPECIAL_BLOB)
    if rom[runtime_off:runtime_off + len(old_runtime)] != old_runtime:
        raise AssertionError("r258 special-runtime preimage changed")
    active = build_runtime()
    if len(active) > len(old_runtime):
        raise AssertionError("HDMA runtime exceeds installed copy length")
    new_runtime = active + bytes(len(old_runtime) - len(active))
    rom[runtime_off:runtime_off + len(new_runtime)] = new_runtime

    publisher = build_publisher()
    publisher_off = bank_offset(BANK, PUBLISH_ENTRY)
    if rom[publisher_off:publisher_off + len(publisher)] != bytes([0xFF]) * len(publisher):
        raise AssertionError("HDMA publisher cave is not erased")
    rom[publisher_off:publisher_off + len(publisher)] = publisher
    checksum(rom)

    candidate = bytes(rom)
    report = {
        "schema": "penta-stage2-runtime-hdma6-r260-build-v1",
        "status": "static-pass-emulator-required",
        "base_sha256": digest,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "runtime_copy_length_unchanged": len(old_runtime),
        "active_runtime_size": len(active),
        "publisher_range": (
            f"bank{BANK}:${PUBLISH_ENTRY:04X}-${PUBLISH_ENTRY + len(publisher) - 1:04X}"
        ),
        "staged_rows": [0, 5],
        "staged_cells_per_row": 24,
        "zero_padding_per_row": 8,
        "dma_blocks": 12,
        "dma_command": "$8B HBlank",
        "exact_destination_source": "$FFA5 & $FE",
        "first_full_per_physical_map": True,
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
        default=Path("tmp/stage2-runtime-hdma6-r260/candidate.gb"),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage2-runtime-hdma6-r260/build-receipt.json"),
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
