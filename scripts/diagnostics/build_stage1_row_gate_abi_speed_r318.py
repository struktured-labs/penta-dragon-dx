#!/usr/bin/env python3
"""Build r318: restore the bank-19 row-helper scene ABI and hot path.

r303 replaced the row helper's native ``LD A,($D880); LD B,A`` sequence
with an FFB7 predicate.  That preserved the local predicate timing but left
``B`` holding the value restored by ``POP BC``.  The unchanged helper at
``$6B70`` later executes ``BIT 3,B``; in the measured Stage-1 route the stale
value is $08, so almost every publication takes the expensive scanner.

This exact-width overlay restores ``B=$D880`` before classifying the
Stage-1 owner with FFB7.  The accepted FFB7=$02 predicate remains 48 T-cycles
after ``POP BC``, exactly matching r300/r303.  The fail-closed rejected path
lands on the existing ``$6BEA: JP $6C50`` and costs 68 T-cycles, 16 more than
r300; live promotion must therefore prove that every bank-19 ``$6BA7`` entry
is Stage-1-owned.  No emulator is invoked here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import build_stage1_selector_latch_cold_init_r317 as r317


ROOT = r317.ROOT
TMP = r317.TMP
BASE = r317.DEFAULT_OUTPUT
BASE_RECEIPT = r317.DEFAULT_RECEIPT
DEFAULT_OUTPUT = TMP / "stage1-row-gate-abi-speed-r318/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-row-gate-abi-speed-r318/build-receipt.json"

BASE_SHA256 = r317.EXPECTED_CANDIDATE_SHA256
BASE_RECEIPT_SHA256 = (
    "e72a095a207fdc1bb86e30b7361ea046484c8acfbb75064faedaca039646706c"
)
BASE_SCHEMA = "penta-stage1-selector-latch-cold-init-r317-build-v1"
EXPECTED_CANDIDATE_SHA256 = (
    "909d7ee16bbf5080fd9992567bbe784e6df3234a08f9bde07ff7a10b2f729abb"
)

ROW_BANK = 19
ROW_ADDR = 0x6BA7
ROW_END = 0x6BBE
ROW_OFFSET = r317.r316.bank_offset(ROW_BANK, ROW_ADDR)
OLD_ROW_PREFIX = bytes.fromhex(
    "C1 F0 B7 FE 02 18 00 00 C2 50 6C "
    "FA FD DC B7 CA 50 6C F0 BF B7 20 0C"
)
NEW_ROW_PREFIX = bytes.fromhex(
    "C1 FA 80 D8 47 F0 B7 FE 02 20 38 "
    "FA FD DC B7 CA 50 6C 78 FE 0A 28 0C"
)
ROW_CHANGED_RELATIVE_OFFSETS = frozenset(
    index
    for index, (before, after) in enumerate(
        zip(OLD_ROW_PREFIX, NEW_ROW_PREFIX, strict=True)
    )
    if before != after
)

# This is the complete unchanged fall-through body from the new prefix to
# the rejected-owner landing.  It includes the only CALL of the downstream
# selector whose ABI requires B=$D880.
POST_PREFIX_ADDR = ROW_END
POST_PREFIX = bytes.fromhex(
    "F0 BD FE 12 28 06 3D FE 0C D2 50 6C "
    "FA 5B DF E6 03 FE 03 C2 50 6C "
    "7C B7 20 08 FA 0B DC 87 87 EE 98 67 "
    "2E 00 E5 F3 AF E0 4F CD 70 6B"
)
REJECT_LANDING_ADDR = 0x6BEA
REJECT_LANDING = bytes.fromhex("C3 50 6C")
DOWNSTREAM_SELECTOR_ADDR = 0x6B70
DOWNSTREAM_SELECTOR = bytes.fromhex("CB 58 28 06 C3 B7 61")
ROOM_FAST_GATE_ADDR = 0x6B7A
ROOM_FAST_GATE = bytes.fromhex("F0 BD FE 03 C2 B7 61 C1 D1 C5 C9")


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    r317.r305.r304.require(condition, message)


def jr_target(address: int, operand: int) -> int:
    displacement = operand if operand < 0x80 else operand - 0x100
    return (address + 2 + displacement) & 0xFFFF


def row_prefix_route(scene: int, ffb7: int, dcfd: int) -> dict[str, Any]:
    """Model the exact observable ABI and exits of the r318 prefix."""
    for name, value in (("scene", scene), ("ffb7", ffb7), ("dcfd", dcfd)):
        require(0 <= value <= 0xFF, f"{name} is not a byte")
    if ffb7 != 0x02:
        target = REJECT_LANDING_ADDR
        route = "non-stage1-reject"
    elif dcfd == 0:
        target = 0x6C50
        route = "inactive-reject"
    elif scene == 0x0A:
        target = 0x6BCA
        route = "miniboss-front-skip"
    else:
        target = ROW_END
        route = "ordinary-fallthrough"
    return {
        "route": route,
        "target": target,
        "b_after": scene,
        "stage1_owner": ffb7 == 0x02,
    }


def exhaustive_contract() -> dict[str, Any]:
    counts = {
        "non-stage1-reject": 0,
        "inactive-reject": 0,
        "miniboss-front-skip": 0,
        "ordinary-fallthrough": 0,
    }
    cases = 0
    for scene in range(0x100):
        for ffb7 in range(0x100):
            for dcfd in (0x00, 0x01, 0xFF):
                result = row_prefix_route(scene, ffb7, dcfd)
                require(result["b_after"] == scene,
                        "row prefix failed to restore B from D880")
                counts[result["route"]] += 1
                if result["route"] == "miniboss-front-skip":
                    require(
                        ffb7 == 0x02 and dcfd != 0 and scene == 0x0A,
                        "front skip admitted a non-miniboss input",
                    )
                cases += 1
    require(all(counts.values()), "row route partition lost a branch")
    require(
        row_prefix_route(0x0B, 0x02, 0x01)["target"] == ROW_END,
        "low-health scene $0B incorrectly aliases the miniboss front skip",
    )
    require(
        row_prefix_route(0x02, 0x02, 0x01)["target"] == ROW_END,
        "ordinary Stage-1 scene $02 lost the native fall-through",
    )
    return {
        "input_tuples": cases,
        "route_counts": counts,
        "b_postcondition": "B equals the complete D880 scene byte",
        "front_skip_iff": "FFB7=02 and DCFD!=00 and D880=0A",
        "scene0B": "ordinary fall-through; downstream BIT 3,B remains live",
    }


def timing_contract() -> dict[str, Any]:
    contract = {
        "scope": "predicate after POP BC, including its transfer decision",
        "stage1_owner_ffb7_02": {
            "r300_t": 48,
            "r303_t": 48,
            "r318_t": 48,
            "delta_from_r300_t": 0,
        },
        "rejected_ffb7_not_02": {
            "r300_t": 52,
            "r318_t": 68,
            "delta_from_r300_t": 16,
            "reason": "taken JR NZ then existing $6BEA JP $6C50",
        },
        "live_precondition": (
            "every bank19:$6BA7 entry is downstream of the Stage-1 mapper "
            "and observes FFB7=02"
        ),
    }
    require(
        contract["stage1_owner_ffb7_02"]["delta_from_r300_t"] == 0,
        "Stage-1 accepted row predicate is no longer cycle exact",
    )
    require(
        contract["rejected_ffb7_not_02"]["delta_from_r300_t"] == 16,
        "rejected row predicate timing claim drifted",
    )
    return contract


def exact_at(payload: bytes, address: int, expected: bytes) -> bool:
    offset = r317.r316.bank_offset(ROW_BANK, address)
    return payload[offset:offset + len(expected)] == expected


def source_preimages(source: bytes) -> dict[str, Any]:
    require(len(source) == r317.r305.r304.ROM_SIZE,
            "r318 base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256,
            f"r318 base identity mismatch: {digest(source)}")
    require(source[ROW_OFFSET:ROW_OFFSET + len(OLD_ROW_PREFIX)]
            == OLD_ROW_PREFIX, "r318 row prefix preimage drift")
    require(exact_at(source, POST_PREFIX_ADDR, POST_PREFIX),
            "r318 row fall-through body drift")
    require(exact_at(source, REJECT_LANDING_ADDR, REJECT_LANDING),
            "r318 rejected-owner landing drift")
    require(exact_at(source, DOWNSTREAM_SELECTOR_ADDR, DOWNSTREAM_SELECTOR),
            "r318 downstream BIT 3,B selector drift")
    require(exact_at(source, ROOM_FAST_GATE_ADDR, ROOM_FAST_GATE),
            "r318 downstream room-$03 fast gate drift")
    return {
        "candidate_sha256": BASE_SHA256,
        "row_prefix": "bank19:$6BA7-$6BBD exact",
        "fallthrough": "bank19:$6BBE-$6BE9 exact",
        "reject_landing": "bank19:$6BEA JP $6C50 exact",
        "downstream_selector": "bank19:$6B70 BIT 3,B exact",
        "room_fast_gate": "bank19:$6B7A-$6B84 exact",
    }


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    require(len(candidate) == len(source), "r318 changed ROM size")
    require(candidate[ROW_OFFSET:ROW_OFFSET + len(NEW_ROW_PREFIX)]
            == NEW_ROW_PREFIX, "r318 row prefix replacement drift")
    require(exact_at(candidate, POST_PREFIX_ADDR, POST_PREFIX),
            "r318 changed the row fall-through body")
    require(exact_at(candidate, REJECT_LANDING_ADDR, REJECT_LANDING),
            "r318 changed the rejected-owner landing")
    require(exact_at(candidate, DOWNSTREAM_SELECTOR_ADDR,
                     DOWNSTREAM_SELECTOR),
            "r318 changed the downstream BIT 3,B selector")
    require(exact_at(candidate, ROOM_FAST_GATE_ADDR, ROOM_FAST_GATE),
            "r318 changed the downstream room-$03 fast gate")

    functional = {
        offset
        for offset, (before, after) in enumerate(
            zip(source, candidate, strict=True)
        )
        if before != after and offset not in r317.r316.CHECKSUM_OFFSETS
    }
    expected = {
        ROW_OFFSET + relative for relative in ROW_CHANGED_RELATIVE_OFFSETS
    }
    require(functional == expected,
            "r318 changed bytes outside the audited row prefix")

    require(candidate[r317.r316.CGB_FLAG_OFFSET]
            == r317.r316.CGB_ONLY_FLAG,
            "r318 lost the accepted CGB-only header")
    require(
        candidate[
            r317.DISPATCH_OFFSET:
            r317.DISPATCH_OFFSET + len(r317.DISPATCH_REPLACEMENT)
        ] == r317.DISPATCH_REPLACEMENT,
        "r318 lost the r317 cold semantic-token definition",
    )
    for site in r317.r316.OPERAND_SITES:
        offset = r317.r316.site_offset(site)
        require(
            candidate[offset:offset + 2]
            == bytes((site.opcode, site.new_operand)),
            f"r318 lost selector-latch relocation at {site.label}",
        )

    checksummed = bytearray(candidate)
    r317.r305.r304.update_checksums(checksummed)
    require(bytes(checksummed) == candidate,
            "r318 header/global checksums are not canonical")
    return {
        "functional_changed_bytes_from_r317": len(functional),
        "changed_file_offsets_from_r317": [
            f"0x{offset:06X}" for offset in sorted(functional)
        ],
        "row_region": "bank19:$6BA7-$6BBD",
        "escaped_bytes": 0,
        "rom_size_delta_bytes": 0,
        "r317_selector_relocations_retained": len(r317.r316.OPERAND_SITES),
        "cgb_only_header_retained": True,
    }


def construct(source: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = source_preimages(source)
    routes = exhaustive_contract()
    timing = timing_contract()

    rom = bytearray(source)
    rom[ROW_OFFSET:ROW_OFFSET + len(OLD_ROW_PREFIX)] = NEW_ROW_PREFIX
    r317.r305.r304.update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    sha = digest(candidate)
    require(sha == EXPECTED_CANDIDATE_SHA256,
            f"r318 candidate identity drift: {sha}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-row-gate-abi-speed-r318-construction-v1",
        "status": "construction-only",
        "historical_evidence_consumed": False,
        "fresh_live_qualification": False,
        "promotable": False,
        "emulator_invoked": False,
        "candidate_sha256": sha,
        "base": preimages,
        "root_cause": (
            "r303 removed LD B,A at bank19:$6BAB while replacing the local "
            "scene predicate; downstream $6B70 BIT 3,B then consumed popped "
            "B instead of the current scene byte, selecting the wrong scanner path"
        ),
        "patch": {
            "region": "bank19:$6BA7-$6BBD (23 bytes, exact width)",
            "abi_repair": "LD A,($D880); LD B,A restored before FFB7 gate",
            "stage_owner_gate": "LDH A,($FFB7); CP $02",
            "miniboss_gate": "LD A,B; CP $0A; JR Z,$6BCA",
            "low_health_scene0B": (
                "does not alias scene0A; falls through with B=$0B"
            ),
        },
        "offline_contract": {
            "routes": routes,
            "timing": timing,
            "branch_targets": {
                "non_stage1": "$6BB0 JR NZ,+$38 -> $6BEA",
                "miniboss": "$6BBC JR Z,+$0C -> $6BCA",
            },
        },
        "ownership": ownership,
        "required_live_gates": [
            "full 2800-frame Stage-1 release speed gate is at least 95%",
            "every observed bank19:$6BA7 entry has FFB7=02",
            "captured scene0B menu round-trip has zero reported visual signatures",
            "natural Stage-1 menu round-trip has zero bad frames or art mismatches",
            "cold CHR writer audit has canonical selectors/pages and zero bad writes",
            "natural death/Continue executes $4AFB->$0C9C and reloads all eight canonical pages",
            "Analogue Pocket visual round-trip before promotion",
        ],
        "decision": "CONSTRUCTION_ONLY_LIVE_GATES_REQUIRED",
    }
    return candidate, receipt


def validate_preimages(source: bytes, base_receipt_bytes: bytes) -> dict[str, Any]:
    contract = source_preimages(source)
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r318 base receipt identity mismatch")
    receipt = json.loads(base_receipt_bytes)
    require(receipt.get("schema") == BASE_SCHEMA,
            "r318 base receipt schema mismatch")
    require(receipt.get("candidate_sha256") == BASE_SHA256,
            "r318 base receipt/candidate mismatch")
    require(receipt.get("emulator_invoked") is False,
            "r318 base build receipt unexpectedly invoked an emulator")
    return {**contract, "build_receipt_sha256": BASE_RECEIPT_SHA256, "schema": BASE_SCHEMA}


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    preimages = validate_preimages(source, base_receipt_bytes)
    candidate, receipt = construct(source)
    receipt.update({
        "schema": "penta-stage1-row-gate-abi-speed-r318-build-v1",
        "status": "STATIC_PASS_R318_RELEASE_GATES_REQUIRED",
        "base": preimages,
        "decision": "STATIC_ABI_REPAIR_COMPLETE_LIVE_GATES_REQUIRED",
    })
    receipt["root_cause"] = (
        "r303 removed LD B,A at bank19:$6BAB while replacing the local "
        "scene predicate; downstream $6B70 BIT 3,B then consumed popped "
        "B=$08 and selected the expensive scanner on the Stage-1 hot path"
    )
    del receipt["historical_evidence_consumed"], receipt["fresh_live_qualification"]
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = r317.r305.r304.checked_output(args.output, "candidate output")
    receipt_path = r317.r305.r304.checked_output(
        args.receipt, "receipt output"
    )
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(r317.r305.r304.receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
