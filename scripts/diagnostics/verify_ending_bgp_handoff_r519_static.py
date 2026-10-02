#!/usr/bin/env python3
"""Static footprint and exact-routing checks for experimental r519."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r519 as r519  # noqa: E402


EXPECTED_SHA256 = (
    "9b368aaef0e48757fb0bfed108e30f20490150f329e78b6001ed0b53fa7f7af9"
)
source = r518.BASE.read_bytes()
parent, parent_receipt = r518.build(source)
candidate, receipt = r519.build(source)
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def span(bank: int, address: int, length: int) -> set[int]:
    start = r518.off(bank, address)
    return set(range(start, start + length))


check(hashlib.sha256(parent).hexdigest() == r519.PARENT_SHA256,
      "r518 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r519 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r519 receipt digest differs")
check(receipt["extension_len"] == 40, "r519 extension length differs")

allowed = set(range(0x14D, 0x150))
allowed.update(range(
    r519.EPILOGUE_PRE_FADE_RESET_CALL,
    r519.EPILOGUE_PRE_FADE_RESET_CALL + 3,
))
allowed.update(span(r518.CAVE_BANK, r519.DISPATCH, 8))
allowed.update(span(r518.CAVE_BANK, r519.EXTENSION,
                    int(receipt["extension_len"])))
changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
check(len(changed) == 47, f"parent delta is {len(changed)} bytes, not 47")
check(changed <= allowed,
      f"r519 changed bytes outside its boundary: {sorted(changed - allowed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r519 changed-offset receipt differs")

call = candidate[
    r519.EPILOGUE_PRE_FADE_RESET_CALL:
    r519.EPILOGUE_PRE_FADE_RESET_CALL + 3
]
check(call == bytes.fromhex("CD 89 42"),
      "epilogue reset does not use the inherited mapper wrapper")
check(parent[r519.NATIVE_MONO_RESET:r519.NATIVE_MONO_RESET + 4]
      == candidate[r519.NATIVE_MONO_RESET:r519.NATIVE_MONO_RESET + 4]
      == bytes.fromhex("3E FF 18 F5"),
      "native monochrome reset was changed")
wrapper = slice(r518.CREDITS_FADE_WRAPPER,
                r518.CREDITS_FADE_WRAPPER + 6)
check(candidate[wrapper] == parent[wrapper] == bytes.fromhex("F5 3E 14 CD 61 00"),
      "inherited bank-1 wrapper changed")

dispatch_offset = r518.off(r518.CAVE_BANK, r519.DISPATCH)
check(candidate[dispatch_offset:dispatch_offset + 8]
      == bytes.fromhex("E5 F8 02 7E E1 C3 40 7B"),
      "out-of-line dispatch hook differs")
extension_offset = r518.off(r518.CAVE_BANK, r519.EXTENSION)
expected_extension = bytes.fromhex(
    "FE 75 CA 36 74 FE 87 CA 3A 74 FE 4D CA 52 7B C3 36 74 "
    "3E FF F5 C5 D5 E5 CD C2 75 E1 D1 C1 F1 "
    "E0 47 E0 48 E0 49 C3 9A 09"
)
check(candidate[extension_offset:extension_offset + len(expected_extension)]
      == expected_extension, "r519 dispatch/preblack extension differs")
check(parent[extension_offset:extension_offset + len(expected_extension)]
      == bytes((0xFF,)) * len(expected_extension),
      "r519 extension did not occupy an erased parent cave")
check(candidate[0x0F5A:0x0F66] == parent[0x0F5A:0x0F66],
      "native global BG fade changed")

if failures:
    print("FAIL")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("PASS")
print(f"extension bytes {len(expected_extension)}")
print(f"parent delta bytes {len(changed)}")
print(f"candidate sha256 {EXPECTED_SHA256}")
