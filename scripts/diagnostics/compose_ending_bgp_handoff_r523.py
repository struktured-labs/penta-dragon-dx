#!/usr/bin/env python3
"""Compose r523: private cycle-equivalent dispatch for epilogue preblack."""

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
OUT = ROOT / "tmp/ending-bgp-handoff-r523"
EPILOGUE_PRE_FADE_RESET_CALL = 0x554A
RETURN_AFTER_PRE_FADE_RESET = EPILOGUE_PRE_FADE_RESET_CALL + 3
PRIVATE_DISPATCH = 0x73C0
PRIVATE_PREBLACK = 0x73E0


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
    rom = bytearray(parent)

    reset_preimage = bytes.fromhex("CD 16 0A")
    if rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] != reset_preimage:
        raise ValueError("epilogue pre-fade reset caller changed")
    wrapper = r518.CREDITS_FADE_WRAPPER
    rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] = bytes((0xCD, wrapper & 0xFF, wrapper >> 8))

    # The existing bank-1 wrapper leaves its saved AF above the source return
    # after mapping bank 20. Preserve it until the private dispatcher chooses
    # one of the two inherited credits paths or the unique $554D epilogue path.
    entry_offset = r518.off(r518.CAVE_BANK, r518.CREDITS_FADE_BANK20_CONT)
    entry_preimage = bytes.fromhex("F1 C3 2A 74")
    if rom[entry_offset:entry_offset + 4] != entry_preimage:
        raise ValueError("r518 credits bank-20 entry changed")
    rom[entry_offset:entry_offset + 3] = bytes((
        0xC3, PRIVATE_DISPATCH & 0xFF, PRIVATE_DISPATCH >> 8,
    ))

    # Entry+dispatch cycles to each inherited credits service are exactly the
    # same as r518. The POP AF moves from $428F to the selected route, while
    # PUSH/POP HL bracket the return-address read before the comparisons.
    dispatch = bytearray.fromhex(
        "E5 F8 04 7E E1 "
        "FE 75 28 08 FE 87 28 08 FE 4D 28 08 "
        "F1 C3 3E 74 F1 C3 49 74 F1 C3 E0 73"
    )
    if len(dispatch) != 29:
        raise AssertionError("r523 private dispatch length changed")
    dispatch_offset = r518.off(r518.CAVE_BANK, PRIVATE_DISPATCH)
    if parent[dispatch_offset:dispatch_offset + len(dispatch)] \
            != bytes((0xFF,)) * len(dispatch):
        raise ValueError("r523 private dispatch cave is not erased")
    rom[dispatch_offset:dispatch_offset + len(dispatch)] = dispatch

    # Exact $0A16 external ABI: original flags and BC/DE/HL, A=$FF, and
    # BGP/OBP0/OBP1=$FF. The only addition is matching black BG CRAM before
    # BGP publication. Fixed $099A maps bank 1 while preserving the final AF.
    preblack = bytearray((0xF5, 0xC5, 0xD5, 0xE5, 0x3E, 0xFF, 0xCD))
    preblack.extend(word(labels["mirror_ending_value"]))
    preblack.extend((0xE1, 0xD1, 0xC1, 0xF1, 0x3E, 0xFF,
                     0xE0, 0x47, 0xE0, 0x48, 0xE0, 0x49,
                     0xC3, 0x9A, 0x09))
    if len(preblack) != 24:
        raise AssertionError("r523 preblack length changed")
    preblack_offset = r518.off(r518.CAVE_BANK, PRIVATE_PREBLACK)
    if parent[preblack_offset:preblack_offset + len(preblack)] \
            != bytes((0xFF,)) * len(preblack):
        raise ValueError("r523 preblack cave is not erased")
    rom[preblack_offset:preblack_offset + len(preblack)] = preblack

    # The inherited dispatcher is deliberately immutable; its earlier users
    # must retain r518 behavior and timing exactly.
    inherited_dispatch = r518.off(r518.CAVE_BANK, labels["credits_fade_dispatch"])
    if rom[inherited_dispatch:inherited_dispatch + 20] \
            != parent[inherited_dispatch:inherited_dispatch + 20]:
        raise AssertionError("r523 changed the inherited credits dispatcher")

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r523-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "private_dispatch": f"{PRIVATE_DISPATCH:04X}",
        "private_dispatch_len": len(dispatch),
        "private_preblack": f"{PRIVATE_PREBLACK:04X}",
        "private_preblack_len": len(preblack),
        "credits_fade_in_cycles": {"r518": 112, "r523": 112},
        "credits_fade_out_cycles": {"r518": 128, "r523": 128},
        "epilogue_pre_fade_reset": (
            "unique bank1:$554A return $554D -> existing $4289 wrapper -> "
            "private bank20 dispatch/preblack; inherited credits dispatcher "
            "unchanged and credits route cycles identical"
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
