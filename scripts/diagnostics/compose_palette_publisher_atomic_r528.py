#!/usr/bin/env python3
"""Compose r528: make each native four-byte BG palette publish atomic."""

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


PARENT_SHA256 = (
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"
)
OUT = ROOT / "tmp/palette-publisher-atomic-r528"
ROUTER = 0x7320
SOURCE_MASKED_ENTRY = 0x71E3
SOURCE_UNMASKED_ENTRY = 0x71F4


def word(value: int) -> bytes:
    return bytes((value & 0xFF, value >> 8))


def build_router() -> bytes:
    # The palette guard has already reached LCD-off, VBlank, or a fresh
    # HBlank. Preserve caller HL and the source-bank byte in B. PUSH/LD/POP do
    # not alter BIT's Z flag, so the LCD-off branch remains interrupt-neutral.
    code = bytearray.fromhex("F0 40 CB 7F E5 78 C1 20 05")
    code.extend((0x21, *word(SOURCE_UNMASKED_ENTRY)))
    code.extend((0x18, 0x04, 0xF3, 0x21, *word(SOURCE_MASKED_ENTRY)))
    code.extend((0xE5, 0xC3, r518.FIXED_SWITCH_RET & 0xFF,
                 r518.FIXED_SWITCH_RET >> 8))
    if len(code) != 22:
        raise AssertionError("r528 palette router length changed")
    return bytes(code)


def source_writer(*, masked: bool) -> bytes:
    # Mapper RET enters here with caller HL on the stack. Four two-byte source
    # writes fit the window selected by the bank-20 guard. On the masked path,
    # EI is delayed until after RET, so no ISR can split the CRAM transaction.
    code = bytearray((0xE1,))
    code.extend(bytes.fromhex("2A E2") * 4)
    if masked:
        code.append(0xFB)
    code.append(0xC9)
    return bytes(code)


def build(source: bytes) -> tuple[bytes, dict[str, object]]:
    parent, _parent_receipt = r527.build(source)
    if hashlib.sha256(parent).hexdigest() != PARENT_SHA256:
        raise ValueError("r527 parent identity changed")
    _r518_candidate, r518_receipt = r518.build(source)
    labels = {
        name: int(address, 16)
        for name, address in r518_receipt["labels"].items()
    }
    rom = bytearray(parent)

    ready = labels["palette_guard_native_ready"]
    ready_offset = r518.off(r518.CAVE_BANK, ready)
    if parent[ready_offset:ready_offset + 3] != bytes.fromhex("78 C1 E5"):
        raise ValueError("r518 palette native-ready entry changed")
    rom[ready_offset:ready_offset + 3] = bytes((
        0xC3, ROUTER & 0xFF, ROUTER >> 8,
    ))

    router = build_router()
    router_offset = r518.off(r518.CAVE_BANK, ROUTER)
    if parent[router_offset:router_offset + len(router)] \
            != bytes((0xFF,)) * len(router):
        raise ValueError("r528 bank-20 router cave is not erased")
    rom[router_offset:router_offset + len(router)] = router

    source_patches: dict[str, dict[str, object]] = {}
    for bank in (13, 16):
        masked = source_writer(masked=True)
        unmasked = source_writer(masked=False)
        masked_offset = r518.off(bank, SOURCE_MASKED_ENTRY)
        unmasked_offset = r518.off(bank, SOURCE_UNMASKED_ENTRY)
        if parent[masked_offset:masked_offset + len(masked)] \
                != bytes.fromhex("E6 03 FE 01 28 0E F0 41 E6 03 FE"):
            raise ValueError(f"bank {bank} masked-writer cave changed")
        if parent[unmasked_offset:unmasked_offset + len(unmasked)] \
                != bytes.fromhex("03 20 FA 2A E2 2A E2 2A E2 2A"):
            raise ValueError(f"bank {bank} unmasked-writer cave changed")
        rom[masked_offset:masked_offset + len(masked)] = masked
        rom[unmasked_offset:unmasked_offset + len(unmasked)] = unmasked
        source_patches[str(bank)] = {
            "masked_entry": f"{SOURCE_MASKED_ENTRY:04X}",
            "masked_len": len(masked),
            "unmasked_entry": f"{SOURCE_UNMASKED_ENTRY:04X}",
            "unmasked_len": len(unmasked),
        }

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-palette-publisher-atomic-r528-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "palette_guard_native_ready": f"{ready:04X}",
        "router": f"{ROUTER:04X}",
        "router_len": len(router),
        "source_patches": source_patches,
        "interrupt_contract": (
            "LCD-off writes preserve caller interrupt state; LCD-on writes "
            "use DI through all four CRAM bytes and delayed EI across RET"
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
