#!/usr/bin/env python3
"""Compose r527: extend the inherited final-byte retry to its color pair."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r524 as r524  # noqa: E402


PARENT_SHA256 = (
    "e2ffa7e6c91cb630066524c49c00b56243f9bc61b137bab367b97a441c95224a"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r527"
FINAL_COLOR_RETRY = 0x7380


def build_final_color_retry() -> bytes:
    # This is the inherited final-byte wait, widened to the whole final color.
    # RST $10 still receives A=$07, as it did in r518; DEC HL then selects
    # byte $3E without changing flags. The final A/F, HL, and interrupt state
    # are therefore identical to the inherited routine's successful path.
    return bytes.fromhex(
        "F0 41 E6 03 FE 02 30 F8 "
        "3E FE E0 68 E5 3E 07 D7 2B "
        "2A E0 69 2A E0 69 E1 C9"
    )


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r524.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r524 parent identity changed")
    _r518_candidate, r518_receipt = r518.build(source)
    labels = {
        name: int(address, 16)
        for name, address in r518_receipt["labels"].items()
    }
    rom = bytearray(parent)

    retry = labels["copy_repeat_retry_last_wait"]
    retry_offset = r518.off(r518.CAVE_BANK, retry)
    if rom[retry_offset:retry_offset + 8] \
            != bytes.fromhex("F0 41 E6 03 FE 02 30 F8"):
        raise ValueError("r518 final-byte retry entry changed")
    rom[retry_offset:retry_offset + 3] = bytes((
        0xC3, FINAL_COLOR_RETRY & 0xFF, FINAL_COLOR_RETRY >> 8,
    ))

    final_color = build_final_color_retry()
    final_color_offset = r518.off(r518.CAVE_BANK, FINAL_COLOR_RETRY)
    if parent[final_color_offset:final_color_offset + len(final_color)] \
            != bytes((0xFF,)) * len(final_color):
        raise ValueError("r527 final-color retry cave is not erased")
    rom[
        final_color_offset:final_color_offset + len(final_color)
    ] = final_color

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r527-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "final_color_retry": f"{FINAL_COLOR_RETRY:04X}",
        "final_color_retry_len": len(final_color),
        "retry_hook": f"{retry:04X}",
        "retry_contract": (
            "replace the inherited byte-$3F retry with the same LCD-phase "
            "wait followed by an AF-equivalent byte-$3E/$3F pair retry"
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
