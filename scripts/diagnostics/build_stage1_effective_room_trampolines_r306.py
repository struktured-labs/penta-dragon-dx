#!/usr/bin/env python3
"""Build r306: select Stage-1 semantic rows by the effective incoming room.

r305's relocated scene-$0B gateway is correct, but r300's four bank-20
semantic-return trampolines classify the row with live room byte FFBD.  During
the hidden-map build FFBD still names the outgoing room.  Native fixed-bank
code has already resolved the incoming/effective room and stores it in FFE5.

Change only the four LDH operands from FFBD to FFE5.  Opcode width, flags,
register ABI, branch layout, and timing are byte-for-byte equivalent.  This is
a strict causal diagnostic overlay; the separate bank-16 resident-installer
hardening is deliberately not mixed into this ROM.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_room01_semantic_row_r300 as r300
import build_stage1_unified_scene0b_r305 as r305


ROOT = r305.ROOT
TMP = r305.TMP
BASE = r305.DEFAULT_OUTPUT
BASE_RECEIPT = r305.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-effective-room-trampolines-r306/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-effective-room-trampolines-r306/build-receipt.json"
)

BASE_SHA256 = r305.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "71a3a477a2be2fad9f0f83e24b9bdf6cacd940c7d772a546658bbaca1166c450"
)
LIVE_REJECTION = BASE.parent / "live-scene0b-dcbb40/receipt.json"
LIVE_REJECTION_SHA256 = (
    "7ceca21f33dabaf91437934549ba1fa1960f42bd4b03b901370b67f445a513b7"
)
R306_LIVE_REJECTION = (
    DEFAULT_OUTPUT.parent / "live-scene0b-dcbb40/receipt.json"
)
R306_LIVE_REJECTION_SHA256 = (
    "9e1f6d683202f8fc5847fb851b0cc615a7d7bf1ff1aa2ae7e134232314884452"
)
EXPECTED_CANDIDATE_SHA256 = (
    "8e170f2eaf3f718c924f47ac3be0c7dec1b5433ffd3975a5f5e299a7a60fb06d"
)

BANK = r300.SEMANTIC_BANK
TRAMPOLINE_ADDRS = r300.TRAMPOLINE_ADDRS
OLD_TRAMPOLINE = r300.CONTEXT_TRAMPOLINE
NEW_TRAMPOLINE = bytes.fromhex("F0 E5 3D C2 00 43 C3 00 45")
ROOM01_HELPER_ADDR = r300.ROOM01_HELPER_ADDR
PRIMARY_HELPER_ADDR = r300.PRIMARY_HELPER_ADDR
EFFECTIVE_ROOM_SETTER_ADDR = 0x0AD3
EFFECTIVE_ROOM_SETTER = bytes.fromhex("7E E0 CE A7 20 02 F0 BD E0 E5")
CHECKSUM_OFFSETS = r305.CHECKSUM_OFFSETS


def bank_offset(bank: int, address: int) -> int:
    return r305.r304.bank_offset(bank, address)


def owned_ranges() -> set[int]:
    # Only each LDH a8 operand changes.  Keep full instruction preimages below
    # for branch/continuation proof, but authorize no surrounding byte.
    return {
        bank_offset(BANK, address) + 1 for address in TRAMPOLINE_ADDRS
    }


def effective_room(table_value: int, ffbd: int) -> int:
    """Model fixed:$0AD4-$0ADD exactly."""
    return table_value if table_value else ffbd


def selected_helper(room: int) -> int:
    # LDH A,[room]; DEC A leaves Z exactly for room $01.
    return ROOM01_HELPER_ADDR if room == 1 else PRIMARY_HELPER_ADDR


def exhaustive_contract() -> dict[str, Any]:
    cases = 0
    for table_value in range(256):
        for ffbd in range(256):
            resolved = effective_room(table_value, ffbd)
            expected = table_value if table_value != 0 else ffbd
            r305.r304.require(resolved == expected,
                              "effective-room resolver model drifted")
            helper = selected_helper(resolved)
            r305.r304.require(
                helper
                == (ROOM01_HELPER_ADDR if expected == 1
                    else PRIMARY_HELPER_ADDR),
                "semantic helper model drifted",
            )
            cases += 1

    # Explicit transition truth rows.  FFBD deliberately remains outgoing;
    # the nonzero native table value is the incoming/effective room.
    rows = []
    for label, table_value, ffbd, expected_room, expected_helper in (
        ("room05_to_room01_hidden_build", 1, 5, 1, ROOM01_HELPER_ADDR),
        ("room01_to_room05_hidden_build", 5, 1, 5, PRIMARY_HELPER_ADDR),
        ("settled_room01_fallback", 0, 1, 1, ROOM01_HELPER_ADDR),
        ("settled_room05_fallback", 0, 5, 5, PRIMARY_HELPER_ADDR),
    ):
        resolved = effective_room(table_value, ffbd)
        helper = selected_helper(resolved)
        r305.r304.require(
            (resolved, helper) == (expected_room, expected_helper),
            f"transition model failed: {label}",
        )
        rows.append({
            "case": label,
            "native_table_A": f"{table_value:02X}",
            "FFBD": f"{ffbd:02X}",
            "FFE5": f"{resolved:02X}",
            "helper": f"${helper:04X}",
        })
    return {
        "cases_exhausted": cases,
        "native_resolver": (
            "FFE5 = table A when A!=00; otherwise FFE5 = FFBD"
        ),
        "transition_rows": rows,
        "room01_helper": "$4500",
        "all_other_rooms_helper": "$4300",
    }


def validate_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    r305.r304.require(
        source[
            EFFECTIVE_ROOM_SETTER_ADDR:
            EFFECTIVE_ROOM_SETTER_ADDR + len(EFFECTIVE_ROOM_SETTER)
        ] == EFFECTIVE_ROOM_SETTER,
        "native effective-room setter changed",
    )
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        r305.r304.require(
            source[offset:offset + len(OLD_TRAMPOLINE)] == OLD_TRAMPOLINE,
            f"bank20:${address:04X} contextual trampoline changed",
        )

    r305.r304.require(r305.r304.digest(LIVE_REJECTION.read_bytes())
                      == LIVE_REJECTION_SHA256,
                      "r305 live rejection identity changed")
    rejected = json.loads(LIVE_REJECTION.read_text())
    r305.r304.require(rejected.get("rom_sha256") == BASE_SHA256,
                      "live rejection names another ROM")
    return {
        "native_setter": "fixed:$0AD3-$0ADC",
        "native_setter_bytes": EFFECTIVE_ROOM_SETTER.hex(" ").upper(),
        "native_setter_semantics": (
            "LD A,[HL]; FFCE=A; if A==0 load FFBD; always store FFE5"
        ),
        "r305_live_rejection_sha256": LIVE_REJECTION_SHA256,
        "r305_transient": "room01 target attrs wrong samples 75-80; clear 81",
    }


def live_rejection_contract() -> dict[str, Any]:
    r305.r304.require(r305.r304.digest(R306_LIVE_REJECTION.read_bytes())
                      == R306_LIVE_REJECTION_SHA256,
                      "r306 live rejection identity changed")
    result = json.loads(R306_LIVE_REJECTION.read_text())
    r305.r304.require(result.get("rom_sha256")
                      == EXPECTED_CANDIDATE_SHA256,
                      "r306 live rejection names another ROM")
    r305.r304.require(result.get("passed") is False,
                      "r306 live receipt is not a rejection")
    mismatches = result.get("hazard_mismatch_frames", {})
    r305.r304.require(
        mismatches.get("total") == 56
        and mismatches.get("first", {}).get("sample") == 75,
        "r306 live mismatch signature changed",
    )
    counters = result.get("hazard_publication_counters", {})
    for name in ("runtime_scene0b_entry_mismatches",
                 "scene0b_atomic_setup_invalid_h",
                 "scene0b_mapdone_invalid_latch"):
        r305.r304.require(counters.get(name) == 0,
                          f"r306 owner/latch control changed: {name}")
    return {
        "receipt_sha256": R306_LIVE_REJECTION_SHA256,
        "rom_sha256": result["rom_sha256"],
        "passed": False,
        "hazard_mismatch_frames": mismatches["total"],
        "first_mismatch_sample": mismatches["first"]["sample"],
        "scene0b_transient_samples": "75-80 (unchanged from r305)",
        "owner_latch_controls_passed": True,
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(source) == len(candidate) == r305.r304.ROM_SIZE,
                      "ROM size changed")
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    allowed = owned_ranges() | CHECKSUM_OFFSETS
    r305.r304.require(changed <= allowed,
                      f"r306 escaped ownership: {sorted(changed-allowed)[:8]}")
    r305.r304.require(functional == owned_ranges(),
                      "r306 functional delta is not exactly four operands")
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        r305.r304.require(
            candidate[offset:offset + len(NEW_TRAMPOLINE)] == NEW_TRAMPOLINE,
            f"bank20:${address:04X} effective-room trampoline changed",
        )
        r305.r304.require(
            candidate[offset] == source[offset] == 0xF0
            and candidate[offset + 2:offset + len(NEW_TRAMPOLINE)]
            == source[offset + 2:offset + len(OLD_TRAMPOLINE)],
            f"bank20:${address:04X} changed beyond LDH operand",
        )

    # Pin the two semantic implementations and LUT pages byte-exact to r305.
    for address, width, label in (
        (r300.PRIMARY_HELPER_ADDR, len(r300.semantic.build_helper()),
         "primary helper"),
        (r300.ROOM01_HELPER_ADDR, len(r300.build_room01_helper(
            r300.semantic.build_helper())), "room01 helper"),
        (r300.PRIMARY_LUT_ADDR, 0x100, "primary LUT"),
        (r300.ROOM01_LUT_ADDR, 0x100, "room01 LUT"),
    ):
        offset = bank_offset(BANK, address)
        r305.r304.require(
            candidate[offset:offset + width] == source[offset:offset + width],
            f"{label} changed",
        )
    return {
        "functional_changed_bytes": len(functional),
        "functional_changed_offsets": [
            f"0x{offset:06X}" for offset in sorted(functional)
        ],
        "checksum_changed_offsets": [
            f"0x{offset:04X}" for offset in sorted(changed & CHECKSUM_OFFSETS)
        ],
        "escaped_bytes": 0,
        "helpers_and_LUTs_byte_exact": True,
        "r305_other_functional_bytes_exact": True,
    }


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    r305.r304.require(r305.r304.digest(base_receipt_bytes)
                      == BASE_RECEIPT_SHA256,
                      "r305 build receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r305 receipt names another ROM")
    preimages = validate_preimages(source)
    semantic = exhaustive_contract()
    live_rejection = live_rejection_contract()

    rom = bytearray(source)
    allowed: set[int] = set()
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        # Patch only the a8 operand.  Full old/new instruction streams are
        # checked independently above and below.
        r305.patch_exact(
            rom, source, offset + 1, bytes((0xBD,)), bytes((0xE5,)), allowed,
            f"effective-room operand bank20:${address:04X}",
        )
    r305.r304.require(allowed == owned_ranges(),
                      "ownership construction drifted")
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(sha == EXPECTED_CANDIDATE_SHA256,
                          f"candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-effective-room-trampolines-r306-build-v1",
        "status": "LIVE_REJECTED",
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r305-live-rejected-wall-transient",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "live_rejection_sha256": LIVE_REJECTION_SHA256,
        },
        "candidate_sha256": sha,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "r300 semantic trampolines read outgoing/live FFBD while native "
            "prepublication code has already resolved the hidden incoming "
            "map's effective room into FFE5"
        ),
        "live_rejection": live_rejection,
        "patch": {
            "bank": BANK,
            "trampolines": [f"${address:04X}" for address in TRAMPOLINE_ADDRS],
            "old": OLD_TRAMPOLINE.hex(" ").upper(),
            "new": NEW_TRAMPOLINE.hex(" ").upper(),
            "change": "four LDH a8 operands only: BD -> E5",
        },
        "offline_contract": {
            "preimages": preimages,
            "semantic": semantic,
            "abi": {
                "instruction_width_exact": True,
                "flags_exact": True,
                "BC_DE_HL_SP_exact": True,
                "A_dead_before_selected_helper": True,
                "branch_targets_exact": ["$4300", "$4500"],
            },
            "timing": {
                "all_paths_delta_t_cycles": 0,
                "trampoline_room01_t_cycles": 44,
                "trampoline_other_room_t_cycles": 32,
                "renderer_delta_t_cycles": 0,
                "transition_delta_t_cycles": 0,
            },
        },
        "ownership": ownership,
        "excluded_followup": {
            "bank16_resident_installer_hardening": (
                "deliberately excluded for strict four-byte causal isolation"
            ),
            "paused_576_cell_postscan": True,
        },
        "required_live_gates": [
            "REJECTED: room01 entry retained samples 75-80 transient",
            "room01 exit/room05 target IDs use primary BG0 semantics",
            "room12 and hazard-menu controls remain exact",
            "r305 FFA5 remains 99/9D",
            "full reported-regression and speed gates",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r305.r304.checked_output(args.receipt, "receipt output")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
