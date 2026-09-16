#!/usr/bin/env python3
"""Compose r530: atomically wait for and publish native BG palette rows."""

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


PARENT_SHA256 = (
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"
)
OUT = ROOT / "tmp/palette-publisher-atomic-r530"
ROUTER = 0x7320
SOURCE_MASKED_ENTRY = r529.SOURCE_MASKED_ENTRY
SOURCE_UNMASKED_ENTRY = r529.SOURCE_UNMASKED_ENTRY


def word(value: int) -> bytes:
    return bytes((value & 0xFF, value >> 8))


def build_router() -> bytes:
    # B holds the source bank and caller BC remains on the stack. For an
    # enabled LCD, close the interrupt race before waiting through mode 3 and
    # into a fresh HBlank. Keep IME clear through the coherent $0061 switch,
    # all four source-bank CRAM writes, and the writer's RET. The LCD-off path
    # preserves the caller's interrupt state and needs no mode wait.
    code = bytearray.fromhex(
        "F0 40 CB 7F 28 17 "              # LCD off -> unmasked route
        "F3 "                             # LCD on: own the whole window
        "F0 41 E6 03 FE 03 20 F8 "        # wait until mode 3
        "F0 41 E6 03 20 FA "              # then fresh mode 0
        "78 C1 E5 "                       # bank -> A; restore BC; save HL
    )
    code.extend((0x21, *word(SOURCE_MASKED_ENTRY)))
    code.extend((0x18, 0x06))
    code.extend(bytes.fromhex("78 C1 E5"))
    code.extend((0x21, *word(SOURCE_UNMASKED_ENTRY)))
    code.extend((0xE5, 0xC3, r518.FIXED_SWITCH & 0xFF,
                 r518.FIXED_SWITCH >> 8))
    if len(code) != 39:
        raise AssertionError("r530 palette router length changed")
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

    native = labels["palette_guard_native"]
    native_offset = r518.off(r518.CAVE_BANK, native)
    if parent[native_offset:native_offset + 3] != bytes.fromhex("F0 40 E6"):
        raise ValueError("r518 palette native entry changed")
    rom[native_offset:native_offset + 3] = bytes((
        0xC3, ROUTER & 0xFF, ROUTER >> 8,
    ))

    router = build_router()
    router_offset = r518.off(r518.CAVE_BANK, ROUTER)
    if parent[router_offset:router_offset + len(router)] \
            != bytes((0xFF,)) * len(router):
        raise ValueError("r530 bank-20 router cave is not erased")
    rom[router_offset:router_offset + len(router)] = router

    source_patches: dict[str, dict[str, object]] = {}
    for bank in (13, 16):
        masked = r529.source_writer(masked=True)
        unmasked = r529.source_writer(masked=False)
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
        "schema": "penta-palette-publisher-atomic-r530-build-v1",
        "experimental": True,
        "promotable": False,
        "base_sha256": r518.BASE_SHA256,
        "parent_sha256": PARENT_SHA256,
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "palette_guard_native": f"{native:04X}",
        "router": f"{ROUTER:04X}",
        "router_len": len(router),
        "source_patches": source_patches,
        "interrupt_contract": (
            "LCD-off writes preserve caller interrupt state; LCD-on writes "
            "DI before the fresh-HBlank wait and use delayed EI across RET"
        ),
        "bank_contract": (
            "source-bank return uses full $0061 switch so DC09, FF99, and "
            "the hardware MBC register are coherent before interrupts resume"
        ),
        "register_contract": (
            "source bank remains in B through the atomic wait; caller BC and "
            "HL are restored before the selected source-bank writer returns"
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
