#!/usr/bin/env python3
"""Compose r526: retry the final BG color in one fresh LCD-safe window."""

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
OUT = ROOT / "tmp/ending-bgp-handoff-r526"
FINAL_COLOR_RETRY = 0x7380


def build_final_color_retry() -> bytes:
    code = bytearray((0xF3,))               # no interrupt can steal the window
    labels: dict[str, int] = {}
    branches: list[tuple[int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(code)

    def jr(opcode: int, target: str) -> None:
        code.extend((opcode, 0))
        branches.append((len(code) - 1, target))

    code.extend((0xF0, 0x40, 0xCB, 0x7F))   # LCD off needs no mode wait
    jr(0x28, "ready")
    label("seek_mode3")
    code.extend((0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01))
    jr(0x28, "ready")                       # VBlank is immediately safe
    code.extend((0xFE, 0x03))
    jr(0x20, "seek_mode3")                 # reach mode 3 first
    label("seek_hblank")
    code.extend((0xF0, 0x41, 0xE6, 0x03))
    jr(0x20, "seek_hblank")                # then enter a fresh mode 0
    label("ready")
    code.extend((
        0x3E, 0xFE, 0xE0, 0x68,             # BG CRAM index $3E, increment
        0xE5, 0x3E, 0x06, 0xD7,             # preserve HL; source += 6
        0x2A, 0xE0, 0x69,                    # byte $3E
        0x2A, 0xE0, 0x69,                    # byte $3F
        0xE1, 0xFB, 0xC9,
    ))
    for position, target in branches:
        displacement = labels[target] - (position + 1)
        if not -128 <= displacement <= 127:
            raise AssertionError("r526 final-color branch escaped JR range")
        code[position] = displacement & 0xFF
    if len(code) != 42:
        raise AssertionError("r526 final-color retry length changed")
    return bytes(code)


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
        raise ValueError("r526 final-color retry cave is not erased")
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
        "schema": "penta-ending-bgp-handoff-r526-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "final_color_retry": f"{FINAL_COLOR_RETRY:04X}",
        "final_color_retry_len": len(final_color),
        "retry_hook": f"{retry:04X}",
        "retry_contract": (
            "after the inherited 64-byte pass, DI; proceed immediately when "
            "the LCD is off, otherwise seek mode 1 or a fresh mode 3->0 "
            "edge; rewrite indices $3E/$3F; restore HL; EI; RET"
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
