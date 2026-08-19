#!/usr/bin/env python3
"""Install the source-built arena semantic helper in its dedicated ROM bank."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arena_semantic_key import (
    HELPER_BANK,
    HELPER_ENTRY,
    PENTA_SEAM_ENTRY,
    build_arena_postcopy_dispatcher,
    build_helper,
    build_penta_seam_helper,
)

from build_v302_title_fix import (
    ARENA_SANITIZER_DISPATCH_ADDR,
    BANK13,
    LAVA_ATTR_DECIDER_ADDR,
    STAGE1_ATOMIC_WRAP_ADDR,
    STAGE1_ATOMIC_WRAP_TAIL_ADDR,
    STAGE1_HAZARD_BANK0_MAP_ADDR,
    STAGE1_HAZARD_BANKED_ENTRY_ADDR,
    build_stage1_atomic_wrap,
    build_stage1_atomic_wrap_tail,
)


BANK_SIZE = 0x4000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_checksum(data: bytes | bytearray) -> int:
    value = 0
    for byte in data[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.candidate.read_bytes()
    if len(source) != 32 * BANK_SIZE:
        parser.error(f"expected a 512 KiB expanded ROM, got {len(source)} bytes")

    helper = build_helper()
    penta_seam = build_penta_seam_helper()
    postcopy_dispatcher = build_arena_postcopy_dispatcher()
    bank = bytearray([0xFF]) * BANK_SIZE
    helper_offset = HELPER_ENTRY - 0x4000
    bank[helper_offset:helper_offset + len(helper)] = helper
    seam_offset = PENTA_SEAM_ENTRY - 0x4000
    bank[seam_offset:seam_offset + len(penta_seam)] = penta_seam

    patched = bytearray(source)
    bank_start = HELPER_BANK * BANK_SIZE
    patched[bank_start:bank_start + BANK_SIZE] = bank
    postcopy_offset = BANK13 + LAVA_ATTR_DECIDER_ADDR - 0x4000
    existing_postcopy = source[
        postcopy_offset:postcopy_offset + len(postcopy_dispatcher)
    ]
    if existing_postcopy[3:] != bytes(len(existing_postcopy) - 3):
        raise AssertionError("arena post-copy dispatcher cave is not canonical")
    patched[
        postcopy_offset:postcopy_offset + len(postcopy_dispatcher)
    ] = postcopy_dispatcher
    banked_entry_offset = (
        BANK13 + STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000
    )
    established_entry = bytes([
        0xC3,
        ARENA_SANITIZER_DISPATCH_ADDR & 0xFF,
        ARENA_SANITIZER_DISPATCH_ADDR >> 8,
    ])
    if source[banked_entry_offset:banked_entry_offset + 3] != established_entry:
        raise AssertionError("arena post-copy banked entry is not canonical")
    patched[banked_entry_offset:banked_entry_offset + 3] = bytes([
        0xC3,
        LAVA_ATTR_DECIDER_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_ADDR >> 8,
    ])
    atomic_wrap = build_stage1_atomic_wrap()
    atomic_tail = build_stage1_atomic_wrap_tail()
    old_atomic_wrap = bytes.fromhex(
        "CD 42 08 FA 5A DF E0 FF 3E 01 BF D9"
    )
    if source[
        STAGE1_ATOMIC_WRAP_ADDR:
        STAGE1_ATOMIC_WRAP_ADDR + len(old_atomic_wrap)
    ] != old_atomic_wrap:
        raise AssertionError("arena atomic completion wrapper is not canonical")
    if source[
        STAGE1_ATOMIC_WRAP_TAIL_ADDR:
        STAGE1_ATOMIC_WRAP_TAIL_ADDR + len(atomic_tail)
    ] != bytes(len(atomic_tail)):
        raise AssertionError("arena atomic completion tail is not free")
    patched[
        STAGE1_ATOMIC_WRAP_ADDR:
        STAGE1_ATOMIC_WRAP_ADDR + len(atomic_wrap)
    ] = atomic_wrap
    patched[
        STAGE1_ATOMIC_WRAP_TAIL_ADDR:
        STAGE1_ATOMIC_WRAP_TAIL_ADDR + len(atomic_tail)
    ] = atomic_tail
    completion_gate = bytes.fromhex("FE 14 C0 3E 0D")
    old_completion_gate = bytes.fromhex("FE 03 D8 3E 0D")
    if source[
        STAGE1_HAZARD_BANK0_MAP_ADDR:
        STAGE1_HAZARD_BANK0_MAP_ADDR + len(old_completion_gate)
    ] != old_completion_gate:
        raise AssertionError("arena completion scene gate is not canonical")
    patched[
        STAGE1_HAZARD_BANK0_MAP_ADDR:
        STAGE1_HAZARD_BANK0_MAP_ADDR + len(completion_gate)
    ] = completion_gate
    patched[0x014D] = header_checksum(patched)
    checksum = global_checksum(patched)
    patched[0x014E:0x0150] = checksum.to_bytes(2, "big")

    changed = [
        offset
        for offset, (before, after) in enumerate(zip(source, patched, strict=True))
        if before != after
    ]
    allowed = (
        set(range(bank_start, bank_start + BANK_SIZE))
        | set(range(postcopy_offset, postcopy_offset + len(postcopy_dispatcher)))
        | set(range(banked_entry_offset, banked_entry_offset + 3))
        | set(range(
            STAGE1_ATOMIC_WRAP_ADDR,
            STAGE1_ATOMIC_WRAP_ADDR + len(atomic_wrap),
        ))
        | set(range(
            STAGE1_ATOMIC_WRAP_TAIL_ADDR,
            STAGE1_ATOMIC_WRAP_TAIL_ADDR + len(atomic_tail),
        ))
        | set(range(
            STAGE1_HAZARD_BANK0_MAP_ADDR,
            STAGE1_HAZARD_BANK0_MAP_ADDR + len(completion_gate),
        ))
        | {
        0x014D, 0x014E, 0x014F,
        }
    )
    if set(changed) - allowed:
        raise AssertionError("semantic-helper patch escaped bank 20/checksums")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    report = {
        "status": "pass",
        "source": str(args.candidate),
        "source_sha256": sha256(source),
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "bank": HELPER_BANK,
        "entry": f"{HELPER_ENTRY:04X}",
        "helper_size": len(helper),
        "penta_seam_entry": f"{PENTA_SEAM_ENTRY:04X}",
        "penta_seam_size": len(penta_seam),
        "arena_postcopy_dispatcher_size": len(postcopy_dispatcher),
        "arena_postcopy_banked_entry": f"{STAGE1_HAZARD_BANKED_ENTRY_ADDR:04X}",
        "arena_atomic_wrap": f"{STAGE1_ATOMIC_WRAP_ADDR:04X}",
        "arena_atomic_wrap_tail": f"{STAGE1_ATOMIC_WRAP_TAIL_ADDR:04X}",
        "arena_completion_scene_gate": f"{STAGE1_HAZARD_BANK0_MAP_ADDR:04X}",
        "bank_sha256": sha256(bank),
        "changed_bytes": len(changed),
        "checksums": {
            "header": f"{patched[0x014D]:02X}",
            "global": f"{checksum:04X}",
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
