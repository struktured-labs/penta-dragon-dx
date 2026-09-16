#!/usr/bin/env python3
"""Compose r525: make repeated CGB BG-row fills atomic in VBlank."""

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
OUT = ROOT / "tmp/ending-bgp-handoff-r525"
ATOMIC_REPEAT = 0x7380


def build_atomic_repeat() -> bytes:
    code = bytearray()
    labels: dict[str, int] = {}
    branches: list[tuple[int, str]] = []

    def label(name: str) -> None:
        labels[name] = len(code)

    def jr(opcode: int, target: str) -> None:
        code.extend((opcode, 0))
        branches.append((len(code) - 1, target))

    code.extend((0xF3, 0xC5, 0xD5, 0xE5, 0x54, 0x5D))
    code.extend((0xF0, 0x40, 0xCB, 0x7F))   # LCD off is immediately safe
    jr(0x28, "copy")
    label("wait_vblank")
    code.extend((0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01))
    jr(0x20, "wait_vblank")
    label("copy")
    code.extend((0x3E, 0x80, 0xE0, 0x68, 0x06, 0x08))
    label("palette")
    code.extend((0x62, 0x6B, 0x0E, 0x08))
    label("byte")
    code.extend((0x2A, 0xE0, 0x69, 0x0D))
    jr(0x20, "byte")
    code.append(0x05)
    jr(0x20, "palette")
    code.extend((0xE1, 0xD1, 0xC1, 0xFB, 0xC9))
    for position, target in branches:
        displacement = labels[target] - (position + 1)
        if not -128 <= displacement <= 127:
            raise AssertionError("r525 atomic-copy branch escaped JR range")
        code[position] = displacement & 0xFF
    if len(code) != 44:
        raise AssertionError("r525 atomic-copy length changed")
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

    repeat = labels["copy_repeat"]
    repeat_offset = r518.off(r518.CAVE_BANK, repeat)
    if rom[repeat_offset:repeat_offset + 8] \
            != bytes.fromhex("3E 80 E0 68 06 08 54 5D"):
        raise ValueError("r518 repeated-row copier entry changed")
    rom[repeat_offset:repeat_offset + 3] = bytes((
        0xC3, ATOMIC_REPEAT & 0xFF, ATOMIC_REPEAT >> 8,
    ))

    atomic = build_atomic_repeat()
    atomic_offset = r518.off(r518.CAVE_BANK, ATOMIC_REPEAT)
    if parent[atomic_offset:atomic_offset + len(atomic)] \
            != bytes((0xFF,)) * len(atomic):
        raise ValueError("r525 atomic-copy cave is not erased")
    rom[atomic_offset:atomic_offset + len(atomic)] = atomic

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r525-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "atomic_repeat": f"{ATOMIC_REPEAT:04X}",
        "atomic_repeat_len": len(atomic),
        "copy_repeat_hook": f"{repeat:04X}",
        "atomic_repeat_max_copy_cycles": 2700,
        "vblank_cycles": 4560,
        "atomic_repeat_contract": (
            "DI; wait for LCD-off or STAT mode 1; write all 64 repeated BG "
            "CRAM bytes in one VBlank; restore HL/DE/BC; EI; RET"
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
