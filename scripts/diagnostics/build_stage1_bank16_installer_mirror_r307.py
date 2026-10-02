#!/usr/bin/env python3
"""Build r307: make the bank-16 cold installer emit canonical shared WRAM.

r305's mirrored lazy installer can execute while either ROM bank 13 or the
private Ted bank 16 is mapped.  Its copy program is bank-relative, but three
bank-16 source fragments were still from the pre-production payload: DA13
lost the odd physical-map tag, DBDF-DBF0 became zero code, and the bank-16
continuation set DF51=$A8 without first installing DBF1-DBFC.

This static-only overlay repairs those bank-16 sources and repacks one exact
36-byte continuation slot.  It models both installer executions and requires
byte-identical canonical output over every byte the DF51 sentinel owns.  It
does not modify the room-wall implementation and does not invoke an emulator.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import build_stage1_unified_scene0b_r305 as r305


ROOT = r305.ROOT
TMP = r305.TMP
BASE = TMP / "stage1-unified-scene0b-r305/candidate.gb"
BASE_RECEIPT = TMP / "stage1-unified-scene0b-r305/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-bank16-installer-mirror-r307/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-bank16-installer-mirror-r307/build-receipt.json"

BASE_SHA256 = "9c83a6937a1b71f2b4d0a6628fa3022d8f46f89e46c7aafa23a61a8d9166ce13"
BASE_RECEIPT_SHA256 = (
    "71a3a477a2be2fad9f0f83e24b9bdf6cacd940c7d772a546658bbaca1166c450"
)
BASE_SCHEMA = "penta-stage1-unified-scene0b-r305-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "77722cf7abfff564de72caf0cdd06dbb774bf0614c071933247178817b3bea84"
)

CANONICAL_BANK = 13
MIRROR_BANK = 16
INSTALLER_ADDR = 0x7CBF
INSTALLER_CALL_SITES = (0x6B15, 0x6B1E, 0x6B85)
INSTALLER_CALL = bytes.fromhex("C4 BF 7C")
INSTALLER = bytes.fromhex(
    "C5 D5 E5 "
    "21 00 7B 11 00 DA 01 5D 00 CD B3 09 "
    "21 B2 7B 11 60 DA 01 2E 00 CD B3 09 "
    "21 4D 7C 11 8E DA 01 72 00 CD B3 09 "
    "21 3A 56 11 80 DB 01 23 00 CD B3 09 "
    "C3 5C 57"
)
INSTALLER_TAIL_ADDR = 0x575C
INSTALLER_TAIL = bytes.fromhex(
    "11 A4 DB 21 9A 56 0E 24 CD B3 09 "
    "21 CA 56 0E 24 CD B3 09 "
    "11 EC DB 21 FA 56 0E 05 CD B3 09 "
    "C3 46 55"
)

ATOMIC_SOURCE_ADDR = 0x7B13
OLD_MIRROR_ATOMIC_SOURCE = bytes.fromhex(
    "7C E0 A5 F3 F0 FF EA 5A DF E6 04 E0 FF C9"
)
CANONICAL_ATOMIC_SOURCE = bytes.fromhex(
    "7C 3C E0 A5 F0 FF EA 5A DF E6 04 E0 FF C9"
)
RUNTIME_SOURCE_B_ADDR = 0x56E1
OLD_MIRROR_RUNTIME_SOURCE_B = bytes(13)
CANONICAL_RUNTIME_SOURCE_B = bytes.fromhex(
    "F0 E1 B7 CA 97 34 F3 3E 15 EA 00 21 C3"
)
RUNTIME_SOURCE_C_ADDR = 0x56FA
OLD_MIRROR_RUNTIME_SOURCE_C = bytes(5)
CANONICAL_RUNTIME_SOURCE_C = bytes.fromhex("00 40 C3 97 34")

CONTINUATION_ADDR = 0x5546
CONTINUATION_END = 0x556A
FINAL_INSTALLER = bytes.fromhex(
    "CD 16 55 3E A8 EA 51 DF E1 D1 C1 C9"
)
OLD_MIRROR_CONTINUATION = FINAL_INSTALLER + bytes(24)
EXTENSION_SOURCE_ADDR = 0x555D
CANONICAL_EXTENSION_SOURCE_ADDR = 0x5830
CANONICAL_EXTENSION = bytes.fromhex(
    "F0 BA B7 28 04 AF E0 A5 C9 C3 E2 10"
)
MIRROR_EXTENSION_PREFIX = bytes.fromhex(
    "11 F1 DB 21 5D 55 0E 0C CD B3 09"
)
NEW_MIRROR_CONTINUATION = (
    MIRROR_EXTENSION_PREFIX
    + FINAL_INSTALLER
    + CANONICAL_EXTENSION
    + bytes(1)
)

R305_FIXED_PREDICATE_GATEWAY_ADDR = 0x7C96
R305_FIXED_PREDICATE_GATEWAY = bytes.fromhex(
    "FA 80 D8 E6 F7 FE 02 C4 13 00"
)
SENTINEL_ADDR = 0xDF51
SENTINEL_VALUE = 0xA8

ABSOLUTE_BRANCH_OPCODES = frozenset({
    0xC2, 0xC3, 0xC4, 0xCA, 0xCC, 0xCD,
    0xD2, 0xD4, 0xDA, 0xDC,
})

# These are the exact source/destination records encoded by $7CBF and $575C.
COPY_REGIONS = (
    ("DA00-DA5C", 0x7B00, 0xDA00, 0x5D),
    ("DA60-DA8D", 0x7BB2, 0xDA60, 0x2E),
    ("DA8E-DAFF", 0x7C4D, 0xDA8E, 0x72),
    ("DB80-DBA2", 0x563A, 0xDB80, 0x23),
    ("DBA4-DBC7", 0x569A, 0xDBA4, 0x24),
    ("DBC8-DBEB", 0x56CA, 0xDBC8, 0x24),
    ("DBEC-DBF0", 0x56FA, 0xDBEC, 0x05),
)
EXTENSION_REGION = ("DBF1-DBFC", 0xDBF1, 0x0C)


def bank_offset(bank: int, address: int) -> int:
    return r305.r304.bank_offset(bank, address)


def bank_bytes(payload: bytes, bank: int, address: int, width: int) -> bytes:
    offset = bank_offset(bank, address)
    return payload[offset:offset + width]


def patch_regions() -> tuple[tuple[int, bytes, bytes, str], ...]:
    return (
        (
            bank_offset(MIRROR_BANK, ATOMIC_SOURCE_ADDR),
            OLD_MIRROR_ATOMIC_SOURCE,
            CANONICAL_ATOMIC_SOURCE,
            "bank16 DA13 tagged-destination source",
        ),
        (
            bank_offset(MIRROR_BANK, RUNTIME_SOURCE_B_ADDR),
            OLD_MIRROR_RUNTIME_SOURCE_B,
            CANONICAL_RUNTIME_SOURCE_B,
            "bank16 DBDF-DBEB runtime source",
        ),
        (
            bank_offset(MIRROR_BANK, RUNTIME_SOURCE_C_ADDR),
            OLD_MIRROR_RUNTIME_SOURCE_C,
            CANONICAL_RUNTIME_SOURCE_C,
            "bank16 DBEC-DBF0 runtime source",
        ),
        (
            bank_offset(MIRROR_BANK, CONTINUATION_ADDR),
            OLD_MIRROR_CONTINUATION,
            NEW_MIRROR_CONTINUATION,
            "bank16 DBF1 extension continuation/source",
        ),
    )


def owned_ranges() -> set[int]:
    result: set[int] = set()
    for offset, old, new, _ in patch_regions():
        r305.r304.require(len(old) == len(new), "r307 patch width changed")
        result.update(range(offset, offset + len(old)))
    return result


def absolute_transfers_to(
    payload: bytes, bank: int, start: int, end: int,
) -> list[tuple[int, int, int]]:
    image = payload[bank * r305.r304.BANK_SIZE:(bank + 1) * r305.r304.BANK_SIZE]
    result = []
    for index in range(len(image) - 2):
        opcode = image[index]
        if opcode not in ABSOLUTE_BRANCH_OPCODES:
            continue
        target = image[index + 1] | (image[index + 2] << 8)
        if start <= target < end:
            result.append((index + 0x4000, opcode, target))
    return result


def validate_structural_preimages(source: bytes) -> dict[str, Any]:
    r305.r304.require(len(source) == r305.r304.ROM_SIZE,
                      "r307 requires a 512 KiB ROM")
    for bank in (CANONICAL_BANK, MIRROR_BANK):
        r305.r304.require(
            bank_bytes(source, bank, INSTALLER_ADDR, len(INSTALLER))
            == INSTALLER,
            f"bank{bank} main installer changed",
        )
        r305.r304.require(
            bank_bytes(source, bank, INSTALLER_TAIL_ADDR, len(INSTALLER_TAIL))
            == INSTALLER_TAIL,
            f"bank{bank} semantic installer tail changed",
        )
        for callsite in INSTALLER_CALL_SITES:
            r305.r304.require(
                bank_bytes(source, bank, callsite, 3) == INSTALLER_CALL,
                f"bank{bank}:${callsite:04X} installer call changed",
            )
        calls = absolute_transfers_to(
            source, bank, INSTALLER_ADDR, INSTALLER_ADDR + 1
        )
        r305.r304.require(
            calls == [(address, 0xC4, INSTALLER_ADDR)
                      for address in INSTALLER_CALL_SITES],
            f"bank{bank} installer entry set changed: {calls}",
        )

    for offset, old, _, label in patch_regions():
        r305.r304.require(source[offset:offset + len(old)] == old,
                          f"{label} preimage changed")

    r305.r304.require(
        bank_bytes(
            source, CANONICAL_BANK, ATOMIC_SOURCE_ADDR,
            len(CANONICAL_ATOMIC_SOURCE),
        ) == CANONICAL_ATOMIC_SOURCE,
        "bank13 canonical DA13 source changed",
    )
    r305.r304.require(
        bank_bytes(
            source, CANONICAL_BANK, RUNTIME_SOURCE_B_ADDR,
            len(CANONICAL_RUNTIME_SOURCE_B),
        ) == CANONICAL_RUNTIME_SOURCE_B,
        "bank13 canonical DBDF-DBEB source changed",
    )
    r305.r304.require(
        bank_bytes(
            source, CANONICAL_BANK, RUNTIME_SOURCE_C_ADDR,
            len(CANONICAL_RUNTIME_SOURCE_C),
        ) == CANONICAL_RUNTIME_SOURCE_C,
        "bank13 canonical DBEC-DBF0 source changed",
    )
    r305.r304.require(
        bank_bytes(
            source, CANONICAL_BANK, CANONICAL_EXTENSION_SOURCE_ADDR,
            len(CANONICAL_EXTENSION),
        ) == CANONICAL_EXTENSION,
        "bank13 canonical DBF1-DBFC extension changed",
    )
    for bank in (CANONICAL_BANK, MIRROR_BANK):
        r305.r304.require(
            bank_bytes(
                source, bank, R305_FIXED_PREDICATE_GATEWAY_ADDR,
                len(R305_FIXED_PREDICATE_GATEWAY),
            ) == R305_FIXED_PREDICATE_GATEWAY,
            f"bank{bank} r305 fixed predicate gateway changed",
        )

    continuation_entries = absolute_transfers_to(
        source, MIRROR_BANK, CONTINUATION_ADDR, CONTINUATION_END
    )
    r305.r304.require(
        continuation_entries == [(0x577A, 0xC3, CONTINUATION_ADDR)],
        f"bank16 continuation entry set changed: {continuation_entries}",
    )
    return {
        "installer_call_sites": {
            f"bank{bank}": [f"${address:04X}" for address in INSTALLER_CALL_SITES]
            for bank in (CANONICAL_BANK, MIRROR_BANK)
        },
        "bank16_continuation_entries": ["JP $577A->$5546"],
        "bank16_continuation_preimage": (
            "12-byte finalizer plus 24 zero bytes at $5546-$5569"
        ),
        "r305_predicate_pointer": (
            "bank13/16:$7C96 both use CALL NZ fixed:$0013; the historical "
            "bank-relative exception is eliminated, not preserved"
        ),
    }


def simulate_installer(payload: bytes, bank: int) -> dict[str, bytes]:
    installed: dict[str, bytes] = {}
    for label, source, _, width in COPY_REGIONS:
        installed[label] = bank_bytes(payload, bank, source, width)
    extension_source = (
        CANONICAL_EXTENSION_SOURCE_ADDR
        if bank == CANONICAL_BANK else EXTENSION_SOURCE_ADDR
    )
    installed[EXTENSION_REGION[0]] = bank_bytes(
        payload, bank, extension_source, EXTENSION_REGION[2]
    )
    return installed


def installer_contract(candidate: bytes) -> dict[str, Any]:
    canonical = simulate_installer(candidate, CANONICAL_BANK)
    mirror = simulate_installer(candidate, MIRROR_BANK)
    r305.r304.require(canonical.keys() == mirror.keys(),
                      "installer inventories differ")
    mismatches = {
        label: (canonical[label], mirror[label])
        for label in canonical
        if canonical[label] != mirror[label]
    }
    r305.r304.require(not mismatches,
                      f"bank16 installer output diverges: {list(mismatches)}")

    # The r305 relocated predicate is now fixed-bridge-relative in both
    # mirrors.  No DA8E-DAFF pointer exception may survive this overlay.
    r305.r304.require(
        canonical["DA8E-DAFF"] == mirror["DA8E-DAFF"],
        "DA8E predicate-pointer exception was reintroduced",
    )
    r305.r304.require(
        R305_FIXED_PREDICATE_GATEWAY in canonical["DA8E-DAFF"],
        "canonical DA8E runtime lacks r305's fixed predicate bridge",
    )

    final_offset = NEW_MIRROR_CONTINUATION.index(FINAL_INSTALLER)
    extension_copy_end = len(MIRROR_EXTENSION_PREFIX)
    sentinel_offset = NEW_MIRROR_CONTINUATION.index(bytes.fromhex("EA 51 DF"))
    r305.r304.require(
        extension_copy_end <= final_offset < sentinel_offset,
        "DF51 sentinel can publish before DBF1 extension copy",
    )
    inventory = []
    for label, source, destination, width in COPY_REGIONS:
        inventory.append({
            "range": label,
            "bank_relative_source": f"${source:04X}",
            "destination": f"${destination:04X}",
            "length": width,
            "sha256": r305.r304.digest(canonical[label]),
        })
    inventory.append({
        "range": EXTENSION_REGION[0],
        "bank13_source": f"${CANONICAL_EXTENSION_SOURCE_ADDR:04X}",
        "bank16_source": f"${EXTENSION_SOURCE_ADDR:04X}",
        "destination": f"${EXTENSION_REGION[1]:04X}",
        "length": EXTENSION_REGION[2],
        "sha256": r305.r304.digest(canonical[EXTENSION_REGION[0]]),
    })
    return {
        "canonical_bank": CANONICAL_BANK,
        "mirror_bank": MIRROR_BANK,
        "copy_region_inventory": inventory,
        "canonical_ranges_equal": list(canonical),
        "mismatched_ranges": [],
        "sentinel": (
            f"DF51={SENTINEL_VALUE:02X} only after DBF1-DBFC copy and all "
            "canonical installer ranges"
        ),
        "unowned_gaps": ["DA5D-DA5F", "DBA3"],
        "predicate_pointer_exceptions": [],
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    r305.r304.require(len(candidate) == len(source), "candidate size changed")
    changed = r305.r304.delta(source, candidate)
    functional = r305.r304.delta(source, candidate, functional=True)
    allowed = owned_ranges() | r305.r304.CHECKSUM_OFFSETS
    r305.r304.require(changed <= allowed,
                      f"r307 escaped ownership: {sorted(changed - allowed)[:8]}")
    expected = {
        offset
        for offset in owned_ranges()
        if source[offset] != candidate[offset]
    }
    r305.r304.require(functional == expected,
                      "r307 functional delta differs from exact patch")
    # The overlay owns bank16 sources only.  The complete bank13 image and all
    # other functional bytes remain exactly r305.
    bank13 = slice(
        CANONICAL_BANK * r305.r304.BANK_SIZE,
        (CANONICAL_BANK + 1) * r305.r304.BANK_SIZE,
    )
    r305.r304.require(candidate[bank13] == source[bank13],
                      "r307 changed canonical bank13")

    continuation_entries = absolute_transfers_to(
        candidate, MIRROR_BANK, CONTINUATION_ADDR, CONTINUATION_END
    )
    r305.r304.require(
        continuation_entries == [(0x577A, 0xC3, CONTINUATION_ADDR)],
        f"r307 added an unexpected continuation entry: {continuation_entries}",
    )
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{offset:06X}" for offset in sorted(functional)],
        "owned_ranges": [
            "bank16:$7B13-$7B20",
            "bank16:$56E1-$56ED",
            "bank16:$56FA-$56FE",
            "bank16:$5546-$5569",
        ],
        "escaped_bytes": 0,
        "bank13_changed_bytes": 0,
        "bank16_continuation_entry_count": len(continuation_entries),
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    """Construct the fixed mirror repair without historical build receipts."""
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    preimages = validate_structural_preimages(source)

    rom = bytearray(source)
    for offset, old, new, label in patch_regions():
        r305.r304.require(rom[offset:offset + len(old)] == old,
                          f"{label} changed before patch")
        rom[offset:offset + len(new)] = new
    r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    installer = installer_contract(candidate)
    candidate_sha256 = r305.r304.digest(candidate)
    if EXPECTED_CANDIDATE_SHA256 != "TO_BE_PINNED":
        r305.r304.require(
            candidate_sha256 == EXPECTED_CANDIDATE_SHA256,
            f"r307 candidate identity drift: {candidate_sha256}",
        )

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-bank16-installer-mirror-r307-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r305",
            "candidate_sha256": BASE_SHA256,
        },
        "candidate_sha256": candidate_sha256,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "root_cause": (
            "bank-relative $7CBF installer could run under bank16 and mark "
            "DF51=A8 after emitting stale DA13 and zero/missing DBDF-DBFC"
        ),
        "preimage_contract": preimages,
        "installer_contract": installer,
        "ownership": ownership,
        "composition": {
            "r305": "byte-exact outside reviewed bank16 source/continuation ranges",
            "wall_repair": "not included; compose only after causal live test",
            "room_semantic_trampolines": "byte-exact r305",
        },
        "required_live_gates": [
            "fresh/cold bank16 installer invocation retains exact odd FFA5 tags",
            "resident DA00-DAFF and DB80-DBFC match canonical bank13 image",
            "scene0B wall/edge oracle and menu roundtrip remain clean",
            "release speed matrix",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    r305.r304.require(r305.r304.digest(source) == BASE_SHA256,
                      "wrong exact r305 base")
    r305.r304.require(
        r305.r304.digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
        "r305 build receipt identity changed",
    )
    base_receipt = json.loads(base_receipt_bytes)
    r305.r304.require(base_receipt.get("schema") == BASE_SCHEMA,
                      "r305 build receipt schema changed")
    r305.r304.require(base_receipt.get("candidate_sha256") == BASE_SHA256,
                      "r305 receipt names another candidate")
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-bank16-installer-mirror-r307-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "decision": "STATIC_DIAGNOSTIC_ONLY_LIVE_GATES_REQUIRED",
    })
    receipt["base"]["build_receipt_sha256"] = BASE_RECEIPT_SHA256
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
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
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
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
