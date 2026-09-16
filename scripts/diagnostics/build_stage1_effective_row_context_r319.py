#!/usr/bin/env python3
"""Build r319: key semantic-row dispatch by the effective incoming room.

r318 already contains r310's precompile repair, which applies the room-$01
wall attributes using native effective-room byte FFE5.  The four later
bank-20 semantic-return trampolines still read FFBD, however.  While a hidden
incoming map is being published, FFBD can still name the outgoing room, so a
rotating-hazard row can select the wrong immutable semantic page.

Change only the four ``LDH A,[$FFBD]`` operands to ``$FFE5``.  The complete
nine-byte preimage and target are checked at every site.  Instruction width,
flags, registers, branch targets, stack behavior, and timing remain exact;
only the already-resolved room source changes.  No emulator is invoked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_precompile_effective_room_r310 as r310
import build_stage1_room01_semantic_row_r300 as r300
import build_stage1_row_gate_abi_speed_r318 as r318


ROOT = r318.ROOT
TMP = r318.TMP
BASE = r318.DEFAULT_OUTPUT
BASE_RECEIPT = r318.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-effective-row-context-r319/candidate.gb"
DEFAULT_RECEIPT = (
    TMP / "stage1-effective-row-context-r319/build-receipt.json"
)

BASE_SHA256 = (
    "909d7ee16bbf5080fd9992567bbe784e6df3234a08f9bde07ff7a10b2f729abb"
)
BASE_RECEIPT_SHA256 = (
    "57e853011f4ba03252be78a60eefc385cc60bc71a97fc0c5b0d92ea4bc8e8cfd"
)
BASE_SCHEMA = "penta-stage1-row-gate-abi-speed-r318-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "2afaa7c87b1cb84f00c25a0f9d6edc8b811144b31ef64430fa0fa9d9d8bcc2db"
)

BANK = 20
TRAMPOLINE_ADDRS = (0x61A0, 0x67ED, 0x6B70, 0x6D9E)
OLD_TRAMPOLINE = bytes.fromhex("F0 BD 3D C2 00 43 C3 00 45")
NEW_TRAMPOLINE = bytes.fromhex("F0 E5 3D C2 00 43 C3 00 45")
CHECKSUM_OFFSETS = r318.r317.r316.CHECKSUM_OFFSETS

EFFECTIVE_ROOM_SETTER_ADDR = 0x0AD3
EFFECTIVE_ROOM_SETTER = bytes.fromhex("7E E0 CE A7 20 02 F0 BD E0 E5")

PRIMARY_HELPER_SHA256 = (
    "1a0eddfae5a08bbed263c7cbee940eb9b13b0f7c16d9dceafc16335d8212cda0"
)
PRIMARY_LUT_SHA256 = (
    "93259ce7973eac613608746296f3b8a12bf9d4501410b479454cafe773a96906"
)
ROOM01_HELPER_SHA256 = (
    "95721ce0d5a562fe65bd99fdeb2aaf6bf49b89d754778f3c6875145be2c8fdd3"
)
ROOM01_LUT_SHA256 = (
    "f2f2665656f551e84c782ae55ab90a0bca28a465043ff7046b31dfea16f3031a"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    r318.require(condition, message)


def bank_offset(bank: int, address: int) -> int:
    return r318.r317.r316.bank_offset(bank, address)


def owned_ranges() -> set[int]:
    """Return the four authorized LDH a8 operand file offsets."""
    return {
        bank_offset(BANK, address) + 1 for address in TRAMPOLINE_ADDRS
    }


def effective_room(table_value: int, ffbd: int) -> int:
    """Model fixed ``$0AD3-$0ADC``: nonzero table A, else FFBD."""
    require(0 <= table_value <= 0xFF, "table_value is not a byte")
    require(0 <= ffbd <= 0xFF, "ffbd is not a byte")
    return table_value if table_value else ffbd


def dec_a_flags(value: int, incoming_f: int) -> tuple[int, int]:
    """Return the exact LR35902 DEC A result and flags."""
    require(0 <= value <= 0xFF, "DEC input is not a byte")
    require(0 <= incoming_f <= 0xF0 and incoming_f & 0x0F == 0,
            "incoming F is not a canonical flags byte")
    result = (value - 1) & 0xFF
    flags = incoming_f & 0x10  # DEC preserves carry only.
    if result == 0:
        flags |= 0x80
    flags |= 0x40  # N is always set.
    if value & 0x0F == 0:
        flags |= 0x20
    return result, flags


def trampoline_model(
    ffe5: int,
    incoming_f: int,
    *,
    bc: int = 0x1234,
    de: int = 0x5678,
    hl: int = 0x9ABC,
    sp: int = 0xDEF0,
) -> dict[str, int]:
    """Model all observable effects through the selected helper entry."""
    for name, value in (("bc", bc), ("de", de), ("hl", hl), ("sp", sp)):
        require(0 <= value <= 0xFFFF, f"{name} is not a word")
    a, flags = dec_a_flags(ffe5, incoming_f)
    room01 = ffe5 == 0x01
    return {
        "a": a,
        "f": flags,
        "bc": bc,
        "de": de,
        "hl": hl,
        "sp": sp,
        "target": r300.ROOM01_HELPER_ADDR
        if room01 else r300.PRIMARY_HELPER_ADDR,
        "t_cycles": 44 if room01 else 32,
    }


def exhaustive_contract() -> dict[str, Any]:
    """Exhaust native resolution plus every FFE5/flags dispatch input."""
    resolver_cases = 0
    outgoing_dispatch_differences = 0
    for table_value in range(0x100):
        for ffbd in range(0x100):
            resolved = effective_room(table_value, ffbd)
            require(
                resolved == (table_value if table_value else ffbd),
                "native effective-room resolver model drifted",
            )
            resolved_target = trampoline_model(resolved, 0)["target"]
            require(
                resolved_target
                == (r300.ROOM01_HELPER_ADDR
                    if resolved == 1 else r300.PRIMARY_HELPER_ADDR),
                "resolved FFE5 dispatch model drifted",
            )
            outgoing_target = trampoline_model(ffbd, 0)["target"]
            if resolved_target != outgoing_target:
                outgoing_dispatch_differences += 1
            resolver_cases += 1
    require(outgoing_dispatch_differences == 509,
            "effective/outgoing dispatch contrast count drifted")

    dispatch_cases = 0
    target_counts = {"primary": 0, "room01": 0}
    for ffe5 in range(0x100):
        for incoming_f in range(0, 0x100, 0x10):
            result = trampoline_model(ffe5, incoming_f)
            expected_target = (
                r300.ROOM01_HELPER_ADDR
                if ffe5 == 0x01 else r300.PRIMARY_HELPER_ADDR
            )
            require(result["target"] == expected_target,
                    "FFE5 semantic dispatch target drifted")
            require(result["a"] == ((ffe5 - 1) & 0xFF),
                    "trampoline A result drifted")
            require(result["f"] & 0x10 == incoming_f & 0x10,
                    "trampoline failed to preserve carry")
            require(result["bc"] == 0x1234
                    and result["de"] == 0x5678
                    and result["hl"] == 0x9ABC
                    and result["sp"] == 0xDEF0,
                    "trampoline changed a preserved register")
            target_counts["room01" if ffe5 == 1 else "primary"] += 1
            dispatch_cases += 1

    truth_rows = []
    for label, table_value, ffbd, expected_room, expected_target in (
        ("room05_to_room01_hidden", 1, 5, 1,
         r300.ROOM01_HELPER_ADDR),
        ("room01_to_room05_hidden", 5, 1, 5,
         r300.PRIMARY_HELPER_ADDR),
        ("settled_room01_fallback", 0, 1, 1,
         r300.ROOM01_HELPER_ADDR),
        ("settled_room05_fallback", 0, 5, 5,
         r300.PRIMARY_HELPER_ADDR),
    ):
        resolved = effective_room(table_value, ffbd)
        route = trampoline_model(resolved, 0)
        require((resolved, route["target"])
                == (expected_room, expected_target),
                f"transition truth row failed: {label}")
        truth_rows.append({
            "case": label,
            "native_table_A": f"{table_value:02X}",
            "FFBD": f"{ffbd:02X}",
            "FFE5": f"{resolved:02X}",
            "target": f"${route['target']:04X}",
        })

    return {
        "native_resolver_cases_exhausted": resolver_cases,
        "resolved_dispatch_cases_exhausted": resolver_cases,
        "effective_vs_outgoing_target_differences": (
            outgoing_dispatch_differences
        ),
        "ffe5_flags_cases_exhausted": dispatch_cases,
        "dispatch_target_counts": target_counts,
        "room01_iff": "FFE5 == $01",
        "native_resolver": "FFE5 = table A when A!=00; otherwise FFBD",
        "transition_truth_rows": truth_rows,
    }


def semantic_artifacts(source: bytes) -> dict[str, tuple[int, bytes]]:
    """Construct and pin both semantic helpers and both immutable LUTs."""
    primary_helper = r300.semantic.build_helper()
    stage1_lut_offset = bank_offset(
        r300.semantic.STAGE1_TABLE_BANK,
        r300.semantic.STAGE1_TABLE_ADDR,
    )
    stage1_lut = source[stage1_lut_offset:stage1_lut_offset + 0x100]
    primary_lut = r300.semantic.build_lut(stage1_lut)
    room01_helper = r300.build_room01_helper(primary_helper)
    room01_lut = r300.build_room01_lut(primary_lut)

    expected = (
        ("primary_helper", primary_helper, PRIMARY_HELPER_SHA256),
        ("primary_lut", primary_lut, PRIMARY_LUT_SHA256),
        ("room01_helper", room01_helper, ROOM01_HELPER_SHA256),
        ("room01_lut", room01_lut, ROOM01_LUT_SHA256),
    )
    for label, payload, expected_sha in expected:
        require(digest(payload) == expected_sha,
                f"{label} generated identity drifted")

    return {
        "primary_helper": (
            bank_offset(BANK, r300.PRIMARY_HELPER_ADDR), primary_helper
        ),
        "primary_lut": (
            bank_offset(BANK, r300.PRIMARY_LUT_ADDR), primary_lut
        ),
        "room01_helper": (
            bank_offset(BANK, r300.ROOM01_HELPER_ADDR), room01_helper
        ),
        "room01_lut": (
            bank_offset(BANK, r300.ROOM01_LUT_ADDR), room01_lut
        ),
    }


def source_preimages(source: bytes) -> dict[str, Any]:
    require(len(source) == r318.r317.r305.r304.ROM_SIZE,
            "r319 base is not exactly 512 KiB")
    require(BASE_SHA256 == r318.EXPECTED_CANDIDATE_SHA256,
            "pinned r318 module identity changed")
    require(digest(source) == BASE_SHA256,
            f"wrong exact r318 base: {digest(source)}")

    preimages = []
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        actual = source[offset:offset + len(OLD_TRAMPOLINE)]
        require(actual == OLD_TRAMPOLINE,
                f"bank20:${address:04X} full trampoline preimage drifted")
        preimages.append({
            "address": f"bank20:${address:04X}",
            "file_offset": f"0x{offset:06X}",
            "preimage": actual.hex(" ").upper(),
            "target": NEW_TRAMPOLINE.hex(" ").upper(),
        })

    setter = source[
        EFFECTIVE_ROOM_SETTER_ADDR:
        EFFECTIVE_ROOM_SETTER_ADDR + len(EFFECTIVE_ROOM_SETTER)
    ]
    require(setter == EFFECTIVE_ROOM_SETTER,
            "native FFE5 effective-room resolver changed")

    require(
        source[
            r310.PRECOMPILE_SITE:
            r310.PRECOMPILE_SITE + len(r310.NEW_PRECOMPILE)
        ] == r310.NEW_PRECOMPILE,
        "r318 lost the r310 precompile route",
    )
    r310_helper = bank_offset(r310.HELPER_BANK, r310.HELPER_ADDR)
    require(
        source[r310_helper:r310_helper + len(r310.NEW_HELPER)]
        == r310.NEW_HELPER,
        "r318 lost the r310 FFE5 precompile helper",
    )
    require(digest(r310.NEW_HELPER) == r310.NEW_HELPER_SHA256,
            "r310 helper constant identity drifted")

    artifacts = semantic_artifacts(source)
    for label, (offset, expected) in artifacts.items():
        require(source[offset:offset + len(expected)] == expected,
                f"r318 {label} preimage changed")

    require(
        source[
            r318.ROW_OFFSET:
            r318.ROW_OFFSET + len(r318.NEW_ROW_PREFIX)
        ] == r318.NEW_ROW_PREFIX,
        "r318 bank19 ABI/speed repair changed",
    )
    require(source[r318.r317.r316.CGB_FLAG_OFFSET]
            == r318.r317.r316.CGB_ONLY_FLAG,
            "r318 CGB-only header changed")
    checksummed = bytearray(source)
    r318.r317.r305.r304.update_checksums(checksummed)
    require(bytes(checksummed) == source,
            "r318 source checksums are not canonical")

    return {
        "candidate_sha256": BASE_SHA256,
        "trampolines": preimages,
        "native_effective_room_setter": setter.hex(" ").upper(),
        "r310_precompile_route": "exact",
        "r310_effective_room_helper_sha256": digest(r310.NEW_HELPER),
        "semantic_artifact_sha256": {
            "primary_helper": PRIMARY_HELPER_SHA256,
            "primary_lut": PRIMARY_LUT_SHA256,
            "room01_helper": ROOM01_HELPER_SHA256,
            "room01_lut": ROOM01_LUT_SHA256,
        },
        "r318_row_abi_speed_repair": "exact",
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    require(len(candidate) == len(source), "r319 changed ROM size")
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        require(
            candidate[offset:offset + len(NEW_TRAMPOLINE)]
            == NEW_TRAMPOLINE,
            f"bank20:${address:04X} full trampoline target drifted",
        )

    changed = {
        offset
        for offset, (before, after) in enumerate(
            zip(source, candidate, strict=True)
        )
        if before != after
    }
    functional = changed - CHECKSUM_OFFSETS
    require(functional == owned_ranges(),
            "r319 functional delta is not exactly four LDH operands")
    require(len(functional) == 4,
            "r319 functional delta count changed")
    require(changed <= owned_ranges() | CHECKSUM_OFFSETS,
            "r319 changed bytes outside owned operands and checksums")

    artifacts = semantic_artifacts(source)
    for label, (offset, expected) in artifacts.items():
        require(
            candidate[offset:offset + len(expected)]
            == source[offset:offset + len(expected)] == expected,
            f"r319 changed {label}",
        )

    require(
        candidate[
            r310.PRECOMPILE_SITE:
            r310.PRECOMPILE_SITE + len(r310.NEW_PRECOMPILE)
        ] == source[
            r310.PRECOMPILE_SITE:
            r310.PRECOMPILE_SITE + len(r310.NEW_PRECOMPILE)
        ] == r310.NEW_PRECOMPILE,
        "r319 changed the r310 precompile route",
    )
    r310_helper = bank_offset(r310.HELPER_BANK, r310.HELPER_ADDR)
    require(
        candidate[r310_helper:r310_helper + len(r310.NEW_HELPER)]
        == source[r310_helper:r310_helper + len(r310.NEW_HELPER)]
        == r310.NEW_HELPER,
        "r319 changed the r310 effective-room precompile helper",
    )
    require(
        candidate[
            r318.ROW_OFFSET:
            r318.ROW_OFFSET + len(r318.NEW_ROW_PREFIX)
        ] == source[
            r318.ROW_OFFSET:
            r318.ROW_OFFSET + len(r318.NEW_ROW_PREFIX)
        ] == r318.NEW_ROW_PREFIX,
        "r319 changed the r318 bank19 ABI/speed repair",
    )
    require(candidate[r318.r317.r316.CGB_FLAG_OFFSET]
            == r318.r317.r316.CGB_ONLY_FLAG,
            "r319 lost the CGB-only header")
    checksummed = bytearray(candidate)
    r318.r317.r305.r304.update_checksums(checksummed)
    require(bytes(checksummed) == candidate,
            "r319 header/global checksums are not canonical")

    return {
        "functional_changed_bytes_from_r318": len(functional),
        "changed_file_offsets_from_r318": [
            f"0x{offset:06X}" for offset in sorted(functional)
        ],
        "checksum_changed_offsets": [
            f"0x{offset:04X}"
            for offset in sorted(changed & CHECKSUM_OFFSETS)
        ],
        "escaped_bytes": 0,
        "rom_size_delta_bytes": 0,
        "full_nine_byte_targets_exact": len(TRAMPOLINE_ADDRS),
        "semantic_helpers_and_luts_exact": True,
        "r310_precompile_fix_exact": True,
        "r318_row_abi_speed_fix_exact": True,
        "cgb_only_header_retained": True,
    }


def timing_contract() -> dict[str, Any]:
    contract = {
        "instruction_width_delta_bytes": 0,
        "all_paths_delta_t_cycles_from_r318": 0,
        "room01_target_4500_t_cycles": 44,
        "other_room_target_4300_t_cycles": 32,
        "renderer_delta_t_cycles": 0,
        "ordinary_frame_delta_t_cycles": 0,
        "reason": "LDH a8 operand-only substitution; opcode and control flow exact",
    }
    require(len(OLD_TRAMPOLINE) == len(NEW_TRAMPOLINE) == 9,
            "trampoline instruction width changed")
    differences = {
        index for index, (before, after) in enumerate(
            zip(OLD_TRAMPOLINE, NEW_TRAMPOLINE, strict=True)
        )
        if before != after
    }
    require(differences == {1},
            "trampoline changed beyond the LDH operand")
    return contract


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    semantics = exhaustive_contract()
    timing = timing_contract()

    rom = bytearray(source)
    for address in TRAMPOLINE_ADDRS:
        offset = bank_offset(BANK, address)
        require(bytes(rom[offset:offset + len(OLD_TRAMPOLINE)])
                == OLD_TRAMPOLINE,
                f"bank20:${address:04X} changed during construction")
        rom[offset + 1] = 0xE5
    r318.r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        require(sha == EXPECTED_CANDIDATE_SHA256,
                f"r319 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-effective-row-context-r319-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "root_cause": (
            "r318 retains r310's FFE5-keyed precompile repair, but the four "
            "bank20 semantic-row return trampolines still select the room01 "
            "or primary immutable page from outgoing FFBD during hidden-map "
            "publication"
        ),
        "composition": {
            "r306_effective_incoming_row_dispatch": "four operand behavior",
            "r310_precompile_fix": "retained byte-exact from r318",
            "r318_row_abi_speed_fix": "retained byte-exact",
        },
        "patch": {
            "bank": BANK,
            "trampolines": [
                f"${address:04X}" for address in TRAMPOLINE_ADDRS
            ],
            "old": OLD_TRAMPOLINE.hex(" ").upper(),
            "new": NEW_TRAMPOLINE.hex(" ").upper(),
            "change": "four LDH a8 operands only: BD -> E5",
        },
        "offline_contract": {
            "semantic": semantics,
            "abi": {
                "A": "FFE5 minus one, exactly as DEC A",
                "F": "Z/N/H from DEC A; incoming carry preserved",
                "BC_DE_HL_SP_exact": True,
                "stack_and_memory_exact": True,
                "branch_targets_exact": ["$4300", "$4500"],
                "room01_helper_iff": "FFE5 == $01",
            },
            "timing": timing,
        },
        "ownership": ownership,
        "required_live_gates": [
            "current-ROM room05-to-room01 transition has no wall-edge corruption",
            "current-ROM hazard/menu round-trip has no yellow trails, gray spikes, or red/green artifacts",
            "rendered-continuity oracle rejects all reported visual signatures",
            "full 2800-frame Stage-1 release speed gate remains at least 95%",
            "cold CHR writer audit remains canonical with zero bad writes",
            "Analogue Pocket visual round-trip before promotion",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def validate_preimages(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    contract = source_preimages(source)
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r318 base receipt identity changed")
    receipt = json.loads(base_receipt_bytes)
    require(receipt.get("schema") == BASE_SCHEMA,
            "r318 base receipt schema changed")
    require(receipt.get("candidate_sha256") == BASE_SHA256,
            "r318 base receipt names another ROM")
    require(receipt.get("emulator_invoked") is False,
            "r318 base build receipt unexpectedly invoked an emulator")
    return {**contract, "build_receipt_sha256": BASE_RECEIPT_SHA256, "schema": BASE_SCHEMA}


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-effective-row-context-r319-build-v1",
        "status": "STATIC_PASS_R319_LIVE_GATES_REQUIRED",
        "base": preimages,
        "decision": "STATIC_EFFECTIVE_ROW_CONTEXT_COMPLETE_LIVE_GATES_REQUIRED",
    })
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r318.r317.r305.r304.checked_output(
        args.output, "candidate output"
    )
    receipt_path = r318.r317.r305.r304.checked_output(
        args.receipt, "receipt output"
    )
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r318.r317.r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
