#!/usr/bin/env python3
"""Compose r532: IME-preserving native BG palette row publication."""

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
OUT = ROOT / "tmp/palette-publisher-atomic-r532"
ROUTER = 0x7320
SOURCE_WRITER_ENTRY = 0x71E3


def word(value: int) -> bytes:
    return bytes((value & 0xFF, value >> 8))


def build_router() -> bytes:
    # The inherited guard enters with source bank in B and caller BC stacked.
    # Save caller DE, carry the source bank in D and original IE in E, then
    # mask interrupt sources without changing IME. Mode 1 is an immediate safe
    # window; visible-line calls acquire a fresh HBlank. The source writer
    # restores IE immediately before RET after all other live state is valid.
    code = bytearray.fromhex(
        "78 C1 D5 57 F0 FF 5F AF E0 FF "  # restore BC; save DE/bank/IE; IE=0
        "F0 40 CB 7F 28 16 "              # LCD off -> write now
        "F0 41 E6 03 FE 01 28 0E "        # VBlank -> write now
        "F0 41 E6 03 FE 03 20 F8 "        # acquire mode 3
        "F0 41 E6 03 20 FA "              # then fresh mode 0
        "7A E5 "                          # source bank -> A; save source HL
    )
    code.extend((0x21, *word(SOURCE_WRITER_ENTRY), 0xE5))
    code.extend((0xC3, r518.FIXED_SWITCH & 0xFF,
                 r518.FIXED_SWITCH >> 8))
    if len(code) != 47:
        raise AssertionError("r532 palette router length changed")
    return bytes(code)


def source_writer() -> bytes:
    # Mapper RET already consumed this entry address. Restore source HL, perform
    # the four native writes, load saved IE before restoring caller DE, then
    # publish IE as the penultimate instruction. Any pending interrupt is safe
    # either before or after the final RET because bank/stack/register state is
    # coherent. A returns as IE; its only exact callers discard A.
    return bytes.fromhex("E1 2A E2 2A E2 2A E2 2A E2 7B D1 E0 FF C9")


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
        raise ValueError("r532 bank-20 router cave is not erased")
    rom[router_offset:router_offset + len(router)] = router

    writer = source_writer()
    source_patches: dict[str, dict[str, object]] = {}
    expected_writer_preimage = bytes.fromhex(
        "E6 03 FE 01 28 0E F0 41 E6 03 FE 03 20 E1"
    )
    for bank in (13, 16):
        writer_offset = r518.off(bank, SOURCE_WRITER_ENTRY)
        if parent[writer_offset:writer_offset + len(writer)] \
                != expected_writer_preimage:
            raise ValueError(f"bank {bank} writer cave changed")
        rom[writer_offset:writer_offset + len(writer)] = writer
        source_patches[str(bank)] = {
            "writer_entry": f"{SOURCE_WRITER_ENTRY:04X}",
            "writer_len": len(writer),
        }

    r518.update_checksums(rom)
    candidate = bytes(rom)
    changed_from_parent = [
        hex(index)
        for index, (before, after) in enumerate(zip(parent, candidate))
        if before != after
    ]
    return candidate, {
        "schema": "penta-palette-publisher-atomic-r532-build-v1",
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
            "save IE and set IE=0 without changing IME; restore IE immediately "
            "before source-writer RET after bank/stack/register coherence"
        ),
        "phase_contract": (
            "LCD-off and mode-1 calls write immediately; visible-line calls "
            "acquire mode 3 then the immediately following mode 0"
        ),
        "bank_contract": (
            "source-bank return uses full $0061 switch so DC09, FF99, and "
            "the hardware MBC register are coherent before IE is restored"
        ),
        "register_contract": (
            "BC/DE restored; HL advances exactly four source bytes; flags "
            "remain phase-derived; A returns original IE and is dead at the "
            "complete exact $71DB->$7FE0->$717C call graph"
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
