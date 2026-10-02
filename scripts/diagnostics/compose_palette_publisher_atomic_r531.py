#!/usr/bin/env python3
"""Compose r531: atomic native BG rows with a safe VBlank fast path."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r527 as r527  # noqa: E402
import compose_palette_publisher_atomic_r529 as r529  # noqa: E402
import compose_palette_publisher_atomic_r530 as r530  # noqa: E402


R530_SHA256 = (
    "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30"
)
PARENT_SHA256 = r530.PARENT_SHA256
OUT = ROOT / "tmp/palette-publisher-atomic-r531"
ROUTER = r530.ROUTER
SOURCE_MASKED_ENTRY = r530.SOURCE_MASKED_ENTRY
SOURCE_UNMASKED_ENTRY = r530.SOURCE_UNMASKED_ENTRY


def word(value: int) -> bytes:
    return bytes((value & 0xFF, value >> 8))


def build_router() -> bytes:
    # Once the LCD-on route executes DI, mode 1 is already a safe bulk-write
    # window and must not be expanded into one whole frame per four bytes.
    # Visible-line modes still wait through mode 3 into a fresh HBlank.
    code = bytearray.fromhex(
        "F0 40 CB 7F 28 1F "              # LCD off -> unmasked route
        "F3 "                             # LCD on: close interrupt race
        "F0 41 E6 03 FE 01 28 0E "        # VBlank -> masked write now
        "F0 41 E6 03 FE 03 20 F8 "        # otherwise acquire mode 3
        "F0 41 E6 03 20 FA "              # then fresh mode 0
        "78 C1 E5 "                       # bank -> A; restore BC; save HL
    )
    code.extend((0x21, *word(SOURCE_MASKED_ENTRY)))
    code.extend((0x18, 0x06))
    code.extend(bytes.fromhex("78 C1 E5"))
    code.extend((0x21, *word(SOURCE_UNMASKED_ENTRY)))
    code.extend((0xE5, 0xC3, r518.FIXED_SWITCH & 0xFF,
                 r518.FIXED_SWITCH >> 8))
    if len(code) != 47:
        raise AssertionError("r531 palette router length changed")
    return bytes(code)


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r527.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r527 parent identity changed")
    predecessor, predecessor_receipt = r530.build(source)
    if hashlib.sha256(predecessor).hexdigest() != R530_SHA256:
        raise ValueError("r530 predecessor identity changed")

    rom = bytearray(predecessor)
    router = build_router()
    router_offset = r518.off(r518.CAVE_BANK, ROUTER)
    old_router = r530.build_router()
    if predecessor[router_offset:router_offset + len(old_router)] != old_router:
        raise ValueError("r530 router preimage changed")
    if predecessor[
        router_offset + len(old_router):router_offset + len(router)
    ] != bytes((0xFF,)) * (len(router) - len(old_router)):
        raise ValueError("r531 router extension is not erased")
    rom[router_offset:router_offset + len(router)] = router

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-palette-publisher-atomic-r531-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "predecessor_sha256": R530_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "palette_guard_native": predecessor_receipt["palette_guard_native"],
        "router": f"{ROUTER:04X}",
        "router_len": len(router),
        "source_patches": predecessor_receipt["source_patches"],
        "interrupt_contract": (
            "LCD-off writes preserve caller interrupt state; LCD-on writes "
            "DI before phase selection and use delayed EI across RET"
        ),
        "phase_contract": (
            "mode 1 writes immediately while masked; visible-line calls wait "
            "through mode 3 into a fresh HBlank while still masked"
        ),
        "bank_contract": predecessor_receipt["bank_contract"],
        "register_contract": predecessor_receipt["register_contract"],
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
