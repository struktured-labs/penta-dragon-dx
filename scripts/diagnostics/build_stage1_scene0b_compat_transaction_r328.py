#!/usr/bin/env python3
"""Build r328: transactional stale-runtime compatibility without input loss.

r314-r327 prove two facts independently: the current DAD7 gateway is needed
to publish coherent Stage-1 tiles/attributes, but leaving that gateway resident
in the authenticated legacy runtime prevents the next native menu-open edge.
r328 therefore treats the current gateway as a one-shot transaction.  After
the native map/attr/hazard publisher completes, it restores the legacy gateway
and records a private DAFF completion marker.  The shared menu invalidator
clears that marker, so a later menu close can request another coherent repair.

The same menu wrapper restores the independently pinned signed BG art.  r320's
scroll-first atomic presentation leaf remains byte exact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import build_stage1_scene0b_menu_return_r321 as r321
import build_stage1_scene0b_publication_commit_r314 as r314
import build_stage1_scene0b_chr_restore_r315 as r315


ROOT = r321.ROOT
TMP = r321.TMP
BASE = r321.BASE
BASE_RECEIPT = r321.BASE_RECEIPT
OUTPUT = TMP / "stage1-scene0b-compat-transaction-r328/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-compat-transaction-r328/build-receipt.json"

BANK = 31
MARKER_ADDR = 0xDAFF
MARKER_VALUE = 0xA3
REPAIR_ADDR = r314.HANDLER_LABELS["repair"]
HOT_RESUME_ADDR = r314.HANDLER_LABELS["hot_resume"]
REPAIR_BYTES = HOT_RESUME_ADDR - REPAIR_ADDR
REPAIR_GATE_CAVE = 0x6F00
ACK_ADDR = 0x6E25
ACK_BYTES = 5
ACK_CAVE = 0x6E50
ART_HELPER_ADDR = 0x6E80
MENU_HOOK_ADDR = 0x6CDA
MENU_INVALIDATION = bytes.fromhex("3E FF EA 53 DF EA 57 DF")
MENU_EXIT_ADDR = 0x6CE2
MENU_WRAPPER_ADDR = 0x6ED0
ART_PAYLOAD_ADDR = 0x7000


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def offset(address: int) -> int:
    return r321.bank_offset(BANK, address)


def erased(rom: bytearray, address: int, width: int, label: str) -> None:
    if rom[offset(address):offset(address) + width] != bytes([0xFF]) * width:
        raise AssertionError(f"r328 {label} cave preimage changed")


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    preimages = r321.validate_preimages(source, receipt_bytes)
    repair_off = offset(REPAIR_ADDR)
    original_repair = source[repair_off:repair_off + REPAIR_BYTES]
    r314_local = REPAIR_ADDR - r314.HANDLER_ADDR
    if original_repair != r314.HANDLER[r314_local:r314_local + REPAIR_BYTES]:
        raise AssertionError("r328 r314 repair preimage changed")
    ack_off = offset(ACK_ADDR)
    if source[ack_off:ack_off + ACK_BYTES] != bytes.fromhex("3E C4 EA DE DA"):
        raise AssertionError("r328 r320 acknowledgment preimage changed")
    menu_off = offset(MENU_HOOK_ADDR)
    if source[menu_off:menu_off + len(MENU_INVALIDATION)] != MENU_INVALIDATION:
        raise AssertionError("r328 menu invalidation preimage changed")

    # A completed legacy transaction resumes directly without touching state.
    # Otherwise replay r314's exact DI/pending/cache/arm sequence.
    repair_gate = (
        bytes.fromhex("FA FF DA FE") + bytes((MARKER_VALUE, 0xCA))
        + HOT_RESUME_ADDR.to_bytes(2, "little") + original_repair
    )
    # Commit becomes legacy-gateway + completion marker, then uses r314's
    # untouched mapper tail.  The map is already complete and r320's atomic
    # leaf has already been selected by the reconstructed continuation.
    ack_cave = b"".join(
        bytes((0x3E, value, 0xEA, address & 0xFF, address >> 8))
        for address, value in (
            (0xDADE, 0xC2), (0xDADF, 0xB9), (0xDAE0, 0xDA),
            (MARKER_ADDR, MARKER_VALUE),
        )
    ) + r321.r320.SCENE0B_TAIL

    art_payload = source[r315.ART_SOURCE_OFFSET:r315.ART_SOURCE_OFFSET + r315.ART_BYTES]
    if digest(art_payload) != r315.ART_PAYLOAD_SHA256:
        raise AssertionError("r328 canonical signed art identity changed")
    menu_wrapper = (
        bytes.fromhex("F3 F0 40 F5 CB EF E0 40")
        + MENU_INVALIDATION
        + bytes((0xCD,)) + ART_HELPER_ADDR.to_bytes(2, "little")
        + bytes.fromhex("20 FB AF EA FF DA F1 CB AF E0 40 FB C3")
        + MENU_EXIT_ADDR.to_bytes(2, "little")
    )

    rom = bytearray(source)
    for address, payload, label in (
        (REPAIR_GATE_CAVE, repair_gate, "repair gate"),
        (ACK_CAVE, ack_cave, "commit acknowledgment"),
        (ART_HELPER_ADDR, r315.LCD_OFF_CANCEL_ART_HELPER, "art helper"),
        (MENU_WRAPPER_ADDR, menu_wrapper, "menu wrapper"),
        (ART_PAYLOAD_ADDR, art_payload, "art payload"),
    ):
        erased(rom, address, len(payload), label)
        rom[offset(address):offset(address) + len(payload)] = payload
    rom[repair_off:repair_off + REPAIR_BYTES] = bytes((0xC3,)) + REPAIR_GATE_CAVE.to_bytes(2, "little") + bytes(REPAIR_BYTES - 3)
    rom[ack_off:ack_off + ACK_BYTES] = bytes((0xC3,)) + ACK_CAVE.to_bytes(2, "little") + bytes(2)
    rom[menu_off:menu_off + len(MENU_INVALIDATION)] = bytes((0xC3,)) + MENU_WRAPPER_ADDR.to_bytes(2, "little") + bytes(5)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    if candidate[r321.r320.PRIMARY_ADDR:r321.r320.PRIMARY_END] != r321.r320.NEW_PRIMARY:
        raise AssertionError("r328 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r328 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-compat-transaction-r328-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "patch": {
            "transaction": "r314 map/attr/hazard publisher retained",
            "commit": "restore DAD7=C2 B9 DA; DAFF=A3",
            "menu_invalidation": "clear DAFF; restore canonical signed BG art",
            "atomic_presentation": "r320 fixed:$12E0-$1302 byte exact",
        },
        "required_live_gates": ["scene0B full menu/visual", "hazard", "north", "speed"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--receipt", type=Path, default=RECEIPT)
    args = parser.parse_args()
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(candidate)
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
