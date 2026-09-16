#!/usr/bin/env python3
"""Compose r522: guard the r521 preblack to completed epilogue text."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r520 as r520  # noqa: E402
import compose_ending_bgp_handoff_r521 as r521  # noqa: E402


PARENT_SHA256 = (
    "37c9e9eccd78013727e1657075e37f02c4e7dc3534eb05baee9f7890fe3246ba"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r522"


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r521.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r521 parent identity changed")
    _r518_candidate, r518_receipt = r518.build(source)
    labels = {
        name: int(address, 16)
        for name, address in r518_receipt["labels"].items()
    }
    rom = bytearray(parent)
    preblack = r520.PREBLACK
    preblack_offset = r518.off(r518.CAVE_BANK, preblack)
    old_preblack = bytes.fromhex(
        "3E FF F5 C5 D5 E5 CD C2 75 E1 D1 C1 F1 "
        "E0 47 E0 48 E0 49 C3 9A 09"
    )
    if rom[preblack_offset:preblack_offset + len(old_preblack)] \
            != old_preblack:
        raise ValueError("r521 preblack body changed")

    code = bytearray((0xF5,))               # original AF, before any guard
    reset_jumps: list[int] = []

    def guard_a16(address: int, expected: int) -> None:
        code.extend((0xFA, address & 0xFF, address >> 8))
        code.extend((0xB7,) if expected == 0 else (0xFE, expected))
        code.extend((0x20, 0x00))           # JR NZ,native_reset
        reset_jumps.append(len(code) - 1)

    guard_a16(0xD880, 0x00)
    guard_a16(0xD889, 0x0C)
    guard_a16(0xDCE2, 0x01)
    code.extend((0xF0, 0xF9, 0xFE, 0x01, 0x20, 0x00))
    reset_jumps.append(len(code) - 1)

    # Only completed epilogue text receives the additional black CRAM deck.
    # Preserve the native reset's otherwise untouched BC/DE/HL registers.
    code.extend((0xC5, 0xD5, 0xE5, 0x3E, 0xFF, 0xCD))
    code.extend(r520.r519.word(labels["mirror_ending_value"]))
    code.extend((0xE1, 0xD1, 0xC1))
    reset = preblack + len(code)

    # Every context reproduces $0A16 exactly: restore the caller's flags,
    # load A=$FF without changing them, publish BGP/OBP, then map bank 1 and
    # return through fixed $099A with AF preserved.
    code.extend((0xF1, 0x3E, 0xFF,
                 0xE0, 0x47, 0xE0, 0x48, 0xE0, 0x49,
                 0xC3, 0x9A, 0x09))
    for position in reset_jumps:
        displacement = reset - (preblack + position + 1)
        if not -128 <= displacement <= 127:
            raise AssertionError("r522 guard branch escaped JR range")
        code[position] = displacement & 0xFF

    old_tail = parent[
        preblack_offset:preblack_offset + len(code)
    ]
    if old_tail[:len(old_preblack)] != old_preblack \
            or old_tail[len(old_preblack):] != bytes((0xFF,)) * (
                len(code) - len(old_preblack)
            ):
        raise ValueError("r522 extension tail is not erased")
    rom[preblack_offset:preblack_offset + len(code)] = code

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r522-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "preblack": f"{preblack:04X}",
        "preblack_len": len(code),
        "native_reset": f"{reset:04X}",
        "epilogue_guard": "D880=00,D889=0C,DCE2=01,FFF9=01",
        "epilogue_pre_fade_reset": (
            "all non-epilogue callers reproduce native $0A16 without CRAM; "
            "completed epilogue text commits black CGB CRAM before the exact "
            "native BGP/OBP reset"
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
