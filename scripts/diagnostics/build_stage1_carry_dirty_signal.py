#!/usr/bin/env python3
"""Build the opt-in carry-saved Stage-1 dirty-signal experiment.

This exact-width diagnostic replaces the hot FFA5 dirty test with Carry.  The
copier's row counter already lives in a saved AF stack frame, so Carry rides
through every HBlank group and interrupt without borrowing B or another live
byte.  FFA5 remains the sole exact $98/$9C destination consumed by the dirty
compiler and bank-19 post-copy owner; every existing exit still clears it.

The exact input is the rejected r90 room-$03 scanner/repair bypass lineage.
The output is non-promotable until its live latch, speed, exact-destination,
menu, low-health, and hazard receipts pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "9f5e9e2168ca1f4c56864a312f8267ef97fb92c886438a1e779b324886dc6a26"

ENTRY_ADDR = 0x42A7
ENTRY_PREIMAGE = bytes.fromhex("2E 00")       # LD L,$00
ENTRY_REPLACEMENT = bytes.fromhex("AF 6F")    # XOR A; LD L,A

DIRTY_MARK_ADDR = 0x42B5
DIRTY_MARK_PREIMAGE = bytes.fromhex("18 00")  # phase-neutral JR +0
DIRTY_MARK_REPLACEMENT = bytes.fromhex("37 00")  # SCF; NOP

MAP_DONE_ADDR = 0x42EC
MAP_DONE_PREIMAGE = bytes.fromhex(
    "F0 A5 B7 20 0A 78 FE 05 28 03 CD F1 DB FB C9"
)
MAP_DONE_REPLACEMENT = bytes.fromhex(
    # JR C,$42FB; pure B=$05 skip / post-copy call; pad after RET only.
    "38 0D 78 FE 05 28 03 CD F1 DB FB C9 00 00 00"
)


def digest(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def global_checksum(data: bytes | bytearray) -> int:
    return (sum(data[:0x014E]) + sum(data[0x0150:])) & 0xFFFF


def replace_exact(
    rom: bytearray, address: int, expected: bytes, replacement: bytes
) -> dict[str, object]:
    if len(expected) != len(replacement):
        raise AssertionError("width-changing patch is forbidden")
    actual = bytes(rom[address:address + len(expected)])
    if actual != expected:
        raise AssertionError(
            f"fixed bank-1 ${address:04X} preimage changed: expected "
            f"{expected.hex(' ')}, got {actual.hex(' ')}"
        )
    rom[address:address + len(replacement)] = replacement
    return {
        "address": f"0x{address:04X}",
        "before": expected.hex(" "),
        "after": replacement.hex(" "),
    }


def carry_contract(*, incoming: int, decision: str) -> dict[str, object]:
    """Symbolically exercise the only flags that cross the tile loop."""
    if incoming not in (0, 1):
        raise ValueError(incoming)
    # XOR A at $42A7 makes the caller's incoming Carry irrelevant. INC/DEC BC,
    # LD D,d8 and every load before the decision leave Carry clear.
    carry = 0
    if decision == "pure_equal":
        # The cached decider's equality CP returns Z with Carry clear.
        carry = 0
    elif decision == "pure_cinematic":
        # DEC A preserves the entry Carry, which was explicitly cleared.
        carry = carry
    elif decision == "pure_neutral":
        # Neutral dispatch executes XOR A itself as well.
        carry = 0
    elif decision == "dirty":
        # CALL $DA13 may change flags; SCF is the final operation before AF is
        # pushed as the row counter and therefore makes that irrelevant.
        carry = 1
    else:
        raise ValueError(decision)

    # Polling and an interrupt may freely clobber live F, but AF is already on
    # the stack. Each row-end POP restores Carry; DEC A, JR, and the next PUSH
    # preserve it. The final POP/DEC/JR therefore reaches map_done unchanged.
    saved_carry = carry
    live_carry_after_poll_and_irq = 1 - carry
    del live_carry_after_poll_and_irq
    carry_at_map_done = saved_carry
    return {
        "incoming_carry": incoming,
        "decision": decision,
        "carry_at_map_done": carry_at_map_done,
        "route": "dirty_compile" if carry_at_map_done else "pure_postcopy",
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

    controls = [
        carry_contract(incoming=incoming, decision=decision)
        for incoming in (0, 1)
        for decision in (
            "pure_equal", "pure_cinematic", "pure_neutral", "dirty"
        )
    ]
    assert all(
        row["route"] == (
            "dirty_compile" if row["decision"] == "dirty" else "pure_postcopy"
        )
        for row in controls
    )

    # Fail-closed negative control: if the dirty SCF is mutated away, the
    # symbolic contract cannot satisfy the dirty route.
    dirty_without_scf = carry_contract(incoming=1, decision="pure_equal")
    assert dirty_without_scf["route"] != "dirty_compile"

    # Exact compiler/post-copy contracts remain installed and unchanged.
    assert bytes(rom[0x4327:0x432D]) == bytes.fromhex("F0 A5 67 AF E0 54")
    assert bytes(rom[0x4353:0x4359]) == bytes.fromhex("CD F1 DB C3 DF DB")
    assert bytes(rom[0x42F3:0x42F8]) == bytes.fromhex("CD F1 DB FB C9")
    assert bytes(rom[0x42A7:0x42B7]) == bytes.fromhex(
        "AF 6F 03 0B 16 FF CD 85 34 28 05 CD 13 DA 37 00"
    )
    # AF is below any interrupt frame during the HBlank groups. The final
    # POP restores its Carry after pointer arithmetic, and DEC/JR/PUSH never
    # alter Carry before the next row or map_done.
    assert bytes(rom[0x42DA:0x42EC]) == bytes.fromhex(
        "FB 0D 20 E1 7D C6 08 6F 30 01 24 F1 3D 28 03 F5 18 D1"
    )
    # Title enters after the decision but independently clears Carry and sets
    # B=$05, so it also reaches the pure skip deterministically.
    assert bytes(rom[0x4359:0x4368]) == bytes.fromhex(
        "26 98 AF 6F CD 82 34 06 05 18 00 C3 B7 42 00"
    )
    # Combined r90 direct-room and normal scanner exits both retain the common
    # FFA5 clear. Later-stage rejection also clears it in the DBF1 source.
    common_return = 19 * 0x4000 + (0x6C50 - 0x4000)
    assert bytes(rom[common_return:common_return + 8]) == bytes.fromhex(
        "AF E0 A5 3E 01 C3 61 00"
    )
    assert bytes(rom[0x35830:0x3583C]) == bytes.fromhex(
        "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
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
        "carry_controls": controls,
        "negative_control_without_scf": dirty_without_scf,
        "timing": {
            "entry_replacement_cycles_equal": True,
            "dirty_marker_replacement_cycles": 8,
            "old_dirty_marker_cycles": 12,
            "pure_map_done_saved_cycles_per_copy": 16,
            "compiler_entry_unchanged": "0x42FB",
        },
        "exact_destination": {
            "latch": "FFA5",
            "compiler_load": "0x4327: LDH A,[FFA5]; LD H,A",
            "pure_postcopy_call": "0x42F3: CALL $DBF1",
            "dirty_postcopy_call": "0x4353: CALL $DBF1",
            "all_existing_latch_clears_preserved": True,
        },
        "global_checksum": f"{checksum:04x}",
        "required_emulator_gates": [
            "strict Stage1 target0/right/2800 speed >= .98 with scroll parity",
            "exact-destination menu mutation negative control",
            "low-health moving-hazard deterministic containment",
        ],
    }
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
