#!/usr/bin/env python3
"""Build an exact-r231 middle-cost OBJ Y-flip helper experiment.

r232's 32-T-cycle high-slot shortcut improved throughput but shifted the
Stage-1 hazard publisher enough to leave two final teeth neutral.  This
variant keeps r231's qualified X helper, uses a smaller shared-tail Y helper,
and permits zero to two 4-T-cycle NOPs on the high/reset tail.  It is a
diagnostic phase/cost sweep until the current-ROM hazard gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BASE_SHA256 = "1e51c4801bfbc8ff961b81e09958e7ce4ba55de0ec4f8644e36f897d6aebc09c"
REGION_START = 0x1188
REGION_END = 0x11C3
OLD_X_ADDR = 0x11A2
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


class Asm:
    """Minimal relative-branch assembler for the fixed helper region."""

    def __init__(self, base: int) -> None:
        self.base = base
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def db(self, *values: int) -> None:
        self.code.extend(value & 0xFF for value in values)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise AssertionError(name)
        self.labels[name] = self.base + len(self.code)

    def jr(self, opcode: int, label: str) -> None:
        self.db(opcode, 0)
        self.fixups.append((len(self.code) - 1, label))

    def finish(self) -> bytes:
        for operand, label in self.fixups:
            delta = self.labels[label] - (self.base + operand + 1)
            if not -128 <= delta <= 127:
                raise AssertionError((label, delta))
            self.code[operand] = delta & 0xFF
        return bytes(self.code)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build_y(high_nops: int) -> bytes:
    a = Asm(REGION_START)
    a.db(0xF5, 0xF0, 0xDD, 0xFE, 0x04)  # PUSH AF; LDH A,[DD]; CP 4
    a.jr(0x38, "low")                   # JR C,low
    a.label("reset")
    a.db(0xF1, 0xCB, 0xBF)              # POP AF; RES 7,A
    a.db(*([0x00] * high_nops))
    a.db(0xC9)
    a.label("low")
    a.db(0xE5, 0x21, 0xC2, 0xFF, 0xD7, 0x7E, 0xA7, 0xE1)
    a.jr(0x20, "set")                   # JR NZ,set
    a.jr(0x18, "reset")                 # zero shares reset tail
    a.label("set")
    a.db(0xF1, 0xCB, 0xFF, 0xC9)        # POP AF; SET 7,A; RET
    return a.finish()


def old_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot >= 4:
        return attr & 0x7F, None
    return ((attr | 0x80) if control else (attr & 0x7F)), 0xFFC2 + slot


def new_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot < 4:
        return ((attr | 0x80) if control else (attr & 0x7F)), 0xFFC2 + slot
    return attr & 0x7F, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--high-nops", type=int, choices=range(3), required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    if digest(source) != BASE_SHA256:
        raise SystemExit(f"unqualified exact r231 base: {digest(source)}")
    if source[REGION_START:REGION_END] != OLD_REGION:
        raise SystemExit("r231 helper-region preimage moved")
    for site in CALL_SITES:
        if source[site:site + 3] != bytes.fromhex("CD A2 11"):
            raise SystemExit(f"X helper CALL moved at 0x{site:05X}")

    y = build_y(args.high_nops)
    if REGION_START + len(y) > NEW_X_ADDR:
        raise SystemExit("middle Y helper crossed the established X entry")
    pre_x_padding = NEW_X_ADDR - REGION_START - len(y)
    x_addr = NEW_X_ADDR
    region = y + bytes(pre_x_padding) + FAST_X
    if len(region) > REGION_END - REGION_START:
        raise SystemExit("middle helper pair outgrew fixed region")
    region += bytes(REGION_END - REGION_START - len(region))

    cases = 0
    for attr in range(256):
        for slot in range(256):
            for control in (0, 1, 0x7F, 0xFF):
                if old_y(attr, slot, control) != new_y(attr, slot, control):
                    raise SystemExit("Y helper exhaustive model mismatch")
                cases += 1

    rom = bytearray(source)
    rom[REGION_START:REGION_END] = region
    for site in CALL_SITES:
        rom[site + 1] = x_addr & 0xFF
        rom[site + 2] = x_addr >> 8
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
        "schema": "penta-oam-yflip-middle-r249-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(candidate),
        "high_nops": args.high_nops,
        "y_size": len(y),
        "x_entry": f"0x{x_addr:04X}",
        "padding_bytes": REGION_END - REGION_START - len(y) - len(FAST_X),
        "pre_x_padding_bytes": pre_x_padding,
        "exhaustive_y_cases": cases,
        "timing_t_cycles": {
            "stock_high_reset": 112,
            "candidate_high_reset": 80 + 4 * args.high_nops,
            "saved_high_reset": 32 - 4 * args.high_nops,
            "stock_low_zero": 160,
            "candidate_low_zero": 172 + 4 * args.high_nops,
            "stock_low_set": 168,
            "candidate_low_set": 164,
        },
        "required_first_gate": "candidate-owned Stage1 current hazard/menu exact attrs",
        "warning": "phase/cost diagnostic; do not speed-test or deploy before hazard PASS",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
