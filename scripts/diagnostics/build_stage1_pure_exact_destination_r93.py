#!/usr/bin/env python3
"""Build the non-promotable r93 Stage-1 exact-destination experiment.

r92 proved that the cached pure-copy path can reach a vertical physical-map
flip whose rotating-hazard geometry changed without changing the four-byte
layout key.  The semantic scanner still runs, but its pure dispatcher throws
away the copier's exact H and reconstructs a map from DC0B.  At that boundary
DC0B names the peer map, leaving stale bank-1 tooth attributes on the map that
becomes visible.

The 24-row copier advances H by exactly three pages.  Preserve that already
live exact destination on the pure path by replacing ``LD H,$00`` plus its
padding with three ``DEC H`` instructions before entering the unchanged row
helper.  Dirty copies continue to use FFA5.  This experiment also includes
r92's measured Carry dirty signal so the strict speed gate can evaluate the
combined candidate; nothing here is production-qualified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_stage1_carry_dirty_signal import (
    BASE_SHA256,
    DIRTY_MARK_ADDR,
    DIRTY_MARK_PREIMAGE,
    DIRTY_MARK_REPLACEMENT,
    ENTRY_ADDR,
    ENTRY_PREIMAGE,
    ENTRY_REPLACEMENT,
    MAP_DONE_ADDR,
    MAP_DONE_PREIMAGE,
    MAP_DONE_REPLACEMENT,
    carry_contract,
    digest,
    global_checksum,
    replace_exact,
)


BANK_SIZE = 0x4000
STAGE1_BANK = 19
PURE_DISPATCH_ADDR = 0x6CD7
PURE_DISPATCH_PREIMAGE = bytes.fromhex("C1 26 00 C3 A8 6B 00")
PURE_DISPATCH_REPLACEMENT = bytes.fromhex("C1 25 25 25 C3 A8 6B")


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def exact_pure_destination(start_h: int) -> dict[str, object]:
    """Model the native 24 rows x 32-byte row stride and r93 handoff."""
    if start_h not in (0x98, 0x9C):
        raise ValueError(start_h)
    pointer = start_h << 8
    for _ in range(24):
        pointer = (pointer + 0x20) & 0xFFFF
    final_h = pointer >> 8
    restored_h = (final_h - 3) & 0xFF
    assert pointer & 0xFF == 0
    assert final_h in (0x9B, 0x9F)
    assert restored_h == start_h
    return {
        "start_h": f"0x{start_h:02X}",
        "rows": 24,
        "row_stride": "0x20",
        "final_h_before_postcopy": f"0x{final_h:02X}",
        "restored_h_after_dec_x3": f"0x{restored_h:02X}",
    }


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
    patches = [
        replace_exact(rom, ENTRY_ADDR, ENTRY_PREIMAGE, ENTRY_REPLACEMENT),
        replace_exact(
            rom, DIRTY_MARK_ADDR, DIRTY_MARK_PREIMAGE, DIRTY_MARK_REPLACEMENT
        ),
        replace_exact(
            rom, MAP_DONE_ADDR, MAP_DONE_PREIMAGE, MAP_DONE_REPLACEMENT
        ),
    ]

    pure_offset = bank_offset(STAGE1_BANK, PURE_DISPATCH_ADDR)
    actual = bytes(
        rom[pure_offset:pure_offset + len(PURE_DISPATCH_PREIMAGE)]
    )
    if actual != PURE_DISPATCH_PREIMAGE:
        raise AssertionError(
            f"bank {STAGE1_BANK}:${PURE_DISPATCH_ADDR:04X} preimage changed: "
            f"expected {PURE_DISPATCH_PREIMAGE.hex(' ')}, got "
            f"{actual.hex(' ')}"
        )
    rom[
        pure_offset:pure_offset + len(PURE_DISPATCH_REPLACEMENT)
    ] = PURE_DISPATCH_REPLACEMENT
    patches.append({
        "bank": STAGE1_BANK,
        "address": f"0x{PURE_DISPATCH_ADDR:04X}",
        "before": PURE_DISPATCH_PREIMAGE.hex(" "),
        "after": PURE_DISPATCH_REPLACEMENT.hex(" "),
    })

    destinations = [exact_pure_destination(value) for value in (0x98, 0x9C)]
    controls = [
        carry_contract(incoming=incoming, decision=decision)
        for incoming in (0, 1)
        for decision in (
            "pure_equal", "pure_cinematic", "pure_neutral", "dirty"
        )
    ]
    assert all(
        row["route"] == (
            "dirty_compile" if row["decision"] == "dirty"
            else "pure_postcopy"
        )
        for row in controls
    )

    # The pure dispatcher still discards exactly one synthetic mapper return
    # and enters after the row helper's own POP. The dirty dispatcher and
    # common FFA5-clearing return remain byte-exact.
    assert bytes(rom[pure_offset:pure_offset + 7]) == PURE_DISPATCH_REPLACEMENT
    dirty_dispatch = bank_offset(STAGE1_BANK, 0x6CCE)
    assert bytes(rom[dirty_dispatch:dirty_dispatch + 9]) == bytes.fromhex(
        "F0 A5 B7 28 04 67 C3 A7 6B"
    )
    common_return = bank_offset(STAGE1_BANK, 0x6C50)
    assert bytes(rom[common_return:common_return + 8]) == bytes.fromhex(
        "AF E0 A5 3E 01 C3 61 00"
    )

    checksum = global_checksum(rom)
    rom[0x014E] = checksum >> 8
    rom[0x014F] = checksum & 0xFF

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rom)
    receipt = {
        "status": "PASS_STATIC_EMULATOR_PENDING",
        "promotable": False,
        "base": str(args.base),
        "base_sha256": base_sha,
        "output": str(args.output),
        "output_sha256": digest(rom),
        "patches": patches,
        "pure_destination_contract": destinations,
        "carry_controls": controls,
        "timing": {
            "old_pure_dispatch_prefix_t_cycles": 12,
            "new_pure_dispatch_prefix_t_cycles": 16,
            "pure_postcopy_delta_t_cycles": 4,
            "mapdone_saving_vs_r90_t_cycles": 16,
            "net_pure_saving_vs_r90_t_cycles": 12,
        },
        "required_emulator_gates": [
            "failing low-health exact-destination fixture passes twice byte-exact",
            "strict Stage1 target0/right/2800 speed >= .98 with scroll parity",
            "menu event-anchored exact-destination mutation control",
        ],
        "global_checksum": f"{checksum:04x}",
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
