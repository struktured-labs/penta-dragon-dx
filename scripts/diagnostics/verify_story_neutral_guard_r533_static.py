#!/usr/bin/env python3
"""Static footprint and routing checks for the r533 story-row guard."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(HERE)]
import build_v302_title_fix as base_build  # noqa: E402
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_palette_publisher_atomic_r532 as r532  # noqa: E402
import compose_story_neutral_guard_r533 as r533  # noqa: E402


EXPECTED_SHA256 = (
    "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba"
)
EXPECTED_HALF_ROW = bytes.fromhex(
    "FE 12 D2 9A 6A FE 08 38 02 0E 80 16 00 C3 00 7F"
)
EXPECTED_WRITER_PREFIX = bytes.fromhex(
    "E5 79 E6 07 20 04 0E"
)
EXPECTED_MODE_GUARD = bytes.fromhex("F0 41 E6 02 20 FA 79 22")

source = r518.BASE.read_bytes()
parent, _parent_receipt = r532.build(source)
candidate, receipt = r533.build(source)
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


check(hashlib.sha256(parent).hexdigest() == r533.PARENT_SHA256,
      "r532 parent digest differs")
check(hashlib.sha256(candidate).hexdigest() == EXPECTED_SHA256,
      "r533 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r533 receipt digest differs")

changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
expected_changed = {0x14F, r518.off(13, r533.NEUTRAL_STORY_MARKER)}
check(changed == expected_changed,
      f"r533 parent delta differs: {sorted(changed)}")
check(changed == {int(value, 16) for value in receipt["changed_from_parent"]},
      "r533 changed-offset receipt differs")

half_row_offset = r518.off(13, r533.STORY_HALF_ROW_HELPER)
check(parent[half_row_offset:half_row_offset + 16]
      == EXPECTED_HALF_ROW[:10] + b"\x00" + EXPECTED_HALF_ROW[11:],
      "r532 neutral story-row preimage differs")
check(candidate[half_row_offset:half_row_offset + 16] == EXPECTED_HALF_ROW,
      "r533 half-row helper differs")
check(base_build.build_story_half_row_helper(0x7F00) == EXPECTED_HALF_ROW,
      "canonical builder does not emit the r533 half-row helper")

# C=$80 retains bit 7 for the existing CALL NZ bank-6 route. The classifier
# masks C to palette bits 0..2, selects its neutral row when those bits are
# zero, and its terminal writer guards every LD [HL+],A with a STAT wait.
bank6_writer = r518.off(6, 0x4CC3)
row_writer = r518.off(6, 0x4CFB)
check(candidate[bank6_writer:bank6_writer + len(EXPECTED_WRITER_PREFIX)]
      == EXPECTED_WRITER_PREFIX,
      "bank-6 classifier no longer masks the marker to palette zero")
check(EXPECTED_MODE_GUARD in candidate[row_writer:row_writer + 49],
      "bank-6 row writer lost its per-cell VRAM mode guard")
story_sweep = candidate[r518.off(13, 0x7E40):r518.off(13, 0x7F40)]
check(bytes.fromhex("CB 79 C4 58 00 20") in story_sweep,
      "story dispatcher no longer routes bit-7 rows through bank 6")

if failures:
    print("FAIL")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("PASS")
print(f"parent delta bytes {len(changed)}")
print("neutral story marker C=$80 -> guarded BG0 writer")
print(f"candidate sha256 {EXPECTED_SHA256}")
