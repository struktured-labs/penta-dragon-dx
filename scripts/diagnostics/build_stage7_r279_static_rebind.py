#!/usr/bin/env python3
"""Rebind the exact Stage-7 static/ABI proof to the frozen r279 candidate.

This is a static-only gate.  It rematerializes the r273 -> r277 -> r278 ->
r279 byte lineage, proves that the only helper changes are the two lazy-disarm
guard targets and the carry-selective row-pointer advance, audits the new
router/cave control flow, and emits a candidate-bound receipt accepted by the
existing Stage-7 ABI wrapper.  It never launches an emulator.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]

R264_SHA256 = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
R273_SHA256 = "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
R277_SHA256 = "0c317aa69425ca3ca6f49b3e65a1671fb4fc4ee50d8b15d4900f12cf4493eb3f"
R278_SHA256 = "1bb98e252995a4da9080bcc7aeeb27237762eb2d0713d9ed7e43409c978efd47"
R279_SHA256 = "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"

R273_STATIC_SHA256 = (
    "60b8f9fb476847c136304f5d34e5cac9c65fc77bb7cba8004f2ea00051635f50"
)
R277_BUILD_SHA256 = (
    "6e9fa21d7b2c5d68251e1ffbf9ba4d01dfd53c119c1ea62777414b3098307a6c"
)
R278_BUILD_SHA256 = (
    "e6f9c93d148881b14c6a10e4abaca33149c272f27a6f79526d81fb03aa079b5d"
)
R279_BUILD_SHA256 = (
    "90842bca233226bcc2cc19d8f0f81e87ade4b6644f315c9552327c55e3f55018"
)

BANK_SIZE = 0x4000
RUNTIME_BANKS = (13, 16)
HELPER_BANK = 22
HELPER_START = 0x6C80
HELPER_END = 0x7232
HELPER_LENGTH = HELPER_END - HELPER_START + 1
R273_HELPER_SHA256 = (
    "5da2866e88a520bd67fd18b984a1cf4b6c7f6c1cb8bf93402d6fadd64f8afebd"
)
R279_HELPER_SHA256 = (
    "220b8f13439dc772adb1747d534382852dd1f47830395eb6f6720a234cc6920b"
)
R279_GUARDED_PREFIX_SHA256 = (
    "8e6b647ebed92be2b7237219ba54097a40e2698428b4c64d109aaad22833c313"
)
DESCRIPTORS_ADDR = 0x7500
DESCRIPTORS_LENGTH = 96
DESCRIPTORS_SHA256 = (
    "2d71e8844827ec11da155fabec1b42d93ea8e039bd56df69f3ddb0e463912874"
)
LUT_ADDR = 0x7600
LUT_LENGTH = 256
LUT_SHA256 = (
    "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a"
)

RUNTIME_REDIRECT_SOURCE_ADDR = 0x7C76
RUNTIME_TAIL_SOURCE_ADDR = 0x7CA8
NONSTAGE_JOIN_SOURCE_ADDR = 0x7CB3
STAGE7_FRONT_ADDR = 0x5407
SELECTOR_ADDR = 0x570E
POINTER_ADVANCE_ADDR = 0x6CFB
POINTER_REJOIN_ADDR = 0x6D04
FIRST_GUARD_OPERAND_ADDR = 0x6C86
SECOND_GUARD_OPERAND_ADDR = 0x6C8D
FALLBACK_NATIVE_ADDR = 0x71B3
CALLER_REJECT_ADDR = 0x71BD
ATOMIC_FALLBACK_ADDR = 0x71C1
DISARM_ADDR = 0x7233
CLASSIFIER_ADDR = 0x723B

OLD_STAGE7_FRONT = bytes.fromhex("CD 9C 54 C3 22 54")
NEW_STAGE7_FRONT = bytes.fromhex("C3 0E 57 00 00 00")
SELECTOR = bytes.fromhex(
    "3E 31 EA B7 DA CD 9C 54 C3 22 54 00 00 00 00 00"
)
R273_ROUTER_TAIL = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 F1 C9 F3 F1 F1 F1 3E 16 C3 47 08"
)
R279_ROUTER_TAIL = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 18 00 F3 F1 F1 F1 3E 16 C3 47 08"
)
OLD_POINTER_ADVANCE = bytes.fromhex("7D C6 08 6F 7C CE 00 67 00")
NEW_POINTER_ADVANCE = bytes.fromhex("7D C6 08 6F 30 03 24 18 00")
OLD_GUARD_TARGET = FALLBACK_NATIVE_ADDR.to_bytes(2, "little")
FIRST_GUARD_TARGET = CLASSIFIER_ADDR.to_bytes(2, "little")
SECOND_GUARD_TARGET = DISARM_ADDR.to_bytes(2, "little")
DISARM = bytes.fromhex("3E EB EA B7 DA C3 B3 71")
CLASSIFIER = bytes.fromhex("F0 BA FE 06 CA B3 71 C3 33 72")
CAVE = DISARM + CLASSIFIER
FALLBACK_NATIVE = bytes.fromhex("F1 11 B3 42 D5 3E 01 C3 61 00")
CALLER_REJECT = bytes.fromhex("E1 C3 B3 71")
FIXED_MAPPER_GLUE = bytes.fromhex("CD 61 00 CD 80 6C C3 61 00")
ROW_HELPER_SOURCE = bytes.fromhex("1A 13 4F 0A 22") * 24 + bytes((0xC9,))


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def region(payload: bytes | bytearray, bank: int, start: int,
           length: int) -> bytes:
    offset = bank_offset(bank, start)
    return bytes(payload[offset:offset + length])


def require_region(payload: bytes | bytearray, bank: int, start: int,
                   expected: bytes, label: str) -> None:
    actual = region(payload, bank, start, len(expected))
    require(
        actual == expected,
        f"{label} changed at bank{bank}:${start:04X}: "
        f"{actual.hex()} != {expected.hex()}",
    )


def patch_region(rom: bytearray, bank: int, start: int, old: bytes,
                 new: bytes, label: str) -> None:
    require(len(old) == len(new), f"{label} width changed")
    require_region(rom, bank, start, old, f"{label} preimage")
    offset = bank_offset(bank, start)
    rom[offset:offset + len(new)] = new


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def require_checksum(payload: bytes, label: str) -> dict[str, str]:
    header = 0
    for value in payload[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    require(payload[0x014D] == header, f"{label} header checksum is invalid")
    total = (sum(payload[:0x014E]) + sum(payload[0x0150:])) & 0xFFFF
    require(int.from_bytes(payload[0x014E:0x0150], "big") == total,
            f"{label} global checksum is invalid")
    return {"header": f"${header:02X}", "global": f"${total:04X}"}


def bound_bytes(path: Path, expected_sha256: str, label: str) -> bytes:
    payload = path.read_bytes()
    actual = digest(payload)
    require(actual == expected_sha256,
            f"{label} identity changed: {actual} != {expected_sha256}")
    return payload


def bound_json(path: Path, expected_sha256: str, label: str) -> dict:
    payload = bound_bytes(path, expected_sha256, label)
    parsed = json.loads(payload)
    require(isinstance(parsed, dict), f"{label} is not a JSON object")
    return parsed


def require_build_receipt(
    receipt: dict, *, schema: str, status: str, base_sha256: str,
    candidate_sha256: str, contracts: set[str], label: str,
) -> None:
    require(receipt.get("schema") == schema, f"{label} schema changed")
    require(receipt.get("status") == status, f"{label} status changed")
    require(receipt.get("promotable") is False,
            f"{label} incorrectly claims promotion")
    require(receipt.get("base_sha256") == base_sha256,
            f"{label} base identity changed")
    require(receipt.get("candidate_sha256") == candidate_sha256,
            f"{label} candidate identity changed")
    actual_contracts = receipt.get("contracts", {})
    require(isinstance(actual_contracts, dict)
            and set(actual_contracts) == contracts,
            f"{label} contract set changed")
    require(all(bool(value) for value in actual_contracts.values()),
            f"{label} contains a failed contract")


def rebuild_r277(r273: bytes) -> bytes:
    rom = bytearray(r273)
    for bank in RUNTIME_BANKS:
        patch_region(rom, bank, RUNTIME_REDIRECT_SOURCE_ADDR,
                     b"\x31", b"\xEB", "native redirect")
        require_region(rom, bank, RUNTIME_TAIL_SOURCE_ADDR,
                       R273_ROUTER_TAIL, "r273 router tail")
        patch_region(rom, bank, STAGE7_FRONT_ADDR, OLD_STAGE7_FRONT,
                     NEW_STAGE7_FRONT, "Stage-7 transition front")
        patch_region(rom, bank, SELECTOR_ADDR, bytes(16), SELECTOR,
                     "Stage-7 redirect selector")
    update_checksums(rom)
    return bytes(rom)


def rebuild_r278(r277: bytes) -> bytes:
    rom = bytearray(r277)
    patch_region(rom, HELPER_BANK, POINTER_ADVANCE_ADDR,
                 OLD_POINTER_ADVANCE, NEW_POINTER_ADVANCE,
                 "carry-selective pointer advance")
    update_checksums(rom)
    return bytes(rom)


def rebuild_r279(r278: bytes) -> bytes:
    rom = bytearray(r278)
    for bank in RUNTIME_BANKS:
        require_region(rom, bank, RUNTIME_TAIL_SOURCE_ADDR,
                       R273_ROUTER_TAIL, "r278 router tail")
        patch_region(rom, bank, NONSTAGE_JOIN_SOURCE_ADDR,
                     bytes.fromhex("F1 C9"), bytes.fromhex("18 00"),
                     "armed non-Stage-7 helper join")
    patch_region(rom, HELPER_BANK, FIRST_GUARD_OPERAND_ADDR,
                 OLD_GUARD_TARGET, FIRST_GUARD_TARGET,
                 "D880 classifier target")
    patch_region(rom, HELPER_BANK, SECOND_GUARD_OPERAND_ADDR,
                 OLD_GUARD_TARGET, SECOND_GUARD_TARGET,
                 "FFBA disarm target")
    patch_region(rom, HELPER_BANK, DISARM_ADDR, bytes([0xFF]) * len(CAVE),
                 CAVE, "lazy-disarm cave")
    update_checksums(rom)
    return bytes(rom)


def verify_lineage(args: argparse.Namespace) -> tuple[dict, dict[str, object]]:
    r264 = bound_bytes(args.r264, R264_SHA256, "r264 ROM")
    r273 = bound_bytes(args.r273, R273_SHA256, "r273 ROM")
    r277 = bound_bytes(args.r277, R277_SHA256, "r277 ROM")
    r278 = bound_bytes(args.r278, R278_SHA256, "r278 ROM")
    candidate = bound_bytes(args.candidate, R279_SHA256, "r279 ROM")
    require(len({len(r264), len(r273), len(r277), len(r278), len(candidate)}) == 1,
            "ROM lineage sizes differ")
    for label, payload in (
        ("r264", r264), ("r273", r273), ("r277", r277),
        ("r278", r278), ("r279", candidate),
    ):
        require_checksum(payload, label)

    r277_build = bound_json(
        args.r277_build, R277_BUILD_SHA256, "r277 build receipt"
    )
    r278_build = bound_json(
        args.r278_build, R278_BUILD_SHA256, "r278 build receipt"
    )
    r279_build = bound_json(
        args.r279_build, R279_BUILD_SHA256, "r279 build receipt"
    )
    require_build_receipt(
        r277_build,
        schema="penta-stage7-isolated-router-r277-build-v1",
        status="STATIC_PASS_SPEED_AND_LIVE_GATES_REQUIRED",
        base_sha256=R273_SHA256,
        candidate_sha256=R277_SHA256,
        contracts={
            "exact_r273_base", "rom_and_cold_default_is_native",
            "both_runtime_sources_default_native",
            "both_Stage7_transition_arms_install_identically",
            "nonstage_dirty_path_byte_and_cycle_exact_to_r264",
            "nonstage_transition_paths_byte_and_cycle_exact_to_r273",
            "stage7_router_tail_and_helper_byte_exact_to_r273",
            "vblank_service_pair_byte_exact_to_r273",
            "compiler_dma_palette_menu_crop_and_pickup_bytes_unchanged",
        },
        label="r277 build receipt",
    )
    require_build_receipt(
        r278_build,
        schema="penta-stage7-pointer-advance-r278-build-v1",
        status="STATIC_PASS_SPEED_AND_LIVE_GATES_REQUIRED",
        base_sha256=R277_SHA256,
        candidate_sha256=R278_SHA256,
        contracts={
            "exact_r277_base", "width_and_rejoin_unchanged",
            "terminal_hl_is_D280", "next_instruction_overwrites_a",
            "following_instruction_overwrites_flags",
            "router_and_stage5_isolation_byte_exact_to_r277",
            "vblank_services_byte_exact_to_r277",
            "dma_palette_menu_crop_and_pickup_bytes_unchanged",
        },
        label="r278 build receipt",
    )
    require_build_receipt(
        r279_build,
        schema="penta-stage7-lazy-disarm-r279-build-v1",
        status="STATIC_PASS_LIFECYCLE_AND_LIVE_GATES_REQUIRED",
        base_sha256=R278_SHA256,
        candidate_sha256=R279_SHA256,
        contracts={
            "exact_r278_base",
            "valid_stage7_hot_path_byte_and_cycle_exact_to_r278",
            "stage7_menu_path_byte_and_cycle_exact_to_r278",
            "disarm_precedes_atomic_setup",
            "disarm_executes_with_svbk1_and_ime_closed",
            "native_fallback_stack_and_mapper_path_reused",
            "pointer_speed_patch_byte_exact_to_r278",
            "vblank_services_dma_palette_menu_crop_and_pickups_unchanged",
        },
        label="r279 build receipt",
    )

    require(rebuild_r277(r273) == r277,
            "r277 is not the exact rematerialized r273 transition isolation")
    require(rebuild_r278(r277) == r278,
            "r278 is not the exact rematerialized pointer optimization")
    require(rebuild_r279(r278) == candidate,
            "r279 is not the exact rematerialized lazy-disarm candidate")

    base_static = bound_json(
        args.r273_static, R273_STATIC_SHA256, "r273 ABI static receipt"
    )
    require(base_static.get("schema")
            == "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
            "r273 ABI static schema changed")
    require(base_static.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "r273 ABI static proof did not pass")
    require(base_static.get("promotable") is False
            and base_static.get("emulator_run") is False,
            "r273 ABI receipt has invalid static-only status")
    require(base_static.get("in_memory_candidate", {}).get("sha256")
            == R273_SHA256, "r273 ABI receipt is bound to another ROM")

    return base_static, {
        "r264": r264,
        "r273": r273,
        "r277": r277,
        "r278": r278,
        "candidate": candidate,
        "r277_build": r277_build,
        "r278_build": r278_build,
        "r279_build": r279_build,
    }


def pointer_proof(candidate: bytes) -> dict[str, object]:
    require_region(candidate, HELPER_BANK, 0x6CF8, bytes.fromhex(
        "CD 00 D4 7D C6 08 6F 30 03 24 18 00 "
        "F0 E0 3D E0 E0 20 ED"
    ), "r279 attribute-row loop")
    require_region(candidate, 21, 0x4A00, ROW_HELPER_SOURCE,
                   "flag-neutral D400 row-helper source")

    rows: list[dict[str, object]] = []
    pointer = 0xD000
    old_total = 0
    new_total = 0
    for row in range(20):
        before = pointer + 24
        low_sum = (before & 0xFF) + 8
        carry = low_sum > 0xFF
        after = (((before >> 8) + int(carry)) << 8) | (low_sum & 0xFF)
        expected = 0xD000 + (row + 1) * 32
        require(after == expected, f"row {row} pointer transform changed")
        old_cycles = 36
        new_cycles = 40 if carry else 28
        rows.append({
            "row": row,
            "before_advance": f"${before:04X}",
            "carry": carry,
            "after_advance": f"${after:04X}",
            "old_cycles": old_cycles,
            "new_cycles": new_cycles,
        })
        old_total += old_cycles
        new_total += new_cycles
        pointer = after
    require(pointer == 0xD280, "pointer optimization no longer ends at $D280")
    carry_rows = [row["row"] for row in rows if row["carry"]]
    require(carry_rows == [7, 15], "pointer carry rows changed")
    require((old_total, new_total) == (720, 584),
            "pointer timing total changed")

    # The row helper's 24 repetitions contain only LD/INC/LDI and RET, none
    # of which reads or writes F.  JR NZ consumes DEC's Z only.  Thus the
    # carry difference on rows 7/15 is dead until the next ADD A,$08 replaces
    # it.  The final row is non-carry, so the old/new exit F is identical.
    return {
        "address": "bank22:$6CFB-$6D03",
        "rejoin": "bank22:$6D04",
        "old_bytes": OLD_POINTER_ADVANCE.hex(" ").upper(),
        "new_bytes": NEW_POINTER_ADVANCE.hex(" ").upper(),
        "terminal_hl": "$D280",
        "old_total_per_publication_t": old_total,
        "new_total_per_publication_t": new_total,
        "saved_per_publication_t": old_total - new_total,
        "carry_rows": carry_rows,
        "rows": rows,
        "flag_liveness": {
            "A": "$6D04 LDH A,[$E0] overwrites the pointer temporary",
            "Z": "$6D05 DEC A defines the only flag consumed by JR NZ",
            "carry": (
                "rows 7/15 carry through only flag-neutral D400 code and are "
                "overwritten by the next ADD A,$08; row 19 exits with carry "
                "clear exactly like the old sequence"
            ),
            "row_helper_source_sha256": digest(ROW_HELPER_SOURCE),
            "row_helper_is_flag_neutral": True,
            "old_and_new_exit_F_identical": True,
        },
    }


def lazy_route_proof() -> dict[str, object]:
    codes = bytearray()
    counts = {
        "hot_stage7": 0,
        "direct_disarm": 0,
        "classifier_preserve_fallback": 0,
        "classifier_disarm": 0,
    }
    code_for = {
        "hot_stage7": 0,
        "direct_disarm": 1,
        "classifier_preserve_fallback": 2,
        "classifier_disarm": 3,
    }
    for d880 in range(256):
        for ffba in range(256):
            if d880 == 0x08:
                route = "hot_stage7" if ffba == 0x06 else "direct_disarm"
            elif ffba == 0x06:
                route = "classifier_preserve_fallback"
            else:
                route = "classifier_disarm"
            counts[route] += 1
            codes.append(code_for[route])
    require(counts == {
        "hot_stage7": 1,
        "direct_disarm": 255,
        "classifier_preserve_fallback": 255,
        "classifier_disarm": 65025,
    }, "lazy-disarm exhaustive route partition changed")
    require(sum(counts.values()) == 65536,
            "lazy-disarm route partition is not exhaustive")
    return {
        "exhaustive_D880_FFBA_states": 65536,
        "counts": counts,
        "classification_sha256": digest(codes),
        "truth_table": [
            {
                "D880": "$08", "FFBA": "$06", "route": "hot_stage7",
                "DAB7_after": "$31", "native_fallback": False,
            },
            {
                "D880": "$08", "FFBA": "!=$06",
                "route": "direct_disarm", "DAB7_after": "$EB",
                "native_fallback": True,
            },
            {
                "D880": "!=$08", "FFBA": "$06",
                "route": "classifier_preserve_fallback",
                "DAB7_after": "$31", "native_fallback": True,
            },
            {
                "D880": "!=$08", "FFBA": "!=$06",
                "route": "classifier_disarm", "DAB7_after": "$EB",
                "native_fallback": True,
            },
        ],
        "preserved_states": 256,
        "disarmed_states": 65280,
    }


def require_critical_contract(candidate: bytes | bytearray) -> None:
    for bank in RUNTIME_BANKS:
        require_region(candidate, bank, RUNTIME_REDIRECT_SOURCE_ADDR, b"\xEB",
                       "cold/native DAB7 redirect source")
        require_region(candidate, bank, RUNTIME_TAIL_SOURCE_ADDR,
                       R279_ROUTER_TAIL, "lazy router tail")
        require_region(candidate, bank, STAGE7_FRONT_ADDR, NEW_STAGE7_FRONT,
                       "Stage-7 transition arm")
        require_region(candidate, bank, SELECTOR_ADDR, SELECTOR,
                       "Stage-7 redirect installer")
    require_region(candidate, HELPER_BANK, HELPER_START, bytes.fromhex(
        "FA 80 D8 FE 08 C2 3B 72 F0 BA FE 06 C2 33 72"
    ), "lazy helper guards")
    require_region(candidate, HELPER_BANK, POINTER_ADVANCE_ADDR,
                   NEW_POINTER_ADVANCE, "pointer optimization")
    require_region(candidate, HELPER_BANK, FALLBACK_NATIVE_ADDR,
                   FALLBACK_NATIVE, "native fallback")
    require_region(candidate, HELPER_BANK, CALLER_REJECT_ADDR,
                   CALLER_REJECT, "caller-reject stack balance")
    require_region(candidate, HELPER_BANK, HELPER_END - 1,
                   bytes.fromhex("37 C9"), "helper fail return boundary")
    require_region(candidate, HELPER_BANK, DISARM_ADDR, CAVE,
                   "lazy-disarm cave")


def mutation_controls(candidate: bytes) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    cases = {
        "router_join": (13, NONSTAGE_JOIN_SOURCE_ADDR),
        "scene_guard_target": (HELPER_BANK, FIRST_GUARD_OPERAND_ADDR),
        "dungeon_guard_target": (HELPER_BANK, SECOND_GUARD_OPERAND_ADDR),
        "pointer_branch": (HELPER_BANK, POINTER_ADVANCE_ADDR + 4),
        "disarm_DAB7_write": (HELPER_BANK, DISARM_ADDR + 3),
        "classifier_FFBA_compare": (HELPER_BANK, CLASSIFIER_ADDR + 3),
        "fallback_stack_rewrite": (HELPER_BANK, FALLBACK_NATIVE_ADDR),
        "selector_arm": (13, SELECTOR_ADDR + 1),
        "helper_cave_boundary": (HELPER_BANK, HELPER_END),
    }
    for name, (bank, address) in cases.items():
        mutant = bytearray(candidate)
        offset = bank_offset(bank, address)
        mutant[offset] ^= 0x01
        try:
            require_critical_contract(mutant)
        except AssertionError:
            controls[f"mutated_{name}_rejected"] = True
        else:
            controls[f"mutated_{name}_rejected"] = False
    require(all(controls.values()), "a critical r279 mutation was admitted")
    return controls


def static_contract(candidate: bytes, r273: bytes) -> dict[str, object]:
    require_critical_contract(candidate)
    helper = region(candidate, HELPER_BANK, HELPER_START, HELPER_LENGTH)
    r273_helper = region(r273, HELPER_BANK, HELPER_START, HELPER_LENGTH)
    require(digest(r273_helper) == R273_HELPER_SHA256,
            "r273 helper identity changed")
    require(digest(helper) == R279_HELPER_SHA256,
            "r279 helper identity changed")

    transferred = bytearray(r273_helper)
    for address, old, new, label in (
        (FIRST_GUARD_OPERAND_ADDR, OLD_GUARD_TARGET, FIRST_GUARD_TARGET,
         "D880 guard transfer"),
        (SECOND_GUARD_OPERAND_ADDR, OLD_GUARD_TARGET, SECOND_GUARD_TARGET,
         "FFBA guard transfer"),
        (POINTER_ADVANCE_ADDR, OLD_POINTER_ADVANCE, NEW_POINTER_ADVANCE,
         "pointer transfer"),
    ):
        relative = address - HELPER_START
        require(transferred[relative:relative + len(old)] == old,
                f"{label} preimage changed")
        transferred[relative:relative + len(new)] = new
    require(bytes(transferred) == helper,
            "helper transfer changed bytes outside the three owned patches")

    prefix = region(candidate, HELPER_BANK, HELPER_START, 0x6CE4 - HELPER_START)
    require(digest(prefix) == R279_GUARDED_PREFIX_SHA256,
            "r279 pre-atomic guarded prefix changed")
    require_region(candidate, HELPER_BANK, 0x6CE4,
                   bytes.fromhex("F1 CD 13 DA"),
                   "first atomic setup sequence")
    require_region(candidate, 21, 0x4A00, ROW_HELPER_SOURCE,
                   "row-helper source")
    require_region(candidate, HELPER_BANK, DESCRIPTORS_ADDR,
                   region(r273, HELPER_BANK, DESCRIPTORS_ADDR,
                          DESCRIPTORS_LENGTH), "descriptor transfer")
    require(digest(region(candidate, HELPER_BANK, DESCRIPTORS_ADDR,
                          DESCRIPTORS_LENGTH)) == DESCRIPTORS_SHA256,
            "descriptor identity changed")
    require_region(candidate, HELPER_BANK, LUT_ADDR,
                   region(r273, HELPER_BANK, LUT_ADDR, LUT_LENGTH),
                   "immutable LUT transfer")
    require(digest(region(candidate, HELPER_BANK, LUT_ADDR, LUT_LENGTH))
            == LUT_SHA256, "immutable LUT identity changed")
    require(region(candidate, HELPER_BANK, DISARM_ADDR + len(CAVE),
                   DESCRIPTORS_ADDR - DISARM_ADDR - len(CAVE))
            == bytes([0xFF])
            * (DESCRIPTORS_ADDR - DISARM_ADDR - len(CAVE)),
            "lazy-disarm cave escaped into the descriptor gap")

    require(candidate[0x0847:0x0847 + len(FIXED_MAPPER_GLUE)]
            == FIXED_MAPPER_GLUE, "fixed mapper/helper glue changed")
    require(candidate[0x4368:0x436E] == bytes.fromhex("E0 FF 3E 01 BF D9"),
            "native IE/AF/RETI completion changed")

    route = lazy_route_proof()
    pointer = pointer_proof(candidate)
    mutations = mutation_controls(candidate)
    return {
        "schema": "penta-stage7-r279-static-rebind-v1",
        "candidate_sha256": R279_SHA256,
        "helper": {
            "bank": HELPER_BANK,
            "range": "$6C80-$7232",
            "length": HELPER_LENGTH,
            "sha256": R279_HELPER_SHA256,
            "base_r273_sha256": R273_HELPER_SHA256,
            "only_owned_changes": [
                "$6C86-$6C87 D880 mismatch target $723B",
                "$6C8D-$6C8E FFBA mismatch target $7233",
                "$6CFB-$6D03 carry-selective pointer advance",
            ],
            "terminal_bytes": "$7231 SCF; $7232 RET",
            "fallthrough_into_cave": False,
        },
        "runtime_router": {
            "source_banks": list(RUNTIME_BANKS),
            "source_range": "$7CA8-$7CBD",
            "runtime_range": "$DAE9-$DAFE",
            "bytes": R279_ROUTER_TAIL.hex(" ").upper(),
            "sha256": digest(R279_ROUTER_TAIL),
            "cold_redirect_source": "$7C76=$EB -> native $DAA3",
            "armed_nonstage_join": "$7CB3-$7CB4 / $DAF4-$DAF5 = JR +0",
            "DI_before_mapper": "$DAF6 DI",
            "mapped_helper_glue": "fixed:$0847 CALL $0061; CALL $6C80; JP $0061",
        },
        "transition_arm": {
            "source_banks": list(RUNTIME_BANKS),
            "front": "$5407 JP $570E; NOP x3",
            "selector_range": "$570E-$571D",
            "selector_bytes": SELECTOR.hex(" ").upper(),
            "effect": "$DAB7=$31, CALL $549C, JP $5422",
        },
        "lazy_disarm": {
            "bank": HELPER_BANK,
            "range": "$7233-$7244",
            "bytes": CAVE.hex(" ").upper(),
            "sha256": digest(CAVE),
            "disarm": "$7233: LD A,$EB; LD [$DAB7],A; JP $71B3",
            "classifier": (
                "$723B: LDH A,[$FFBA]; CP $06; JP Z,$71B3; JP $7233"
            ),
            "descriptor_gap_after_cave": "$7245-$74FF remains erased $FF",
            "pre_atomic": True,
            "SVBK": 1,
            "IME": "closed by router $DAF6 DI",
            "stack_operations": [],
            "register_effects_before_fallback": {
                "A_F": "clobbered but immediately replaced by $71B3 POP AF",
                "BC": "unchanged",
                "DE": "unchanged until native fallback deliberately loads $42B3",
                "HL": "unchanged",
            },
            "native_stack_rewrite": {
                "helper_entry": ["synthetic $084D", "outer caller"],
                "after_$71B3_POP_AF": ["outer caller"],
                "after_PUSH_$42B3": ["synthetic $42B3", "outer caller"],
            },
            "routes": route,
        },
        "pointer_advance": pointer,
        "abi_transfer": {
            "entry": "bank22:$6C80",
            "entry_stack": ["synthetic $084D", "outer caller"],
            "first_VRAM_SVBK_atomic_mutation": "$6CE5 CALL $DA13",
            "fallback_native": "bank22:$71B3",
            "caller_reject": "bank22:$71BD",
            "fallback_after_atomic": "bank22:$71C1",
            "phase_boundaries": ["bank22:$7108", "bank22:$714B"],
            "DMA_stores": ["bank22:$713D", "bank22:$7187"],
            "helper_exit": "bank1:$436D pre-RETI",
            "admitted_outer_return": "fixed:$12E0",
            "rejected_outer_return": "fixed:$0AB8",
            "hot_stage7_and_menu_first_two_guards_cycle_exact_to_r278": True,
            "fallback_and_completion_bytes_exact_to_r273": True,
            "services_DMA_palette_menu_crop_pickups_exact_to_r273": True,
        },
        "mutation_controls": mutations,
        "contracts": {
            "exact_candidate_identity": True,
            "exact_r273_r277_r278_r279_rematerialization": True,
            "helper_change_set_exhaustive": True,
            "router_and_both_runtime_mirrors_exact": True,
            "Stage7_transition_arms_exact_and_mirrored": True,
            "lazy_disarm_cave_exact_and_nonfallthrough": True,
            "all_65536_D880_FFBA_states_partitioned": True,
            "disarm_before_SVBK_VBK_VRAM_or_atomic_mutation": True,
            "disarm_stack_balanced_and_native_fallback_reused": True,
            "valid_Stage7_hot_path_cycle_exact_to_r278": True,
            "Stage7_SELECT_menu_preserves_arm": True,
            "pointer_terminal_HL_and_live_flags_equivalent": True,
            "descriptor_LUT_DMA_service_menu_palette_pickup_bytes_inherited": True,
            "base_ABI_labels_stack_and_completion_inherited": True,
        },
        "required_live_gates": [
            "forced D880/FFBA lazy-disarm execution matrix",
            "Stage7 SELECT-menu roundtrip with DAB7 retained as $31",
            "candidate-bound Stage7 ABI run",
            "candidate-bound visual and Crystal containment",
        ],
    }


def build_receipt(
    base_static: dict, lineage: dict[str, object], args: argparse.Namespace,
) -> dict:
    candidate = lineage["candidate"]
    r264 = lineage["r264"]
    r273 = lineage["r273"]
    require(isinstance(candidate, bytes) and isinstance(r264, bytes)
            and isinstance(r273, bytes), "internal ROM lineage type changed")
    qualification = static_contract(candidate, r273)
    receipt = copy.deepcopy(base_static)

    built = receipt.get("in_memory_candidate")
    require(isinstance(built, dict), "base receipt candidate record changed")
    built.update({
        "path": str(args.candidate.resolve()),
        "sha256": R279_SHA256,
        "changed_byte_count": sum(
            left != right for left, right in zip(r264, candidate, strict=True)
        ),
        "checksums": require_checksum(candidate, "r279"),
        "runtime_source_patches": [
            "r277 cold/native $DAB7=$EB default and Stage7-only $31 installer",
            "r279 armed nonstage $DAF4 join into bank22 pre-atomic classifier",
            "D880/FFBA exact Stage7 guards with lazy-disarm targets $723B/$7233",
            "FFC1 guards still admit exactly transition/gameplay states 00/01",
            "r273 visible crop plus r278 carry-selective HL row advance",
        ],
    })
    installed = built.get("installed_regions")
    require(isinstance(installed, list), "installed-region list changed")
    helper_install = [row for row in installed
                      if isinstance(row, dict) and row.get("name") == "helper"]
    require(len(helper_install) == 1, "base helper install record changed")
    helper_install[0]["sha256"] = R279_HELPER_SHA256
    require(not any(isinstance(row, dict)
                    and row.get("name") == "lazy_disarm_cave"
                    for row in installed), "base receipt already has r279 cave")
    installed.append({
        "name": "lazy_disarm_cave",
        "bank": HELPER_BANK,
        "range": "$7233-$7244",
        "length": len(CAVE),
        "sha256": digest(CAVE),
    })

    helper = receipt.get("helper")
    require(isinstance(helper, dict)
            and helper.get("entry") == "$6C80"
            and helper.get("end") == "$7232"
            and helper.get("length") == HELPER_LENGTH,
            "base helper geometry changed")
    helper["sha256"] = R279_HELPER_SHA256
    helper["expansion_after_end"] = {
        "range": "$7233-$7244",
        "sha256": digest(CAVE),
        "fallthrough_from_helper": False,
    }

    emitted = receipt.get("emitted_guard_verification")
    require(isinstance(emitted, dict), "base guard proof changed")
    patterns = emitted.get("patterns")
    require(isinstance(patterns, dict), "base guard patterns changed")
    require(patterns.get("post_DI_scene")
            == "FA 80 D8 FE 08 C2 B3 71"
            and patterns.get("post_DI_dungeon")
            == "F0 BA FE 06 C2 B3 71",
            "r273 guard target preimage changed")
    patterns["post_DI_scene"] = "FA 80 D8 FE 08 C2 3B 72"
    patterns["post_DI_dungeon"] = "F0 BA FE 06 C2 33 72"
    emitted["guarded_prefix_sha256"] = R279_GUARDED_PREFIX_SHA256
    emitted["lazy_disarm_retarget"] = {
        "D880_mismatch": "bank22:$723B classifier",
        "FFBA_mismatch": "bank22:$7233 disarm",
        "all_other_guard_patterns": "byte-exact to r273",
        "first_atomic_mutation_if_admitted": "$DA13 tagged atomic setup",
    }
    emitted["r279_mutation_controls"] = qualification["mutation_controls"]

    timing = receipt.get("timing")
    require(isinstance(timing, dict), "base timing proof changed")
    phase1 = timing.get("phase1")
    require(isinstance(phase1, dict)
            and phase1.get("semantic_attribute_compile_and_padding_advance_t")
            == 19668
            and phase1.get("core_t") == 26384
            and phase1.get("full_interrupt_closed_upper_t") == 27040
            and phase1.get("timer_margin_t") == 20064,
            "r273 phase-1 timing preimage changed")
    phase1.update({
        "semantic_attribute_compile_and_padding_advance_t": 19532,
        "core_t": 26248,
        "full_interrupt_closed_upper_t": 26904,
        "timer_margin_t": 20200,
        "r278_pointer_saving_t": 136,
    })
    require(timing.get("candidate_dirty_conservative_typical_upper_t") == 80000
            and timing.get("current_dirty_approx_t") == 110984
            and timing.get("saving_per_dirty_approx_t") == 30984
            and timing.get("stage7_patrol_dirty_compiles") == 351,
            "r273 aggregate timing preimage changed")
    timing.update({
        "candidate_dirty_conservative_typical_upper_t": 79864,
        "saving_per_dirty_approx_t": 31120,
        "patrol_saving_projection_t": 10923120,
        "projection": (
            "r279 exact static hot-path delta from r273; live speed receipts "
            "remain mandatory"
        ),
    })

    crop = receipt.get("visible_crop_rebind")
    require(isinstance(crop, dict)
            and crop.get("schema") == "penta-stage7-r273-static-rebind-v1"
            and crop.get("candidate_sha256") == R273_SHA256,
            "r273 crop rebind changed")
    crop["candidate_sha256"] = R279_SHA256
    crop["transfer_base_candidate_sha256"] = R273_SHA256
    # These two historical compound claims included byte-exact guard targets.
    # r279 deliberately retargets the first two mismatch branches, so retain
    # the inherited geometry proof without mislabelling those bytes unchanged.
    crop_contracts = crop.get("contracts")
    require(isinstance(crop_contracts, dict),
            "r273 crop contract record changed")
    crop_contracts["all_other_guards_and_r265_menu_repairs_byte_exact"] = False
    crop_contracts[
        "r271_transport_timing_and_r269_guards_otherwise_byte_exact"
    ] = False
    crop["proof_inputs"].update({
        "r277": {
            "schema": lineage["r277_build"]["schema"],
            "base_sha256": R273_SHA256,
            "candidate_sha256": R277_SHA256,
            "receipt_sha256": R277_BUILD_SHA256,
        },
        "r278": {
            "schema": lineage["r278_build"]["schema"],
            "base_sha256": R277_SHA256,
            "candidate_sha256": R278_SHA256,
            "receipt_sha256": R278_BUILD_SHA256,
        },
        "r279": {
            "schema": lineage["r279_build"]["schema"],
            "base_sha256": R278_SHA256,
            "candidate_sha256": R279_SHA256,
            "receipt_sha256": R279_BUILD_SHA256,
        },
    })
    crop["current_transfer_contracts"] = {
        "geometry_and_40_block_transport_byte_exact_to_r273": True,
        "menu_palette_pickup_and_visible_crop_bytes_exact_to_r273": True,
        "pointer_transform_and_terminal_HL_equivalent": True,
        "guard_predicates_unchanged_but_mismatch_targets_lazily_disarm": True,
    }

    runtime_guards = receipt.get("runtime_guards")
    require(isinstance(runtime_guards, dict), "runtime guard record changed")
    runtime_guards["lifecycle_disarm"] = (
        "while DAB7=$31, D880!=08 classifies FFBA; FFBA!=06 writes "
        "DAB7=$EB before atomic setup, while FFBA=06 preserves transient "
        "death/retry/miniboss fallback"
    )
    memory = receipt.get("memory_ownership")
    require(isinstance(memory, dict), "memory ownership record changed")
    memory["stage1_and_arenas"] = (
        "fresh entry uses native DAB7=$EB and cannot enter helper; a stale "
        "armed transition is classified and self-disarmed before SVBK/VBK/VRAM"
    )

    receipt["r279_static_rebind"] = {
        **qualification,
        "lineage": {
            "r273_candidate_sha256": R273_SHA256,
            "r273_static_receipt_sha256": R273_STATIC_SHA256,
            "r277_candidate_sha256": R277_SHA256,
            "r277_build_receipt_sha256": R277_BUILD_SHA256,
            "r278_candidate_sha256": R278_SHA256,
            "r278_build_receipt_sha256": R278_BUILD_SHA256,
            "r279_build_receipt_sha256": R279_BUILD_SHA256,
        },
    }
    return receipt


def validate_with_existing_abi_static_parser(
    output: Path, candidate: Path,
) -> dict:
    # Importing this module is static; its emulator launch lives under main().
    import verify_stage7_dual_plane_abi as abi  # noqa: PLC0415

    arguments = SimpleNamespace(
        compiler_bank=HELPER_BANK,
        entry_addr=HELPER_START,
        compiler_start=HELPER_START,
        compiler_end=HELPER_END,
        phase_addr=[0x7108, 0x714B],
        fallback_addr=FALLBACK_NATIVE_ADDR,
        caller_reject_addr=CALLER_REJECT_ADDR,
        atomic_fallback_addr=ATOMIC_FALLBACK_ADDR,
        outer_return_addr=[0x0AB8, 0x12E0],
        exit_bank=1,
        exit_addr=0x436D,
        dma_command_addr=[0x713D, 0x7187],
        expected_dma_command=[0xA7, 0x81],
    )
    result = abi.validate_static_receipt(
        output, candidate, R279_SHA256, arguments
    )
    require(result.get("helper_range") == "bank22:$6C80-$7232",
            "ABI static parser returned a different helper")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--r264", type=Path,
        default=ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb",
    )
    parser.add_argument(
        "--r273", type=Path,
        default=ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb",
    )
    parser.add_argument(
        "--r273-static", type=Path,
        default=(ROOT / "tmp/stage7-skip-invisible-padding-r273/"
                 "abi-static-receipt.json"),
    )
    parser.add_argument(
        "--r277", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/candidate.gb",
    )
    parser.add_argument(
        "--r277-build", type=Path,
        default=ROOT / "tmp/stage7-isolated-router-r277/build-receipt.json",
    )
    parser.add_argument(
        "--r278", type=Path,
        default=ROOT / "tmp/stage7-pointer-advance-r278/candidate.gb",
    )
    parser.add_argument(
        "--r278-build", type=Path,
        default=ROOT / "tmp/stage7-pointer-advance-r278/build-receipt.json",
    )
    parser.add_argument(
        "--candidate", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/candidate.gb",
    )
    parser.add_argument(
        "--r279-build", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/build-receipt.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/abi-static-receipt.json",
    )
    args = parser.parse_args()

    base_static, lineage = verify_lineage(args)
    receipt = build_receipt(base_static, lineage, args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    abi_contract = validate_with_existing_abi_static_parser(
        args.output, args.candidate
    )
    receipt_sha256 = digest(args.output.read_bytes())
    print(json.dumps({
        "status": receipt["status"],
        "candidate_sha256": R279_SHA256,
        "helper_sha256": R279_HELPER_SHA256,
        "static_rebind_schema": receipt["r279_static_rebind"]["schema"],
        "abi_static_parser": "PASS",
        "abi_helper_range": abi_contract["helper_range"],
        "output": str(args.output.resolve()),
        "receipt_sha256": receipt_sha256,
        "emulator_run": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
