#!/usr/bin/env python3
"""Static footprint, timing-boundary, and ABI checks for palette r530."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r527 as r527  # noqa: E402
import compose_palette_publisher_atomic_r529 as r529  # noqa: E402
import compose_palette_publisher_atomic_r530 as r530  # noqa: E402


EXPECTED_SHA256 = (
    "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30"
)
EXPECTED_ROUTER = bytes.fromhex(
    "F0 40 CB 7F 28 17 F3 "
    "F0 41 E6 03 FE 03 20 F8 "
    "F0 41 E6 03 20 FA "
    "78 C1 E5 21 E3 71 18 06 "
    "78 C1 E5 21 F4 71 "
    "E5 C3 61 00"
)
EXPECTED_MASKED = bytes.fromhex("E1 2A E2 2A E2 2A E2 2A E2 FB C9")
EXPECTED_UNMASKED = bytes.fromhex("E1 2A E2 2A E2 2A E2 2A E2 C9")

source = r518.BASE.read_bytes()
parent, _parent_receipt = r527.build(source)
candidate, receipt = r530.build(source)
_r518_candidate, r518_receipt = r518.build(source)
labels = {
    name: int(address, 16)
    for name, address in r518_receipt["labels"].items()
}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


check(hashlib.sha256(parent).hexdigest() == r530.PARENT_SHA256,
      "r527 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r530 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r530 receipt digest differs")
check(receipt["router_len"] == len(EXPECTED_ROUTER) == 39,
      "r530 router length differs")

native = labels["palette_guard_native"]
native_offset = r518.off(r518.CAVE_BANK, native)
router_offset = r518.off(r518.CAVE_BANK, r530.ROUTER)
allowed = set(range(0x14D, 0x150))
allowed.update(range(native_offset, native_offset + 3))
allowed.update(range(router_offset, router_offset + len(EXPECTED_ROUTER)))
for bank in (13, 16):
    masked_offset = r518.off(bank, r530.SOURCE_MASKED_ENTRY)
    unmasked_offset = r518.off(bank, r530.SOURCE_UNMASKED_ENTRY)
    allowed.update(range(masked_offset, masked_offset + len(EXPECTED_MASKED)))
    allowed.update(range(unmasked_offset,
                         unmasked_offset + len(EXPECTED_UNMASKED)))
changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
check(len(changed) == 74, f"parent delta is {len(changed)} bytes, not 74")
check(changed <= allowed,
      f"r530 changed bytes outside its boundary: {sorted(changed - allowed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r530 changed-offset receipt differs")

check(candidate[native_offset:native_offset + 3]
      == bytes((0xC3, r530.ROUTER & 0xFF, r530.ROUTER >> 8)),
      "palette native entry does not jump to r530")
check(parent[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == bytes((0xFF,)) * len(EXPECTED_ROUTER),
      "r530 router did not occupy an erased parent cave")
check(candidate[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == EXPECTED_ROUTER, "r530 router bytes differ")

# Enabled-LCD path: DI precedes both polling loops, the first loop observes
# mode 3, and the second waits for the following mode 0. Source-bank A is not
# materialized until after the waits, then caller BC and HL are restored.
check(EXPECTED_ROUTER[:7] == bytes.fromhex("F0 40 CB 7F 28 17 F3"),
      "r530 does not mask before the fresh-HBlank wait")
check(EXPECTED_ROUTER[7:15] == bytes.fromhex("F0 41 E6 03 FE 03 20 F8"),
      "r530 mode-3 acquisition loop differs")
check(EXPECTED_ROUTER[15:21] == bytes.fromhex("F0 41 E6 03 20 FA"),
      "r530 fresh-HBlank loop differs")
check(EXPECTED_ROUTER[21:29]
      == bytes.fromhex("78 C1 E5 21 E3 71 18 06"),
      "r530 masked source route differs")
check(EXPECTED_ROUTER[29:35] == bytes.fromhex("78 C1 E5 21 F4 71"),
      "r530 LCD-off source route differs")
check(EXPECTED_ROUTER[35:] == bytes.fromhex("E5 C3 61 00"),
      "r530 does not use the coherent full bank switch")
check(bytes.fromhex("C3 C0 09") not in EXPECTED_ROUTER,
      "r530 still bypasses the software bank mirrors")

for bank in (13, 16):
    masked_offset = r518.off(bank, r530.SOURCE_MASKED_ENTRY)
    unmasked_offset = r518.off(bank, r530.SOURCE_UNMASKED_ENTRY)
    check(candidate[masked_offset:masked_offset + len(EXPECTED_MASKED)]
          == EXPECTED_MASKED, f"bank {bank} masked writer differs")
    check(candidate[unmasked_offset:unmasked_offset + len(EXPECTED_UNMASKED)]
          == EXPECTED_UNMASKED, f"bank {bank} unmasked writer differs")
    check(EXPECTED_MASKED.count(bytes.fromhex("2A E2")) == 4,
          "masked writer does not contain exactly four CRAM writes")
    check(EXPECTED_UNMASKED.count(bytes.fromhex("2A E2")) == 4,
          "unmasked writer does not contain exactly four CRAM writes")

# r527's ending repair remains byte-for-byte inherited.
for address, length, name in (
    (r527.FINAL_COLOR_RETRY, 25, "ending final-color retry"),
    (0x73C0, 4, "credits-in trampoline"),
    (0x73E0, 26, "epilogue preblack"),
):
    start = r518.off(r518.CAVE_BANK, address)
    check(candidate[start:start + length] == parent[start:start + length],
          f"r527 {name} changed")

if failures:
    print("FAIL")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("PASS")
print(f"router bytes {len(EXPECTED_ROUTER)}")
print(f"parent delta bytes {len(changed)}")
print(f"candidate sha256 {EXPECTED_SHA256}")
