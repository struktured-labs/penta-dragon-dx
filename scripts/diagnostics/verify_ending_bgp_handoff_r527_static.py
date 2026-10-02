#!/usr/bin/env python3
"""Static footprint and exact-retry checks for experimental r527."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r524 as r524  # noqa: E402
import compose_ending_bgp_handoff_r527 as r527  # noqa: E402


EXPECTED_SHA256 = (
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"
)
EXPECTED_RETRY = bytes.fromhex(
    "F0 41 E6 03 FE 02 30 F8 "
    "3E FE E0 68 E5 3E 07 D7 2B "
    "2A E0 69 2A E0 69 E1 C9"
)
source = r518.BASE.read_bytes()
parent, _parent_receipt = r524.build(source)
candidate, receipt = r527.build(source)
_r518_candidate, r518_receipt = r518.build(source)
labels = {
    name: int(address, 16)
    for name, address in r518_receipt["labels"].items()
}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


check(hashlib.sha256(parent).hexdigest() == r527.PARENT_SHA256,
      "r524 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r527 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r527 receipt digest differs")
check(receipt["final_color_retry_len"] == len(EXPECTED_RETRY) == 25,
      "r527 retry length differs")

retry = labels["copy_repeat_retry_last_wait"]
retry_offset = r518.off(r518.CAVE_BANK, retry)
cave_offset = r518.off(r518.CAVE_BANK, r527.FINAL_COLOR_RETRY)
allowed = set(range(0x14D, 0x150))
allowed.update(range(retry_offset, retry_offset + 3))
allowed.update(range(cave_offset, cave_offset + len(EXPECTED_RETRY)))
changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
check(len(changed) == 30, f"parent delta is {len(changed)} bytes, not 30")
check(changed <= allowed,
      f"r527 changed bytes outside its boundary: {sorted(changed - allowed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r527 changed-offset receipt differs")

check(candidate[retry_offset:retry_offset + 3]
      == bytes((0xC3, r527.FINAL_COLOR_RETRY & 0xFF,
                r527.FINAL_COLOR_RETRY >> 8)),
      "final-byte retry hook does not jump to r527")
check(candidate[retry_offset + 3:retry_offset + 24]
      == parent[retry_offset + 3:retry_offset + 24],
      "bytes after the retry hook changed")
check(parent[cave_offset:cave_offset + len(EXPECTED_RETRY)]
      == bytes((0xFF,)) * len(EXPECTED_RETRY),
      "r527 retry did not occupy an erased parent cave")
check(candidate[cave_offset:cave_offset + len(EXPECTED_RETRY)]
      == EXPECTED_RETRY, "r527 retry bytes differ")
check(0xF3 not in EXPECTED_RETRY and 0xFB not in EXPECTED_RETRY,
      "r527 retry changes interrupt state")

# The widened retry keeps the inherited RST-$10 A=$07 calculation and uses
# flag-neutral DEC HL to select byte $3E. Its last load remains byte $3F, so
# successful-path A/F and HL match r518 while the write covers one whole color.
check(EXPECTED_RETRY[12:17] == bytes.fromhex("E5 3E 07 D7 2B"),
      "r527 no longer preserves inherited RST-$10 flags")
check(EXPECTED_RETRY.count(bytes.fromhex("2A E0 69")) == 2,
      "r527 does not write exactly the final color pair")

# Everything in r524's late-epilogue repair is inherited byte-for-byte.
check(candidate[
          r524.EPILOGUE_PRE_FADE_RESET_CALL:
          r524.EPILOGUE_PRE_FADE_RESET_CALL + 3
      ] == parent[
          r524.EPILOGUE_PRE_FADE_RESET_CALL:
          r524.EPILOGUE_PRE_FADE_RESET_CALL + 3
      ] == bytes.fromhex("CD 89 42"),
      "r524 epilogue wrapper call changed")
for address, length, name in (
    (r524.CREDITS_DISPATCH, 20, "credits dispatcher"),
    (r524.CREDITS_IN_TRAMPOLINE, 4, "credits-in trampoline"),
    (r524.PRIVATE_PREBLACK, 26, "epilogue preblack"),
):
    start = r518.off(r518.CAVE_BANK, address)
    check(candidate[start:start + length] == parent[start:start + length],
          f"r524 {name} changed")
check(candidate[0x0F5A:0x0F66] == parent[0x0F5A:0x0F66],
      "native global BG fade changed")

if failures:
    print("FAIL")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("PASS")
print(f"retry bytes {len(EXPECTED_RETRY)}")
print(f"parent delta bytes {len(changed)}")
print(f"candidate sha256 {EXPECTED_SHA256}")
