#!/usr/bin/env python3
"""Build an exact-r199 Stage-5 prelude upper-bound control.

This artifact is deliberately non-promotable: it retains the current scene
detector and ROM-resident level-select continuation, but replaces the rest of
the per-VBlank color prelude with an immediate return.  Its only purpose is to
measure whether the prelude contains enough recoverable time to bring Stage 5
to 99% of the original game before a semantic-preserving fast path is built.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_v302_title_fix as build  # noqa: E402


BASE_SHA256 = "0ebae52b5c74ecb5e0cd2bbee11c4ee4fa6aca118aeb0515333722e0273518e8"
BANK_SIZE = 0x4000
BANK13 = 13 * BANK_SIZE
PRELUDE_OFFSET = BANK13 + build.COLORIZE_PRELUDE_ADDR - 0x4000
EXECUTABLE_END = build.LEVELSEL_ROM_TAIL_ADDR


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    global_sum = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = global_sum.to_bytes(2, "big")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    source = args.base.read_bytes()
    source_sha = digest(source)
    if source_sha != BASE_SHA256:
        raise SystemExit(f"wrong exact r199 base: {source_sha}")
    if len(source) != 32 * BANK_SIZE:
        raise SystemExit(f"expected 512 KiB ROM, got {len(source)} bytes")

    start = PRELUDE_OFFSET
    end = BANK13 + EXECUTABLE_END - 0x4000
    original = source[start:end]
    if original[:3] != bytes((
        0xCD, build.SCENE_DETECT_ADDR & 0xFF,
        build.SCENE_DETECT_ADDR >> 8,
    )):
        raise SystemExit("r199 scene-detect preimage moved")
    if len(original) != EXECUTABLE_END - build.COLORIZE_PRELUDE_ADDR:
        raise SystemExit("r199 executable prelude extent changed")

    replacement = bytes((
        0xCD, build.SCENE_DETECT_ADDR & 0xFF,
        build.SCENE_DETECT_ADDR >> 8, 0xC9,
    )) + bytes(len(original) - 4)
    rom = bytearray(source)
    rom[start:end] = replacement
    update_checksums(rom)
    output = bytes(rom)

    report = {
        "schema": "penta-stage5-prelude-upper-bound-r200-v1",
        "status": "NON_PROMOTABLE_ATTRIBUTION_ONLY",
        "promotable": False,
        "base_sha256": source_sha,
        "candidate_sha256": digest(output),
        "prelude_cpu_range": (
            f"bank13:${build.COLORIZE_PRELUDE_ADDR:04X}-"
            f"${EXECUTABLE_END - 1:04X}"
        ),
        "original_prelude_sha256": digest(original),
        "replacement": "CALL scene_detect; RET; zero padding",
        "level_select_tail_preserved": True,
        "required_use": "Stage 5 speed attribution only",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
