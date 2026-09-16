#!/usr/bin/env python3
"""Compose r519: synchronize the stock epilogue's pre-fade FF reset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402


PARENT_SHA256 = (
    "918d95a88349aa2bb29c5a52285c79d5dba7a014848e5ccf41bae46890961808"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r519"

EPILOGUE_PRE_FADE_RESET_CALL = 0x554A
NATIVE_MONO_RESET = 0x0A16
RETURN_AFTER_PRE_FADE_RESET = EPILOGUE_PRE_FADE_RESET_CALL + 3
DISPATCH = 0x742A
EXTENSION = 0x7B40
FIXED_BANK1_PRESERVE_AF = 0x099A


def word(value: int) -> bytes:
    return bytes((value & 0xFF, value >> 8))


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, parent_receipt = r518.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r518 parent identity changed")
    labels = {
        name: int(address, 16)
        for name, address in parent_receipt["labels"].items()
    }
    if labels["credits_fade_dispatch"] != DISPATCH:
        raise ValueError("r518 credits dispatcher moved")

    rom = bytearray(parent)
    reset_preimage = bytes((0xCD, NATIVE_MONO_RESET & 0xFF,
                            NATIVE_MONO_RESET >> 8))
    if rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] != reset_preimage:
        raise ValueError("epilogue pre-fade reset caller changed")

    dispatch_offset = r518.off(r518.CAVE_BANK, DISPATCH)
    dispatch_preimage = bytes.fromhex(
        "E5 F8 02 7E FE 75 28 04 FE 87 28 04"
    )
    if rom[dispatch_offset:dispatch_offset + len(dispatch_preimage)] \
            != dispatch_preimage:
        raise ValueError("r518 credits dispatcher preimage changed")

    # Read the low byte of the source return address exactly as r518 did, but
    # move the three-way decision out of line. This admits the new $554D
    # return without shifting any inherited service entry.
    dispatch_hook = bytes.fromhex("E5 F8 02 7E E1 C3") + word(EXTENSION)
    rom[dispatch_offset:dispatch_offset + len(dispatch_hook)] = dispatch_hook

    dispatch_in = labels["credits_fade_dispatch_in"]
    dispatch_out = labels["credits_fade_dispatch_out"]
    preblack = EXTENSION + 18
    extension = bytearray()
    for return_low, target in (
        (0x75, dispatch_in),
        (0x87, dispatch_out),
        (RETURN_AFTER_PRE_FADE_RESET & 0xFF, preblack),
    ):
        extension.extend((0xFE, return_low, 0xCA))
        extension.extend(word(target))
    extension.append(0xC3)
    extension.extend(word(dispatch_in))
    if EXTENSION + len(extension) != preblack:
        raise AssertionError("r519 dispatch length changed")

    # Reproduce $0A16's exact external ABI (A=$FF; original flags and
    # BC/DE/HL; BGP/OBP0/OBP1=$FF), but prepare matching CGB BG CRAM before
    # publishing BGP. $099A restores bank 1 while preserving AF, then RETs to
    # the original $554D continuation already on the source stack.
    extension.extend((0x3E, 0xFF, 0xF5, 0xC5, 0xD5, 0xE5, 0xCD))
    extension.extend(word(labels["mirror_ending_value"]))
    extension.extend((0xE1, 0xD1, 0xC1, 0xF1,
                      0xE0, 0x47, 0xE0, 0x48, 0xE0, 0x49, 0xC3))
    extension.extend(word(FIXED_BANK1_PRESERVE_AF))

    extension_offset = r518.off(r518.CAVE_BANK, EXTENSION)
    if parent[extension_offset:extension_offset + len(extension)] \
            != bytes((0xFF,)) * len(extension):
        raise ValueError("r519 extension cave is not erased")
    rom[extension_offset:extension_offset + len(extension)] = extension

    wrapper = r518.CREDITS_FADE_WRAPPER
    rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] = bytes((0xCD, wrapper & 0xFF, wrapper >> 8))

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r519-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "extension": f"{EXTENSION:04X}",
        "extension_len": len(extension),
        "dispatch": f"{DISPATCH:04X}",
        "preblack": f"{preblack:04X}",
        "epilogue_pre_fade_reset": (
            "bank1:$554A -> existing $4289 mapper wrapper -> bank20; "
            "exact black CGB deck before native-equivalent FF47/FF48/FF49"
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
