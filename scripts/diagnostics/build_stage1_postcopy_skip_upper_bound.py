#!/usr/bin/env python3
"""Build a non-promotable Stage-1 post-copy throughput upper bound.

This diagnostic replaces only the relocated WRAM guard source copied from
bank 13:$5830 to $DBF1.  The replacement clears the consumed FFA5 latch and
returns, deliberately skipping every Stage-1 hazard scanner/repair.  It is
therefore useful only to measure whether the bank-19 post-copy round trip is
large enough to explain the remaining throughput deficit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BANK_SIZE = 0x4000
BASE_SHA256 = "9f5e9e2168ca1f4c56864a312f8267ef97fb92c886438a1e779b324886dc6a26"
GUARD_BANK = 13
GUARD_ADDR = 0x5830
GUARD_PREIMAGE = bytes.fromhex("F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10")
SKIP_GUARD = bytes.fromhex("AF E0 A5 C9") + bytes(8)


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    assert 0x4000 <= address < 0x8000
    return bank * BANK_SIZE + address - 0x4000


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    original = args.base.read_bytes()
    base_sha = digest(original)
    if base_sha != BASE_SHA256:
        raise SystemExit(
            f"base is not exact rejected r90: {base_sha} != {BASE_SHA256}"
        )
    rom = bytearray(original)
    offset = bank_offset(GUARD_BANK, GUARD_ADDR)
    before = bytes(rom[offset:offset + len(GUARD_PREIMAGE)])
    if before != GUARD_PREIMAGE:
        raise SystemExit(
            "relocated guard source preimage changed: " + before.hex(" ")
        )
    rom[offset:offset + len(SKIP_GUARD)] = SKIP_GUARD

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF
    assert bytes(rom[offset:offset + len(SKIP_GUARD)]) == SKIP_GUARD

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "status": "PASS_NON_PROMOTABLE",
        "purpose": "post-copy mapper/scanner upper bound only",
        "base": str(args.base),
        "base_sha256": base_sha,
        "output": str(args.output),
        "output_sha256": digest(rom),
        "patch": {
            "bank": GUARD_BANK,
            "address": f"0x{GUARD_ADDR:04X}",
            "before": before.hex(" "),
            "after": SKIP_GUARD.hex(" "),
        },
        "global_checksum": f"{checksum:04x}",
        "promotable": False,
        "known_semantic_loss": [
            "all Stage-1 rotating-hazard palette publication",
            "all Stage-1 seam and transition repair",
        ],
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
