#!/usr/bin/env python3
"""Patch a production image with the collision-safe three-way arena cache.

This is intentionally a candidate splicer: it changes only the three cold-boot
WRAM source fragments, installs the dedicated bank-20 key helper, and repairs
the cartridge header/checksums. A 256 KiB MBC1 diagnostic image is expanded to
512 KiB MBC5 so the same isolated helper can be tested without consuming native
layout data; an already-expanded v51 image is preserved in place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from arena_semantic_key import HELPER_BANK, HELPER_ENTRY, build_helper
from build_v302_title_fix import (
    ARENA_ATTR_SEMANTIC_COMPARE_ADDR,
    ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
    ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
    build_arena_attr_semantic_runtime,
)


BANK_SIZE = 0x4000
SOURCE_BANK = 13
ROM_SIZE = 32 * BANK_SIZE
PRODUCTION_ROM_SIZE = 16 * BANK_SIZE
SOURCE_CHUNKS = (
    (ARENA_ATTR_SEMANTIC_SIG_A_ADDR, 36),
    (ARENA_ATTR_SEMANTIC_SIG_B_ADDR, 36),
    (ARENA_ATTR_SEMANTIC_COMPARE_ADDR, 5),
)
LEGACY_TAIL_COPY = bytes.fromhex("21 FA 56 0E 05 CD B3 09")


def bank_offset(bank: int, address: int) -> int:
    return bank * BANK_SIZE + address - 0x4000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_checksum(data: bytes) -> int:
    value = 0
    for byte in data[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(data: bytes) -> int:
    return sum(data[:0x014E] + data[0x0150:]) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    source = args.source.read_bytes()
    if len(source) not in (PRODUCTION_ROM_SIZE, ROM_SIZE):
        parser.error(f"expected a 256/512 KiB image, got {len(source)} bytes")
    source_size = len(source)
    patched = bytearray(source)
    if source_size == PRODUCTION_ROM_SIZE:
        if patched[0x0147] != 0x03 or patched[0x0148] != 0x03:
            parser.error("expected a 256 KiB MBC1+RAM+battery diagnostic")
        patched.extend(bytes([0xFF]) * PRODUCTION_ROM_SIZE)
        patched[0x0147] = 0x1B             # MBC5 + RAM + battery
        patched[0x0148] = 0x04             # 512 KiB

    runtime = build_arena_attr_semantic_runtime()
    assert len(runtime) <= sum(length for _, length in SOURCE_CHUNKS)
    padded_runtime = runtime + bytes(77 - len(runtime))
    cursor = 0
    source_ranges = []
    for address, length in SOURCE_CHUNKS:
        offset = bank_offset(SOURCE_BANK, address)
        payload = padded_runtime[cursor:cursor + length]
        assert len(payload) == length
        patched[offset:offset + length] = payload
        source_ranges.append({
            "bank": SOURCE_BANK,
            "address": f"{address:04X}",
            "length": length,
        })
        cursor += length
    assert cursor == len(padded_runtime)

    # Receipt-lock the legacy installer locations. The candidate pads its
    # shorter runtime to the same 77 copied bytes, so neither count changes.
    installer_count_sites = []
    start = 0
    while True:
        found = source.find(LEGACY_TAIL_COPY, start)
        if found < 0:
            break
        installer_count_sites.append(found + 4)
        start = found + 1
    expected_installer_sites = (
        [0x35776] if source_size == PRODUCTION_ROM_SIZE
        else [0x35776, 0x41776]
    )
    if installer_count_sites != expected_installer_sites:
        parser.error(
            "unexpected legacy semantic installer sites: "
            + ", ".join(f"{site:06X}" for site in installer_count_sites)
        )

    helper = build_helper()
    helper_offset = bank_offset(HELPER_BANK, HELPER_ENTRY)
    helper_bank_start = HELPER_BANK * BANK_SIZE
    if bytes(patched[
        helper_bank_start:helper_bank_start + BANK_SIZE
    ]) != bytes([0xFF]) * BANK_SIZE:
        parser.error(f"expansion bank {HELPER_BANK} is not unused/FF")
    patched[helper_offset:helper_offset + len(helper)] = helper

    patched[0x014D] = header_checksum(patched)
    checksum = global_checksum(patched)
    patched[0x014E] = checksum >> 8
    patched[0x014F] = checksum & 0xFF

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)
    comparison_source = source + bytes(len(patched) - len(source))
    changed = [
        index for index, (before, after) in enumerate(zip(comparison_source, patched))
        if before != after
    ]
    report = {
        "status": "pass",
        "source": str(args.source),
        "source_sha256": sha256(source),
        "source_size": source_size,
        "output": str(args.output),
        "output_sha256": sha256(patched),
        "runtime_length": len(runtime),
        "runtime_sources": source_ranges,
        "installer_count_sites": [f"{site:06X}" for site in installer_count_sites],
        "helper": {
            "bank": HELPER_BANK,
            "address": f"{HELPER_ENTRY:04X}",
            "length": len(helper),
        },
        "changed_bytes": len(changed),
        "checksums": {
            "header": f"{patched[0x014D]:02X}",
            "global": f"{checksum:04X}",
        },
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
