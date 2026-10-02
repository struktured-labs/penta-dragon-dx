#!/usr/bin/env python3
"""Build exact-r210 compact ABI-equivalent OBJ flip helpers.

The two stock helpers occupy one contiguous fixed-bank region.  Repacking the
Y helper first and the X helper immediately after it preserves their complete
semantics while giving the common Y-reset route an early return that does not
save/restore HL or perform an indexed memory lookup.  Both generated central
emitter sources are retargeted to the relocated X entry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
REGION_START = 0x1188
REGION_END = 0x11C3
NEW_X_ADDR = 0x11A5
CALL_SITES = (0x37B3B, 0x43B3B)
OLD_REGION = bytes.fromhex(
    "E5 F5 F0 DD FE 04 30 0D 21 C2 FF D7 7E A7 28 05 F1 CB FF 18 03 "
    "F1 CB BF E1 C9 "
    "E5 C5 D5 F5 7B CB 3F CB 3F E0 DD 21 C0 AB D7 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 D1 C1 E1 C9"
)
NEW_Y = bytes.fromhex(
    "F5 F0 DD FE 04 38 04 F1 CB BF C9 "
    "E5 21 C2 FF D7 7E A7 E1 28 04 F1 CB FF C9 F1 CB BF C9"
)
NEW_X = bytes.fromhex(
    "E5 F5 7B CB 3F CB 3F E0 DD C6 C0 6F 26 AB 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 E1 C9"
)
NEW_REGION = NEW_Y + NEW_X


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def old_x(attr: int, e: int, countdown: int) -> tuple[int, int, int, int]:
    slot = ((e >> 1) >> 1) & 0x7F
    address = (0xABC0 + slot) & 0xFFFF
    if countdown:
        return attr | 0x10, (countdown - 1) & 0xFF, slot, address
    return attr & 0xEF, countdown, slot, address


def new_x(attr: int, e: int, countdown: int) -> tuple[int, int, int, int]:
    slot = (e >> 2) & 0xFF
    low = 0xC0 + slot
    if low > 0xFF:
        raise AssertionError(f"X direct index carried for E={e:02X}")
    address = 0xAB00 | low
    if countdown:
        return attr | 0x10, (countdown - 1) & 0xFF, slot, address
    return attr & 0xEF, countdown, slot, address


def old_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot >= 4:
        return attr & 0x7F, None
    address = 0xFFC2 + slot
    return ((attr | 0x80) if control else (attr & 0x7F)), address


def new_y(attr: int, slot: int, control: int) -> tuple[int, int | None]:
    if slot < 4:
        address = 0xFFC2 + slot
        output = (attr | 0x80) if control else (attr & 0x7F)
        return output, address
    return attr & 0x7F, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    source_sha = digest(source)
    if source_sha != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {source_sha}")
    if len(OLD_REGION) != REGION_END - REGION_START:
        raise SystemExit("old helper-region width contract changed")
    if len(NEW_Y) != NEW_X_ADDR - REGION_START:
        raise SystemExit("new Y helper no longer ends at relocated X entry")
    if len(NEW_REGION) != REGION_END - REGION_START:
        raise SystemExit("repacked helper region is not exact-width")
    if source[REGION_START:REGION_END] != OLD_REGION:
        raise SystemExit("fixed-bank flip-helper preimage moved")
    for site in CALL_SITES:
        if source[site:site + 3] != bytes.fromhex("CD A2 11"):
            raise SystemExit(f"X-helper CALL preimage moved at 0x{site:05X}")
    raw_refs = [
        index for index in range(len(source) - 1)
        if source[index:index + 2] == bytes.fromhex("A2 11")
    ]
    if raw_refs != [site + 1 for site in CALL_SITES]:
        raise SystemExit(f"unexpected raw $11A2 references: {raw_refs}")

    x_cases = 0
    for attr in range(256):
        for e in range(256):
            for countdown in (0, 1, 2, 0x7F, 0xFF):
                if old_x(attr, e, countdown) != new_x(attr, e, countdown):
                    raise SystemExit("X helper exhaustive model mismatch")
                x_cases += 1
    y_cases = 0
    for attr in range(256):
        for slot in range(256):
            for control in (0, 1, 0x7F, 0xFF):
                if old_y(attr, slot, control) != new_y(attr, slot, control):
                    raise SystemExit("Y helper exhaustive model mismatch")
                y_cases += 1

    rom = bytearray(source)
    rom[REGION_START:REGION_END] = NEW_REGION
    for site in CALL_SITES:
        rom[site + 1] = NEW_X_ADDR & 0xFF
        rom[site + 2] = NEW_X_ADDR >> 8
    update_checksums(rom)
    candidate = bytes(rom)
    changed = {i for i, pair in enumerate(zip(source, candidate))
               if pair[0] != pair[1]}
    allowed = set(range(REGION_START, REGION_END))
    for site in CALL_SITES:
        allowed.update((site + 1, site + 2))
    allowed.update((0x014D, 0x014E, 0x014F))
    if changed - allowed:
        raise SystemExit("candidate changed bytes outside audited regions")

    receipt = {
        "schema": "penta-oam-flip-pair-fast-r232-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(candidate),
        "fixed_region": f"0x{REGION_START:04X}-0x{REGION_END - 1:04X}",
        "new_x_entry": f"0x{NEW_X_ADDR:04X}",
        "retargeted_call_sites": [f"0x{site:05X}" for site in CALL_SITES],
        "raw_old_x_references_remaining": 0,
        "exhaustive_x_cases": x_cases,
        "exhaustive_y_cases": y_cases,
        "preserved_contract": [
            "BC/DE/HL and input flags",
            "FFDD = E >> 2",
            "ABC0 countdown mutation and X flip",
            "FFC2 low-slot control and high-slot Y reset",
        ],
        "required_gates": [
            "all-stage strict speed matrix",
            "central helper output trace parity",
            "boss/miniboss/spotlight animation receipts",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
