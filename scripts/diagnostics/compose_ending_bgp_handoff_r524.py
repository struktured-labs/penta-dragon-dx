#!/usr/bin/env python3
"""Compose r524: zero-perturbation credits dispatch plus epilogue preblack."""

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
OUT = ROOT / "tmp/ending-bgp-handoff-r524"
EPILOGUE_PRE_FADE_RESET_CALL = 0x554A
RETURN_AFTER_PRE_FADE_RESET = EPILOGUE_PRE_FADE_RESET_CALL + 3
CREDITS_DISPATCH = 0x742A
CREDITS_IN_TRAMPOLINE = 0x73C0
PRIVATE_PREBLACK = 0x73E0
NATIVE_RESET_AF = 0xFFA0


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

    if rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] != bytes.fromhex("CD 16 0A"):
        raise ValueError("epilogue pre-fade reset caller changed")
    wrapper = r518.CREDITS_FADE_WRAPPER
    rom[
        EPILOGUE_PRE_FADE_RESET_CALL:EPILOGUE_PRE_FADE_RESET_CALL + 3
    ] = bytes((0xCD, wrapper & 0xFF, wrapper >> 8))

    dispatch_offset = r518.off(r518.CAVE_BANK, CREDITS_DISPATCH)
    dispatch_preimage = bytes.fromhex(
        "E5 F8 02 7E FE 75 28 04 FE 87 28 04 "
        "E1 C3 3E 74 E1 C3 49 74"
    )
    if rom[dispatch_offset:dispatch_offset + len(dispatch_preimage)] \
            != dispatch_preimage:
        raise ValueError("r518 credits dispatcher changed")

    # The $3E75 credits-in path takes the same JR/POP HL/JP sequence and the
    # same 112 cycles as r518, merely fetching its POP/JP from $73C0. $3E87
    # remains byte-for-byte untouched. Return $554D is the sole fallthrough.
    displacement = CREDITS_IN_TRAMPOLINE - (CREDITS_DISPATCH + 8)
    if displacement != -0x72:
        raise AssertionError("r524 credits trampoline displacement changed")
    rom[dispatch_offset + 7] = displacement & 0xFF
    rom[dispatch_offset + 14:dispatch_offset + 16] = word(PRIVATE_PREBLACK)

    trampoline = bytes((0xE1, 0xC3)) + word(labels["credits_fade_sync"])
    trampoline_offset = r518.off(
        r518.CAVE_BANK, CREDITS_IN_TRAMPOLINE
    )
    if parent[trampoline_offset:trampoline_offset + len(trampoline)] \
            != bytes((0xFF,)) * len(trampoline):
        raise ValueError("r524 credits-in trampoline cave is not erased")
    rom[trampoline_offset:trampoline_offset + len(trampoline)] = trampoline

    # The dispatcher has restored HL and leaves A=$4D after CP $87. Preserve
    # BC/DE/HL around the inherited mirror, then synthesize the exact AF=FFA0
    # observed at native $0A16's BGP write: AND clears C, INC $FF creates
    # Z+H, and the final LD A,$FF preserves those flags.
    preblack = bytearray((0xC5, 0xD5, 0xE5, 0x3E, 0xFF, 0xCD))
    preblack.extend(word(labels["mirror_ending_value"]))
    preblack.extend((0xE1, 0xD1, 0xC1,
                     0x3E, 0xFF, 0xA7, 0x3C, 0x3E, 0xFF,
                     0xE0, 0x47, 0xE0, 0x48, 0xE0, 0x49,
                     0xC3, 0x9A, 0x09))
    if len(preblack) != 26:
        raise AssertionError("r524 preblack length changed")
    preblack_offset = r518.off(r518.CAVE_BANK, PRIVATE_PREBLACK)
    if parent[preblack_offset:preblack_offset + len(preblack)] \
            != bytes((0xFF,)) * len(preblack):
        raise ValueError("r524 preblack cave is not erased")
    rom[preblack_offset:preblack_offset + len(preblack)] = preblack

    # Credits-out is fully unchanged; credits-in differs only in fetch address
    # and is instruction/cycle/register equivalent through the service entry.
    if rom[dispatch_offset + 8:dispatch_offset + 12] \
            != parent[dispatch_offset + 8:dispatch_offset + 12]:
        raise AssertionError("r524 changed credits-out dispatch")

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-ending-bgp-handoff-r524-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "credits_in_trampoline": f"{CREDITS_IN_TRAMPOLINE:04X}",
        "credits_in_trampoline_len": len(trampoline),
        "private_preblack": f"{PRIVATE_PREBLACK:04X}",
        "private_preblack_len": len(preblack),
        "native_reset_af": f"{NATIVE_RESET_AF:04X}",
        "credits_fade_in_cycles": {"r518": 112, "r524": 112},
        "credits_fade_out": "byte-for-byte r518 dispatch path",
        "epilogue_pre_fade_reset": (
            "unique bank1:$554A return $554D -> existing $4289 wrapper -> "
            "formerly unreachable dispatcher fallthrough -> bank20 preblack; "
            "native-equivalent BGP/OBP reset returns AF=FFA0"
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
