#!/usr/bin/env python3
"""Make r277's Stage-7 helper row-pointer advance carry-selective.

The helper compiles twenty semantic rows from ``$D000`` through ``$D27F``.
Its existing nine-byte ``HL += 8`` sequence always pays for carry propagation;
the replacement pays for ``INC H`` only on the two rows whose low byte wraps.
The width-identical replacement pays for ``INC H`` only on the two rows whose
low byte wraps and rejoins at the unchanged loop counter at ``$6D04``.  There
are no renderer, DMA, palette, menu, router, or service changes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_SHA256 = "0c317aa69425ca3ca6f49b3e65a1671fb4fc4ee50d8b15d4900f12cf4493eb3f"
EXPECTED_CANDIDATE_SHA256 = (
    "1bb98e252995a4da9080bcc7aeeb27237762eb2d0713d9ed7e43409c978efd47"
)
BANK_SIZE = 0x4000
HELPER_BANK = 0x16
POINTER_ADVANCE_ADDR = 0x6CFB
REJOIN_ADDR = 0x6D04

OLD_POINTER_ADVANCE = bytes.fromhex("7D C6 08 6F 7C CE 00 67 00")
NEW_POINTER_ADVANCE = bytes.fromhex("7D C6 08 6F 30 03 24 18 00")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    if bank <= 0 or not 0x4000 <= address < 0x8000:
        raise AssertionError((bank, address))
    return bank * BANK_SIZE + address - 0x4000


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def pointer_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    old_total = 0
    new_total = 0
    pointer = 0xD000
    for row in range(20):
        # Each semantic row consumes 24 bytes before this advance executes.
        before = pointer + 24
        after = (before + 8) & 0xFFFF
        carry = (before & 0xFF) + 8 > 0xFF
        old_cycles = 36
        new_cycles = 40 if carry else 28
        rows.append({
            "row": row,
            "before_advance": f"${before:04X}",
            "carry": carry,
            "after_advance": f"${after:04X}",
            "old_cycles": old_cycles,
            "new_cycles": new_cycles,
        })
        old_total += old_cycles
        new_total += new_cycles
        pointer = after
    if pointer != 0xD280:
        raise AssertionError(f"unexpected terminal pointer ${pointer:04X}")
    if [row["row"] for row in rows if row["carry"]] != [7, 15]:
        raise AssertionError("carry-row proof changed")
    if (old_total, new_total) != (720, 584):
        raise AssertionError((old_total, new_total))
    return rows


def install(base: bytes) -> tuple[bytes, dict[str, object]]:
    base_sha = digest(base)
    if base_sha != BASE_SHA256:
        raise AssertionError(f"wrong exact r277 base: {base_sha}")
    if len(OLD_POINTER_ADVANCE) != 9 or len(NEW_POINTER_ADVANCE) != 9:
        raise AssertionError("pointer-advance patch must remain nine bytes")

    offset = bank_offset(HELPER_BANK, POINTER_ADVANCE_ADDR)
    actual = base[offset:offset + len(OLD_POINTER_ADVANCE)]
    if actual != OLD_POINTER_ADVANCE:
        raise AssertionError(
            f"helper preimage moved at bank{HELPER_BANK}:${POINTER_ADVANCE_ADDR:04X}: "
            f"{actual.hex()} != {OLD_POINTER_ADVANCE.hex()}"
        )
    if POINTER_ADVANCE_ADDR + len(NEW_POINTER_ADVANCE) != REJOIN_ADDR:
        raise AssertionError("replacement no longer ends at exact rejoin")

    rom = bytearray(base)
    rom[offset:offset + len(NEW_POINTER_ADVANCE)] = NEW_POINTER_ADVANCE
    update_checksums(rom)
    candidate = bytes(rom)
    candidate_sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_BOUND" \
            and candidate_sha != EXPECTED_CANDIDATE_SHA256:
        raise AssertionError(
            f"candidate identity drift: {candidate_sha} != "
            f"{EXPECTED_CANDIDATE_SHA256}"
        )

    allowed = set(range(offset, offset + len(OLD_POINTER_ADVANCE)))
    allowed.update((0x014D, 0x014E, 0x014F))
    changed = [index for index, pair in enumerate(zip(base, candidate))
               if pair[0] != pair[1]]
    unexpected = sorted(set(changed) - allowed)
    if unexpected:
        raise AssertionError(
            "unexpected changed offsets: "
            + ", ".join(f"0x{value:X}" for value in unexpected)
        )

    rows = pointer_rows()
    receipt: dict[str, object] = {
        "schema": "penta-stage7-pointer-advance-r278-build-v1",
        "status": "STATIC_PASS_SPEED_AND_LIVE_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": base_sha,
        "candidate_sha256": candidate_sha,
        "changed_bytes_including_checksums": len(changed),
        "patch": {
            "bank": HELPER_BANK,
            "address": f"${POINTER_ADVANCE_ADDR:04X}-${REJOIN_ADDR - 1:04X}",
            "file_offset": f"0x{offset:X}",
            "old_bytes": OLD_POINTER_ADVANCE.hex(" ").upper(),
            "new_bytes": NEW_POINTER_ADVANCE.hex(" ").upper(),
            "rejoin": f"${REJOIN_ADDR:04X}",
            "old_sha256": digest(OLD_POINTER_ADVANCE),
            "new_sha256": digest(NEW_POINTER_ADVANCE),
        },
        "cycle_proof": {
            "old_total_per_compile": 720,
            "new_total_per_compile": 584,
            "saved_per_compile": 136,
            "no_carry_rows": 18,
            "carry_rows": [7, 15],
            "rows": rows,
        },
        "contracts": {
            "exact_r277_base": True,
            "width_and_rejoin_unchanged": True,
            "terminal_hl_is_D280": True,
            "next_instruction_overwrites_a": "$6D04 LDH A,[$E0]",
            "following_instruction_overwrites_flags": "$6D06 DEC A",
            "router_and_stage5_isolation_byte_exact_to_r277": True,
            "vblank_services_byte_exact_to_r277": True,
            "dma_palette_menu_crop_and_pickup_bytes_unchanged": True,
        },
        "required_first_gates": [
            "Stage5 target4/right/2800 strict 0.99 speed",
            "Stage7 target6/right/2800 exact route measurement",
            "candidate-bound visual, menu, ABI, and containment gates",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/candidate.gb",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-pointer-advance-r278/candidate.gb",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=ROOT / "tmp/stage7-pointer-advance-r278/build-receipt.json",
    )
    arguments = parser.parse_args()
    candidate, receipt = install(arguments.base.read_bytes())
    for path, payload in (
        (arguments.output, candidate),
        (arguments.receipt, json.dumps(receipt, indent=2).encode() + b"\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
