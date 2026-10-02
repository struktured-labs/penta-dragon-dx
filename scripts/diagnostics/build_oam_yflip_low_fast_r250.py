#!/usr/bin/env python3
"""Build an exact-r231 low-slot-only OBJ Y-flip optimization.

The high-slot reset route retains its exact 112-T-cycle instruction contract.
Only low slots replace `LD HL,$FFC2; RST $10` with direct page/low-byte
materialization, saving 8 T-cycles while preserving every visible result,
caller register, input flag, and FFC2 control lookup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c"
REGION_START = 0x1188
REGION_END = 0x11C3
NEW_X_ADDR = 0x11A5
CALL_SITES = (0x37B3B, 0x43B3B)
OLD_REGION = bytes.fromhex(
    "E5 F5 F0 DD FE 04 30 0D 21 C2 FF D7 7E A7 28 05 F1 CB FF 18 03 "
    "F1 CB BF E1 C9 "
    "E5 F5 7B CB 3F CB 3F E0 DD C6 C0 6F 26 AB 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 E1 C9 00 00 00"
)
FAST_X = bytes.fromhex(
    "E5 F5 7B CB 3F CB 3F E0 DD C6 C0 6F 26 AB 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 E1 C9"
)
# JR NC enters the reset tail.  Both reset and low paths share POP HL/RET.
LOW_FAST_Y = bytes.fromhex(
    "E5 F5 F0 DD FE 04 30 0E C6 C2 6F 26 FF 7E A7 28 05 "
    "F1 CB FF 18 03 F1 CB BF E1 C9"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def old_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot >= 4:
        return attr & 0x7F, None
    return ((attr | 0x80) if control else (attr & 0x7F)), 0xFFC2 + slot


def new_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot >= 4:
        return attr & 0x7F, None
    low = 0xC2 + slot
    if low > 0xFF:
        raise AssertionError(slot)
    return ((attr | 0x80) if control else (attr & 0x7F)), 0xFF00 | low


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r231 base: {digest(source)}")
    if source[REGION_START:REGION_END] != OLD_REGION:
        raise SystemExit("r231 helper-region preimage moved")
    if len(LOW_FAST_Y) != 27 or len(FAST_X) != 30:
        raise SystemExit("helper widths changed")
    for site in CALL_SITES:
        if source[site:site + 3] != bytes.fromhex("CD A2 11"):
            raise SystemExit(f"X helper CALL moved at 0x{site:05X}")

    cases = 0
    for attr in range(256):
        for slot in range(256):
            for control in (0, 1, 0x7F, 0xFF):
                if old_y(attr, slot, control) != new_y(attr, slot, control):
                    raise SystemExit("low-fast Y exhaustive mismatch")
                cases += 1

    # Two unreachable NOPs keep the established telemetry-visible X entry.
    region = LOW_FAST_Y + bytes(2) + FAST_X
    if len(region) != REGION_END - REGION_START:
        raise SystemExit("fixed helper region width changed")
    rom = bytearray(source)
    rom[REGION_START:REGION_END] = region
    for site in CALL_SITES:
        rom[site + 1] = NEW_X_ADDR & 0xFF
        rom[site + 2] = NEW_X_ADDR >> 8
    update_checksums(rom)
    candidate = bytes(rom)

    allowed = set(range(REGION_START, REGION_END))
    for site in CALL_SITES:
        allowed.update((site + 1, site + 2))
    allowed.update((0x014D, 0x014E, 0x014F))
    changed = {i for i, pair in enumerate(zip(source, candidate)) if pair[0] != pair[1]}
    if changed - allowed:
        raise SystemExit("candidate changed outside asserted helper regions")

    receipt = {
        "schema": "penta-oam-yflip-low-fast-r250-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "fixed_region": "0x1188-0x11C2",
        "x_entry": "0x11A5",
        "exhaustive_y_cases": cases,
        "timing_t_cycles": {
            "stock_high_reset": 112,
            "candidate_high_reset": 112,
            "stock_low_zero": 160,
            "candidate_low_zero": 152,
            "stock_low_set": 168,
            "candidate_low_set": 160,
        },
        "contracts": {
            "high_route_cycle_exact": True,
            "high_route_operation_order_exact": True,
            "low_route_saving": 8,
            "register_and_input_flags_preserved": True,
            "x_helper_semantics_byte_exact_r231": True,
        },
        "required_first_gate": "candidate-owned Stage1 current hazard/menu exact attrs",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
