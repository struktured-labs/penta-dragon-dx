#!/usr/bin/env python3
"""Verify exact-r287's inherited Stage-4 lazy-departure lifecycle in one process.

The live gate cold-boots the native level-select route into Stage 4, observes
the exact atomic WRAM payload installation, exercises Stage4->Stage5 and
Stage4->Stage7 from one naturally armed candidate state, then reloads the
same process's cold candidate state and follows title into fresh Stage 1.

Every emulator launch goes through the checked-in single-flight wrapper.  The
static audit and mutation controls never launch an emulator.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
from typing import Any
import zlib

from verify_stage_speed_matrix import stop_owned_process_group


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
PROBE = ROOT / "scripts/diagnostics/probe_stage4_lazy_lifecycle_r287.lua"
VERIFIER = Path(__file__).resolve()
BUILDER = ROOT / "scripts/diagnostics/build_stage4_menu_exit_invalidation_r287.py"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_CANDIDATE = TMP / "stage4-menu-exit-invalidation-r287/candidate.gb"
DEFAULT_BUILD_RECEIPT = (
    TMP / "stage4-menu-exit-invalidation-r287/build-receipt.json"
)
DEFAULT_OUTPUT = TMP / "stage4-menu-exit-invalidation-r287/lifecycle-r1"

EXPECTED_ROM_SHA256 = (
    "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
)
EXPECTED_R286_SHA256 = (
    "a5521815ee25ca1c35a063198aec5f6a69609f99df7554201e41ab73699fc3c1"
)
EXPECTED_BUILD_RECEIPT_SHA256 = (
    "cf44305b10189d5549b2c2a2bc555a5c9729450b8d948acaf8b68258c58f1f4c"
)
EXPECTED_BUILDER_SHA256 = (
    "e44d7aa2b0bd809250717a1f6d10d6c5f0caae015f23d1c758d8e1f4d68e39ba"
)
EXPECTED_ROM_SIZE = 0x80000
EXPECTED_BUILD_SCHEMA = "penta-stage4-menu-exit-invalidation-r287-build-v1"
EXPECTED_PROBE_SCHEMA = "penta-stage4-lazy-lifecycle-r287-probe-v1"

BANK_SIZE = 0x4000
STAGE4_ENTRY = bytes.fromhex("F0 99 F5 3E 16 CD 61 00")
STAGE4_A_STUB = bytes.fromhex("3E 04 C9")
STAGE4_LANDING = bytes.fromhex("C3 00 60")
INSTALLER = bytes.fromhex(
    "3E EB EA B7 DA 3E 60 EA D5 DA C5 D5 "
    "21 00 63 11 00 DB 01 3E 00 CD B3 09 "
    "21 3E 63 11 5D DA 01 03 00 CD B3 09 "
    "3E 5D EA D5 DA D1 C1 F1 21 44 7C E5 "
    "21 13 54 E5 21 01 C6 06 08 C3 61 00"
)
PAYLOAD = bytes.fromhex(
    "3E 60 EA D5 DA FA 80 D8 D6 03 C3 60 DA "
    "00 00 00 00 00 00 C9 "
    "00 00 00 00 00 00 00 00 00 00 00 00 "
    "F0 BA FE 03 20 DA "
    "C5 D5 E5 AF E0 E0 7C EE CB 5F 16 DF "
    "21 F1 C1 46 24 4E CD 0D DB C3 92 DA"
)
TRAMPOLINE = bytes.fromhex("C3 20 DB")
ROUTER = bytes.fromhex(
    "E1 D1 C1 F5 FA 80 D8 FE 08 28 02 18 00 "
    "F3 F1 F1 F1 3E 16 C3 47 08"
)
NATIVE_LANDING = bytes.fromhex("C3 60 DA")
MENU_INVALIDATOR = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 AF EA 53 DF EA 57 DF 3C C9 00"
)
MENU_INVALIDATOR_NEXT = bytes.fromhex("0E 08 2A E0 69 0D 20 FA C9")
EXPECTED_STAGE7_HELPER_SHA256 = (
    "220b8f13439dc772adb1747d534382852dd1f47830395eb6f6720a234cc6920b"
)
EXPECTED_RUNTIME_SHA256 = (
    "d813c49c60df17c0169d9c571a3dd21c18b398357d1002a929866f94fff58b6d"
)
EXPECTED_TRANSITION_FRONT_SHA256 = {
    13: "886d2c78ba7e50d227c65da216777afe33ddc7e36e8e7bcc267bb3b2ba057400",
    16: "5e341d02893bdf20fbefc3b4fd6394c85f3eb0ef3be53da4d8a318dfcab66281",
}
EXPECTED_STAGE7_ARM_SHA256 = (
    "9017ad29a1451aa0644d162085b244ff97a8c6eecc8266a319cfed00e71237ac"
)

GB_STATE_SIZE = 0x11800
GB_STATE_MAGIC = 0x00400003


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest_bytes(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def scratch_child(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and resolved.is_relative_to(scratch),
            f"{label} must be a child of repository tmp/: {resolved}")
    return resolved


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def region(rom: bytes | bytearray, bank: int, address: int, size: int) -> bytes:
    offset = bank_offset(bank, address)
    return bytes(rom[offset:offset + size])


def checksum_contract(rom: bytes | bytearray) -> dict[str, str]:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    require(rom[0x014D] == header, "candidate header checksum is invalid")
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    require(int.from_bytes(rom[0x014E:0x0150], "big") == total,
            "candidate global checksum is invalid")
    return {"header": f"{header:02X}", "global": f"{total:04X}"}


def audit_candidate(rom: bytes | bytearray, *, exact_identity: bool) -> dict[str, Any]:
    require(len(rom) == EXPECTED_ROM_SIZE,
            f"candidate size is {len(rom):#x}, expected {EXPECTED_ROM_SIZE:#x}")
    if exact_identity:
        require(digest_bytes(rom) == EXPECTED_ROM_SHA256,
                f"wrong exact r287 candidate: {digest_bytes(rom)}")

    require(region(rom, 13, 0x6A40, len(MENU_INVALIDATOR))
            == MENU_INVALIDATOR,
            "r287 bank13 menu invalidator changed")
    require(region(rom, 13, 0x6A57, len(MENU_INVALIDATOR_NEXT))
            == MENU_INVALIDATOR_NEXT,
            "r287 menu invalidator overlaps the next live helper")

    for bank in (13, 16):
        require(region(rom, bank, 0x7C22, len(STAGE4_ENTRY)) == STAGE4_ENTRY,
                f"bank{bank} Stage4 mapper entry changed")
        require(region(rom, bank, 0x5413, len(STAGE4_A_STUB)) == STAGE4_A_STUB,
                f"bank{bank} Stage4 A-return stub changed")
        require(digest_bytes(region(rom, bank, 0x53F2, 33))
                == EXPECTED_TRANSITION_FRONT_SHA256[bank],
                f"bank{bank} normal transition front changed")
        require(digest_bytes(region(rom, bank, 0x570E, 16))
                == EXPECTED_STAGE7_ARM_SHA256,
                f"bank{bank} Stage7 arm helper changed")
        runtime = (
            region(rom, bank, 0x7BB2, 46)
            + region(rom, bank, 0x7C4D, 114)
        )
        require(digest_bytes(runtime) == EXPECTED_RUNTIME_SHA256,
                f"bank{bank} DA60 runtime source changed")
        require(region(rom, bank, 0x7C93, 3) == NATIVE_LANDING,
                f"bank{bank} native DAD4 landing changed")
        require(region(rom, bank, 0x7C94, 1) == bytes((0x60,)),
                f"bank{bank} native DAD5 landing operand changed")
        require(region(rom, bank, 0x7C76, 1) == bytes((0xEB,)),
                f"bank{bank} native DAB7 redirect operand changed")
        require(region(rom, bank, 0x7CA8, len(ROUTER)) == ROUTER,
                f"bank{bank} exact DAE9 router source changed")

    require(region(rom, 22, 0x7C2A, len(STAGE4_LANDING)) == STAGE4_LANDING,
            "bank22 Stage4 landing changed")
    require(region(rom, 22, 0x6000, len(INSTALLER)) == INSTALLER,
            "bank22 r286 fail-closed installer changed")
    require(region(rom, 22, 0x6300, len(PAYLOAD)) == PAYLOAD,
            "bank22 DB00-DB3D payload changed")
    require(region(rom, 22, 0x633E, len(TRAMPOLINE)) == TRAMPOLINE,
            "bank22 DA5D trampoline payload changed")
    require(digest_bytes(region(rom, 22, 0x6C80, 0x5B3))
            == EXPECTED_STAGE7_HELPER_SHA256,
            "exact r279 Stage7 helper/lazy-disarm region changed")

    checksums = checksum_contract(rom) if exact_identity else None
    return {
        "rom_sha256": digest_bytes(rom),
        "rom_size": len(rom),
        "checksums": checksums,
        "stage4_entry_mirrors": [13, 16],
        "inherited_runtime_operands": {"DAD5": "60", "DAB7": "EB"},
        "installer_sha256": digest_bytes(INSTALLER),
        "payload_sha256": digest_bytes(PAYLOAD),
        "trampoline_sha256": digest_bytes(TRAMPOLINE),
        "router_sha256": digest_bytes(ROUTER),
        "stage7_helper_sha256": EXPECTED_STAGE7_HELPER_SHA256,
        "menu_invalidator": {
            "range": "bank13:$6A40-$6A56",
            "bytes": MENU_INVALIDATOR.hex(" ").upper(),
            "sha256": digest_bytes(MENU_INVALIDATOR),
            "next_live_helper_sha256": digest_bytes(MENU_INVALIDATOR_NEXT),
        },
        "inherited_r286_sha256": EXPECTED_R286_SHA256,
    }


def audit_build_receipt(path: Path) -> dict[str, Any]:
    require(digest_file(path) == EXPECTED_BUILD_RECEIPT_SHA256,
            "exact r287 build receipt identity changed")
    receipt = json.loads(path.read_text())
    require(receipt.get("schema") == EXPECTED_BUILD_SCHEMA,
            "wrong r287 build receipt schema")
    require(receipt.get("candidate_sha256") == EXPECTED_ROM_SHA256,
            "build receipt candidate identity mismatch")
    require(receipt.get("base_sha256") == EXPECTED_R286_SHA256,
            "build receipt no longer derives from exact r286")
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "build receipt is not static-pass/live-required")
    require(receipt.get("emulator_invoked") is False,
            "build receipt unexpectedly claims an emulator launch")
    patch = receipt.get("patch", {})
    require(patch.get("range") == "bank13:$6A40-$6A56"
            and patch.get("rom_offset") == "0x036A40"
            and patch.get("new") == MENU_INVALIDATOR.hex(" ").upper()
            and patch.get("functional_changed_bytes") == 15
            and patch.get("changed_bytes_including_checksums") == 16,
            "build receipt menu invalidator ownership changed")
    invalidation = receipt.get("invalidation_contract", {})
    require(invalidation.get("old_scenes") == ["$02", "$08"]
            and invalidation.get("new_scenes")
            == [f"${value:02X}" for value in range(2, 9)]
            and invalidation.get("Stage4_scene") == "$05"
            and invalidation.get("operation")
            == "DF53=DF57=0 before Window maintenance/publication"
            and invalidation.get("repeated_menu_safe") is True,
            "build receipt invalidation semantics changed")
    controls = receipt.get("semantic_controls", {})
    require(controls.get("state_pairs") == 65536
            and controls.get("passed") == 65536
            and controls.get("FFE4_zero_byte_cycle_and_semantic_exact") is True
            and controls.get("FFE4_nonzero_returns_NZ_for_every_scene") is True
            and controls.get("invalidation_exactly_scenes_02_through_08") is True,
            "build receipt exhaustive menu controls changed")
    timing = receipt.get("timing_t_cycles", {})
    require(timing.get("ffe4_zero", {}).get("old") == 36
            and timing.get("ffe4_zero", {}).get("new") == 36
            and timing.get("ffe4_zero", {}).get("delta") == 0,
            "build receipt changed the gameplay/no-menu path")
    transferred = receipt.get("transferred_r286_contracts", {})
    require(transferred
            and all(value is True for value in transferred.values())
            and transferred.get("Stage4_DB00_DB3D_payload_exact") is True
            and transferred.get("DA5D_trampoline_DAD5_DAB7_exact") is True,
            "build receipt did not transfer the r286 lifecycle ownership")
    return receipt


def audit_probe_source(source: str) -> dict[str, Any]:
    required_once = (
        'SCHEMA = "penta-stage4-lazy-lifecycle-r287-probe-v1"',
        "emu:saveStateFile(COLD_STATE)",
        "emu:saveStateFile(ARMED_STATE)",
        "emu:loadStateFile(path)",
        "add_watch(0xDB00, 0xDB7F",
        'add_breakpoint("installer_pc_6005", 0x6005, 22)',
        'add_breakpoint("installer_pc_600A", 0x600A, 22)',
        'add_breakpoint("installer_pc_6018", 0x6018, 22)',
        'add_breakpoint("installer_pc_6024", 0x6024, 22)',
        'add_breakpoint("installer_pc_6029", 0x6029, 22)',
        'add_breakpoint("DAD4", 0xDAD4)',
        'add_breakpoint("DB20", 0xDB20)',
        'add_breakpoint("DB00", 0xDB00)',
        'add_breakpoint("DAE9", 0xDAE9)',
        'add_breakpoint("stage7_helper", 0x6C80, 22)',
        'add_breakpoint("stage7_fast", 0x6CE8, 22)',
        'add_breakpoint("stage7_exit", 0x436D, 1)',
        'pin_departure_identity(0x04, 0x06, 0x05, "stage5")',
        'pin_departure_identity(0x06, 0x08, 0x05, "stage7")',
        'require_live((reg("A") & 0xFF) == 0x03',
        'require_live((reg("A") & 0xFF) == 0x05',
        'finish("PASS", "same-process-stage4-lazy-lifecycle")',
    )
    for token in required_once:
        require(source.count(token) == 1,
                f"probe source token cardinality changed: {token!r}")
    for forbidden in (
        "add_watch(0xDA5D", "add_watch(0xDAD5", "add_watch(0xDAB7",
    ):
        require(forbidden not in source,
                f"probe restored fragile WRAM commit watch: {forbidden!r}")
    require(source.count("add_watch(") == 2,
            "probe must retain only its DB ownership write watch")
    require("/tmp" not in source, "probe source uses forbidden system /tmp")
    require("mgba" not in source.lower(), "Lua probe attempts to launch mGBA")
    return {
        "sha256": digest_bytes(source.encode()),
        "required_tokens": len(required_once),
        "same_process_save_load": True,
        "db_write_watch": "$DB00-$DB7F",
        "installer_pc_checkpoints": ["$6005", "$600A", "$6018", "$6024", "$6029"],
        "fragile_operand_write_watches": False,
        "level_select_targets": [3, 0],
    }


def expected_db_hex() -> str:
    return (PAYLOAD + bytes(0x80 - len(PAYLOAD))).hex().upper()


def valid_synthetic_metrics() -> dict[str, str]:
    values = {
        "schema": EXPECTED_PROBE_SCHEMA,
        "status": "PASS",
        "message": "same-process-stage4-lazy-lifecycle",
        "same_process": "1",
        "natural_stage4_install": "1",
        "title_reset_seen": "1",
        "title_reset_db_zero": "1",
        "stage1_stable": "1",
        "breakpoint_failures": "0",
        "watchpoint_failures": "0",
        "cold_state_save_requested": "1",
        "armed_state_save_requested": "1",
        "cold_state_loads": "1",
        "armed_state_loads": "1",
        "db_install_write_count": str(len(PAYLOAD)),
        "db_unexpected_writes": "0",
        "no_unexpected_db_writes": "1",
        "atomic_install_order": "1",
        "atomic_install_event_count": str(2 + len(PAYLOAD) + 3 + 1),
        "stage4_entry_hits": "1",
        "stage4_installer_hits": "1",
        "stage4_installer_pc_6005": "1",
        "stage4_installer_pc_600A": "1",
        "stage4_installer_pc_6018": "1",
        "stage4_installer_pc_6024": "1",
        "stage4_installer_pc_6029": "1",
        "installer_checkpoint_count": "5",
        "installer_checkpoint_order": "6005,600A,6018,6024,6029",
        "stage4_hot_dad4": "4",
        "stage4_hot_da5d": "4",
        "stage4_hot_db20": "4",
        "stage4_hot_delay": "4",
        "stage4_hot_da92": "4",
        "stage4_hot_da60": "0",
        "stage4_hot_db00": "0",
        "stage4_payload_exact": "1",
        "stage4_trampoline_exact": "1",
        "stage4_router_exact": "1",
        "stage4_dad5": "5D",
        "stage4_dab7": "EB",
        "stage4_db00_db7f": expected_db_hex(),
        "stage5_guard_a": "04",
        "stage5_pre_pin_identity_at_dad4": "04/05",
        "stage5_identity_at_dad4": "04/06",
        "stage5_normalized_a": "03",
        "stage5_first_dad4": "1",
        "stage5_first_da5d": "1",
        "stage5_first_db20": "1",
        "stage5_first_db00": "1",
        "stage5_first_da60": "1",
        "stage5_first_da92": "1",
        "stage5_later_dad4": "1",
        "stage5_later_da5d": "0",
        "stage5_later_db20": "0",
        "stage5_later_db00": "0",
        "stage5_later_da60": "1",
        "stage5_later_da92": "1",
        "stage5_restored_dad5": "60",
        "stage5_dab7": "EB",
        "stage5_payload_retained": "1",
        "stage7_guard_a": "06",
        "stage7_pre_pin_identity_at_dad4": "06/05",
        "stage7_identity_at_dad4": "06/08",
        "stage7_normalized_a": "05",
        "stage7_first_dad4": "1",
        "stage7_first_da5d": "1",
        "stage7_first_db20": "1",
        "stage7_first_db00": "1",
        "stage7_first_da60": "1",
        "stage7_first_da92": "1",
        "stage7_dae9": "1",
        "stage7_helper_entry": "1",
        "stage7_fastpath": "1",
        "stage7_exact_exit": "1",
        "stage7_disarm_hits": "0",
        "stage7_fallback_hits": "0",
        "stage7_router_exact_live": "1",
        "stage7_restored_dad5": "60",
        "stage7_preserved_dab7": "31",
        "stage7_payload_retained": "1",
        "stage7_forced_dirty_address": "DF00",
        "stage1_dad5": "60",
        "stage1_dab7": "EB",
        "stage1_db_zero": "1",
        "stage1_trampoline_zero": "1",
        "stage1_router_exact": "1",
        "stage1_dad4_hits": "0",
        "stage1_db20_hits": "0",
        "stage1_steady_db_writes": "0",
        "stage1_db00_db7f": bytes(0x80).hex().upper(),
        "payload_exact_while_armed": "1",
        "lazy_reset_stage5": "1",
        "lazy_reset_stage7": "1",
        "later_native_path": "1",
        "stage7_router_preserved": "1",
        "cold_title_stage1_reset": "1",
        "frames": "1800",
        "event_count": "20",
    }
    return values


def validate_metrics(metrics: dict[str, str]) -> dict[str, Any]:
    require(metrics.get("schema") == EXPECTED_PROBE_SCHEMA,
            "live probe schema mismatch")
    require(metrics.get("status") == "PASS",
            f"live probe failed: {metrics.get('message', 'no message')}")
    require(metrics.get("message") == "same-process-stage4-lazy-lifecycle",
            "live completion message changed")

    ones = {
        "same_process", "natural_stage4_install", "title_reset_seen",
        "title_reset_db_zero", "stage1_stable", "cold_state_save_requested",
        "armed_state_save_requested", "cold_state_loads", "armed_state_loads",
        "no_unexpected_db_writes", "atomic_install_order",
        "stage4_installer_hits", "stage4_payload_exact",
        "stage4_installer_pc_6005", "stage4_installer_pc_600A",
        "stage4_installer_pc_6018", "stage4_installer_pc_6024",
        "stage4_installer_pc_6029",
        "stage4_trampoline_exact", "stage4_router_exact",
        "stage5_first_dad4", "stage5_first_da5d", "stage5_first_db20",
        "stage5_first_db00", "stage5_first_da60", "stage5_first_da92",
        "stage5_later_dad4", "stage5_later_da60", "stage5_later_da92",
        "stage5_payload_retained", "stage7_first_dad4", "stage7_first_da5d",
        "stage7_first_db20", "stage7_first_db00", "stage7_first_da60",
        "stage7_first_da92", "stage7_dae9", "stage7_helper_entry",
        "stage7_fastpath", "stage7_exact_exit", "stage7_router_exact_live",
        "stage7_payload_retained", "stage1_db_zero", "stage1_trampoline_zero",
        "stage1_router_exact", "payload_exact_while_armed",
        "lazy_reset_stage5", "lazy_reset_stage7", "later_native_path",
        "stage7_router_preserved", "cold_title_stage1_reset",
    }
    for key in sorted(ones):
        require(metrics.get(key) == "1", f"{key} did not pass")

    zeros = {
        "breakpoint_failures", "watchpoint_failures", "db_unexpected_writes",
        "stage4_hot_da60", "stage4_hot_db00", "stage5_later_da5d",
        "stage5_later_db20", "stage5_later_db00", "stage7_disarm_hits",
        "stage7_fallback_hits", "stage1_dad4_hits", "stage1_db20_hits",
        "stage1_steady_db_writes",
    }
    for key in sorted(zeros):
        require(metrics.get(key) == "0", f"{key} is nonzero")

    require(metrics.get("stage4_dad5") == "5D"
            and metrics.get("stage4_dab7") == "EB",
            "Stage4 armed operands changed")
    require(metrics.get("stage5_guard_a") == "04"
            and metrics.get("stage5_pre_pin_identity_at_dad4") == "04/05"
            and metrics.get("stage5_identity_at_dad4") == "04/06"
            and metrics.get("stage5_normalized_a") == "03"
            and metrics.get("stage5_restored_dad5") == "60"
            and metrics.get("stage5_dab7") == "EB",
            "Stage5 lazy-reset semantics changed")
    require(metrics.get("stage7_guard_a") == "06"
            and metrics.get("stage7_pre_pin_identity_at_dad4") == "06/05"
            and metrics.get("stage7_identity_at_dad4") == "06/08"
            and metrics.get("stage7_normalized_a") == "05"
            and metrics.get("stage7_restored_dad5") == "60"
            and metrics.get("stage7_preserved_dab7") == "31",
            "Stage7 lazy-reset/router semantics changed")
    require(metrics.get("stage1_dad5") == "60"
            and metrics.get("stage1_dab7") == "EB",
            "fresh Stage1 native operands changed")
    require(metrics.get("stage4_db00_db7f") == expected_db_hex(),
            "armed Stage4 DB00-DB7F payload changed")
    require(metrics.get("stage1_db00_db7f") == bytes(0x80).hex().upper(),
            "fresh Stage1 DB00-DB7F is not zero")
    require(int(metrics.get("db_install_write_count", "-1")) == len(PAYLOAD),
            "installer did not write DB00-DB3D exactly once")
    require(int(metrics.get("atomic_install_event_count", "-1"))
            == 2 + len(PAYLOAD) + 3 + 1,
            "atomic install event count changed")
    require(metrics.get("installer_checkpoint_count") == "5"
            and metrics.get("installer_checkpoint_order")
            == "6005,600A,6018,6024,6029",
            "installer PC checkpoint sequence changed")
    for key in (
        "stage4_entry_hits", "stage4_hot_dad4", "stage4_hot_da5d",
        "stage4_hot_db20", "stage4_hot_delay", "stage4_hot_da92",
    ):
        require(int(metrics.get(key, "0")) > 0, f"{key} has no coverage")
    dirty = metrics.get("stage7_forced_dirty_address", "")
    require(re.fullmatch(r"D[0-9A-F]{3}", dirty) is not None,
            "Stage7 forced-dirty address is not WRAM")
    require(not (0xDB00 <= int(dirty, 16) <= 0xDB7F),
            "Stage7 dirty control touched the owned DB range")
    require(int(metrics.get("event_count", "0")) > 0,
            "live event trace is empty")
    return {
        "stage4_hot_decisions": int(metrics["stage4_hot_dad4"]),
        "atomic_install_events": int(metrics["atomic_install_event_count"]),
        "installer_pc_checkpoints": metrics["installer_checkpoint_order"],
        "db_install_writes": int(metrics["db_install_write_count"]),
        "stage5_pre_pin_identity_at_dad4": metrics[
            "stage5_pre_pin_identity_at_dad4"],
        "stage5_identity_at_dad4": metrics["stage5_identity_at_dad4"],
        "stage5_normalized_a": metrics["stage5_normalized_a"],
        "stage7_pre_pin_identity_at_dad4": metrics[
            "stage7_pre_pin_identity_at_dad4"],
        "stage7_identity_at_dad4": metrics["stage7_identity_at_dad4"],
        "stage7_normalized_a": metrics["stage7_normalized_a"],
        "stage7_dirty_address": dirty,
        "frames": int(metrics["frames"]),
    }


def parse_report(path: Path) -> tuple[dict[str, str], list[str]]:
    metrics: dict[str, str] = {}
    events: list[str] = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        require("=" in line, f"report line {number} is malformed")
        key, value = line.split("=", 1)
        if key == "event":
            events.append(value)
        else:
            require(key not in metrics, f"duplicate report key: {key}")
            metrics[key] = value
    require(events, "live report has no event lines")
    require(int(metrics.get("event_count", "-1")) == len(events),
            "live report event count does not match trace")
    return metrics, events


def serialized_state(path: Path) -> bytes:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not an mGBA PNG savestate: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + size
        require(end <= len(data), f"truncated PNG payload: {path}")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        observed_crc = struct.unpack(">I", data[offset + 8 + size:end])[0]
        require(observed_crc == zlib.crc32(kind + payload) & 0xFFFFFFFF,
                f"PNG chunk CRC mismatch ({kind!r}): {path}")
        if kind == b"gbAs":
            decoder = zlib.decompressobj()
            state = decoder.decompress(payload) + decoder.flush()
            require(decoder.eof and not decoder.unused_data
                    and not decoder.unconsumed_tail,
                    f"malformed compressed gbAs payload: {path}")
            states.append(state)
        if kind == b"IEND":
            require(size == 0 and end == len(data),
                    f"malformed/trailing IEND: {path}")
            saw_iend = True
        offset = end
    require(saw_iend and len(states) == 1,
            f"savestate must contain one gbAs chunk: {path}")
    state = states[0]
    require(len(state) == GB_STATE_SIZE,
            f"gbAs size {len(state):#x}, expected {GB_STATE_SIZE:#x}")
    require(int.from_bytes(state[:4], "little") == GB_STATE_MAGIC,
            "unsupported Game Boy savestate version")
    require(state[0x0008] & 0x80, "savestate is not a CGB machine")
    return state


def audit_state(path: Path, rom: bytes, *, label: str) -> dict[str, Any]:
    state = serialized_state(path)
    expected_crc = zlib.crc32(rom) & 0xFFFFFFFF
    observed_crc = int.from_bytes(state[4:8], "little")
    require(observed_crc == expected_crc,
            f"{label} embedded ROM CRC does not bind exact r287")
    require(state[0x10:0x20] == rom[0x134:0x144],
            f"{label} cartridge title does not bind exact r287")
    return {
        "path": relative(path),
        "sha256": digest_file(path),
        "gbas_sha256": digest_bytes(state),
        "size": path.stat().st_size,
        "gbas_size": len(state),
        "rom_crc32": f"{observed_crc:08x}",
        "candidate_bound": True,
    }


def expect_rejected(action, label: str) -> None:
    try:
        action()
    except (AssertionError, ValueError, KeyError):
        return
    raise AssertionError(f"mutation control was accepted: {label}")


def mutation_controls(rom: bytes, source: str) -> dict[str, bool]:
    controls: dict[str, bool] = {}

    mutant = bytearray(rom)
    mutant[0x200] ^= 1
    expect_rejected(lambda: audit_candidate(mutant, exact_identity=True),
                    "exact ROM identity")
    controls["exact_rom_identity_mutation_rejected"] = True

    mutations = (
        ("menu_invalidator", bank_offset(13, 0x6A40)),
        ("stage4_entry", bank_offset(13, 0x7C22)),
        ("installer", bank_offset(22, 0x6000)),
        ("payload", bank_offset(22, 0x6300)),
        ("trampoline", bank_offset(22, 0x633E)),
        ("DAD5_operand", bank_offset(13, 0x7C94)),
        ("DAB7_operand", bank_offset(16, 0x7C76)),
        ("router_source", bank_offset(16, 0x7CA8)),
        ("stage7_helper", bank_offset(22, 0x6C80)),
    )
    for label, offset in mutations:
        mutant = bytearray(rom)
        mutant[offset] ^= 1
        expect_rejected(lambda mutant=mutant: audit_candidate(
            mutant, exact_identity=False), label)
        controls[f"{label}_mutation_rejected"] = True

    source_mutant = source.replace(
        'add_breakpoint("DB00", 0xDB00)',
        'add_breakpoint("DB00", 0xDB01)', 1,
    )
    expect_rejected(lambda: audit_probe_source(source_mutant),
                    "probe DB00 breakpoint")
    controls["probe_route_mutation_rejected"] = True

    source_mutant = source.replace(
        'add_breakpoint("installer_pc_6029", 0x6029, 22)',
        'add_breakpoint("installer_pc_6029", 0x6028, 22)', 1,
    )
    expect_rejected(lambda: audit_probe_source(source_mutant),
                    "probe installer commit checkpoint")
    controls["probe_commit_checkpoint_mutation_rejected"] = True

    source_mutant = source.replace(
        'require_live((reg("A") & 0xFF) == 0x03',
        'require_live((reg("A") & 0xFF) == 0x02', 1,
    )
    expect_rejected(lambda: audit_probe_source(source_mutant),
                    "probe Stage5 normalized A")
    controls["probe_stage5_normalized_A_mutation_rejected"] = True

    source_mutant = source.replace(
        'pin_departure_identity(0x06, 0x08, 0x05, "stage7")',
        'pin_departure_identity(0x06, 0x07, 0x05, "stage7")', 1,
    )
    expect_rejected(lambda: audit_probe_source(source_mutant),
                    "probe Stage7 DAD4 identity pin")
    controls["probe_stage7_identity_pin_mutation_rejected"] = True

    good = valid_synthetic_metrics()
    validate_metrics(good)
    for label, key, value in (
        ("normalized_A", "stage5_normalized_a", "02"),
        ("lazy_landing", "stage5_later_db20", "1"),
        ("Stage7_arm", "stage7_preserved_dab7", "EB"),
        ("Stage1_DB", "stage1_db00_db7f", "01" + good["stage1_db00_db7f"][2:]),
        ("atomic_order", "atomic_install_order", "0"),
        ("checkpoint_order", "installer_checkpoint_order",
         "6005,600A,6018,6024,6028"),
    ):
        mutant_metrics = copy.deepcopy(good)
        mutant_metrics[key] = value
        expect_rejected(lambda mutant_metrics=mutant_metrics: validate_metrics(
            mutant_metrics), label)
        controls[f"report_{label}_mutation_rejected"] = True
    return controls


def state_crc_mutation_control(state_path: Path, rom: bytes) -> bool:
    state = bytearray(serialized_state(state_path))
    state[4] ^= 1

    def reject() -> None:
        expected_crc = zlib.crc32(rom) & 0xFFFFFFFF
        require(int.from_bytes(state[4:8], "little") == expected_crc,
                "mutated state CRC accepted")

    expect_rejected(reject, "savestate ROM CRC")
    return True


def run_probe(candidate: Path, output: Path, timeout: float) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    report = output / "probe.report"
    marker = output / "DONE"
    cold_state = output / "cold.ss0"
    armed_state = output / "stage4-armed.ss0"
    log = output / "mgba.log"
    for path in (report, marker, cold_state, armed_state, log):
        path.unlink(missing_ok=True)
    for stale_save in output.glob("*.sav"):
        stale_save.unlink()

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE4_LIFECYCLE_OUT": str(report),
        "STAGE4_LIFECYCLE_DONE": str(marker),
        "STAGE4_LIFECYCLE_COLD_STATE": str(cold_state),
        "STAGE4_LIFECYCLE_ARMED_STATE": str(armed_state),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                str(LAUNCHER), "--fastforward",
                "-C", f"savegamePath={output}",
                "-C", f"savestatePath={output}",
                str(candidate), "--script", str(PROBE), "-l", "0",
            ],
            cwd=output,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if report.is_file() and marker.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        return_code = stop_owned_process_group(process)
    require(report.is_file() and marker.is_file(),
            f"lifecycle probe did not finish (exit={return_code}); see {log}")
    marker_text = marker.read_text().strip()
    require(marker_text == "PASS\tsame-process-stage4-lazy-lifecycle",
            f"lifecycle completion marker failed: {marker_text}")
    metrics, events = parse_report(report)
    summary = validate_metrics(metrics)
    rom = candidate.read_bytes()
    states = {
        "cold": audit_state(cold_state, rom, label="cold state"),
        "stage4_armed": audit_state(armed_state, rom, label="armed state"),
    }
    require(states["cold"]["sha256"] != states["stage4_armed"]["sha256"],
            "cold and armed savestates are unexpectedly identical")
    return {
        "metrics": metrics,
        "summary": summary,
        "events": events,
        "report": relative(report),
        "report_sha256": digest_file(report),
        "marker": relative(marker),
        "marker_sha256": digest_file(marker),
        "states": states,
        "state_crc_mutation_rejected": state_crc_mutation_control(
            armed_state, rom),
        "log": relative(log),
        "log_sha256": digest_file(log),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path, nargs="?", default=DEFAULT_CANDIDATE)
    parser.add_argument("--build-receipt", type=Path, default=DEFAULT_BUILD_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--replays", type=int, choices=(1, 2), default=1)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    build_receipt_path = args.build_receipt.resolve()
    output = scratch_child(args.output, "output")
    require(candidate.is_file(), f"candidate missing: {candidate}")
    require(build_receipt_path.is_file(),
            f"build receipt missing: {build_receipt_path}")
    require(PROBE.is_file(), f"probe missing: {PROBE}")
    require(BUILDER.is_file(), f"builder missing: {BUILDER}")
    require(digest_file(BUILDER) == EXPECTED_BUILDER_SHA256,
            "exact r287 builder identity changed")
    require(LAUNCHER.is_file(), f"single-flight launcher missing: {LAUNCHER}")

    rom = candidate.read_bytes()
    source = PROBE.read_text()
    static = audit_candidate(rom, exact_identity=True)
    build = audit_build_receipt(build_receipt_path)
    probe = audit_probe_source(source)
    controls = mutation_controls(rom, source)
    output.mkdir(parents=True, exist_ok=True)

    receipt: dict[str, Any] = {
        "schema": "penta-stage4-lazy-lifecycle-r287-verifier-v1",
        "status": "STATIC_PASS_LIVE_REQUIRED" if args.static_only else "RUNNING",
        "promotable": False,
        "candidate": relative(candidate),
        "candidate_sha256": EXPECTED_ROM_SHA256,
        "build_receipt": relative(build_receipt_path),
        "build_receipt_sha256": digest_file(build_receipt_path),
        "build_receipt_schema": build["schema"],
        "builder": relative(BUILDER),
        "builder_sha256": EXPECTED_BUILDER_SHA256,
        "probe": relative(PROBE),
        "probe_sha256": digest_file(PROBE),
        "verifier": relative(VERIFIER),
        "verifier_sha256": digest_file(VERIFIER),
        "launcher": relative(LAUNCHER),
        "launcher_sha256": digest_file(LAUNCHER),
        "emulator_singleflight": True,
        "static_audit": static,
        "probe_audit": probe,
        "mutation_controls": controls,
        "runs": [],
    }
    receipt_path = output / "receipt.json"
    if args.static_only:
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print("STATIC PASS: exact-r287 lifecycle contract; live run still required")
        print(f"Receipt: {receipt_path}")
        return 0

    runs = [
        run_probe(candidate, output / f"run-{index}", args.timeout)
        for index in range(1, args.replays + 1)
    ]
    if len(runs) == 2:
        semantic = lambda run: {
            "metrics": run["metrics"],
            "summary": run["summary"],
            "events": [re.sub(r"\|f\d+\|", "|f#|", value)
                       for value in run["events"]],
        }
        require(semantic(runs[0]) == semantic(runs[1]),
                "duplicate same-process lifecycle replay diverged")
    receipt["runs"] = runs
    receipt["status"] = "PASS"
    receipt["promotable"] = False
    receipt["contracts"] = {
        "natural_Stage4_install_and_exact_payload": True,
        "atomic_DAB7_DAD5_copy_commit_order": True,
        "DB00_DB3D_exact_while_armed": True,
        "no_DB3E_DB7F_or_post_install_writes": True,
        "Stage4_to_Stage5_first_call_restores_DAD5_and_normalized_A": True,
        "Stage5_later_call_uses_native_DA60_without_lazy_path": True,
        "Stage4_to_Stage7_preserves_DAB7_31_and_executes_DAE9_helper": True,
        "synthetic_departure_identities_pinned_at_DAD4": True,
        "Stage7_router_helper_and_exact_exit_observed": True,
        "cold_reload_title_and_fresh_Stage1_clear_private_payload": True,
        "generated_states_embedded_CRC_and_title_bind_exact_r287": True,
        "one_emulator_process_per_replay": True,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS: exact-r287 same-process Stage4 lazy lifecycle")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
