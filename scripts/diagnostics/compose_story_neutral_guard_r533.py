#!/usr/bin/env python3
"""Compose r533: keep neutral story rows on the VRAM-guarded writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_palette_publisher_atomic_r532 as r532  # noqa: E402


PARENT_SHA256 = (
    "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821"
)
OUT = ROOT / "tmp/story-neutral-guard-r533"
STORY_HALF_ROW_HELPER = 0x6D70
NEUTRAL_STORY_MARKER = STORY_HALF_ROW_HELPER + 10


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r532.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r532 parent identity changed")
    rom = bytearray(parent)

    marker_offset = r518.off(13, NEUTRAL_STORY_MARKER)
    if parent[marker_offset] != 0x00:
        raise ValueError("neutral story-row marker preimage changed")
    rom[marker_offset] = 0x80

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-story-neutral-guard-r533-build-v1",
        "experimental": True,
        "promotable": False,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "story_half_row_helper": f"{STORY_HALF_ROW_HELPER:04X}",
        "neutral_story_marker": f"{NEUTRAL_STORY_MARKER:04X}",
        "routing_contract": (
            "neutral dialogue rows carry C=$80: palette bits remain BG0 "
            "while bit 7 routes all twenty cells through the bank-6 "
            "per-cell VRAM mode guard"
        ),
        "changed_from_parent": changed_from_parent,
    }


def main() -> int:
    source = r518.BASE.read_bytes()
    candidate, receipt = build(source)
    OUT.mkdir(exist_ok=True)
    target = OUT / "candidate.gb"
    if target.exists() and target.read_bytes() != candidate:
        raise ValueError("immutable candidate collision")
    target.write_bytes(candidate)
    payload = json.dumps(receipt, indent=2) + "\n"
    receipt_path = OUT / "build-receipt.json"
    if receipt_path.exists() and receipt_path.read_text() != payload:
        raise ValueError("immutable build receipt collision")
    receipt_path.write_text(payload)
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
