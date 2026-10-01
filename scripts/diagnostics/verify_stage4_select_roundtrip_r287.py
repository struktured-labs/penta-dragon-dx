#!/usr/bin/env python3
"""Exact-r287 Stage-4 cold-route SELECT open/hold/close release gate.

Static mode binds the ROM, r287 build receipt, probe, verifier, menu oracle,
and checked-in single-flight launcher, then runs mutation controls without an
emulator.  Live mode accepts only that hash-bound static receipt and performs
two sequential cold-boot replays through the native level selector.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
VERIFIER = Path(__file__).resolve()
PROBE = Path(__file__).with_name("probe_stage4_select_roundtrip_r287.lua")
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
SINGLEFLIGHT = ROOT / "scripts/mgba_singleflight.py"
MENU_COLORIZER = ROOT / "scripts/menu_icon_colorization.py"
BUILDER = Path(__file__).with_name("build_stage4_menu_exit_invalidation_r287.py")
CANDIDATE = TMP / "stage4-menu-exit-invalidation-r287/candidate.gb"
BUILD_RECEIPT = TMP / "stage4-menu-exit-invalidation-r287/build-receipt.json"
DEFAULT_STATIC_OUTPUT = (
    TMP / "stage4-menu-exit-invalidation-r287/menu-roundtrip-static-receipt.json"
)

EXPECTED_CANDIDATE_SHA256 = (
    "a9bc2d2d5d7112584797229d03bfb2fe55a9bcb5fa3c1a33d30cddc3a8364898"
)
EXPECTED_BUILD_RECEIPT_SHA256 = (
    "cf44305b10189d5549b2c2a2bc555a5c9729450b8d948acaf8b68258c58f1f4c"
)
EXPECTED_PROBE_SHA256 = (
    "43ee73a21e6c4424e174a1940c54a14386b2ed5834131d321905fc6286b3489b"
)
EXPECTED_LAUNCHER_SHA256 = (
    "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570"
)
EXPECTED_SINGLEFLIGHT_SHA256 = (
    "6475c791468ffa2cd0ca0f73ab28af4e424aef067a7d6b33bcacff05c0e52e07"
)
EXPECTED_MENU_COLORIZER_SHA256 = (
    "eaefbff75c94d45e4cda19667f67b973e9febb9a8f426b3ee4724b9c8ef99a3a"
)
EXPECTED_BUILDER_SHA256 = (
    "e44d7aa2b0bd809250717a1f6d10d6c5f0caae015f23d1c758d8e1f4d68e39ba"
)
EXPECTED_PAYLOAD_SHA256 = (
    "f054b744ddd4d8e4d06d453dcf5f13c9a115cd68eb7d921f531f875ec6f6b009"
)
EXPECTED_STAGE_LUT_SHA256 = (
    "0487e8f299c13e19462115a601e89de5f56989f4dd7afef25003aeb4f292ddcd"
)
EXPECTED_MENU_LUT_SHA256 = (
    "5ae3ca4d14527ad90517f37f4f7dc4e1e614642d7f970f3d072a8e0b769bb1a5"
)
EXPECTED_CANONICAL_LUT_SHA256 = (
    "487c1443ddec16171cc0f2744b3fbbd013cdcac5e1d7fd8145fe46f277805734"
)

BANK_SIZE = 0x4000
TARGET = 3
EXPECTED_SCENE = 5
PAYLOAD = bytes.fromhex(
    "3E 60 EA D5 DA FA 80 D8 D6 03 C3 60 DA 00 00 00 "
    "00 00 00 C9 00 00 00 00 00 00 00 00 00 00 00 00 "
    "F0 BA FE 03 20 DA C5 D5 E5 AF E0 E0 7C EE CB 5F "
    "16 DF 21 F1 C1 46 24 4E CD 0D DB C3 92 DA"
)
TRAMPOLINE = bytes.fromhex("C3 20 DB")
STAGE4_ENTRY = bytes.fromhex("F0 99 F5 3E 16 CD 61 00")
MENU_FIRST_PREFIX = bytes.fromhex("F0 99 F5 3E 14 CD 61 00 CD 00 40")
MENU_INTERACTIVE_PREFIX = bytes.fromhex("F0 99 F5 3E 14 CD 61 00 CD 17 40")
INVALIDATOR = bytes.fromhex(
    "F0 E4 B7 C8 FA 80 D8 D6 02 FE 07 3D D0 AF EA 53 DF EA 57 DF 3C C9 00"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def scratch_child(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    root = TMP.resolve()
    require(resolved != root and root in resolved.parents,
            f"{label} must be a child of repository tmp/: {resolved}")
    return resolved


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000,
            f"invalid banked address bank{bank}:${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def region(rom: bytes, bank: int, address: int, size: int) -> bytes:
    offset = bank_offset(bank, address)
    result = rom[offset:offset + size]
    require(len(result) == size, "candidate banked region is truncated")
    return result


def stage4_lut() -> bytes:
    result = bytearray(0x100)
    for tile in range(0x01, 0x09):
        result[tile] = 4
    result[0x2D] = result[0x2E] = 2
    payload = bytes(result)
    require(sha256_bytes(payload) == EXPECTED_STAGE_LUT_SHA256,
            "independent Stage-4 material LUT changed")
    return payload


def menu_lut(canonical: bytes) -> bytes:
    """Independent equivalent of the immutable menu-only LUT overlay."""

    require(len(canonical) == 0x100, "canonical menu LUT has wrong size")
    result = bytearray(canonical)
    overrides = {
        0x86: 5, 0x87: 5,
        0x82: 5, 0x83: 5, 0x92: 5, 0x93: 5,
        0x80: 4, 0x81: 4, 0x90: 4, 0x91: 4,
        0xFC: 1,
    }
    for tile, palette in overrides.items():
        require(canonical[tile] == 0,
                f"menu-only tile ${tile:02X} is not neutral")
        result[tile] = palette
    payload = bytes(result)
    require(sha256_bytes(payload) == EXPECTED_MENU_LUT_SHA256,
            "independent menu LUT changed")
    return payload


def audit_candidate() -> dict[str, Any]:
    require(CANDIDATE.is_file(), f"candidate missing: {CANDIDATE}")
    require(BUILD_RECEIPT.is_file(), f"build receipt missing: {BUILD_RECEIPT}")
    rom = CANDIDATE.read_bytes()
    require(len(rom) == 0x80000, "r287 candidate is not exactly 512 KiB")
    require(sha256_bytes(rom) == EXPECTED_CANDIDATE_SHA256,
            "candidate identity changed")
    require(sha256(BUILD_RECEIPT) == EXPECTED_BUILD_RECEIPT_SHA256,
            "r287 build receipt identity changed")
    receipt = json.loads(BUILD_RECEIPT.read_text())
    require(receipt.get("schema")
            == "penta-stage4-menu-exit-invalidation-r287-build-v1",
            "wrong r287 build receipt schema")
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "r287 build static status is not green")
    require(receipt.get("emulator_invoked") is False,
            "r287 build receipt unexpectedly claims emulator evidence")
    require(receipt.get("candidate_sha256") == EXPECTED_CANDIDATE_SHA256,
            "r287 build receipt binds another candidate")
    require(receipt.get("promotable") is False,
            "static build receipt unexpectedly claims promotion")
    require(receipt.get("base_sha256")
            == "a5521815ee25ca1c35a063198aec5f6a69609f99df7554201e41ab73699fc3c1",
            "r287 receipt does not bind exact r286")
    require(receipt.get("base_build_receipt_sha256")
            == "4a1209778c471dc833ab574d6bac46e70e8f8d925a80a4ec48dd61099f117d49",
            "r287 receipt does not bind the exact r286 receipt")

    candidate_payload = region(rom, 22, 0x6300, len(PAYLOAD))
    require(PAYLOAD == candidate_payload, "bank22 WRAM payload bytes changed")
    require(sha256_bytes(candidate_payload) == EXPECTED_PAYLOAD_SHA256,
            "bank22 WRAM payload identity changed")
    require(region(rom, 22, 0x633E, len(TRAMPOLINE)) == TRAMPOLINE,
            "bank22 DA5D trampoline payload changed")
    require(region(rom, 22, 0x7C2A, 3) == bytes.fromhex("C3 00 60"),
            "Stage-4 bank22 landing changed")
    for bank in (13, 16):
        require(region(rom, bank, 0x7C22, len(STAGE4_ENTRY)) == STAGE4_ENTRY,
                f"Stage-4 owned entry changed in bank {bank}")

    canonical = region(rom, 13, 0x7000, 0x100)
    require(sha256_bytes(canonical) == EXPECTED_CANONICAL_LUT_SHA256,
            "canonical menu LUT identity changed")
    expected_menu = menu_lut(canonical)
    require(region(rom, 20, 0x4100, 0x100) == expected_menu,
            "candidate private menu LUT differs from its canonical oracle")
    require(region(rom, 13, 0x6A40, len(INVALIDATOR)) == INVALIDATOR,
            "r287 bank13 Window invalidator changed")
    require(rom[0x1B48:0x1B48 + len(MENU_FIRST_PREFIX)] == MENU_FIRST_PREFIX,
            "first native menu wrapper changed")
    require(rom[0x1D78:0x1D78 + len(MENU_INTERACTIVE_PREFIX)]
            == MENU_INTERACTIVE_PREFIX,
            "interactive native menu wrapper changed")

    patch = receipt.get("patch", {})
    require(patch.get("range") == "bank13:$6A40-$6A56"
            and patch.get("new") == INVALIDATOR.hex(" ").upper(),
            "r287 receipt invalidator binding changed")
    invalidation = receipt.get("invalidation_contract", {})
    require(invalidation.get("Stage4_scene") == "$05"
            and invalidation.get("operation")
            == "DF53=DF57=0 before Window maintenance/publication",
            "r287 receipt lacks the exact Stage-4 dual-cache operation")
    transferred = receipt.get("transferred_r286_contracts", {})
    require(transferred.get("Stage4_DB00_DB3D_payload_exact") is True
            and transferred.get("DA5D_trampoline_DAD5_DAB7_exact") is True,
            "r287 receipt did not transfer the exact r286 runtime contract")
    required_gates = receipt.get("required_live_gates", [])
    require(any("Stage4 SELECT" in gate for gate in required_gates),
            "r287 build receipt does not require this menu gate")
    return {
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "build_receipt_sha256": EXPECTED_BUILD_RECEIPT_SHA256,
        "candidate_size": len(rom),
        "stage4_entry": ["bank13:$7C22", "bank16:$7C22"],
        "wram_payload": {
            "rom": "bank22:$6300-$633D",
            "runtime": "$DB00-$DB3D",
            "size": len(PAYLOAD),
            "sha256": EXPECTED_PAYLOAD_SHA256,
        },
        "runtime_operands": {"DAD5": "$5D", "DAB7": "$EB"},
        "menu_invalidator": {
            "rom": "bank13:$6A40-$6A56",
            "effect_pc": "$6A54",
            "operation": "DF53=DF57=0 while FFE4!=0",
            "sha256": sha256_bytes(INVALIDATOR),
        },
        "menu_lut_sha256": EXPECTED_MENU_LUT_SHA256,
        "stage4_lut_sha256": EXPECTED_STAGE_LUT_SHA256,
    }


PROBE_CONSTANTS = {
    "TARGET": TARGET,
    "EXPECTED_SCENE": EXPECTED_SCENE,
    "DECIDER_ENTRY": 0xDAD4,
    "HELPER_ENTRY": 0xDB20,
    "HELPER_JOIN": 0xDA92,
    "CACHE_MISS_ENTRY": 0xDAA9,
    "CACHE_DIRTY_RETURN": 0xDAB6,
    "CACHE_RETURN": 0xDAA3,
    "ATTR_COMPILER_ENTRY": 0x42FC,
    "ATTR_COMPILER_BANK": 0x01,
    "INVALIDATOR_ENTRY": 0x6A40,
    "INVALIDATOR_EFFECT": 0x6A54,
    "INVALIDATOR_BANK": 0x0D,
    "PAYLOAD_FIRST": 0xDB00,
    "PAYLOAD_LAST": 0xDB3D,
    "TRAMPOLINE_FIRST": 0xDA5D,
    "TRAMPOLINE_LAST": 0xDA5F,
}

PROBE_REQUIRED_SNIPPETS = (
    'local OUT = assert(os.getenv("STAGE4_MENU_OUT"),',
    "local raw_vram = assert(emu.memory.vram)",
    "native_assistance.write(0xDCFD, 0x01)",
    "emu:write8(0xFFBA, TARGET)",
    'phase = "level_select"',
    'phase = "loading"',
    'phase = "pre"',
    'phase = "open"',
    'phase = "menu"',
    'phase = "close"',
    'phase = "post"',
    "local wanted = string.byte(\n        expected_payload, address - PAYLOAD_FIRST + 1)",
    "and dad5 == 0x5D and dab7 == 0xEB",
    "local df_address = 0xDF00 + ((helper_h ~ 0xCB) & 0xFF)",
    "cache53, cache54, cache55,\n    cache57, cache58, cache59",
    "frame, cpu_h, helper_h, emu:read8(0xC1F1), emu:read8(0xC2F1)",
    'capture_key_snapshot("settled_pre")',
    'capture_key_snapshot("open")',
    'capture_key_snapshot("menu")',
    'capture_key_snapshot("invalidation_effect")',
    'capture_key_snapshot("first_post")',
    'capture_key_snapshot("first_post_helper")',
    'capture_key_snapshot("first_post_repaint")',
    'capture_key_snapshot("final")',
    "local wanted = string.byte(expected_stage_lut, tile + 1)",
    "local wanted = string.byte(expected_menu_lut, tiles[index] + 1)",
    "if actual ~= wanted then",
    "if base == bg_base then",
    "if helper_active then",
    "install_breakpoint(DECIDER_ENTRY",
    "install_breakpoint(HELPER_ENTRY",
    "install_breakpoint(HELPER_JOIN",
    "install_breakpoint(CACHE_MISS_ENTRY",
    "install_breakpoint(CACHE_DIRTY_RETURN",
    "install_breakpoint(CACHE_RETURN",
    "install_breakpoint(ATTR_COMPILER_ENTRY",
    "install_breakpoint(INVALIDATOR_ENTRY",
    "install_breakpoint(INVALIDATOR_EFFECT",
    'type(result) ~= "number" or result <= 0',
    'if phase_frame <= 6 then keys = KEY_SELECT end',
    'finish("fail", "select-open-not-acknowledged")',
    'finish("fail", "select-close-not-acknowledged")',
    'finish("ok", "complete")',
    'marker:write(status .. "\\n")',
)


def audit_probe_source(source: str, *, enforce_hash: bool = True) -> dict[str, Any]:
    if enforce_hash:
        require(sha256_bytes(source.encode()) == EXPECTED_PROBE_SHA256,
                "Stage-4 menu probe identity changed")
    for name, expected in PROBE_CONSTANTS.items():
        match = re.search(
            rf"^local {re.escape(name)} = (0x[0-9A-Fa-f]+|[0-9]+)$",
            source, re.MULTILINE,
        )
        require(match is not None, f"probe lacks exact constant {name}")
        require(int(match.group(1), 0) == expected,
                f"probe changed {name}")
    for snippet in PROBE_REQUIRED_SNIPPETS:
        require(snippet in source, f"probe lacks contract: {snippet}")
    require(source.count("install_breakpoint(DECIDER_ENTRY") == 1,
            "decider breakpoint installation is not unique")
    require(source.count("install_breakpoint(HELPER_ENTRY") == 1,
            "helper breakpoint installation is not unique")
    require(source.count("install_breakpoint(HELPER_JOIN") == 1,
            "helper join breakpoint installation is not unique")
    for name in (
        "CACHE_MISS_ENTRY", "CACHE_DIRTY_RETURN", "CACHE_RETURN",
        "ATTR_COMPILER_ENTRY", "INVALIDATOR_ENTRY", "INVALIDATOR_EFFECT",
    ):
        require(source.count(f"install_breakpoint({name}") == 1,
                f"{name} breakpoint installation is not unique")
    require(source.count("audit_visible_gameplay(period)") == 2,
            "visible gameplay semantic oracle definition/call changed")
    require(source.count("audit_window()") == 2,
            "visible Window oracle definition/call changed")
    return {
        "probe_sha256": sha256_bytes(source.encode()),
        "constants": {
            key: f"${value:04X}" if value > 0xFF else value
            for key, value in PROBE_CONSTANTS.items()
        },
        "cold_route": "native GAME START -> native level selector -> Stage 4",
        "menu_input": "native SELECT open, hold, native SELECT close",
        "gameplay_oracle": "every visible attr equals Stage4 C600[tile]",
        "window_oracle": "C4E0 6x20 tiles plus private immutable menu LUT",
    }


REPORT_INT_FIELDS = (
    "frames", "frame_limit", "menu_hold", "target", "expected_scene",
    "stage_seen", "install_seen", "semantic_armed", "menu_seen", "menu_closed",
    "stable_stage_frames", "breakpoint_failures",
    "stage_context_violations", "ffc1_non1_frames", "installed_context_frames",
    "payload_checked_frames", "payload_mismatch_frames",
    "payload_mismatch_bytes", "dad5_mismatch_frames",
    "dab7_mismatch_frames", "trampoline_mismatch_frames",
    "svbk_non1_frames", "stage_lut_checked_frames",
    "stage_lut_mismatch_frames", "stage_lut_mismatch_bytes",
    "decider_entries_pre", "decider_entries_menu", "decider_entries_post",
    "helper_entries_pre", "helper_entries_menu", "helper_entries_post",
    "helper_joins_pre", "helper_joins_menu", "helper_joins_post",
    "helper_wrong_context", "helper_contract_failures",
    "helper_cache_hits_pre", "helper_cache_hits_menu", "helper_cache_hits_post",
    "helper_cache_misses_pre", "helper_cache_misses_menu",
    "helper_cache_misses_post", "first_post_helper_forced_miss",
    "first_post_helper_stale_hit", "first_post_helper_dirty_signal",
    "helper_dirty_signal_failures", "post_repaint_compiler_entries",
    "post_clean_after_repaint_frames", "invalidator_entries",
    "invalidator_menu_entries", "invalidator_effect_hits",
    "invalidator_effect_wrong_context", "invalidator_effect_nonzero_df53",
    "invalidator_effect_nonzero_df57", "menu_zero_cache_frames",
    "menu_cache_repopulation_frames",
    "helper_active_menu_frames", "menu_owned_frames",
    "menu_visible_frames", "ffe4_nonzero_frames",
    "menu_stage_context_violations", "window_checked_cells",
    "window_tile_mismatch_frames", "window_tile_mismatch_cells",
    "window_attr_mismatch_frames", "window_attr_mismatch_cells",
    "window_unsafe_attr_cells", "window_geometry_mismatch_frames",
    "window_map_alias_frames", "pre_visible_frames", "pre_visible_cells",
    "pre_semantic_mismatch_frames", "pre_semantic_mismatch_cells",
    "pre_write_trail_cells", "pre_unsafe_attr_cells",
    "pre_material_cells", "pre_warmup_mismatch_frames",
    "pre_warmup_mismatch_cells", "post_visible_frames", "post_visible_cells",
    "post_semantic_mismatch_frames", "post_semantic_mismatch_cells",
    "post_write_trail_cells", "post_unsafe_attr_cells",
    "post_material_cells",
)

FINAL_STATE_RE = re.compile(
    r"^scene:05,ffc1:01,stage:03,ffe4:00,lcdc:([0-9A-F]{2}),"
    r"wx:([0-9A-F]{2}),wy:([0-9A-F]{2}),scx:([0-9A-F]{2}),"
    r"scy:([0-9A-F]{2}),vbk:00,svbk:01,ff55:FF,dad5:5D,"
    r"dab7:EB,base:(9800|9C00),helper:0$"
)

KEY_SNAPSHOT_TAGS = (
    "settled_pre", "open", "invalidation_effect", "menu", "first_post",
    "first_post_helper", "first_post_repaint", "final",
)
KEY_SNAPSHOT_RE = re.compile(
    r"^frame:(\d+),cpu_h:([0-9A-F]{2}),helper_h:([0-9A-F]{2}),"
    r"c1f1:([0-9A-F]{2}),c2f1:([0-9A-F]{2}),room:([0-9A-F]{2}),"
    r"df_addr:(DF[0-9A-F]{2}),df0:([0-9A-F]{2}),df1:([0-9A-F]{2}),"
    r"df2:([0-9A-F]{2}),cache53:([0-9A-F]{6}),"
    r"cache57:([0-9A-F]{6}),known:"
    r"([0-9A-F]{2}/DF[0-9A-F]{2}/[0-9A-F]{6}"
    r"(?:;[0-9A-F]{2}/DF[0-9A-F]{2}/[0-9A-F]{6})*)$"
)


def parse_key_snapshots(report: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    snapshots: dict[str, Any] = {}
    failures: list[str] = []
    previous_frame = -1
    for tag in KEY_SNAPSHOT_TAGS:
        raw = report.get(f"key_{tag}", "")
        match = KEY_SNAPSHOT_RE.fullmatch(raw)
        if match is None:
            failures.append(f"missing/invalid native key snapshot {tag}")
            continue
        frame = int(match.group(1), 10)
        cpu_h = int(match.group(2), 16)
        helper_h = int(match.group(3), 16)
        c1f1 = int(match.group(4), 16)
        c2f1 = int(match.group(5), 16)
        room = int(match.group(6), 16)
        df_address = int(match.group(7), 16)
        df_record = tuple(int(match.group(index), 16) for index in (8, 9, 10))
        known: list[dict[str, Any]] = []
        cache53 = match.group(11)
        cache57 = match.group(12)
        for record in match.group(13).split(";"):
            raw_h, raw_address, raw_bytes = record.split("/")
            known_h = int(raw_h, 16)
            known_address = int(raw_address, 16)
            if known_address != 0xDF00 + (known_h ^ 0xCB):
                failures.append(f"{tag} known-H DF selector formula changed")
            known.append({
                "helper_h": known_h,
                "df_address": f"${known_address:04X}",
                "df_record": raw_bytes,
            })
        if df_address != 0xDF00 + (helper_h ^ 0xCB):
            failures.append(f"{tag} selected DF address disagrees with helper H")
        selected_cache = cache53 if df_address == 0xDF53 else cache57
        if df_address in {0xDF53, 0xDF57}:
            if selected_cache != "".join(f"{value:02X}" for value in df_record):
                failures.append(f"{tag} selected DF record disagrees with fixed cache")
        else:
            failures.append(f"{tag} helper H did not select a Stage-4 page cache")
        if frame < previous_frame:
            failures.append(f"native key snapshot order regressed at {tag}")
        previous_frame = frame
        snapshots[tag] = {
            "frame": frame,
            "cpu_h": f"${cpu_h:02X}",
            "helper_h": f"${helper_h:02X}",
            "shortcut": {"C1F1": f"${c1f1:02X}", "C2F1": f"${c2f1:02X}"},
            "room": f"${room:02X}",
            "selected_df_address": f"${df_address:04X}",
            "selected_df_record": "".join(f"{value:02X}" for value in df_record),
            "cache_records": {"DF53": cache53, "DF57": cache57},
            "known_helper_h_records": known,
        }
    return snapshots, failures


def cache_lifecycle_failures(snapshots: dict[str, Any]) -> list[str]:
    """Prove invalidation, forced miss, repaint, and final cache recovery."""

    if set(snapshots) != set(KEY_SNAPSHOT_TAGS):
        return ["native cache lifecycle is incomplete"]
    failures: list[str] = []
    settled = snapshots["settled_pre"]
    source = (
        settled["shortcut"]["C1F1"], settled["shortcut"]["C2F1"],
        settled["room"],
    )
    expected = "".join(value.removeprefix("$") for value in source)
    for tag, snapshot in snapshots.items():
        current = (
            snapshot["shortcut"]["C1F1"], snapshot["shortcut"]["C2F1"],
            snapshot["room"],
        )
        if current != source:
            failures.append(f"native source key changed at {tag}")

    for tag in ("settled_pre", "open"):
        records = snapshots[tag]["cache_records"]
        if records != {"DF53": expected, "DF57": expected}:
            failures.append(f"both page caches were not settled at {tag}")

    for tag in ("invalidation_effect", "menu"):
        records = snapshots[tag]["cache_records"]
        if records["DF53"][:2] != "00" or records["DF57"][:2] != "00":
            failures.append(f"dual Stage-4 cache invalidation absent at {tag}")

    helper = snapshots["first_post_helper"]
    if helper["selected_df_record"] == expected:
        failures.append("first post-menu helper retained a matching cache record")
    if helper["selected_df_record"][:2] != "00":
        failures.append("first post-menu helper did not consume the zero invalidator")

    repaint = snapshots["first_post_repaint"]
    if repaint["selected_df_record"] != expected:
        failures.append("first post-menu repaint did not restore its selected cache")
    if repaint["cache_records"] != {"DF53": expected, "DF57": expected}:
        failures.append("both physical page caches were not restored by repaint")

    final = snapshots["final"]["cache_records"]
    if final != {"DF53": expected, "DF57": expected}:
        failures.append("both physical page caches were not restored by final Stage 4")
    return failures


def parse_report(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        require(key and key not in result, f"duplicate probe report field: {key}")
        result[key] = value
    return result


def report_failures(
    report: dict[str, str], *, frames: int, menu_hold: int,
) -> list[str]:
    failures: list[str] = []
    values: dict[str, int] = {}
    for key in REPORT_INT_FIELDS:
        try:
            values[key] = int(report.get(key, ""), 10)
        except ValueError:
            failures.append(f"missing/invalid integer {key}")
    if failures:
        return failures

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(report.get("status") == "ok" and report.get("reason") == "complete",
          "probe did not complete the SELECT roundtrip")
    check(values["frame_limit"] == frames and values["menu_hold"] == menu_hold,
          "probe route parameters differ from the requested gate")
    check(0 < values["frames"] <= frames, "probe frame count is out of range")
    check(values["target"] == TARGET
          and values["expected_scene"] == EXPECTED_SCENE,
          "probe did not target exact Stage 4")
    for key in (
        "stage_seen", "install_seen", "semantic_armed", "menu_seen", "menu_closed",
    ):
        check(values[key] == 1, f"required lifecycle marker {key} was not seen")
    check(values["stable_stage_frames"] >= 300,
          "too few stable Stage-4 frames were observed")
    check(values["breakpoint_failures"] == 0,
          "one or more execution breakpoints failed to install")
    check(values["installed_context_frames"] >= 250,
          "too few exact installed-runtime frames were checked")
    check(values["payload_checked_frames"] == values["installed_context_frames"],
          "DB00-DB3D coverage does not span every installed frame")
    check(values["stage_lut_checked_frames"] == values["installed_context_frames"],
          "Stage-4 LUT coverage does not span every installed frame")
    for key in (
        "stage_context_violations", "payload_mismatch_frames",
        "payload_mismatch_bytes", "dad5_mismatch_frames",
        "dab7_mismatch_frames", "trampoline_mismatch_frames",
        "stage_lut_mismatch_frames",
        "stage_lut_mismatch_bytes", "decider_entries_menu",
        "helper_entries_menu", "helper_joins_menu",
        "helper_wrong_context", "helper_contract_failures",
        "first_post_helper_stale_hit", "helper_dirty_signal_failures",
        "invalidator_effect_wrong_context",
        "invalidator_effect_nonzero_df53",
        "invalidator_effect_nonzero_df57", "menu_cache_repopulation_frames",
        "helper_active_menu_frames", "menu_stage_context_violations",
        "window_tile_mismatch_frames", "window_tile_mismatch_cells",
        "window_attr_mismatch_frames", "window_attr_mismatch_cells",
        "window_unsafe_attr_cells", "window_geometry_mismatch_frames",
        "window_map_alias_frames", "pre_semantic_mismatch_frames",
        "pre_semantic_mismatch_cells", "pre_write_trail_cells",
        "pre_unsafe_attr_cells", "post_semantic_mismatch_frames",
        "post_semantic_mismatch_cells", "post_write_trail_cells",
        "post_unsafe_attr_cells",
    ):
        check(values[key] == 0, f"nonzero containment field {key}")
    check(values["ffc1_non1_frames"] <= 4,
          "too many transient non-gameplay bank samples")
    check(values["svbk_non1_frames"] <= 4,
          "too many transient non-WRAM1 publication samples")
    check(values["pre_warmup_mismatch_frames"] <= 10,
          "cold Stage-4 semantic warmup exceeded its bounded allowance")
    check(values["pre_warmup_mismatch_cells"] <= 3600,
          "cold Stage-4 semantic warmup damage exceeded one viewport budget")
    check(values["invalidator_entries"] > 0,
          "bank13 Window invalidator never executed")
    check(values["invalidator_menu_entries"] > 0,
          "bank13 Window invalidator never saw Stage-4 menu ownership")
    check(values["invalidator_effect_hits"]
          == values["invalidator_menu_entries"],
          "Stage-4 Window invalidator entry/effect coverage is incomplete")
    check(values["menu_zero_cache_frames"] > 0,
          "menu ownership never retained both zeroed page caches")
    check(values["first_post_helper_forced_miss"] == 1,
          "first post-menu helper did not take exactly one proved forced miss")
    check(values["first_post_helper_dirty_signal"] == 1,
          "first post-menu miss did not assert the native repaint signal")
    check(values["post_repaint_compiler_entries"] == 1,
          "native attribute compiler did not service exactly one post-menu repaint")
    check(values["post_clean_after_repaint_frames"] > 0,
          "no clean visible Stage-4 frame followed the proved repaint")
    for period in ("pre", "post"):
        entries = values[f"helper_entries_{period}"]
        joins = values[f"helper_joins_{period}"]
        check(entries >= 2, f"optimized helper did not run {period}-menu")
        check(entries == joins, f"helper lifecycle is unbalanced {period}-menu")
        check(entries == values[f"helper_cache_hits_{period}"]
              + values[f"helper_cache_misses_{period}"],
              f"helper cache outcome coverage is incomplete {period}-menu")
        check(values[f"decider_entries_{period}"] >= entries,
              f"ordinary decider coverage is incomplete {period}-menu")
        check(values[f"{period}_visible_frames"] >= (30 if period == "pre" else 60),
              f"too few semantic visible frames {period}-menu")
        check(values[f"{period}_visible_cells"]
              >= 360 * values[f"{period}_visible_frames"],
              f"visible-plane cell coverage is incomplete {period}-menu")
        check(values[f"{period}_material_cells"] > 0,
              f"no Stage-4 material cell was visible {period}-menu")
    check(values["helper_cache_misses_post"] >= 1,
          "no post-menu helper cache miss was observed")
    check(values["helper_cache_hits_menu"] == 0
          and values["helper_cache_misses_menu"] == 0,
          "helper cache comparison ran while the menu owned the plane")
    check(values["menu_visible_frames"] >= menu_hold,
          "native Window was not held for the required duration")
    check(values["menu_owned_frames"] >= values["menu_visible_frames"],
          "native menu ownership was shorter than Window visibility")
    check(values["ffe4_nonzero_frames"] > 0,
          "native FFE4 menu ownership was not observed")
    check(values["window_checked_cells"] == 120 * values["menu_visible_frames"],
          "6x20 Window coverage is incomplete")
    final_match = FINAL_STATE_RE.fullmatch(report.get("final_state", ""))
    check(final_match is not None, "final Stage-4 hardware state was not restored")
    if final_match is not None:
        lcdc = int(final_match.group(1), 16)
        check(lcdc & 0x80 != 0 and lcdc & 0x20 == 0,
              "final LCD is disabled or Window remains visible")
        expected_base = "9C00" if lcdc & 0x08 else "9800"
        check(final_match.group(6) == expected_base,
              "final active BG base disagrees with LCDC")
    check(report.get("rom_sha256") == EXPECTED_CANDIDATE_SHA256,
          "probe report binds another candidate")
    check(report.get("probe_sha256") == EXPECTED_PROBE_SHA256,
          "probe report identity differs from the verifier")
    check(report.get("transitions", "").find(":stage4:") >= 0,
          "transition log lacks Stage-4 entry")
    for phase in (":open:", ":menu:", ":close:", ":post:"):
        check(phase in report.get("transitions", ""),
              f"transition log lacks {phase[1:-1]}")
    snapshots, snapshot_failures = parse_key_snapshots(report)
    failures.extend(snapshot_failures)
    if not snapshot_failures:
        failures.extend(cache_lifecycle_failures(snapshots))
    return failures


def passing_report(frames: int = 3000, menu_hold: int = 80) -> dict[str, str]:
    report = {key: "0" for key in REPORT_INT_FIELDS}
    report.update({
        "status": "ok", "reason": "complete", "frames": "1100",
        "frame_limit": str(frames), "menu_hold": str(menu_hold),
        "target": "3", "expected_scene": "5", "stage_seen": "1",
        "install_seen": "1", "semantic_armed": "1",
        "menu_seen": "1", "menu_closed": "1",
        "stable_stage_frames": "500", "installed_context_frames": "480",
        "payload_checked_frames": "480", "stage_lut_checked_frames": "480",
        "decider_entries_pre": "40", "decider_entries_post": "50",
        "helper_entries_pre": "40", "helper_joins_pre": "40",
        "helper_entries_post": "50", "helper_joins_post": "50",
        "helper_cache_hits_pre": "38", "helper_cache_misses_pre": "2",
        "helper_cache_hits_post": "49", "helper_cache_misses_post": "1",
        "first_post_helper_forced_miss": "1",
        "first_post_helper_dirty_signal": "1",
        "post_repaint_compiler_entries": "1",
        "post_clean_after_repaint_frames": "100",
        "invalidator_entries": "90", "invalidator_menu_entries": "80",
        "invalidator_effect_hits": "80", "menu_zero_cache_frames": "80",
        "menu_owned_frames": "90", "menu_visible_frames": str(menu_hold),
        "ffe4_nonzero_frames": "88", "window_checked_cells": str(120 * menu_hold),
        "pre_visible_frames": "100", "pre_visible_cells": "36000",
        "pre_material_cells": "1200", "post_visible_frames": "120",
        "post_visible_cells": "43200", "post_material_cells": "1400",
        "final_state": (
            "scene:05,ffc1:01,stage:03,ffe4:00,lcdc:8B,wx:07,wy:90,"
            "scx:00,scy:00,vbk:00,svbk:01,ff55:FF,dad5:5D,dab7:EB,"
            "base:9C00,helper:0"
        ),
        "rom_sha256": EXPECTED_CANDIDATE_SHA256,
        "probe_sha256": EXPECTED_PROBE_SHA256,
        "verifier_sha256": "synthetic",
        "transitions": (
            "f1:stage4:05:01:03:00:8B;f2:open:05:01:03:00:8B;"
            "f3:menu:05:01:03:01:AB;f83:close:05:01:03:01:AB;"
            "f90:post:05:01:03:00:8B"
        ),
    })
    cache_by_tag = {
        "settled_pre": ("040201", "040201"),
        "open": ("040201", "040201"),
        "invalidation_effect": ("000201", "000201"),
        "menu": ("000201", "000201"),
        "first_post": ("040201", "000201"),
        "first_post_helper": ("000201", "000201"),
        "first_post_repaint": ("040201", "040201"),
        "final": ("040201", "040201"),
    }
    frames_by_tag = (100, 101, 102, 104, 184, 185, 186, 300)
    for tag, frame in zip(KEY_SNAPSHOT_TAGS, frames_by_tag, strict=True):
        cache53, cache57 = cache_by_tag[tag]
        helper_h = "9C" if tag in {
            "first_post_helper", "first_post_repaint", "final",
        } else "98"
        df_address = "DF57" if helper_h == "9C" else "DF53"
        selected = cache57 if helper_h == "9C" else cache53
        report[f"key_{tag}"] = (
            f"frame:{frame},cpu_h:{helper_h},helper_h:{helper_h},c1f1:04,"
            f"c2f1:02,room:01,df_addr:{df_address},df0:{selected[:2]},"
            f"df1:{selected[2:4]},df2:{selected[4:]},cache53:{cache53},"
            f"cache57:{cache57},known:{helper_h}/{df_address}/{selected}"
        )
    return report


def mutation_controls(source: str) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    source_mutations = {
        "stage_target": ("local TARGET = 3", "local TARGET = 4"),
        "stage_scene": ("local EXPECTED_SCENE = 0x05",
                        "local EXPECTED_SCENE = 0x06"),
        "helper_entry": ("local HELPER_ENTRY = 0xDB20",
                         "local HELPER_ENTRY = 0xDB21"),
        "helper_join": ("local HELPER_JOIN = 0xDA92",
                        "local HELPER_JOIN = 0xDA93"),
        "invalidator_entry": ("local INVALIDATOR_ENTRY = 0x6A40",
                              "local INVALIDATOR_ENTRY = 0x6A41"),
        "invalidator_effect": ("local INVALIDATOR_EFFECT = 0x6A54",
                               "local INVALIDATOR_EFFECT = 0x6A53"),
        "payload_end": ("local PAYLOAD_LAST = 0xDB3D",
                        "local PAYLOAD_LAST = 0xDB3C"),
        "trampoline_start": ("local TRAMPOLINE_FIRST = 0xDA5D",
                             "local TRAMPOLINE_FIRST = 0xDA5E"),
        "df_selector": (
            "local df_address = 0xDF00 + ((helper_h ~ 0xCB) & 0xFF)",
            "local df_address = 0xDF00 + ((helper_h ~ 0xCA) & 0xFF)",
        ),
        "pagepair_shortcut": (
            "frame, cpu_h, helper_h, emu:read8(0xC1F1), emu:read8(0xC2F1)",
            "frame, cpu_h, helper_h, emu:read8(0xC1F0), emu:read8(0xC2F1)",
        ),
        "window_alias": ("if base == bg_base then", "if base ~= bg_base then"),
        "stage_oracle": (
            "local wanted = string.byte(expected_stage_lut, tile + 1)",
            "local wanted = 0",
        ),
        "menu_oracle": (
            "local wanted = string.byte(expected_menu_lut, tiles[index] + 1)",
            "local wanted = 0",
        ),
        "breakpoint_positive_id": (
            'type(result) ~= "number" or result <= 0',
            'type(result) ~= "number"',
        ),
    }
    for name, (old, new) in source_mutations.items():
        require(old in source, f"mutation anchor missing: {name}")
        mutant = source.replace(old, new, 1)
        try:
            audit_probe_source(mutant, enforce_hash=False)
        except AssertionError:
            controls[f"mutated_probe_{name}_rejected"] = True
        else:
            controls[f"mutated_probe_{name}_rejected"] = False

    baseline = passing_report()
    require(not report_failures(baseline, frames=3000, menu_hold=80),
            "synthetic passing report does not pass")
    report_mutations: dict[str, tuple[str, str]] = {
        "payload": ("payload_mismatch_frames", "1"),
        "dad5": ("dad5_mismatch_frames", "1"),
        "dab7": ("dab7_mismatch_frames", "1"),
        "helper_menu": ("helper_entries_menu", "1"),
        "decider_menu": ("decider_entries_menu", "1"),
        "menu_tiles": ("window_tile_mismatch_cells", "1"),
        "menu_attrs": ("window_attr_mismatch_cells", "1"),
        "menu_alias": ("window_map_alias_frames", "1"),
        "post_trail": ("post_write_trail_cells", "1"),
        "post_material_absent": ("post_material_cells", "0"),
        "single_helper_pre": ("helper_entries_pre", "1"),
        "wrong_candidate": ("rom_sha256", "00" * 32),
        "missing_key_snapshot": ("key_menu", "missing"),
        "missing_invalidator_effect": ("invalidator_effect_hits", "0"),
        "nonzero_menu_cache": ("menu_cache_repopulation_frames", "1"),
        "first_post_stale_hit": ("first_post_helper_stale_hit", "1"),
        "missing_forced_miss": ("first_post_helper_forced_miss", "0"),
        "missing_repaint": ("post_repaint_compiler_entries", "0"),
        "duplicate_repaint": ("post_repaint_compiler_entries", "2"),
    }
    for name, (field, value) in report_mutations.items():
        mutant = dict(baseline)
        mutant[field] = value
        controls[f"mutated_report_{name}_rejected"] = bool(
            report_failures(mutant, frames=3000, menu_hold=80)
        )
    mutant = dict(baseline)
    mutant["key_invalidation_effect"] = mutant["key_invalidation_effect"].replace(
        "cache53:000201", "cache53:040201", 1,
    )
    controls["mutated_report_invalidator_cache_rejected"] = bool(
        report_failures(mutant, frames=3000, menu_hold=80)
    )
    mutant = dict(baseline)
    mutant["key_first_post_helper"] = (
        mutant["key_first_post_helper"]
        .replace("df0:00,df1:02,df2:01", "df0:04,df1:02,df2:01", 1)
        .replace("cache57:000201", "cache57:040201", 1)
        .replace("known:9C/DF57/000201", "known:9C/DF57/040201", 1)
    )
    controls["mutated_report_first_helper_clean_cache_rejected"] = bool(
        report_failures(mutant, frames=3000, menu_hold=80)
    )
    controls["mutated_candidate_identity_rejected"] = (
        sha256_bytes(CANDIDATE.read_bytes()[:-1]
                     + bytes([CANDIDATE.read_bytes()[-1] ^ 1]))
        != EXPECTED_CANDIDATE_SHA256
    )
    require(all(controls.values()),
            "one or more Stage-4 menu mutation controls escaped: "
            + repr([key for key, passed in controls.items() if not passed]))
    return controls


def identity() -> dict[str, str]:
    return {
        "candidate_sha256": sha256(CANDIDATE),
        "build_receipt_sha256": sha256(BUILD_RECEIPT),
        "builder_sha256": sha256(BUILDER),
        "probe_sha256": sha256(PROBE),
        "verifier_sha256": sha256(VERIFIER),
        "launcher_sha256": sha256(LAUNCHER),
        "singleflight_sha256": sha256(SINGLEFLIGHT),
        "menu_colorizer_sha256": sha256(MENU_COLORIZER),
    }


def build_static_receipt() -> dict[str, Any]:
    for path in (
        CANDIDATE, BUILD_RECEIPT, BUILDER, PROBE, VERIFIER, LAUNCHER,
        SINGLEFLIGHT, MENU_COLORIZER,
    ):
        require(path.is_file(), f"required gate dependency missing: {path}")
    identities = identity()
    expected = {
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "build_receipt_sha256": EXPECTED_BUILD_RECEIPT_SHA256,
        "builder_sha256": EXPECTED_BUILDER_SHA256,
        "probe_sha256": EXPECTED_PROBE_SHA256,
        "launcher_sha256": EXPECTED_LAUNCHER_SHA256,
        "singleflight_sha256": EXPECTED_SINGLEFLIGHT_SHA256,
        "menu_colorizer_sha256": EXPECTED_MENU_COLORIZER_SHA256,
    }
    for key, value in expected.items():
        require(identities[key] == value, f"identity changed: {key}")
    source = PROBE.read_text()
    return {
        "schema": "penta-stage4-select-roundtrip-r287-static-v1",
        "status": "STATIC_PASS_TWO_LIVE_REPLAYS_REQUIRED",
        "emulator_invoked": False,
        "candidate": audit_candidate(),
        "probe_contract": audit_probe_source(source),
        "identities": identities,
        "mutation_controls": mutation_controls(source),
        "live_contract": {
            "replays": 2,
            "parallel_emulators": 0,
            "entry": "cold boot through native GAME START and level selector",
            "stage": "FFC1=$01, D880=$05, FFBA=$03",
            "installed_runtime": (
                "DAD5=$5D, DAB7=$EB, DA5D-DA5F=C3 20 DB, and exact "
                "DB00-DB3D payload on every installed frame"
            ),
            "helper": "DB20->DA92 runs before and after, never during menu ownership",
            "invalidation": (
                "bank13:$6A40 executes under native bank13/FFE4 ownership; "
                "$6A54 proves DF53=DF57=0, and menu frames retain both zeros"
            ),
            "forced_repaint": (
                "the first post-menu DB20 helper consumes a zero cache, takes "
                "DAA9 miss, asserts FFE0 at DAB6, reaches the bank1:$42FC "
                "compiler, and is followed by a clean visible plane"
            ),
            "native_key_snapshots": (
                "settled-pre/open/invalidation/menu/first-post/helper/repaint/final "
                "bind C1F1, C2F1, helper H, DF[H XOR CB], DF53, and DF57"
            ),
            "menu": (
                "FFE4/Window owns an isolated 6x20 C4E0 plane whose attrs "
                "match the immutable private menu LUT"
            ),
            "gameplay": (
                "every pre/post visible attr equals the exact Stage4 "
                "material LUT; zero semantic write-trail cells"
            ),
            "determinism": "exact parsed report and all binary evidence hashes",
        },
        "decision": "STATIC_GO_FOR_TWO_SEQUENTIAL_SINGLE_FLIGHT_REPLAYS",
    }


def write_static_receipt(path: Path) -> tuple[dict[str, Any], str]:
    path = scratch_child(path, label="static receipt")
    receipt = build_static_receipt()
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    return receipt, sha256_bytes(payload.encode())


def validate_static_receipt(path: Path, expected_sha: str) -> dict[str, Any]:
    require(path.is_file(), f"static receipt missing: {path}")
    require(sha256(path) == expected_sha,
            "static receipt SHA differs from the command binding")
    receipt = json.loads(path.read_text())
    require(receipt.get("schema")
            == "penta-stage4-select-roundtrip-r287-static-v1",
            "wrong static receipt schema")
    require(receipt.get("status") == "STATIC_PASS_TWO_LIVE_REPLAYS_REQUIRED",
            "static Stage-4 menu audit is not green")
    require(receipt.get("emulator_invoked") is False,
            "static receipt unexpectedly claims emulator evidence")
    require(receipt.get("decision")
            == "STATIC_GO_FOR_TWO_SEQUENTIAL_SINGLE_FLIGHT_REPLAYS",
            "static receipt did not authorize the bounded live gate")
    require(receipt.get("identities") == identity(),
            "candidate or gate identity changed after static audit")
    require(receipt == build_static_receipt(),
            "static receipt is stale or was modified")
    return receipt


def stop_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def parse_final_state(raw: str) -> dict[str, int | str]:
    match = FINAL_STATE_RE.fullmatch(raw)
    require(match is not None, "cannot audit artifacts from invalid final state")
    return {
        "lcdc": int(match.group(1), 16),
        "wx": int(match.group(2), 16),
        "wy": int(match.group(3), 16),
        "scx": int(match.group(4), 16),
        "scy": int(match.group(5), 16),
        "base": match.group(6),
    }


def replay_artifact_paths(prefix: Path) -> dict[str, Path]:
    return {
        "payload": Path(str(prefix) + ".payload.bin"),
        "stage_lut": Path(str(prefix) + ".stage-lut.bin"),
        "menu_tiles": Path(str(prefix) + ".menu.tiles.bin"),
        "menu_hud": Path(str(prefix) + ".menu.hud.bin"),
        "menu_attrs": Path(str(prefix) + ".menu.attrs.bin"),
        "final_tiles": Path(str(prefix) + ".final.tiles.bin"),
        "final_attrs": Path(str(prefix) + ".final.attrs.bin"),
    }


def available_artifact_hashes(prefix: Path) -> dict[str, str]:
    return {
        name: sha256(path) for name, path in replay_artifact_paths(prefix).items()
        if path.is_file()
    }


def audit_replay_artifacts(prefix: Path, report: dict[str, str]) -> dict[str, Any]:
    paths = replay_artifact_paths(prefix)
    expected_sizes = {
        "payload": 0x3E, "stage_lut": 0x100,
        "menu_tiles": 120, "menu_hud": 120, "menu_attrs": 120,
        "final_tiles": 0x400, "final_attrs": 0x400,
    }
    for name, path in paths.items():
        require(path.is_file(), f"replay artifact missing: {name}")
        require(path.stat().st_size == expected_sizes[name],
                f"replay artifact has wrong size: {name}")
    payload = paths["payload"].read_bytes()
    runtime_lut = paths["stage_lut"].read_bytes()
    menu_tiles = paths["menu_tiles"].read_bytes()
    menu_hud = paths["menu_hud"].read_bytes()
    menu_attrs = paths["menu_attrs"].read_bytes()
    final_tiles = paths["final_tiles"].read_bytes()
    final_attrs = paths["final_attrs"].read_bytes()
    require(payload == PAYLOAD, "dumped DB00-DB3D differs from ROM payload")
    expected_stage = stage4_lut()
    require(runtime_lut == expected_stage, "dumped C600 is not exact Stage4 LUT")
    require(menu_tiles == menu_hud, "first visible Window differs from C4E0")
    canonical = region(CANDIDATE.read_bytes(), 13, 0x7000, 0x100)
    expected_menu = menu_lut(canonical)
    menu_mismatches = sum(
        attr != expected_menu[tile]
        for tile, attr in zip(menu_tiles, menu_attrs, strict=True)
    )
    require(menu_mismatches == 0,
            f"first visible Window has {menu_mismatches} palette mismatches")
    require(all(attr & 0xF8 == 0 for attr in menu_attrs),
            "first visible Window contains unsafe attribute bits")

    final = parse_final_state(report.get("final_state", ""))
    scx, scy = int(final["scx"]), int(final["scy"])
    columns = 20 if scx & 7 == 0 else 21
    rows = 18 if scy & 7 == 0 else 19
    first_col, first_row = scx >> 3, scy >> 3
    semantic_mismatches = 0
    material_cells = 0
    for row in range(rows):
        for col in range(columns):
            index = ((first_row + row) & 31) * 32 + ((first_col + col) & 31)
            tile, attr = final_tiles[index], final_attrs[index]
            semantic_mismatches += attr != expected_stage[tile]
            material_cells += tile in {*range(0x01, 0x09), 0x2D, 0x2E}
    require(semantic_mismatches == 0,
            f"final visible plane has {semantic_mismatches} semantic trails")
    require(material_cells > 0, "final visible plane lacks Stage4 material cells")
    return {
        "hashes": available_artifact_hashes(prefix),
        "payload_matches_rom": True,
        "stage_lut_exact": True,
        "first_window_tile_mismatches": 0,
        "first_window_attribute_mismatches": 0,
        "final_visible_semantic_mismatches": 0,
        "final_visible_material_cells": material_cells,
        "final_visible_cells": rows * columns,
    }


def run_replay(output: Path, args: argparse.Namespace) -> dict[str, Any]:
    output.mkdir()
    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(CANDIDATE, runtime_rom)
    require(sha256(runtime_rom) == EXPECTED_CANDIDATE_SHA256,
            "runtime candidate copy changed")
    payload_path = runtime / "stage4-wram-payload.bin"
    stage_lut_path = runtime / "stage4-lut.bin"
    menu_lut_path = runtime / "menu-window-lut.bin"
    payload_path.write_bytes(PAYLOAD)
    stage_lut_path.write_bytes(stage4_lut())
    canonical = region(CANDIDATE.read_bytes(), 13, 0x7000, 0x100)
    menu_lut_path.write_bytes(menu_lut(canonical))

    prefix = output / "stage4-menu"
    report_path = Path(str(prefix) + ".report")
    marker = Path(str(prefix) + ".done")
    emulator_log = output / "emulator.log"
    before = identity()
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE4_MENU_OUT": str(prefix),
        "STAGE4_MENU_PAYLOAD": str(payload_path),
        "STAGE4_MENU_STAGE_LUT": str(stage_lut_path),
        "STAGE4_MENU_WINDOW_LUT": str(menu_lut_path),
        "STAGE4_MENU_ROM_SHA256": EXPECTED_CANDIDATE_SHA256,
        "STAGE4_MENU_PROBE_SHA256": EXPECTED_PROBE_SHA256,
        "STAGE4_MENU_VERIFIER_SHA256": before["verifier_sha256"],
        "STAGE4_MENU_FRAMES": str(args.frames),
        "STAGE4_MENU_HOLD": str(args.menu_hold),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command = [
        str(LAUNCHER), "--fastforward", str(runtime_rom),
        "--script", str(PROBE), "-C", f"savegamePath={runtime}",
    ]
    timed_out = False
    completion = None
    with emulator_log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=ROOT, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + args.timeout
        try:
            while time.monotonic() < deadline:
                if marker.is_file():
                    value = marker.read_text().strip()
                    if value in {"ok", "fail"} and report_path.is_file():
                        completion = value
                        break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            else:
                timed_out = True
        finally:
            stop_owned_process(process)
    after = identity()
    failures: list[str] = []
    if timed_out:
        failures.append(f"replay timed out after {args.timeout:.1f}s")
    if process.returncode == 75:
        failures.append("single-flight emulator slot is already owned (exit 75)")
    if completion is None:
        failures.append("ordered Lua completion marker/report pair is missing")
    elif completion != "ok":
        failures.append("Lua probe reported failure")
    if before != after:
        failures.append("candidate or gate identity changed during replay")
    report: dict[str, str] = {}
    artifact_audit: dict[str, Any] | None = None
    key_snapshots: dict[str, Any] | None = None
    if report_path.is_file():
        try:
            report = parse_report(report_path)
        except AssertionError as error:
            failures.append(str(error))
        else:
            failures.extend(report_failures(
                report, frames=args.frames, menu_hold=args.menu_hold,
            ))
            key_snapshots, _snapshot_failures = parse_key_snapshots(report)
            if report.get("verifier_sha256") != before["verifier_sha256"]:
                failures.append("probe report binds another verifier")
            try:
                artifact_audit = audit_replay_artifacts(prefix, report)
            except AssertionError as error:
                failures.append(str(error))
                # Preserve deterministic evidence even when its semantic
                # content correctly fails the release gate.
                artifact_audit = {
                    "hashes": available_artifact_hashes(prefix),
                    "audit_status": "FAIL",
                    "audit_error": str(error),
                }
    else:
        failures.append("probe report is missing")
    return {
        "status": "PASS" if not failures else "FAIL",
        "path": relative(output),
        "identity_before": before,
        "identity_after": after,
        "runtime_candidate_sha256": sha256(runtime_rom),
        "return_code": process.returncode,
        "timed_out": timed_out,
        "completion": completion,
        "single_flight_busy": process.returncode == 75,
        "probe_report": report,
        "native_key_snapshots": key_snapshots,
        "artifacts": artifact_audit,
        "failures": failures,
    }


def determinism_checks(replays: list[dict[str, Any]]) -> dict[str, bool]:
    checks = {"two_replays": len(replays) == 2,
              "parsed_reports_exact": False,
              "binary_evidence_hashes_exact": False}
    if len(replays) != 2:
        return checks
    first, second = replays
    first_artifacts = first.get("artifacts")
    second_artifacts = second.get("artifacts")
    checks["parsed_reports_exact"] = (
        first.get("probe_report") == second.get("probe_report")
    )
    checks["binary_evidence_hashes_exact"] = (
        isinstance(first_artifacts, dict)
        and isinstance(second_artifacts, dict)
        and bool(first_artifacts.get("hashes"))
        and first_artifacts.get("hashes") == second_artifacts.get("hashes")
    )
    return checks


def run_live(args: argparse.Namespace) -> int:
    require(args.static_receipt is not None,
            "--run requires --static-receipt")
    require(args.static_receipt_sha is not None,
            "--run requires --static-receipt-sha")
    require(args.output is not None, "--run requires --output")
    static_receipt = validate_static_receipt(
        args.static_receipt.resolve(), args.static_receipt_sha,
    )
    output = scratch_child(args.output, label="live output")
    require(not output.exists(),
            f"live output already exists; choose a fresh directory: {output}")
    output.mkdir(parents=True)
    gate_before = identity()
    replays: list[dict[str, Any]] = []
    for replay_index in (1, 2):
        replay = run_replay(output / f"replay-{replay_index}", args)
        replays.append(replay)
        if replay["single_flight_busy"]:
            break
    failures = [
        f"replay-{index}: {failure}"
        for index, replay in enumerate(replays, 1)
        for failure in replay["failures"]
    ]
    deterministic = determinism_checks(replays)
    for name, passed in deterministic.items():
        if not passed:
            failures.append(f"determinism check failed: {name}")
    gate_after = identity()
    if gate_before != gate_after:
        failures.append("gate identities changed across the two replays")
    receipt = {
        "schema": "penta-stage4-select-roundtrip-r287-live-v1",
        "status": "PASS" if not failures else "FAIL",
        "candidate": relative(CANDIDATE),
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "static_receipt": relative(args.static_receipt.resolve()),
        "static_receipt_sha256": args.static_receipt_sha,
        "static_decision": static_receipt["decision"],
        "identity_before": gate_before,
        "identity_after": gate_after,
        "invocation": {
            "replays": 2,
            "frames": args.frames,
            "menu_hold": args.menu_hold,
            "timeout_per_replay": args.timeout,
            "single_flight_launcher": relative(LAUNCHER),
            "parallel_emulators": 0,
        },
        "replays": replays,
        "determinism": deterministic,
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if failures:
        print("FAIL: exact-r287 Stage-4 SELECT roundtrip gate")
        for failure in failures:
            print(f"  - {failure}")
        print(f"Receipt: {receipt_path}")
        return 1
    print("PASS: deterministic Stage-4 helper/menu invalidation on exact r287")
    print(f"Receipt: {receipt_path}")
    return 0


def parse_sha(raw: str) -> str:
    value = raw.lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise argparse.ArgumentTypeError("SHA-256 must be 64 hexadecimal digits")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--static-output", type=Path, default=DEFAULT_STATIC_OUTPUT)
    parser.add_argument("--static-receipt", type=Path)
    parser.add_argument("--static-receipt-sha", type=parse_sha)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--menu-hold", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    require(1200 <= args.frames <= 6000, "--frames must be 1200..6000")
    require(40 <= args.menu_hold <= 600, "--menu-hold must be 40..600")
    if args.static_only:
        receipt, receipt_sha = write_static_receipt(args.static_output)
        print("STATIC GO: two sequential single-flight Stage-4 menu replays")
        print(f"Receipt: {args.static_output.resolve()}")
        print(f"Receipt SHA-256: {receipt_sha}")
        print("Candidate: " + receipt["candidate"]["candidate_sha256"])
        print("Live command:")
        print(
            "python3 scripts/diagnostics/verify_stage4_select_roundtrip_r287.py "
            f"--run --static-receipt {relative(args.static_output.resolve())} "
            f"--static-receipt-sha {receipt_sha} "
            "--output tmp/stage4-menu-exit-invalidation-r287/menu-roundtrip-live-r2"
        )
        return 0
    return run_live(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
