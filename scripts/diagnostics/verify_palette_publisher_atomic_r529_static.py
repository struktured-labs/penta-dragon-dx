#!/usr/bin/env python3
"""Static footprint and ABI checks for experimental palette publisher r529."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r527 as r527  # noqa: E402
import compose_palette_publisher_atomic_r529 as r529  # noqa: E402


EXPECTED_SHA256 = (
    "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208"
)
EXPECTED_ROUTER = bytes.fromhex(
    "F0 40 CB 7F 78 C1 20 06 "
    "E5 21 F4 71 18 05 F3 E5 21 E3 71 "
    "E5 C3 C0 09"
)
EXPECTED_MASKED = bytes.fromhex("E1 2A E2 2A E2 2A E2 2A E2 FB C9")
EXPECTED_UNMASKED = bytes.fromhex("E1 2A E2 2A E2 2A E2 2A E2 C9")

source = r518.BASE.read_bytes()
parent, _parent_receipt = r527.build(source)
candidate, receipt = r529.build(source)
_r518_candidate, r518_receipt = r518.build(source)
labels = {
    name: int(address, 16)
    for name, address in r518_receipt["labels"].items()
}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


check(hashlib.sha256(parent).hexdigest() == r529.PARENT_SHA256,
      "r527 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r529 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r529 receipt digest differs")
check(receipt["router_len"] == len(EXPECTED_ROUTER) == 23,
      "r529 router length differs")

ready = labels["palette_guard_native_ready"]
ready_offset = r518.off(r518.CAVE_BANK, ready)
router_offset = r518.off(r518.CAVE_BANK, r529.ROUTER)
allowed = set(range(0x14D, 0x150))
allowed.update(range(ready_offset, ready_offset + 3))
allowed.update(range(router_offset, router_offset + len(EXPECTED_ROUTER)))
for bank in (13, 16):
    masked_offset = r518.off(bank, r529.SOURCE_MASKED_ENTRY)
    unmasked_offset = r518.off(bank, r529.SOURCE_UNMASKED_ENTRY)
    allowed.update(range(masked_offset, masked_offset + len(EXPECTED_MASKED)))
    allowed.update(range(unmasked_offset,
                         unmasked_offset + len(EXPECTED_UNMASKED)))
changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
check(len(changed) == 58, f"parent delta is {len(changed)} bytes, not 58")
check(changed <= allowed,
      f"r529 changed bytes outside its boundary: {sorted(changed - allowed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r529 changed-offset receipt differs")

check(candidate[ready_offset:ready_offset + 3]
      == bytes((0xC3, r529.ROUTER & 0xFF, r529.ROUTER >> 8)),
      "palette native-ready hook does not jump to r529")
check(parent[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == bytes((0xFF,)) * len(EXPECTED_ROUTER),
      "r529 router did not occupy an erased parent cave")
check(candidate[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == EXPECTED_ROUTER, "r529 router bytes differ")

# Router order is the core stack contract: capture B, POP caller BC, branch,
# then PUSH caller HL. The LCD-off branch contains no interrupt opcode; the
# LCD-on branch performs DI before selecting its EI-completing source entry.
check(EXPECTED_ROUTER[:8] == bytes.fromhex("F0 40 CB 7F 78 C1 20 06"),
      "r529 no longer restores caller BC before its branch")
check(EXPECTED_ROUTER[8:14] == bytes.fromhex("E5 21 F4 71 18 05"),
      "r529 LCD-off branch differs")
check(EXPECTED_ROUTER[14:19] == bytes.fromhex("F3 E5 21 E3 71"),
      "r529 LCD-on masked branch differs")
check(EXPECTED_ROUTER[19:] == bytes.fromhex("E5 C3 C0 09"),
      "r529 mapper return stack differs")

for bank in (13, 16):
    masked_offset = r518.off(bank, r529.SOURCE_MASKED_ENTRY)
    unmasked_offset = r518.off(bank, r529.SOURCE_UNMASKED_ENTRY)
    check(candidate[masked_offset:masked_offset + len(EXPECTED_MASKED)]
          == EXPECTED_MASKED, f"bank {bank} masked writer differs")
    check(candidate[unmasked_offset:unmasked_offset + len(EXPECTED_UNMASKED)]
          == EXPECTED_UNMASKED, f"bank {bank} unmasked writer differs")
    check(EXPECTED_MASKED.count(bytes.fromhex("2A E2")) == 4,
          "masked writer does not contain exactly four CRAM writes")
    check(EXPECTED_UNMASKED.count(bytes.fromhex("2A E2")) == 4,
          "unmasked writer does not contain exactly four CRAM writes")

# r527's ending retry and late preblack remain byte-for-byte inherited.
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
