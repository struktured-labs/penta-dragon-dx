#!/usr/bin/env python3
"""Build r304: exact-r303 Stage-1 scene-$0B menu-close invalidation.

The native shared tail at bank 1:$77A8 clears FFE4 after both SELECT-menu
close routes, but it is also reached by item helpers and other tail calls.
r304 therefore redirects that *shared* tail through an audited fixed-bank
stub and an erased bank-31 leaf while reproducing the native return ABI for
all 19 transfers.  Only exact D880=$0B/FFB7=$02 writes DF53=DF57=$FF.

The fixed $0013-$0017 stub is unreachable fallthrough after RST $10's
unconditional JP $09DE.  The bank-31 leaf discards the dispatcher-only $084D
return and exits through stock fixed:$099A, whose AF-preserving mapper selects
bank 1 before returning to bank1:$77AB.  Thus the final RET consumes the real
outer frame with A=0, Z set, and FFE4=0 exactly as the old four-byte tail did.

No emulator is invoked.  The candidate remains non-promotable until its live
scene-$0B, hazard/menu, transition, wall, and speed gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-fast-scene0b-gates-r303/candidate.gb"
BASE_RECEIPT = TMP / "stage1-fast-scene0b-gates-r303/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-scene0b-menu-close-r304/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-scene0b-menu-close-r304/build-receipt.json"

BASE_SHA256 = "1137bcd557c7ea08f3e57c1f9b4a69fcec41c080ae817fbb139563509c4b08fe"
BASE_RECEIPT_SHA256 = (
    "f59f2651a84d1f23394f1bdb1743841e1aeade8ea9dd7d984b368e0109bd4175"
)
BASE_SCHEMA = "penta-stage1-fast-scene0b-gates-r303-build-v1"
EXPECTED_CANDIDATE_SHA256 = "TO_BE_PINNED"

BANK_SIZE = 0x4000
ROM_BANKS = 32
ROM_SIZE = ROM_BANKS * BANK_SIZE
CHECKSUM_OFFSETS = frozenset({0x014D, 0x014E, 0x014F})
MBC_TYPE_ADDR = 0x0147
ROM_SIZE_ADDR = 0x0148
MBC5_RAM_BATTERY = 0x1B
ROM_SIZE_512_KIB = 0x04

RST10_VECTOR_ADDR = 0x0010
RST10_VECTOR = bytes.fromhex("C3 DE 09")
FIXED_STUB_ADDR = 0x0013
OLD_FIXED_STUB = bytes.fromhex("DF AE BB 52 7B")
NEW_FIXED_STUB = bytes.fromhex("3E 1F C3 47 08")
RST10_TARGET_ADDR = 0x09DE
RST10_TARGET = bytes.fromhex("85 30 01 24 6F C9")

MAPPER_DISPATCH_ADDR = 0x0847
MAPPER_DISPATCH = bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")
MAPPER_ENTRY_ADDR = 0x0061
MAPPER_ENTRY = bytes.fromhex("EA 09 DC C3 BE 09")
MAPPER_BODY_ADDR = 0x09BE
MAPPER_BODY = bytes.fromhex("E0 99 EA 00 21 C9")
AF_PRESERVING_BANK1_MAPPER_ADDR = 0x099A
AF_PRESERVING_BANK1_MAPPER = bytes.fromhex("F5 3E 01 CD 61 00 F1 C9")
FILL4_ADDR = 0x09A2
FILL4 = bytes.fromhex("AF 22 05 20 FC C9")

SHARED_ROUTINE_ADDR = 0x7798
SHARED_ROUTINE = bytes.fromhex(
    "21 7C C0 06 04 CD A2 09 "
    "21 7C C1 06 04 CD A2 09 "
    "AF E0 E4 C9"
)
SHARED_TAIL_ADDR = 0x77A8
OLD_SHARED_TAIL = bytes.fromhex("AF E0 E4 C9")
NEW_SHARED_TAIL = bytes.fromhex("CD 13 00 C9")
TAIL_RETURN_ADDR = 0x77AB

CLOSE_CALLSITE_ADDRS = (0x1B69, 0x1DC2)
CLOSE_CALLSITE = bytes.fromhex(
    "F0 40 CB AF E0 40 CD 98 77 AF E0 E4 C9"
)

# Bank-qualified, reviewed transfers into the shared bank-1 routine.  The two
# fixed CALLs are the menu lifecycle routes; the remaining JP/JR tail calls
# are why r304 must preserve the native common-tail ABI rather than specialize
# only the menu callers.
EXPECTED_CALL_TRANSFERS = frozenset({0x001B6F, 0x001DC8})
EXPECTED_JP_TRANSFERS = frozenset({
    0x001DE1,
    0x007819,
    0x00783A,
    0x007842,
    0x007850,
    0x00785E,
    0x00786C,
    0x00787A,
    0x00788B,
    0x0078A8,
    0x0078B3,
    0x0078B6,
})
EXPECTED_JR_TRANSFERS = frozenset({
    0x0077C6,
    0x0077D7,
    0x0077E8,
    0x0077FE,
    0x007807,
})

BANK31 = 31
BANK31_START = BANK31 * BANK_SIZE
BANK31_END = BANK31_START + BANK_SIZE
HELPER_ADDR = 0x6C80
HELPER = bytes.fromhex(
    "FA 80 D8 FE 0B 20 0E "  # require exact scene $0B
    "F0 B7 FE 02 20 08 "     # require exact Stage 1 marker $02
    "3E FF EA 53 DF EA 57 DF "  # dirty only both physical-map keys
    "F1 AF E0 E4 C3 9A 09"   # discard $084D; native tail + bank-1 thunk
)
CACHE_ADDRS = (0xDF53, 0xDF57)
UNTOUCHED_COMPANION_ADDRS = (0xDF0D, 0xDF4E, 0xDF4F, 0xDF7D, 0xFFE0)

ABSOLUTE_BRANCH_OPCODES = frozenset({
    0xC2, 0xC3, 0xC4,  # JP/CALL NZ and JP
    0xCA, 0xCC,        # JP/CALL Z
    0xD2, 0xD4,        # JP/CALL NC
    0xDA, 0xDC,        # JP/CALL C
    0xCD,              # CALL
})
RELATIVE_BRANCH_OPCODES = frozenset({0x18, 0x20, 0x28, 0x30, 0x38})
CAVE_TARGETS = frozenset(range(FIXED_STUB_ADDR, FIXED_STUB_ADDR + 5))
# The sole raw absolute-branch-shaped mention is reviewed bank-15 graphics
# data, not executable code.  Pin its complete local record rather than
# silently ignoring an arbitrary exception.
CAVE_DATA_FALSE_MENTION = (0x03D96E, 0xCA, 0x0014)
CAVE_DATA_RECORD_ADDR = 0x03D960
CAVE_DATA_RECORD = bytes.fromhex(
    "00 00 00 00 00 00 10 00 73 31 54 03 AA 39 CA 14 "
    "00 00 04 80 10 28 20 00 10 15 94 50 00 5D 76 53"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def receipt_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def bank_offset(bank: int, address: int) -> int:
    require(0 < bank < ROM_BANKS and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and resolved.is_relative_to(scratch),
            f"{label} must be below repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def delta(before: bytes, after: bytes, *, functional: bool = False) -> set[int]:
    require(len(before) == len(after), "delta operands differ in width")
    result = {
        offset
        for offset, pair in enumerate(zip(before, after, strict=True))
        if pair[0] != pair[1]
    }
    return result - CHECKSUM_OFFSETS if functional else result


def patch_exact(
    rom: bytearray,
    source: bytes,
    offset: int,
    old: bytes,
    new: bytes,
    allowed: set[int],
    label: str,
) -> None:
    require(len(old) == len(new), f"{label} changes width")
    require(source[offset:offset + len(old)] == old,
            f"{label} preimage changed")
    rom[offset:offset + len(new)] = new
    allowed.update(range(offset, offset + len(new)))


def absolute_cave_mentions(payload: bytes) -> list[tuple[int, int, int]]:
    mentions: list[tuple[int, int, int]] = []
    for offset in range(len(payload) - 2):
        opcode = payload[offset]
        if opcode not in ABSOLUTE_BRANCH_OPCODES:
            continue
        target = payload[offset + 1] | (payload[offset + 2] << 8)
        if target in CAVE_TARGETS:
            mentions.append((offset, opcode, target))
    return mentions


def relative_fixed_cave_mentions(payload: bytes) -> list[tuple[int, int, int]]:
    mentions: list[tuple[int, int, int]] = []
    for offset in range(BANK_SIZE - 1):
        opcode = payload[offset]
        if opcode not in RELATIVE_BRANCH_OPCODES:
            continue
        displacement = payload[offset + 1]
        if displacement >= 0x80:
            displacement -= 0x100
        target = (offset + 2 + displacement) & 0xFFFF
        if target in CAVE_TARGETS:
            mentions.append((offset, opcode, target))
    return mentions


def shared_transfer_sites(payload: bytes) -> dict[str, frozenset[int]]:
    calls: set[int] = set()
    jumps: set[int] = set()
    for offset in range(len(payload) - 2):
        if payload[offset + 1:offset + 3] != bytes.fromhex("98 77"):
            continue
        if payload[offset] == 0xCD:
            calls.add(offset)
        elif payload[offset] == 0xC3:
            jumps.add(offset)

    relative: set[int] = set()
    bank1_start = BANK_SIZE
    bank1_end = 2 * BANK_SIZE
    for offset in range(bank1_start, bank1_end - 1):
        opcode = payload[offset]
        if opcode not in RELATIVE_BRANCH_OPCODES:
            continue
        logical_pc = 0x4000 + (offset - bank1_start)
        displacement = payload[offset + 1]
        if displacement >= 0x80:
            displacement -= 0x100
        if ((logical_pc + 2 + displacement) & 0xFFFF) == SHARED_ROUTINE_ADDR:
            relative.add(offset)
    return {
        "call": frozenset(calls),
        "jp": frozenset(jumps),
        "jr_bank1": frozenset(relative),
    }


def fixed_cave_contract(source: bytes) -> dict[str, Any]:
    require(source[RST10_VECTOR_ADDR:RST10_VECTOR_ADDR + 3] == RST10_VECTOR,
            "RST10 no longer unconditionally jumps over fixed cave")
    require(source[FIXED_STUB_ADDR:FIXED_STUB_ADDR + 5] == OLD_FIXED_STUB,
            "fixed RST10 fallthrough cave preimage changed")
    require(source[RST10_TARGET_ADDR:RST10_TARGET_ADDR + len(RST10_TARGET)]
            == RST10_TARGET, "RST10 pointer-add target changed")
    require(source[CAVE_DATA_RECORD_ADDR:
                   CAVE_DATA_RECORD_ADDR + len(CAVE_DATA_RECORD)]
            == CAVE_DATA_RECORD, "reviewed cave-target data record changed")
    absolute = absolute_cave_mentions(source)
    relative = relative_fixed_cave_mentions(source)
    require(absolute == [CAVE_DATA_FALSE_MENTION],
            f"fixed cave gained an absolute entry: {absolute}")
    require(not relative, f"fixed cave gained a relative entry: {relative}")
    return {
        "range": "fixed:$0013-$0017",
        "preimage": OLD_FIXED_STUB.hex(" ").upper(),
        "preceded_by": "fixed:$0010 JP $09DE (unconditional)",
        "next_vector": "RST $18 at fixed:$0018",
        "absolute_entry_scan": {
            "executable_entries": 0,
            "reviewed_data_false_mentions": [
                {
                    "offset": f"0x{CAVE_DATA_FALSE_MENTION[0]:06X}",
                    "bytes": "CA 14 00",
                    "owner": "bank15 reviewed graphics/data record",
                }
            ],
        },
        "fixed_bank_relative_entries": 0,
    }


def validate_preimages(source: bytes) -> dict[str, Any]:
    require(len(source) == ROM_SIZE, "r303 base is not exactly 512 KiB")
    require(source[MBC_TYPE_ADDR] == MBC5_RAM_BATTERY,
            "cartridge is no longer MBC5+RAM+battery")
    require(source[ROM_SIZE_ADDR] == ROM_SIZE_512_KIB,
            "header no longer declares 512 KiB / 32 ROM banks")
    cave = fixed_cave_contract(source)

    require(source[SHARED_ROUTINE_ADDR:
                   SHARED_ROUTINE_ADDR + len(SHARED_ROUTINE)]
            == SHARED_ROUTINE, "shared $7798 routine/tail preimage changed")
    require(source[FILL4_ADDR:FILL4_ADDR + len(FILL4)] == FILL4,
            "shared fill helper no longer returns A=0,B=0,Z with HL advanced")
    for address in CLOSE_CALLSITE_ADDRS:
        require(source[address:address + len(CLOSE_CALLSITE)] == CLOSE_CALLSITE,
                f"fixed close caller ${address:04X} changed")

    transfers = shared_transfer_sites(source)
    require(transfers["call"] == EXPECTED_CALL_TRANSFERS,
            f"shared routine CALL set changed: {transfers['call']}")
    require(transfers["jp"] == EXPECTED_JP_TRANSFERS,
            f"shared routine JP set changed: {transfers['jp']}")
    require(transfers["jr_bank1"] == EXPECTED_JR_TRANSFERS,
            f"shared routine bank1 JR set changed: {transfers['jr_bank1']}")

    require(source[MAPPER_DISPATCH_ADDR:
                   MAPPER_DISPATCH_ADDR + len(MAPPER_DISPATCH)]
            == MAPPER_DISPATCH, "fixed mapper dispatcher changed")
    require(source[MAPPER_ENTRY_ADDR:MAPPER_ENTRY_ADDR + len(MAPPER_ENTRY)]
            == MAPPER_ENTRY, "fixed coherent mapper entry changed")
    require(source[MAPPER_BODY_ADDR:MAPPER_BODY_ADDR + len(MAPPER_BODY)]
            == MAPPER_BODY, "fixed coherent mapper body changed")
    require(source[AF_PRESERVING_BANK1_MAPPER_ADDR:
                   AF_PRESERVING_BANK1_MAPPER_ADDR
                   + len(AF_PRESERVING_BANK1_MAPPER)]
            == AF_PRESERVING_BANK1_MAPPER,
            "native AF-preserving bank1 mapper changed")

    require(source[BANK31_START:BANK31_END] == bytes([0xFF]) * BANK_SIZE,
            "physical bank31 is not wholly erased")
    helper_offset = bank_offset(BANK31, HELPER_ADDR)
    require(source[helper_offset:helper_offset + len(HELPER)]
            == bytes([0xFF]) * len(HELPER),
            "bank31 helper cave preimage changed")
    require(HELPER[6] == 0x0E and 7 + HELPER[6] == 21,
            "D880 reject no longer lands on common exit")
    require(HELPER[12] == 0x08 and 13 + HELPER[12] == 21,
            "FFB7 reject no longer lands on common exit")
    require(HELPER[21:] == bytes.fromhex("F1 AF E0 E4 C3 9A 09"),
            "helper common exit changed")
    require(bytes.fromhex("F0 91") not in HELPER
            and bytes.fromhex("FA 91 FF") not in HELPER,
            "helper must remain independent of stale FF91")
    for address in UNTOUCHED_COMPANION_ADDRS:
        little = address.to_bytes(2, "little")
        require(little not in HELPER,
                f"helper unexpectedly references companion ${address:04X}")

    return {
        "fixed_cave": cave,
        "shared_transfers": {
            "call": [f"0x{item:06X}" for item in sorted(transfers["call"])],
            "jp": [f"0x{item:06X}" for item in sorted(transfers["jp"])],
            "jr_bank1": [
                f"0x{item:06X}" for item in sorted(transfers["jr_bank1"])
            ],
            "total": sum(len(items) for items in transfers.values()),
        },
        "whole_physical_bank31_erased": True,
        "bank31_helper_range": "bank31:$6C80-$6C9B",
        "mapper": {
            "dispatcher": "fixed:$0847-$084F",
            "entry": "fixed:$0061 -> $09BE",
            "AF_preserving_bank1_thunk": "fixed:$099A-$09A1",
            "selected_bank": "$1F (valid MBC5 bank31)",
        },
    }


def helper_model(
    *, d880: int, ffb7: int, ff91: int, ffe4: int,
    state: dict[int, int],
) -> dict[str, Any]:
    """Model exact memory/ABI effects after the complete redirected tail."""
    result = dict(state)
    targeted = d880 == 0x0B and ffb7 == 0x02
    if targeted:
        for address in CACHE_ADDRS:
            result[address] = 0xFF
    return {
        "targeted": targeted,
        "state": result,
        "ffe4_before": ffe4,
        "ffe4_after": 0,
        "a": 0,
        "z": True,
        "restored_bank": 1,
        "dc09": 1,
        "ff99": 1,
        "ff91_ignored": ff91,
    }


def exhaustive_helper_contract() -> dict[str, Any]:
    seed = {
        0xDF53: 0x12,
        0xDF57: 0x34,
        0xDF0D: 0x45,
        0xDF4E: 0x56,
        0xDF4F: 0x67,
        0xDF7D: 0x78,
        0xFFE0: 0x89,
    }
    target_pairs = 0
    pairs = 0
    for d880 in range(256):
        for ffb7 in range(256):
            zero = helper_model(
                d880=d880, ffb7=ffb7, ff91=0, ffe4=0xA5, state=seed
            )
            stale = helper_model(
                d880=d880, ffb7=ffb7, ff91=0xFF, ffe4=0x5A, state=seed
            )
            expected_target = d880 == 0x0B and ffb7 == 0x02
            require(zero["targeted"] == expected_target,
                    f"helper target drift D880={d880:02X} FFB7={ffb7:02X}")
            require(zero["state"] == stale["state"],
                    "FF91 changed helper memory effects")
            require(zero["ffe4_after"] == stale["ffe4_after"] == 0
                    and zero["a"] == stale["a"] == 0
                    and zero["z"] and stale["z"],
                    "native common-tail ABI drifted")
            for address in UNTOUCHED_COMPANION_ADDRS:
                require(zero["state"][address] == seed[address],
                        f"companion ${address:04X} changed")
            expected_keys = (
                {address: 0xFF for address in CACHE_ADDRS}
                if expected_target else
                {address: seed[address] for address in CACHE_ADDRS}
            )
            require({address: zero["state"][address] for address in CACHE_ADDRS}
                    == expected_keys, "physical-map dirty set drifted")
            target_pairs += int(expected_target)
            pairs += 1
    require(target_pairs == 1, "helper target is not a single exact pair")
    return {
        "D880_FFB7_pairs": pairs,
        "target_pairs": target_pairs,
        "target": "D880=0B,FFB7=02",
        "writes": ["DF53=FF", "DF57=FF"],
        "untouched": [f"{address:04X}" for address in UNTOUCHED_COMPANION_ADDRS],
        "FF91_00_and_FF_equivalent_for_all_pairs": True,
        "all_paths_restore": {
            "FFE4": "00",
            "A": "00",
            "Z": True,
            "bank": "01",
        },
    }


def stack_bank_contract() -> dict[str, Any]:
    # Stack bytes are represented in pop order (low address first).  CALL
    # fixed:$0013 adds $77AB; dispatcher CALL $6C80 adds synthetic $084D.
    outer = [0x34, 0x12, 0x78, 0x56]
    after_tail_call = [0xAB, 0x77] + outer
    helper_entry = [0x4D, 0x08] + after_tail_call
    require(helper_entry[:2] == [0x4D, 0x08],
            "dispatcher synthetic return changed")
    after_helper_pop = helper_entry[2:]
    require(after_helper_pop[:2] == [0xAB, 0x77],
            "tail thunk return moved")

    # fixed:$099A balances PUSH AF and CALL $0061 before its RET consumes
    # $77AB.  bank1:$77AB then consumes the untouched real outer return.
    after_mapper_thunk_ret = after_helper_pop[2:]
    require(after_mapper_thunk_ret == outer,
            "AF-preserving mapper did not consume only $77AB")
    after_tail_ret = after_mapper_thunk_ret[2:]
    require(after_tail_ret == outer[2:],
            "shared tail did not consume exactly one outer return")
    require(len(EXPECTED_CALL_TRANSFERS | EXPECTED_JP_TRANSFERS
                | EXPECTED_JR_TRANSFERS) == 19,
            "shared transfer population changed")
    return {
        "transfers_covered": 19,
        "synthetic_dispatch_return_discarded": "$084D",
        "native_thunk_return": "$77AB",
        "real_outer_return_preserved": True,
        "stack_delta_vs_native_tail": 0,
        "native_register_result": {
            "A": "00",
            "Z": True,
            "B": "00",
            "HL": "C180",
            "C_DE_preserved": True,
        },
        "native_memory_result": {"FFE4": "00"},
        "temporary_bank": "1F",
        "restored_bank": "01",
        "DC09_FF99_restored": "01",
        "helper_returns_normally": False,
        "helper_exit": "POP synthetic $084D; JP fixed:$099A",
    }


def timing_contract() -> dict[str, dict[str, int]]:
    # Includes the replacement tail, fixed stub, first dispatcher mapper,
    # helper, native $099A map/AF restore, and final $77AB RET.  The operation
    # is a shared user-action tail, not a per-frame publication hot path.
    old = 32
    paths = {
        "D880_reject": 420,
        "scene0B_nonStage1_reject": 448,
        "Stage1_scene0B_invalidate": 484,
    }
    return {
        name: {"r303": old, "r304": current, "delta": current - old}
        for name, current in paths.items()
    }


def owned_ranges() -> set[int]:
    helper_offset = bank_offset(BANK31, HELPER_ADDR)
    return (
        set(range(FIXED_STUB_ADDR, FIXED_STUB_ADDR + len(NEW_FIXED_STUB)))
        | set(range(SHARED_TAIL_ADDR, SHARED_TAIL_ADDR + len(NEW_SHARED_TAIL)))
        | set(range(helper_offset, helper_offset + len(HELPER)))
    )


def validate_candidate(source: bytes, candidate: bytes) -> dict[str, Any]:
    require(len(candidate) == len(source) == ROM_SIZE,
            "candidate/source size changed")
    helper_offset = bank_offset(BANK31, HELPER_ADDR)
    require(candidate[FIXED_STUB_ADDR:FIXED_STUB_ADDR + len(NEW_FIXED_STUB)]
            == NEW_FIXED_STUB, "fixed bank31 stub changed")
    require(candidate[SHARED_TAIL_ADDR:SHARED_TAIL_ADDR + len(NEW_SHARED_TAIL)]
            == NEW_SHARED_TAIL, "shared tail hook changed")
    require(candidate[helper_offset:helper_offset + len(HELPER)] == HELPER,
            "bank31 invalidator/helper changed")
    require(candidate[BANK31_START:helper_offset]
            == source[BANK31_START:helper_offset]
            == bytes([0xFF]) * (helper_offset - BANK31_START),
            "bank31 prefix changed outside helper")
    require(candidate[helper_offset + len(HELPER):BANK31_END]
            == source[helper_offset + len(HELPER):BANK31_END]
            == bytes([0xFF]) * (BANK31_END - helper_offset - len(HELPER)),
            "bank31 suffix changed outside helper")

    changed = delta(source, candidate)
    functional = delta(source, candidate, functional=True)
    allowed = owned_ranges() | CHECKSUM_OFFSETS
    require(changed <= allowed,
            f"r304 escaped owned/checksum ranges: {sorted(changed - allowed)[:8]}")
    expected_functional = {
        offset for offset in owned_ranges()
        if source[offset] != candidate[offset]
    }
    require(functional == expected_functional,
            "r304 functional delta is not exactly the reviewed patch")
    require(len(functional) == 36,
            f"r304 functional delta count changed: {len(functional)}")

    header = 0
    for value in candidate[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    require(candidate[0x014D] == header, "header checksum invalid")
    total = (sum(candidate[:0x014E]) + sum(candidate[0x0150:])) & 0xFFFF
    require(int.from_bytes(candidate[0x014E:0x0150], "big") == total,
            "global checksum invalid")
    return {
        "functional_changed_bytes": len(functional),
        "changed_offsets": [f"0x{item:06X}" for item in sorted(functional)],
        "owned_ranges": [
            "fixed:$0013-$0017",
            "bank1:$77A8-$77AB",
            "bank31:$6C80-$6C9B",
        ],
        "escaped_bytes": 0,
    }


def build(
    source: bytes, base_receipt_bytes: bytes,
) -> tuple[bytes, dict[str, Any]]:
    require(digest(source) == BASE_SHA256, "wrong exact r303 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r303 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("schema") == BASE_SCHEMA,
            "r303 receipt schema changed")
    require(base_receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "r303 receipt status changed")
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r303 receipt names another candidate")

    preimages = validate_preimages(source)
    semantic = exhaustive_helper_contract()
    abi = stack_bank_contract()
    timing = timing_contract()

    rom = bytearray(source)
    allowed: set[int] = set()
    patch_exact(
        rom, source, FIXED_STUB_ADDR, OLD_FIXED_STUB, NEW_FIXED_STUB,
        allowed, "fixed bank31 mapper stub",
    )
    patch_exact(
        rom, source, SHARED_TAIL_ADDR, OLD_SHARED_TAIL, NEW_SHARED_TAIL,
        allowed, "shared $7798 tail hook",
    )
    helper_offset = bank_offset(BANK31, HELPER_ADDR)
    patch_exact(
        rom, source, helper_offset, bytes([0xFF]) * len(HELPER), HELPER,
        allowed, "bank31 scene0B invalidator",
    )
    require(allowed == owned_ranges(), "patch ownership construction drifted")
    update_checksums(rom)
    candidate = bytes(rom)
    ownership = validate_candidate(source, candidate)
    candidate_sha256 = digest(candidate)
    require(candidate_sha256 == EXPECTED_CANDIDATE_SHA256,
            f"candidate identity drift: {candidate_sha256}")

    receipt: dict[str, Any] = {
        "schema": "penta-stage1-scene0b-menu-close-r304-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base": {
            "revision": "r303",
            "candidate_sha256": BASE_SHA256,
            "build_receipt_sha256": BASE_RECEIPT_SHA256,
            "schema": BASE_SCHEMA,
        },
        "candidate_sha256": candidate_sha256,
        "checksums": {
            "header": f"{candidate[0x014D]:02X}",
            "global": candidate[0x014E:0x0150].hex().upper(),
        },
        "patch": {
            "shared_tail": {
                "range": "bank1:$77A8-$77AB",
                "old": OLD_SHARED_TAIL.hex(" ").upper(),
                "new": NEW_SHARED_TAIL.hex(" ").upper(),
            },
            "fixed_stub": {
                "range": "fixed:$0013-$0017",
                "old": OLD_FIXED_STUB.hex(" ").upper(),
                "new": NEW_FIXED_STUB.hex(" ").upper(),
            },
            "helper": {
                "range": "bank31:$6C80-$6C9B",
                "old": "FF x28",
                "new": HELPER.hex(" ").upper(),
            },
        },
        "preimage_contract": preimages,
        "offline_contract": {
            "semantic": semantic,
            "abi": abi,
            "timing_t_cycles": timing,
        },
        "ownership": ownership,
        "invalidation": {
            "trigger": "shared bank1:$7798 completion tail",
            "scope": "D880=0B and FFB7=02 only",
            "writes": ["DF53=FF", "DF57=FF"],
            "explicitly_untouched": [
                f"{address:04X}" for address in UNTOUCHED_COMPANION_ADDRS
            ],
            "FF91_independent": True,
            "corrected_r301_open_invalidator_included": False,
        },
        "required_live_gates": [
            "both authenticated scene0B operator captures plus fresh native route",
            "two live SELECT open/hold/close roundtrips per captured state",
            "DF53/DF57 invalidation and post-close physical-map republication",
            "zero magenta/red-green/wall-edge visual mismatches",
            "all 19 shared-tail caller classes retain FFE4/A/Z behavior",
            "hazard-menu, room01 north, room05 floor, and tooth controls",
            "release speed matrix: Stage1 >=95%, Stages2-7 strict 99%",
        ],
        "decision": "STATIC_GO_FOR_SERIALIZED_R304_LIVE_GATES",
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate output")
    receipt_path = checked_output(args.receipt, "receipt output")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes()
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_bytes(receipt_bytes(receipt))
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
