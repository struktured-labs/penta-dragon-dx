#!/usr/bin/env python3
"""Static footprint, call-graph, and interrupt-state checks for palette r532."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r527 as r527  # noqa: E402
import compose_palette_publisher_atomic_r532 as r532  # noqa: E402


EXPECTED_SHA256 = (
    "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821"
)
EXPECTED_ROUTER = bytes.fromhex(
    "78 C1 D5 57 F0 FF 5F AF E0 FF "
    "F0 40 CB 7F 28 16 "
    "F0 41 E6 03 FE 01 28 0E "
    "F0 41 E6 03 FE 03 20 F8 "
    "F0 41 E6 03 20 FA "
    "7A E5 21 E3 71 E5 C3 61 00"
)
EXPECTED_WRITER = bytes.fromhex(
    "E1 2A E2 2A E2 2A E2 2A E2 7B D1 E0 FF C9"
)

source = r518.BASE.read_bytes()
parent, _parent_receipt = r527.build(source)
candidate, receipt = r532.build(source)
_r518_candidate, r518_receipt = r518.build(source)
labels = {
    name: int(address, 16)
    for name, address in r518_receipt["labels"].items()
}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def direct_sites(bank: int, opcode: int, target: int) -> list[int]:
    bank_start = bank * 0x4000
    bank_end = bank_start + 0x4000
    needle = bytes((opcode, target & 0xFF, target >> 8))
    sites: list[int] = []
    cursor = bank_start
    while True:
        found = parent.find(needle, cursor, bank_end)
        if found < 0:
            return sites
        sites.append(0x4000 + found - bank_start)
        cursor = found + 1


check(hashlib.sha256(parent).hexdigest() == r532.PARENT_SHA256,
      "r527 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r532 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r532 receipt digest differs")
check(receipt["router_len"] == len(EXPECTED_ROUTER) == 47,
      "r532 router length differs")

native = labels["palette_guard_native"]
native_offset = r518.off(r518.CAVE_BANK, native)
router_offset = r518.off(r518.CAVE_BANK, r532.ROUTER)
allowed = set(range(0x14D, 0x150))
allowed.update(range(native_offset, native_offset + 3))
allowed.update(range(router_offset, router_offset + len(EXPECTED_ROUTER)))
for bank in (13, 16):
    writer_offset = r518.off(bank, r532.SOURCE_WRITER_ENTRY)
    allowed.update(range(writer_offset, writer_offset + len(EXPECTED_WRITER)))
changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
check(len(changed) == 78, f"parent delta is {len(changed)} bytes, not 78")
check(changed <= allowed,
      f"r532 changed bytes outside its boundary: {sorted(changed - allowed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r532 changed-offset receipt differs")
check(candidate[native_offset:native_offset + 3]
      == bytes((0xC3, r532.ROUTER & 0xFF, r532.ROUTER >> 8)),
      "palette native entry does not jump to r532")
check(parent[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == bytes((0xFF,)) * len(EXPECTED_ROUTER),
      "r532 router did not occupy an erased parent cave")
check(candidate[router_offset:router_offset + len(EXPECTED_ROUTER)]
      == EXPECTED_ROUTER, "r532 router bytes differ")

# Router restores BC before saving DE; source bank and IE travel in D/E. IE is
# zeroed without touching IME, and no DI/EI opcode exists in either component.
check(EXPECTED_ROUTER[:10]
      == bytes.fromhex("78 C1 D5 57 F0 FF 5F AF E0 FF"),
      "r532 IE-mask/register prologue differs")
check(EXPECTED_ROUTER[10:24]
      == bytes.fromhex("F0 40 CB 7F 28 16 F0 41 E6 03 FE 01 28 0E"),
      "r532 LCD-off/VBlank fast paths differ")
check(EXPECTED_ROUTER[24:38] == bytes.fromhex(
    "F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA"),
    "r532 fresh-HBlank loops differ")
check(EXPECTED_ROUTER[38:] == bytes.fromhex("7A E5 21 E3 71 E5 C3 61 00"),
      "r532 coherent source route differs")
check(0xF3 not in EXPECTED_ROUTER and 0xFB not in EXPECTED_ROUTER,
      "r532 changes IME in its router")
check(bytes.fromhex("C3 C0 09") not in EXPECTED_ROUTER,
      "r532 bypasses the software bank mirrors")

for bank in (13, 16):
    writer_offset = r518.off(bank, r532.SOURCE_WRITER_ENTRY)
    check(candidate[writer_offset:writer_offset + len(EXPECTED_WRITER)]
          == EXPECTED_WRITER, f"bank {bank} source writer differs")
check(EXPECTED_WRITER.count(bytes.fromhex("2A E2")) == 4,
      "r532 writer does not perform exactly four source/CRAM writes")
check(EXPECTED_WRITER[-5:] == bytes.fromhex("7B D1 E0 FF C9"),
      "r532 does not restore DE then IE immediately before RET")
check(0xF3 not in EXPECTED_WRITER and 0xFB not in EXPECTED_WRITER,
      "r532 changes IME in its source writer")

# A returns as IE instead of the fourth source byte. Prove that value is dead
# across the complete exact direct-call graph rather than relying on a comment.
for bank in (13, 16):
    check(direct_sites(bank, 0xCD, 0x71DB) == [0x7FE0, 0x7FE3],
          f"bank {bank} $71DB direct-call graph differs")
    check(direct_sites(bank, 0xC3, 0x71DB) == [],
          f"bank {bank} has an unexpected JP $71DB")
    check(direct_sites(bank, 0xCD, 0x7FE0) == [0x717C],
          f"bank {bank} $7FE0 direct-call graph differs")
    wrapper = parent[r518.off(bank, 0x7FE0):r518.off(bank, 0x7FE0) + 7]
    check(wrapper == bytes.fromhex("CD DB 71 CD DB 71 C9"),
          f"bank {bank} palette wrapper differs")
    continuation = parent[r518.off(bank, 0x717C):r518.off(bank, 0x717C) + 6]
    check(continuation == bytes.fromhex("CD E0 7F 15 20 F7"),
          f"bank {bank} palette wrapper continuation uses A")

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
print(f"writer bytes {len(EXPECTED_WRITER)} per source bank")
print(f"parent delta bytes {len(changed)}")
print(f"candidate sha256 {EXPECTED_SHA256}")
