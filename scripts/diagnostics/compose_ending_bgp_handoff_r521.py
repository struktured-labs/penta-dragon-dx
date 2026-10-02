#!/usr/bin/env python3
"""Compose r521: route restored dispatcher state past inherited POP HLs."""

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


PARENT_SHA256 = (
    "6e56a1589072b878df4135e02950c617cb8c87aace4b53fe58dc554b429f7261"
)
OUT = ROOT / "tmp/ending-bgp-handoff-r521"


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r520.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r520 parent identity changed")
    _r518_candidate, r518_receipt = r518.build(source)
    labels = {
        name: int(address, 16)
        for name, address in r518_receipt["labels"].items()
    }
    rom = bytearray(parent)
    extension_offset = r518.off(r518.CAVE_BANK, r520.r519.EXTENSION)

    # r520 has already restored HL and AF. Jump directly to the inherited
    # fade bodies; r518's dispatch labels at $7436/$743A each begin POP HL
    # and would otherwise consume the source caller's return address again.
    old_routes = bytes.fromhex("F1 C3 36 74 F1 C3 3A 74")
    route_offset = extension_offset + 12
    if rom[route_offset:route_offset + len(old_routes)] != old_routes:
        raise ValueError("r520 restored dispatch routes changed")
    new_routes = bytearray((0xF1, 0xC3))
    new_routes.extend(r520.r519.word(labels["credits_fade_sync"]))
    new_routes.extend((0xF1, 0xC3))
    new_routes.extend(r520.r519.word(labels["credits_fade_out_sync"]))
    rom[route_offset:route_offset + len(new_routes)] = new_routes

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r521-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "route_patch": f"{r520.r519.EXTENSION + 12:04X}",
        "route_patch_len": len(new_routes),
        "credits_fade_in": f"{labels['credits_fade_sync']:04X}",
        "credits_fade_out": f"{labels['credits_fade_out_sync']:04X}",
        "epilogue_pre_fade_reset": (
            "bank1:$554A -> existing $4289 mapper wrapper -> bank20; "
            "caller AF/BC/DE/HL exact; black CGB deck before native-equivalent "
            "FF47/FF48/FF49; restored dispatcher bypasses inherited POP HLs"
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
