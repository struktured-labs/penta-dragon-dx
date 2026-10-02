#!/usr/bin/env python3
"""Build r329: stackless stale-runtime map publication transaction.

r328 proves that restoring the legacy gateway after r314 commits does not
restore menu input; r314's reconstructed return stack is itself the lasting
control-flow regression.  r329 never edits the caller stack.  A private DAFF
state arms the ordinary candidate DAD7 route, waits for both physical semantic
keys to be repopulated, then restores the legacy gateway.  The existing native
publisher reaches r320's atomic $12E0 leaf normally.

The shared menu invalidator clears the completion state and restores canonical
signed BG art, making each menu close an explicit, deterministic repair hook.
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
OUTPUT = TMP / "stage1-scene0b-stackless-transaction-r329/candidate.gb"
RECEIPT = TMP / "stage1-scene0b-stackless-transaction-r329/build-receipt.json"

BANK = 31
HANDLER_ADDR = r314.HANDLER_ADDR
OLD_HANDLER = r314.HANDLER
MARKER_ADDR = 0xDAFF
MARKER_PENDING = 0xA4
MARKER_COMPLETE = 0xA3
STALE = bytes.fromhex("C2 B9 DA")
PENDING = bytes.fromhex("CD 13 00")
CURRENT = bytes.fromhex("C4 13 00")
CACHE_ADDRS = (0xDF53, 0xDF57)
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


def emit_triplet_compare(a: r314.Asm, payload: bytes, failure: str) -> None:
    for index, value in enumerate(payload):
        address = 0xDADE + index
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, value)
        a.jp(0xC2, failure)


def emit_triplet_write(a: r314.Asm, payload: bytes) -> None:
    for index, value in enumerate(payload):
        address = 0xDADE + index
        a.db(0x3E, value, 0xEA, address & 0xFF, address >> 8)


def assemble_handler() -> tuple[bytes, dict[str, int]]:
    a = r314.Asm(HANDLER_ADDR)
    a.label("entry")
    a.db(0xFE, r314.RST_OUTER_RETURN & 0xFF)
    a.jp(0xC2, "unknown")
    a.db(0x23, 0x7E, 0xFE, r314.RST_OUTER_RETURN >> 8)
    a.jp(0xC2, "unknown")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x0B)
    a.jp(0xC2, "resume")
    a.db(0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x01)
    a.jp(0xC2, "resume")
    a.db(0xF0, 0xB7, 0xFE, 0x02)
    a.jp(0xC2, "resume")

    a.db(0xFA, MARKER_ADDR & 0xFF, MARKER_ADDR >> 8, 0xFE, MARKER_COMPLETE)
    a.jp(0xCA, "complete")
    a.db(0xFE, MARKER_PENDING)
    a.jp(0xCA, "pending")

    # Marker-free current and stale runtimes both get one ordinary dirty
    # publication.  Stale first receives the temporary unconditional CALL.
    emit_triplet_compare(a, CURRENT, "check_stale")
    a.jp(0xC3, "arm_current")
    a.label("check_stale")
    emit_triplet_compare(a, STALE, "resume")
    a.db(0xF3)
    emit_triplet_write(a, PENDING)
    a.jp(0xC3, "arm_common")

    a.label("arm_current")
    a.db(0xF3)
    a.label("arm_common")
    a.db(0x3E, 0xFF)
    for address in CACHE_ADDRS:
        a.db(0xEA, address & 0xFF, address >> 8)
    a.db(0x3E, MARKER_PENDING, 0xEA, MARKER_ADDR & 0xFF, MARKER_ADDR >> 8)
    a.jp(0xC3, "resume")

    a.label("pending")
    # Accept only an exact temporary/current gateway.  Both physical keys
    # must have been consumed and repopulated before compatibility commits.
    emit_triplet_compare(a, PENDING, "pending_current")
    a.jp(0xC3, "pending_keys")
    a.label("pending_current")
    emit_triplet_compare(a, CURRENT, "resume")
    a.label("pending_keys")
    for address in CACHE_ADDRS:
        a.db(0xFA, address & 0xFF, address >> 8, 0xFE, 0xFF)
        a.jp(0xCA, "resume")
    a.db(0xF3)
    emit_triplet_write(a, STALE)
    a.db(0x3E, MARKER_COMPLETE, 0xEA, MARKER_ADDR & 0xFF, MARKER_ADDR >> 8)
    a.jp(0xC3, "resume")

    a.label("complete")
    emit_triplet_compare(a, STALE, "resume")
    a.label("resume")
    a.db(0xF8, 0x02, 0x36, r314.r305.RUNTIME_RELOCATED_ADDR & 0xFF)
    a.db(0x23, 0x36, r314.r305.RUNTIME_RELOCATED_ADDR >> 8)
    a.db(0xE1, 0x3E, 0x01, 0xC3, 0x61, 0x00)
    a.label("unknown")
    a.db(0xE1, 0x3E, 0x01, 0xB7, 0xC9)
    return a.finish(), dict(a.labels)


HANDLER, HANDLER_LABELS = assemble_handler()


def build(source: bytes, receipt_bytes: bytes) -> tuple[bytes, dict]:
    preimages = r321.validate_preimages(source, receipt_bytes)
    old_off = offset(HANDLER_ADDR)
    if source[old_off:old_off + len(OLD_HANDLER)] != r321.r320.r319.r318.r317.r316.r314.HANDLER:
        # r320 changes three bytes inside the r314 handler; validate those via
        # its own exact scene0B contract rather than accepting arbitrary drift.
        r321.r320.scene0b_static_contract(source)
    if len(HANDLER) > len(OLD_HANDLER):
        raise AssertionError("r329 handler exceeds r314-owned cave")
    menu_off = offset(MENU_HOOK_ADDR)
    if source[menu_off:menu_off + len(MENU_INVALIDATION)] != MENU_INVALIDATION:
        raise AssertionError("r329 menu invalidation preimage changed")
    art_payload = source[r315.ART_SOURCE_OFFSET:r315.ART_SOURCE_OFFSET + r315.ART_BYTES]
    if digest(art_payload) != r315.ART_PAYLOAD_SHA256:
        raise AssertionError("r329 canonical signed art identity changed")
    menu_wrapper = (
        bytes.fromhex("F3 F0 40 F5 CB EF E0 40") + MENU_INVALIDATION
        + bytes((0xCD,)) + ART_HELPER_ADDR.to_bytes(2, "little")
        + bytes.fromhex("20 FB AF EA FF DA F1 CB AF E0 40 FB C3")
        + MENU_EXIT_ADDR.to_bytes(2, "little")
    )
    rom = bytearray(source)
    rom[old_off:old_off + len(OLD_HANDLER)] = bytes([0xFF]) * len(OLD_HANDLER)
    rom[old_off:old_off + len(HANDLER)] = HANDLER
    for address, payload, label in (
        (ART_HELPER_ADDR, r315.LCD_OFF_CANCEL_ART_HELPER, "art helper"),
        (MENU_WRAPPER_ADDR, menu_wrapper, "menu wrapper"),
        (ART_PAYLOAD_ADDR, art_payload, "art payload"),
    ):
        target = offset(address)
        if rom[target:target + len(payload)] != bytes([0xFF]) * len(payload):
            raise AssertionError(f"r329 {label} cave preimage changed")
        rom[target:target + len(payload)] = payload
    rom[menu_off:menu_off + len(MENU_INVALIDATION)] = bytes((0xC3,)) + MENU_WRAPPER_ADDR.to_bytes(2, "little") + bytes(5)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    if candidate[r321.r320.PRIMARY_ADDR:r321.r320.PRIMARY_END] != r321.r320.NEW_PRIMARY:
        raise AssertionError("r329 changed r320 atomic publisher")
    checked = bytearray(candidate)
    r321.r320.r319.r318.r317.r305.r304.update_checksums(checked)
    if bytes(checked) != candidate:
        raise AssertionError("r329 checksums not canonical")
    sha = digest(candidate)
    return candidate, {
        "schema": "penta-stage1-scene0b-stackless-transaction-r329-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED", "promotable": False,
        "emulator_invoked": False, "candidate_sha256": sha, "base": preimages,
        "patch": {"handler": f"bank31:$6CEA-${HANDLER_ADDR + len(HANDLER) - 1:04X}", "stack_edits": 0, "pending": "DAFF=A4 until DF53/DF57 repopulate", "complete": "DAD7=C2 B9 DA; DAFF=A3", "menu": "clear marker + canonical art", "atomic_publisher": "r320 exact"},
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
    print(json.dumps({"candidate_sha256": receipt["candidate_sha256"], "handler_bytes": len(HANDLER), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
