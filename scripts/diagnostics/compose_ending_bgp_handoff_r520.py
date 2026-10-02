#!/usr/bin/env python3
"""Compose r520: preserve caller AF across r519's return dispatcher."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_ending_bgp_handoff_r519 as r519  # noqa: E402


PARENT_SHA256 = (
    "9b368aaef0e48757fb0bfed108e30f20490150f329e78b6001ed0b53fa7f7af9"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r520"
PREBLACK_ROUTE = r519.EXTENSION + 20
PREBLACK = PREBLACK_ROUTE + 1


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r519.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r519 parent identity changed")
    _r518_candidate, r518_receipt = r518.build(source)
    labels = {
        name: int(address, 16)
        for name, address in r518_receipt["labels"].items()
    }
    rom = bytearray(parent)

    dispatch_offset = r518.off(r518.CAVE_BANK, r519.DISPATCH)
    old_hook = bytes.fromhex("E5 F8 02 7E E1 C3 40 7B")
    if rom[dispatch_offset:dispatch_offset + len(old_hook)] != old_hook:
        raise ValueError("r519 dispatch hook changed")
    # Save AF before LD HL,SP+r8 alters flags. The source return is now four
    # bytes above SP; the out-of-line branches pop that saved AF before using
    # any inherited service or the new preblack path.
    hook = bytes.fromhex("F5 E5 F8 04 7E E1 C3 40 7B")
    rom[dispatch_offset:dispatch_offset + len(hook)] = hook

    old_extension = bytes.fromhex(
        "FE 75 CA 36 74 FE 87 CA 3A 74 FE 4D CA 52 7B C3 36 74 "
        "3E FF F5 C5 D5 E5 CD C2 75 E1 D1 C1 F1 "
        "E0 47 E0 48 E0 49 C3 9A 09"
    )
    extension_offset = r518.off(r518.CAVE_BANK, r519.EXTENSION)
    if rom[extension_offset:extension_offset + len(old_extension)] \
            != old_extension:
        raise ValueError("r519 extension changed")

    extension = bytearray.fromhex(
        # CP return; JR Z to restore-in/restore-out/restore-preblack.
        "FE 75 28 08 FE 87 28 08 FE 4D 28 08 "
        # Preserve r518's fail-safe fallback to credits fade-in.
        "F1 C3 36 74 F1 C3 3A 74 F1 "
        # Native-equivalent reset, now beginning with the restored flags.
        "3E FF F5 C5 D5 E5 CD C2 75 E1 D1 C1 F1 "
        "E0 47 E0 48 E0 49 C3 9A 09"
    )
    if len(extension) != 43:
        raise AssertionError("r520 extension length changed")
    tail = parent[
        extension_offset + len(old_extension):extension_offset + len(extension)
    ]
    if tail != bytes((0xFF,)) * len(tail):
        raise ValueError("r520 extension tail is not erased")
    rom[extension_offset:extension_offset + len(extension)] = extension

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r520-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "extension": f"{r519.EXTENSION:04X}",
        "extension_len": len(extension),
        "dispatch": f"{r519.DISPATCH:04X}",
        "preblack_route": f"{PREBLACK_ROUTE:04X}",
        "preblack": f"{PREBLACK:04X}",
        "epilogue_pre_fade_reset": (
            "bank1:$554A -> existing $4289 mapper wrapper -> bank20; "
            "caller AF/BC/DE/HL exact; black CGB deck before native-equivalent "
            "FF47/FF48/FF49; fixed:$099A bank-1 return preserves AF"
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
