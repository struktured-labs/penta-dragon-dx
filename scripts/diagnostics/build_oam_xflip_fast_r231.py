#!/usr/bin/env python3
"""Build an exact-r210 ABI-equivalent fast $11A2 OBJ X-flip helper.

The stock helper preserves BC, DE, and HL around an operation that only needs
HL as an indexed scratch pointer.  This candidate retains the exact FFDD slot
publication, ABC0 countdown mutation, input flags, output attribute bit 4,
and every caller-visible register while removing the redundant BC/DE stack
traffic and the generic RST-$10 address adder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "dbc1001bdeef221ed1611a1e728f63050e25111f81cdadbcd8f900f628e02273"
HELPER_ADDR = 0x11A2
HELPER_SIZE = 33
OLD_HELPER = bytes.fromhex(
    "E5 C5 D5 F5 7B CB 3F CB 3F E0 DD 21 C0 AB D7 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 D1 C1 E1 C9"
)
NEW_BODY = bytes.fromhex(
    "E5 F5 7B CB 3F CB 3F E0 DD C6 C0 6F 26 AB 7E A7 28 07 "
    "3D 77 F1 CB E7 18 03 F1 CB A7 E1 C9"
)
NEW_HELPER = NEW_BODY + bytes(HELPER_SIZE - len(NEW_BODY))


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def old_model(attr: int, e: int, countdown: int) -> tuple[int, int, int, int]:
    # Two stock SRL instructions followed by RST-$10's 16-bit HL addition.
    first = (e >> 1) & 0x7F
    slot = (first >> 1) & 0x7F
    address = (0xABC0 + slot) & 0xFFFF
    if countdown:
        return attr | 0x10, (countdown - 1) & 0xFF, slot, address
    return attr & 0xEF, countdown, slot, address


def new_model(attr: int, e: int, countdown: int) -> tuple[int, int, int, int]:
    slot = (e >> 2) & 0xFF
    # The replacement writes the low byte directly.  Prove that its addition
    # never carries into a different page for any reachable 8-bit E.
    low_sum = 0xC0 + slot
    if low_sum > 0xFF:
        raise AssertionError(f"direct index unexpectedly carried: E={e:02X}")
    address = 0xAB00 | low_sum
    if countdown:
        return attr | 0x10, (countdown - 1) & 0xFF, slot, address
    return attr & 0xEF, countdown, slot, address


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    source_sha = digest(source)
    if source_sha != BASE_SHA256:
        raise SystemExit(f"unqualified exact r210 base: {source_sha}")
    if len(OLD_HELPER) != HELPER_SIZE or len(NEW_HELPER) != HELPER_SIZE:
        raise SystemExit("helper width contract changed")
    if source[HELPER_ADDR:HELPER_ADDR + HELPER_SIZE] != OLD_HELPER:
        raise SystemExit("stock $11A2 helper preimage moved")

    # Exhaust every observable input class.  E is intentionally unrestricted:
    # the arithmetic is equivalent for the complete 8-bit domain, not merely
    # the reviewed OAM offsets ending in 3/7/B/F.
    cases = 0
    for attr in range(256):
        for e in range(256):
            for countdown in (0, 1, 2, 0x7F, 0xFF):
                old = old_model(attr, e, countdown)
                new = new_model(attr, e, countdown)
                if old != new:
                    raise SystemExit(
                        f"semantic mismatch attr={attr:02X} e={e:02X} "
                        f"countdown={countdown:02X}: {old} != {new}"
                    )
                cases += 1

    rom = bytearray(source)
    rom[HELPER_ADDR:HELPER_ADDR + HELPER_SIZE] = NEW_HELPER
    update_checksums(rom)
    candidate = bytes(rom)
    changed = {i for i, (before, after) in enumerate(zip(source, candidate))
               if before != after}
    allowed = set(range(HELPER_ADDR, HELPER_ADDR + HELPER_SIZE))
    allowed.update((0x014D, 0x014E, 0x014F))
    if changed - allowed:
        raise SystemExit("candidate changed bytes outside the helper/checksums")

    receipt = {
        "schema": "penta-oam-xflip-fast-r231-v1",
        "status": "PASS_STATIC_EMULATOR_REQUIRED",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(candidate),
        "helper_address": f"0x{HELPER_ADDR:04X}",
        "helper_width": HELPER_SIZE,
        "exhaustive_model_cases": cases,
        "observable_contract": {
            "preserved_registers": ["BC", "DE", "HL"],
            "preserved_input_flags": True,
            "ffdd": "E >> 2",
            "abc0_slot": "FFDD",
            "nonzero_countdown": "decrement and SET 4,A",
            "zero_countdown": "unchanged and RES 4,A",
        },
        "instruction_changes": [
            "remove redundant PUSH/POP BC and DE",
            "replace LD HL,$ABC0; RST $10 with direct page/low-byte index",
        ],
        "required_gates": [
            "Stage 5 strict speed >= 0.99",
            "central attribute helper trace parity",
            "all-stage speed matrix",
            "boss/miniboss/spotlight animation visual receipts",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
