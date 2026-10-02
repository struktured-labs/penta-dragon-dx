#!/usr/bin/env python3
"""Bind Stage-1 hardware OAM, OBJ CRAM, and referenced OBJ CHR.

The existing Stage-1 visual gates authenticate background maps, attributes,
BG CRAM, and BG CHR.  Their OAM metadata is only a raster-exclusion rectangle,
while the older gameplay OBJ check grades only palette bits for selected enemy
tile ranges.  This verifier closes the remaining sprite-side gap on the exact
scene-$0B native SELECT route:

* every geometrically visible hardware-OAM entry is checked against the
  production semantic palette policy (including Sara, miniboss, and fixed
  slot-31 rules);
* all 64 hardware OBJ-CRAM bytes are compared with a hash-pinned, independently
  reconstructed deck on every sampled frame; and
* every physical OBJ pattern referenced by visible OAM is compared with the
  exact tile-ID destination in the reviewed scene-$0B OBJ page.  That page is
  independently reconstructed from the two narrow, hash-pinned ROM source
  spans loaded by this route.  Stage 1 may not select OBJ VRAM bank one.

``--run`` is the only mode that starts an emulator.  It always uses the
checked-in project-wide single-flight launcher and the reviewed operator
capture; there is no executable override.  ``--trace`` performs only the
offline binding step and is useful for mutation tests.  ``--receipt`` strictly
revalidates durable live evidence without starting an emulator.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
import zlib


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

from build_v301_teleport import build_obj_pal_table  # noqa: E402
from normalize_mgba_state_pc import normalize, retarget_rom_identity  # noqa: E402
from verify_stage1_scene0b_captured_menu_receipt import (  # noqa: E402
    gbas_payload,
)


SCHEMA = "penta-stage1-obj-visual-contract-v1"
TRACE_HEADER = (
    "sample\tframe\tphase\tphase_frame\tscene\tactive\troom\tmenu_owned"
    "\tffe4\tlcdc\tffbe\tffbf\tffc0\tffd0\tdf04\tobj_cram"
    "\tvisible_oam"
)
ROM_SIZE = 0x80000

PROBE = DIAGNOSTICS / "probe_stage1_obj_visual_contract.lua"
LAUNCHER = ROOT / "scripts" / "mgba-qt-singleflight"
SINGLEFLIGHT_IMPLEMENTATION = ROOT / "scripts" / "mgba_singleflight.py"
PROCESS_CHECK = ROOT / "scripts" / "check_emulator_processes.sh"
STATE_RETARGETER = DIAGNOSTICS / "normalize_mgba_state_pc.py"
CAPTURE_BINDER = DIAGNOSTICS / "verify_stage1_scene0b_captured_menu_receipt.py"
OBJ_LUT_BUILDER = ROOT / "scripts" / "build_v301_teleport.py"
OBJ_LUT_SOURCE = ROOT / "palettes" / "monster_palette_map.yaml"
OPERATOR_CAPTURE = ROOT / "save_states_for_claude/rc11_corrupted-walls.ss0"
OPERATOR_CAPTURE_SHA256 = (
    "052f2a9e7a80fc9073bf3fd452a0985a007c77afd54078274ad6408ea4010f15"
)
OPERATOR_GBAS_SHA256 = (
    "5f80b932414a73e8c252331a35069a47996508c219c04e9a7b670e8706c20716"
)

# The exact operator-state OBJ page maps physical tile IDs $00-$7F directly to
# two narrow ROM loader sources: $00-$2F are the first $300 bytes of the Sara /
# effects sheet and $30-$7F are the first $500 bytes of the Gargoyle sheet.
# These are byte-for-byte concatenated in physical VRAM.  Their hashes prove
# the reviewed split in the operator fixture; a candidate is checked at the
# exact source offset only for tile IDs referenced by visible OAM.
SARA_OBJ_SOURCE_OFFSET = 0x20000
SARA_OBJ_SOURCE_SIZE = 0x300
SARA_OBJ_SOURCE_SHA256 = (
    "06b9a44a1e51c5bc5266ded11fb834735996fe13fc514b62d241fddc05d248b8"
)
GARGOYLE_OBJ_SOURCE_OFFSET = 0x24000
GARGOYLE_OBJ_SOURCE_SIZE = 0x500
GARGOYLE_OBJ_SOURCE_SHA256 = (
    "183750614a76ca4c6800a4b272f515e054ab99a09eeded523f7b92e59ee8921e"
)
GBAS_VRAM_BANK0_OFFSET = 0x400
SCENE0B_VISIBLE_OBJ_PAGE_SIZE = 0x800
SCENE0B_VISIBLE_OBJ_PAGE_SHA256 = (
    "e69e6d8861b2f8e73e40f08ee65fc5c130285e7852fbc6ca40a05c8fccd95c1b"
)

# Candidate palette sources in bank 13.  The primary span contains base OBJ0-
# OBJ7, all eight boss rows, and the boss destination-slot table.  The variant
# span contains Sara jet rows plus Spiral/Shield/Turbo OBJ0 rows.
OBJ_PRIMARY_OFFSET = 13 * 0x4000 + (0x6840 - 0x4000)
OBJ_PRIMARY_SIZE = 0x88
OBJ_PRIMARY_SHA256 = (
    "ff4d1f2a2233c1f3498559d3f85c9df2a02c441ecb23b7394a1a741e38d0a49b"
)
OBJ_VARIANT_OFFSET = 13 * 0x4000 + (0x68D0 - 0x4000)
OBJ_VARIANT_SIZE = 0x28
OBJ_VARIANT_SHA256 = (
    "9fb3f897c3207debcfcd76ae4b938bbb3798fb6529793ede23f3aa640c3955e7"
)

# The gameplay LUT is generated into WRAM rather than retained as a static ROM
# page in current builds.  Pin the compiler output itself, then use it only as
# an independent semantic oracle for hardware OAM.
OBJ_LUT_SHA256 = (
    "80cb44eeec1bb057843d926be668076b26386ba131fce2c1b0b16cde00a2e384"
)

PHASE_ORDER = (
    "baseline", "menu_entry", "menu_hold", "menu_exit", "post_close",
)
PHASE_MINIMUMS = {
    "baseline": 12,
    "menu_entry": 1,
    "menu_hold": 60,
    "menu_exit": 1,
    "post_close": 60,
}
FRAME_LIMIT = 720
RUN_TIMEOUT_SECONDS = 60.0

CORE_RECEIPT_KEYS = frozenset({
    "schema", "status", "candidate", "candidate_sha256", "candidate_size",
    "trace", "trace_sha256", "samples", "phase_samples",
    "visible_oam_entries", "referenced_obj_patterns",
    "referenced_obj_loader_source_patterns",
    "unique_referenced_obj_patterns", "sara_oam_entries",
    "sara_priority_entries",
    "gargoyle_oam_entries", "obj_cram_mismatch_frames",
    "oam_palette_mismatches", "obj_bank1_entries",
    "obj_pattern_mismatches", "obj_loader_source_pattern_mismatches",
    "reviewed_sara_obj_loader_span_sha256",
    "reviewed_gargoyle_obj_loader_span_sha256",
    "scene0b_visible_obj_page_sha256",
    "obj_primary_palette_authority_sha256",
    "obj_variant_palette_authority_sha256", "semantic_obj_lut_sha256",
    "semantic_fingerprint", "checks",
})
LIVE_RECEIPT_EXTRA_KEYS = frozenset({
    "source_candidate", "source_candidate_sha256", "runtime_candidate",
    "runtime_candidate_sha256", "operator_state", "startup_marker",
    "startup_marker_sha256", "core_ready_marker",
    "core_ready_marker_sha256", "producer_report",
    "producer_report_sha256", "completion_marker",
    "completion_marker_sha256", "launch_contract",
    "launch_contract_sha256", "emulator_log", "emulator_log_sha256",
    "tool_identity", "controlled_teardown", "launch_started_at_ns",
    "bound_at_ns",
})
LIVE_RECEIPT_KEYS = CORE_RECEIPT_KEYS | LIVE_RECEIPT_EXTRA_KEYS
RETARGET_KEYS = frozenset({
    "source", "source_sha256", "source_gbAs_sha256", "retargeted",
    "retargeted_sha256", "retargeted_gbAs_sha256", "candidate_crc32",
    "changed_gbAs_offsets", "normalization_writes", "vram_injection_bytes",
})
TOOL_IDENTITY_KEYS = frozenset({
    "probe_sha256", "launcher_sha256",
    "singleflight_implementation_sha256", "state_retargeter_sha256",
    "capture_binder_sha256", "obj_lut_builder_sha256",
    "obj_lut_source_sha256", "emulator_path", "emulator_sha256",
    "verifier_sha256", "raw_vram_bank0_only", "emulator_override",
    "obj_cram_data_writes", "obj_cram_index_write_sites",
    "obj_cram_index_restored",
})
TEARDOWN_KEYS = frozenset({
    "exact_child_terminated", "termination_method", "return_code",
})
LAUNCH_KEYS = frozenset({
    "schema", "command", "cwd", "candidate", "candidate_sha256",
    "source_candidate", "source_candidate_sha256", "startup_token_sha256",
    "launch_started_at_ns", "frame_limit", "timeout_seconds", "retarget",
    "tool_identity", "probe_environment",
})
PROBE_ENVIRONMENT_KEYS = frozenset({
    "QT_QPA_PLATFORM", "SDL_AUDIODRIVER", "PENTA_STAGE1_OBJ_OUT",
    "PENTA_STAGE1_OBJ_STATE", "PENTA_STAGE1_OBJ_FRAME_LIMIT",
    "PENTA_STAGE1_OBJ_BASELINE_FRAMES", "PENTA_STAGE1_OBJ_MENU_HOLD_FRAMES",
    "PENTA_STAGE1_OBJ_POST_CLOSE_FRAMES",
})
REPORT_KEYS = frozenset({
    "status", "reason", "startup_token", "frames", "samples",
    "menu_open_events", "menu_close_events", "samples_baseline",
    "samples_menu_entry", "samples_menu_hold", "samples_menu_exit",
    "samples_post_close", "obj_cram_domain_samples",
    "obj_cram_index_samples", "obj_cram_restore_failures",
})


class ObjVisualError(RuntimeError):
    """A fail-closed Stage-1 OBJ contract violation."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ObjVisualError(message)


def exact_keys(value: Any, expected: frozenset[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} is not an object")
    actual = set(value)
    require(actual == set(expected),
            f"{label} fields changed; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}")


def scratch_descendant(path: Path, label: str) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in roots
    ), f"{label} must be below repo tmp/ or /mnt/data/tmp/")
    return resolved


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    def reject_constant(value: str) -> None:
        raise ObjVisualError(f"{label} contains non-finite number {value}")
    try:
        value = json.loads(path.read_text(), parse_constant=reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ObjVisualError(f"{label} is not valid JSON: {error}") from error
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def json_exact_equal(first: Any, second: Any) -> bool:
    """Compare JSON values without Python's bool/int or int/float coercion."""
    return json.dumps(
        first, sort_keys=True, separators=(",", ":")
    ) == json.dumps(second, sort_keys=True, separators=(",", ":"))


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_hex(value: str, length: int, label: str) -> bytes:
    require(len(value) == length * 2,
            f"{label} has {len(value) // 2} bytes, expected {length}")
    try:
        payload = bytes.fromhex(value)
    except ValueError as error:
        raise ObjVisualError(f"{label} is not hexadecimal") from error
    require(len(payload) == length, f"{label} decoded to the wrong size")
    return payload


def candidate_contract(candidate: bytes) -> dict[str, Any]:
    """Authenticate candidate-independent OBJ art and palette authorities."""
    require(len(candidate) == ROM_SIZE,
            f"candidate is {len(candidate)} bytes, expected {ROM_SIZE}")
    primary = candidate[
        OBJ_PRIMARY_OFFSET:OBJ_PRIMARY_OFFSET + OBJ_PRIMARY_SIZE
    ]
    variants = candidate[
        OBJ_VARIANT_OFFSET:OBJ_VARIANT_OFFSET + OBJ_VARIANT_SIZE
    ]
    require(sha256_bytes(primary) == OBJ_PRIMARY_SHA256,
            "candidate OBJ base/boss palette authority changed")
    require(sha256_bytes(variants) == OBJ_VARIANT_SHA256,
            "candidate OBJ variant palette authority changed")
    lut = build_obj_pal_table()
    require(len(lut) == 0x100 and sha256_bytes(lut) == OBJ_LUT_SHA256,
            "compiled semantic OBJ LUT differs from the reviewed YAML output")
    require(sha256(OPERATOR_CAPTURE) == OPERATOR_CAPTURE_SHA256,
            "reviewed scene-$0B operator capture hash changed")
    operator_state = gbas_payload(OPERATOR_CAPTURE)
    require(sha256_bytes(operator_state) == OPERATOR_GBAS_SHA256,
            "reviewed scene-$0B serialized machine state changed")
    operator_obj_page = operator_state[
        GBAS_VRAM_BANK0_OFFSET:
        GBAS_VRAM_BANK0_OFFSET + SCENE0B_VISIBLE_OBJ_PAGE_SIZE
    ]
    require(len(operator_obj_page) == SCENE0B_VISIBLE_OBJ_PAGE_SIZE
            and sha256_bytes(operator_obj_page)
            == SCENE0B_VISIBLE_OBJ_PAGE_SHA256,
            "reviewed scene-$0B physical OBJ page changed")
    require(sha256_bytes(
        operator_obj_page[:SARA_OBJ_SOURCE_SIZE]
    ) == SARA_OBJ_SOURCE_SHA256,
            "reviewed Sara OBJ loader split changed")
    require(sha256_bytes(
        operator_obj_page[
            SARA_OBJ_SOURCE_SIZE:
            SARA_OBJ_SOURCE_SIZE + GARGOYLE_OBJ_SOURCE_SIZE
        ]
    ) == GARGOYLE_OBJ_SOURCE_SHA256,
            "reviewed Gargoyle OBJ loader split changed")
    return {
        "obj_page": operator_obj_page,
        "primary": primary,
        "variants": variants,
        "lut": lut,
    }


def obj_loader_source_offset(physical_tile: int) -> int:
    """Map a reviewed physical scene-$0B tile to its exact ROM source."""
    require(0 <= physical_tile < 0x80,
            f"physical OBJ tile ${physical_tile:02X} has no reviewed source")
    if physical_tile < 0x30:
        return SARA_OBJ_SOURCE_OFFSET + physical_tile * 16
    return GARGOYLE_OBJ_SOURCE_OFFSET + (physical_tile - 0x30) * 16


def expected_obj_cram(
    contract: Mapping[str, Any], *, ffbf: int, ffc0: int, ffd0: int,
) -> bytes:
    """Reconstruct the phased loader's final 64-byte OBJ deck."""
    primary = contract["primary"]
    variants = contract["variants"]
    deck = bytearray(primary[:0x40])

    # OBJ0 projectile/power-up variant.
    if ffc0:
        source = 0x10 if ffc0 == 1 else 0x18 if ffc0 == 2 else 0x20
        deck[0:8] = variants[source:source + 8]

    # FFD0==1 selects the two form-specific jet rows already resident in ROM.
    if ffd0 == 1:
        deck[8:16] = variants[8:16]   # Sara Dragon jet
        deck[16:24] = variants[0:8]   # Sara Witch jet

    if ffbf:
        boss_index = (ffbf - 1) & 0x07
        boss_source = 0x40 + boss_index * 8
        slot = primary[0x80 + boss_index]
        require(slot in (6, 7), "reviewed boss OBJ slot escaped 6/7")
        deck[slot * 8:slot * 8 + 8] = primary[
            boss_source:boss_source + 8
        ]
    return bytes(deck)


def expected_oam_palette(
    contract: Mapping[str, Any], *, slot: int, tile: int,
    ffbe: int, ffbf: int,
) -> int:
    """Return the semantic emitter's expected CGB OBJ palette index."""
    # Native fixed slot 31 bypasses the semantic emitter and is patched to
    # OBJ4 at its exact stock write site.
    if slot == 31 and tile == 0x1D:
        return 4
    # Active miniboss selectors replace all five animation pages $30-$7F.
    if ffbf and 0x30 <= tile < 0x80:
        return ((ffbf - 1) & 0x01) + 6
    expected = contract["lut"][tile]
    if expected == 0xFF:
        return 2 if ffbe == 0 else 1
    require(0 <= expected <= 7,
            f"semantic OBJ LUT has invalid tile ${tile:02X} value")
    return expected


def parse_visible_oam(value: str, lcdc: int, sample: int) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_slots: set[int] = set()
    sprite_8x16 = bool(lcdc & 0x04)
    pattern_bytes = 32 if sprite_8x16 else 16
    height = 16 if sprite_8x16 else 8
    if not value:
        return result
    for raw in value.split(";"):
        parts = raw.split(",", 5)
        require(len(parts) == 6,
                f"sample {sample} has malformed visible-OAM entry")
        try:
            slot, y, x, tile, attr = (int(item) for item in parts[:5])
        except ValueError as error:
            raise ObjVisualError(
                f"sample {sample} visible-OAM scalar is not decimal"
            ) from error
        require(0 <= slot < 40 and slot not in seen_slots,
                f"sample {sample} has invalid/duplicate OAM slot {slot}")
        require(all(0 <= item <= 0xFF for item in (y, x, tile, attr)),
                f"sample {sample} OAM slot {slot} byte escaped 0..255")
        left, top = x - 8, y - 16
        require(left < 160 and left + 8 > 0
                and top < 144 and top + height > 0,
                f"sample {sample} OAM slot {slot} is not visible")
        patterns = parse_hex(
            parts[5], pattern_bytes,
            f"sample {sample} OAM slot {slot} referenced CHR",
        )
        seen_slots.add(slot)
        result.append({
            "slot": slot, "y": y, "x": x, "tile": tile, "attr": attr,
            "patterns": patterns,
        })
    require([row["slot"] for row in result] == sorted(seen_slots),
            f"sample {sample} visible OAM is not slot ordered")
    return result


def parse_trace(path: Path) -> list[dict[str, Any]]:
    require(path.is_file(), f"OBJ trace is missing: {path}")
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ObjVisualError(f"OBJ trace is unreadable: {error}") from error
    require(lines and lines[0] == TRACE_HEADER,
            "OBJ trace header/schema changed")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines[1:], 2):
        fields = line.split("\t")
        require(len(fields) == 17,
                f"OBJ trace line {line_number} has {len(fields)} fields")
        try:
            numbers = [int(value) for value in fields[:2]]
            numbers.extend(int(value) for value in fields[3:15])
        except ValueError as error:
            raise ObjVisualError(
                f"OBJ trace line {line_number} has a non-decimal scalar"
            ) from error
        (
            sample, frame, phase_frame, scene, active, room, menu_owned,
            ffe4, lcdc, ffbe, ffbf, ffc0, ffd0, df04,
        ) = numbers
        phase = fields[2]
        require(phase in PHASE_ORDER,
                f"sample {sample} has unknown phase {phase!r}")
        require(menu_owned in (0, 1),
                f"sample {sample} has non-boolean menu ownership")
        for label, value in (
            ("scene", scene), ("active", active), ("room", room),
            ("FFE4", ffe4),
            ("LCDC", lcdc), ("FFBE", ffbe), ("FFBF", ffbf),
            ("FFC0", ffc0), ("FFD0", ffd0), ("DF04", df04),
        ):
            require(0 <= value <= 0xFF,
                    f"sample {sample} {label} escaped one byte")
        cram = parse_hex(fields[15], 64, f"sample {sample} OBJ CRAM")
        rows.append({
            "sample": sample, "frame": frame, "phase": phase,
            "phase_frame": phase_frame, "scene": scene, "active": active,
            "room": room, "menu_owned": menu_owned, "ffe4": ffe4,
            "lcdc": lcdc,
            "ffbe": ffbe, "ffbf": ffbf, "ffc0": ffc0, "ffd0": ffd0,
            "df04": df04, "obj_cram": cram,
            "visible_oam": parse_visible_oam(fields[16], lcdc, sample),
        })
    require(rows, "OBJ trace contains no samples")
    return rows


def _phase_runs(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    result: list[str] = []
    for row in rows:
        if not result or result[-1] != row["phase"]:
            result.append(row["phase"])
    return result


def bind_trace(candidate_path: Path, trace_path: Path) -> dict[str, Any]:
    """Offline, fail-closed binding of a durable producer trace."""
    candidate_path = candidate_path.resolve()
    trace_path = trace_path.resolve()
    require(candidate_path.is_file(), f"candidate is missing: {candidate_path}")
    candidate = candidate_path.read_bytes()
    contract = candidate_contract(candidate)
    rows = parse_trace(trace_path)

    require([row["sample"] for row in rows] == list(range(1, len(rows) + 1)),
            "OBJ trace sample IDs are not contiguous from one")
    require(all(first["frame"] < second["frame"]
                for first, second in zip(rows, rows[1:])),
            "OBJ trace frames are not strictly increasing")
    require(_phase_runs(rows) == list(PHASE_ORDER),
            "OBJ trace did not traverse the exact native menu phase order")

    counts = Counter(row["phase"] for row in rows)
    for phase, minimum in PHASE_MINIMUMS.items():
        require(counts[phase] >= minimum,
                f"OBJ trace has {counts[phase]} {phase} samples; need {minimum}")
    for phase in PHASE_ORDER:
        phase_rows = [row for row in rows if row["phase"] == phase]
        require(phase_rows[0]["phase_frame"] >= 1
                and all(first["phase_frame"] < second["phase_frame"]
                        for first, second in zip(phase_rows, phase_rows[1:])),
                f"OBJ trace {phase} phase-frame sequence is not increasing")

    require(all(row["scene"] == 0x0B and row["active"] == 0x01
                and row["room"] == 0x07
                for row in rows),
            "OBJ route left active scene-$0B room $07")
    require(all((row["lcdc"] & 0x83) == 0x83 for row in rows),
            "OBJ route changed required LCD/BG/OBJ display bits")
    # The selected operator fixture is specifically Gargoyle scene-$0B.  Keep
    # that identity fixed so the gate really exercises boss LUT/CRAM override.
    require(all(row["ffbe"] == 0 and row["ffbf"] == 1
                and row["ffc0"] == 0 and row["ffd0"] == 0 for row in rows),
            "OBJ route lost the reviewed Witch/Gargoyle/no-powerup identity")

    baseline = [row for row in rows if row["phase"] == "baseline"]
    entry = [row for row in rows if row["phase"] == "menu_entry"]
    hold = [row for row in rows if row["phase"] == "menu_hold"]
    exit_rows = [row for row in rows if row["phase"] == "menu_exit"]
    post = [row for row in rows if row["phase"] == "post_close"]
    require(all(row["menu_owned"] == 0 for row in baseline + post),
            "closed-menu OBJ phases report menu ownership")
    require(all(row["menu_owned"] == 1 for row in hold),
            "menu-hold OBJ phase lost ownership")
    require({row["menu_owned"] for row in entry} == {0, 1},
            "menu-entry OBJ evidence lacks one side of the native edge")
    require({row["menu_owned"] for row in exit_rows} == {0, 1},
            "menu-exit OBJ evidence lacks one side of the native edge")

    cram_mismatch_frames = 0
    palette_mismatches = 0
    bank1_entries = 0
    pattern_mismatches = 0
    source_pattern_mismatches = 0
    visible_entries = 0
    referenced_patterns = 0
    referenced_source_patterns = 0
    sara_entries = 0
    sara_priority_entries = 0
    boss_entries = 0
    phases_with_oam: set[str] = set()
    unique_patterns: set[str] = set()
    first_failures: list[str] = []
    obj_page = contract["obj_page"]

    for row in rows:
        expected_cram = expected_obj_cram(
            contract, ffbf=row["ffbf"], ffc0=row["ffc0"], ffd0=row["ffd0"],
        )
        if row["obj_cram"] != expected_cram:
            cram_mismatch_frames += 1
            if len(first_failures) < 16:
                differences = [
                    index for index, pair in enumerate(zip(
                        row["obj_cram"], expected_cram, strict=True
                    )) if pair[0] != pair[1]
                ]
                first_failures.append(
                    f"sample {row['sample']} OBJ CRAM bytes {differences[:8]}"
                )
        if row["visible_oam"]:
            phases_with_oam.add(row["phase"])
        visible_entries += len(row["visible_oam"])
        for obj in row["visible_oam"]:
            tile, attr, slot = obj["tile"], obj["attr"], obj["slot"]
            actual_palette = attr & 0x07
            expected_palette = expected_oam_palette(
                contract, slot=slot, tile=tile,
                ffbe=row["ffbe"], ffbf=row["ffbf"],
            )
            if actual_palette != expected_palette:
                palette_mismatches += 1
                if len(first_failures) < 16:
                    first_failures.append(
                        f"sample {row['sample']} slot {slot} tile {tile:02X} "
                        f"palette {actual_palette}!={expected_palette}"
                    )
            if attr & 0x08:
                bank1_entries += 1
                if len(first_failures) < 16:
                    first_failures.append(
                        f"sample {row['sample']} slot {slot} selected OBJ bank 1"
                    )
            if 0x10 <= tile <= 0x2F:
                sara_entries += 1
                if slot < 4 and attr & 0x80:
                    sara_priority_entries += 1
                    if len(first_failures) < 16:
                        first_failures.append(
                            f"sample {row['sample']} Sara slot {slot} tile "
                            f"{tile:02X} exposes BG through priority attr "
                            f"{attr:02X}"
                        )
            if 0x30 <= tile < 0x80:
                boss_entries += 1
            patterns = obj["patterns"]
            physical_tile = tile if len(patterns) == 16 else tile & 0xFE
            tile_count = len(patterns) // 16
            out_of_page = physical_tile + tile_count > 0x80
            if out_of_page:
                if len(first_failures) < 16:
                    first_failures.append(
                        f"sample {row['sample']} slot {slot} tile {tile:02X} "
                        "escaped the exact scene-$0B OBJ page"
                    )
                expected_patterns = bytes(len(patterns))
            else:
                expected_patterns = obj_page[
                    physical_tile * 16:
                    (physical_tile + tile_count) * 16
                ]
            for offset in range(0, len(patterns), 16):
                pattern = patterns[offset:offset + 16]
                referenced_patterns += 1
                unique_patterns.add(sha256_bytes(pattern))
                expected_pattern = expected_patterns[offset:offset + 16]
                referenced_tile = physical_tile + offset // 16
                if not out_of_page:
                    source_offset = obj_loader_source_offset(referenced_tile)
                    source_pattern = candidate[
                        source_offset:source_offset + 16
                    ]
                    referenced_source_patterns += 1
                    if source_pattern != expected_pattern:
                        source_pattern_mismatches += 1
                        if len(first_failures) < 16:
                            first_failures.append(
                                f"sample {row['sample']} slot {slot} physical "
                                f"tile {referenced_tile:02X} candidate source "
                                f"${source_offset:05X} differs from exact page"
                            )
                if out_of_page or pattern != expected_pattern:
                    pattern_mismatches += 1
                    if len(first_failures) < 16:
                        first_failures.append(
                            f"sample {row['sample']} slot {slot} physical tile "
                            f"{physical_tile + offset // 16:02X} pattern "
                            f"{sha256_bytes(pattern)[:12]}!=exact "
                            f"{sha256_bytes(expected_pattern)[:12]}"
                        )

    require(cram_mismatch_frames == 0,
            f"OBJ CRAM differs on {cram_mismatch_frames} frames: "
            + "; ".join(first_failures))
    require(palette_mismatches == 0,
            f"visible hardware OAM has {palette_mismatches} semantic palette "
            f"mismatches: " + "; ".join(first_failures))
    require(bank1_entries == 0,
            f"visible Stage-1 OAM selected OBJ bank 1 {bank1_entries} times: "
            + "; ".join(first_failures))
    require(pattern_mismatches == 0,
            f"visible OAM referenced {pattern_mismatches} wrong physical "
            f"tile-ID CHR patterns: " + "; ".join(first_failures))
    require(source_pattern_mismatches == 0,
            f"visible OAM referenced {source_pattern_mismatches} wrong exact "
            f"candidate OBJ loader-source patterns: "
            + "; ".join(first_failures))
    require(visible_entries > 0 and referenced_patterns > 0,
            "OBJ route did not exercise visible hardware OAM/CHR")
    require(referenced_source_patterns == referenced_patterns,
            "not every visible OAM pattern resolved to a reviewed ROM source")
    require(sara_entries > 0, "OBJ route did not exercise dynamic Sara OAM")
    require(
        sara_priority_entries == 0,
        f"visible Sara OAM set floor-through priority bit 7 "
        f"{sara_priority_entries} times: " + "; ".join(first_failures),
    )
    require(boss_entries > 0,
            "OBJ route did not exercise the Gargoyle OBJ override")
    require(phases_with_oam == set(PHASE_ORDER),
            "visible OAM was absent from one or more menu phases")

    semantic_rows = [
        {
            "sample": row["sample"], "frame": row["frame"],
            "phase": row["phase"], "menu_owned": row["menu_owned"],
            "obj_cram_sha256": sha256_bytes(row["obj_cram"]),
            "oam": [
                {
                    "slot": obj["slot"], "y": obj["y"], "x": obj["x"],
                    "tile": obj["tile"], "attr": obj["attr"],
                    "patterns_sha256": sha256_bytes(obj["patterns"]),
                }
                for obj in row["visible_oam"]
            ],
        }
        for row in rows
    ]
    semantic_fingerprint = sha256_bytes(json.dumps(
        semantic_rows, sort_keys=True, separators=(",", ":")
    ).encode())
    checks = {
        "reviewed Sara/Gargoyle OBJ loader split is independently hash-pinned": True,
        "reviewed scene-$0B physical OBJ page is independently hash-pinned": True,
        "candidate OBJ palette authorities are independently hash-pinned": True,
        "compiled semantic OBJ LUT is independently hash-pinned": True,
        "exact native SELECT phase order and both transition edges observed": True,
        "active Gargoyle scene-$0B identity remains fixed": True,
        "all 64 OBJ CRAM bytes are exact on every sampled frame": True,
        "every visible hardware-OAM palette is semantically exact": True,
        "visible Stage-1 OAM never selects OBJ VRAM bank one": True,
        "every visible tile ID maps to its exact candidate loader source": True,
        "every visible tile ID resolves to its exact loader destination pattern": True,
        "Sara and Gargoyle override paths are both exercised": True,
        "visible Sara OAM never exposes BG through priority bit 7": True,
    }
    return {
        "schema": SCHEMA,
        "status": "pass",
        "candidate": str(candidate_path),
        "candidate_sha256": sha256_bytes(candidate),
        "candidate_size": len(candidate),
        "trace": str(trace_path),
        "trace_sha256": sha256(trace_path),
        "samples": len(rows),
        "phase_samples": dict(sorted(counts.items())),
        "visible_oam_entries": visible_entries,
        "referenced_obj_patterns": referenced_patterns,
        "referenced_obj_loader_source_patterns": referenced_source_patterns,
        "unique_referenced_obj_patterns": len(unique_patterns),
        "sara_oam_entries": sara_entries,
        "sara_priority_entries": sara_priority_entries,
        "gargoyle_oam_entries": boss_entries,
        "obj_cram_mismatch_frames": cram_mismatch_frames,
        "oam_palette_mismatches": palette_mismatches,
        "obj_bank1_entries": bank1_entries,
        "obj_pattern_mismatches": pattern_mismatches,
        "obj_loader_source_pattern_mismatches": source_pattern_mismatches,
        "reviewed_sara_obj_loader_span_sha256": SARA_OBJ_SOURCE_SHA256,
        "reviewed_gargoyle_obj_loader_span_sha256": GARGOYLE_OBJ_SOURCE_SHA256,
        "scene0b_visible_obj_page_sha256": SCENE0B_VISIBLE_OBJ_PAGE_SHA256,
        "obj_primary_palette_authority_sha256": OBJ_PRIMARY_SHA256,
        "obj_variant_palette_authority_sha256": OBJ_VARIANT_SHA256,
        "semantic_obj_lut_sha256": OBJ_LUT_SHA256,
        "semantic_fingerprint": semantic_fingerprint,
        "checks": checks,
    }


def parse_key_values(path: Path, label: str) -> dict[str, str]:
    require(path.is_file(), f"{label} is missing: {path}")
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        require(key not in result, f"{label} repeats key {key!r}")
        result[key] = value
    return result


def parse_exact_key_values(
    path: Path, expected: frozenset[str], label: str,
) -> dict[str, str]:
    require(path.is_file(), f"{label} is missing: {path}")
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ObjVisualError(f"{label} is unreadable: {error}") from error
    require(lines and all(line and line.count("=") == 1 for line in lines),
            f"{label} is not an exact key=value artifact")
    result: dict[str, str] = {}
    for line in lines:
        key, value = line.split("=", 1)
        require(key not in result, f"{label} repeats key {key!r}")
        result[key] = value
    exact_keys(result, expected, label)
    return result


def stop_exact_child(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    existing = process.poll()
    if existing is not None:
        return {
            "exact_child_terminated": False,
            "termination_method": "already-exited",
            "return_code": existing,
        }
    process.terminate()
    method = "SIGTERM"
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        method = "SIGKILL-after-SIGTERM-timeout"
    return {
        "exact_child_terminated": True,
        "termination_method": method,
        "return_code": process.returncode,
    }


def run_process_check(path: Path) -> None:
    with path.open("wb") as handle:
        subprocess.run(
            [str(PROCESS_CHECK)], cwd=ROOT, stdout=handle,
            stderr=subprocess.STDOUT, check=False,
        )


def inspect_retargeted_state(
    source: Path, destination: Path, rom: Path,
) -> dict[str, Any]:
    """Reconstruct a retarget claim without modifying either state file."""
    require(sha256(source) == OPERATOR_CAPTURE_SHA256,
            "reviewed scene-$0B operator capture hash changed")
    before = gbas_payload(source)
    require(sha256_bytes(before) == OPERATOR_GBAS_SHA256,
            "reviewed scene-$0B serialized machine state changed")
    after = gbas_payload(destination)
    changed = [
        index for index, pair in enumerate(zip(before, after, strict=True))
        if pair[0] != pair[1]
    ]
    rom_bytes = rom.read_bytes()
    identity_changed = before[0x1F] != rom_bytes[0x143]
    allowed = {4, 5, 6, 7}
    if identity_changed:
        require(before[0x1F] == 0x80 and rom_bytes[0x143] == 0xC0,
                "unreviewed cartridge identity transition")
        allowed.add(0x1F)
    require(set(changed) <= allowed,
            "operator-state retarget changed machine/video memory")
    require(after[0x10:0x20] == rom_bytes[0x134:0x144],
            "retargeted state cartridge identity differs")
    candidate_crc = zlib.crc32(rom.read_bytes()) & 0xFFFFFFFF
    require(int.from_bytes(after[4:8], "little") == candidate_crc,
            "retargeted state contains the wrong candidate CRC32")
    return {
        "source": str(source.resolve()),
        "source_sha256": sha256(source),
        "source_gbAs_sha256": sha256_bytes(before),
        "retargeted": str(destination.resolve()),
        "retargeted_sha256": sha256(destination),
        "retargeted_gbAs_sha256": sha256_bytes(after),
        "candidate_crc32": f"{candidate_crc:08x}",
        "changed_gbAs_offsets": changed,
        "normalization_writes": 0,
        "vram_injection_bytes": 0,
    }


def retarget_operator_state(
    source: Path, destination: Path, rom: Path,
) -> dict[str, Any]:
    if gbas_payload(source)[0x1F] != rom.read_bytes()[0x143]:
        retarget_rom_identity(source, destination, rom)
    else:
        normalize(source, destination, 0x016C, [], rom=rom, retarget_only=True)
    return inspect_retargeted_state(source, destination, rom)


def default_qt_emulator() -> Path:
    """Resolve the same override-free Qt binary as the single-flight guard."""
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise ObjVisualError("default checked Qt emulator executable is missing")


def verify_probe_source() -> dict[str, Any]:
    source = PROBE.read_text()
    required = (
        "emu.memory and emu.memory.vram",
        "emu.memory and emu.memory.cgbObjPalette",
        "raw_vram:read8(first * 16 + offset)",
        "local base = 0xFE00 + slot * 4",
        "emu:loadStateFile(STATE_FILE)",
        "local KEY_SELECT = 0x04",
        "emu:write8(0xFF6A, index)",
        "emu:write8(0xFF6A, old_index)",
        "emu:read8(0xFF6A) ~= old_index",
    )
    for snippet in required:
        require(snippet in source, f"OBJ probe lost required observer: {snippet}")
    require(source.count("emu:write8(") == 2,
            "OBJ probe gained an unreviewed direct memory write")
    for forbidden in (
        "emu:write8(0xFF6B", "emu:write16", "raw_vram:write",
        "obj_cram:write", "emu.memory.vram:write",
    ):
        require(forbidden not in source,
                f"OBJ probe gained a forbidden mutation API: {forbidden}")
    emulator = default_qt_emulator()
    return {
        "probe_sha256": sha256(PROBE),
        "launcher_sha256": sha256(LAUNCHER),
        "singleflight_implementation_sha256": sha256(
            SINGLEFLIGHT_IMPLEMENTATION
        ),
        "state_retargeter_sha256": sha256(STATE_RETARGETER),
        "capture_binder_sha256": sha256(CAPTURE_BINDER),
        "obj_lut_builder_sha256": sha256(OBJ_LUT_BUILDER),
        "obj_lut_source_sha256": sha256(OBJ_LUT_SOURCE),
        "emulator_path": str(emulator),
        "emulator_sha256": sha256(emulator),
        "verifier_sha256": sha256(Path(__file__).resolve()),
        "raw_vram_bank0_only": True,
        "emulator_override": False,
        "obj_cram_data_writes": False,
        "obj_cram_index_write_sites": 2,
        "obj_cram_index_restored": True,
    }


def _validate_claimed_artifact(
    receipt: Mapping[str, Any], key: str, expected: Path, label: str,
    *, not_before_ns: int | None = None,
) -> Path:
    require(isinstance(receipt.get(key), str), f"{label} path is not a string")
    path = Path(receipt[key]).resolve()
    require(path == expected.resolve(), f"{label} path changed")
    require(path.is_file(), f"{label} is missing: {path}")
    hash_key = f"{key}_sha256"
    require(isinstance(receipt.get(hash_key), str)
            and receipt[hash_key] == sha256(path),
            f"{label} hash differs")
    if not_before_ns is not None:
        require(path.stat().st_mtime_ns >= not_before_ns,
                f"{label} predates the bound launch")
    return path


def validate_live_receipt(receipt_path: Path, candidate_path: Path) -> dict[str, Any]:
    """Strictly revalidate a live receipt without starting an emulator."""
    receipt_path = scratch_descendant(receipt_path, "OBJ live receipt")
    candidate_path = candidate_path.resolve()
    require(candidate_path.is_file(), f"candidate is missing: {candidate_path}")
    candidate_sha = sha256(candidate_path)
    receipt = load_json_object(receipt_path, "OBJ live receipt")
    exact_keys(receipt, LIVE_RECEIPT_KEYS, "OBJ live receipt")
    require(receipt["schema"] == SCHEMA and receipt["status"] == "pass",
            "OBJ live receipt is not the exact passing schema")
    require(receipt["source_candidate"] == str(candidate_path)
            and receipt["source_candidate_sha256"] == candidate_sha,
            "OBJ live receipt targets another source candidate")

    output = receipt_path.parent.resolve()
    runtime = output / "runtime"
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "operator.ss0"
    prefix = output / "stage1-obj"
    trace = Path(str(prefix) + ".trace.tsv")
    startup = Path(str(prefix) + ".startup")
    core_ready = Path(str(prefix) + ".core-ready")
    report_path = Path(str(prefix) + ".report")
    done = Path(str(prefix) + ".done")
    launch_path = output / "launch-contract.json"
    log = output / "emulator.log"

    require(receipt["candidate"] == str(runtime_rom)
            and receipt["runtime_candidate"] == str(runtime_rom),
            "OBJ live receipt runtime candidate path changed")
    require(runtime_rom.is_file() and sha256(runtime_rom) == candidate_sha,
            "OBJ runtime candidate differs from the source candidate")
    require(receipt["candidate_sha256"] == candidate_sha
            and receipt["runtime_candidate_sha256"] == candidate_sha
            and receipt["candidate_size"] == runtime_rom.stat().st_size
            == candidate_path.stat().st_size,
            "OBJ live receipt candidate hash/size binding differs")
    require(receipt["trace"] == str(trace),
            "OBJ live receipt trace path changed")

    launch_started = receipt["launch_started_at_ns"]
    bound_at = receipt["bound_at_ns"]
    require(type(launch_started) is int and type(bound_at) is int
            and 0 < launch_started <= bound_at <= time.time_ns(),
            "OBJ live receipt time window is invalid")
    require(receipt_path.stat().st_mtime_ns >= bound_at,
            "OBJ live receipt predates its claimed bind time")

    startup = _validate_claimed_artifact(
        receipt, "startup_marker", startup, "OBJ startup marker",
        not_before_ns=launch_started,
    )
    core_ready = _validate_claimed_artifact(
        receipt, "core_ready_marker", core_ready, "OBJ core-ready marker",
        not_before_ns=launch_started,
    )
    report_path = _validate_claimed_artifact(
        receipt, "producer_report", report_path, "OBJ producer report",
        not_before_ns=launch_started,
    )
    done = _validate_claimed_artifact(
        receipt, "completion_marker", done, "OBJ completion marker",
        not_before_ns=launch_started,
    )
    launch_path = _validate_claimed_artifact(
        receipt, "launch_contract", launch_path, "OBJ launch contract",
        not_before_ns=launch_started,
    )
    _validate_claimed_artifact(
        receipt, "emulator_log", log, "OBJ emulator log",
        not_before_ns=launch_started,
    )

    exact_keys(receipt["operator_state"], RETARGET_KEYS,
               "OBJ operator-state claim")
    expected_retarget = inspect_retargeted_state(
        OPERATOR_CAPTURE, runtime_state, runtime_rom
    )
    require(json_exact_equal(receipt["operator_state"], expected_retarget),
            "OBJ operator-state claim differs from the exact CRC-only delta")

    exact_keys(receipt["tool_identity"], TOOL_IDENTITY_KEYS,
               "OBJ tool identity")
    current_tools = verify_probe_source()
    require(json_exact_equal(receipt["tool_identity"], current_tools),
            "OBJ live receipt differs from current checked tool identities")

    launch = load_json_object(launch_path, "OBJ launch contract")
    exact_keys(launch, LAUNCH_KEYS, "OBJ launch contract")
    exact_keys(launch["probe_environment"], PROBE_ENVIRONMENT_KEYS,
               "OBJ launch probe environment")
    expected_command = [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        "--script", str(PROBE), str(runtime_rom),
    ]
    expected_probe_environment = {
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "PENTA_STAGE1_OBJ_OUT": str(prefix),
        "PENTA_STAGE1_OBJ_STATE": str(runtime_state),
        "PENTA_STAGE1_OBJ_FRAME_LIMIT": str(FRAME_LIMIT),
        "PENTA_STAGE1_OBJ_BASELINE_FRAMES": str(PHASE_MINIMUMS["baseline"]),
        "PENTA_STAGE1_OBJ_MENU_HOLD_FRAMES": str(PHASE_MINIMUMS["menu_hold"]),
        "PENTA_STAGE1_OBJ_POST_CLOSE_FRAMES": str(
            PHASE_MINIMUMS["post_close"]
        ),
    }
    require(launch["schema"] == "penta-stage1-obj-visual-launch-v1"
            and launch["command"] == expected_command
            and launch["cwd"] == str(output)
            and launch["candidate"] == str(runtime_rom)
            and launch["candidate_sha256"] == candidate_sha
            and launch["source_candidate"] == str(candidate_path)
            and launch["source_candidate_sha256"] == candidate_sha
            and type(launch["launch_started_at_ns"]) is int
            and launch["launch_started_at_ns"] == launch_started
            and type(launch["frame_limit"]) is int
            and launch["frame_limit"] == FRAME_LIMIT
            and type(launch["timeout_seconds"]) is float
            and launch["timeout_seconds"] == RUN_TIMEOUT_SECONDS
            and json_exact_equal(launch["retarget"], expected_retarget)
            and json_exact_equal(launch["tool_identity"], current_tools)
            and json_exact_equal(
                launch["probe_environment"], expected_probe_environment
            ),
            "OBJ launch contract differs from the fixed guarded route")

    startup_values = parse_exact_key_values(
        startup, frozenset({"startup_token"}), "OBJ startup marker"
    )
    core_values = parse_exact_key_values(
        core_ready, frozenset({"startup_token"}), "OBJ core-ready marker"
    )
    completion = parse_exact_key_values(
        done, frozenset({"status", "startup_token"}),
        "OBJ completion marker",
    )
    report = parse_exact_key_values(
        report_path, REPORT_KEYS, "OBJ producer report"
    )
    token = startup_values["startup_token"]
    require(len(token) == 64 and token == token.lower(),
            "OBJ startup token is not 32-byte lowercase hexadecimal")
    try:
        token_bytes = bytes.fromhex(token)
    except ValueError as error:
        raise ObjVisualError("OBJ startup token is not hexadecimal") from error
    require(len(token_bytes) == 32
            and core_values["startup_token"] == token
            and completion == {"status": "ok", "startup_token": token}
            and report["status"] == "ok"
            and report["reason"] == "complete"
            and report["startup_token"] == token
            and launch["startup_token_sha256"]
            == sha256_bytes(token.encode()),
            "OBJ startup/core/report/completion token binding differs")

    recomputed = bind_trace(runtime_rom, trace)
    receipt_core = {key: receipt[key] for key in CORE_RECEIPT_KEYS}
    require(json_exact_equal(receipt_core, recomputed),
            "OBJ live receipt core claims differ from the rebound trace")
    rows = parse_trace(trace)
    numeric_report_keys = REPORT_KEYS - {
        "status", "reason", "startup_token",
    }
    require(all(report[key].isdigit() for key in numeric_report_keys),
            "OBJ producer report has a non-decimal count")
    require(int(report["frames"]) == rows[-1]["frame"]
            and int(report["samples"]) == recomputed["samples"]
            and int(report["menu_open_events"]) == 1
            and int(report["menu_close_events"]) == 1
            and all(
                int(report[f"samples_{phase}"])
                == recomputed["phase_samples"][phase]
                for phase in PHASE_ORDER
            ), "OBJ producer report differs from the rebound native route")

    exact_keys(receipt["controlled_teardown"], TEARDOWN_KEYS,
               "OBJ controlled teardown")
    teardown = receipt["controlled_teardown"]
    if teardown["exact_child_terminated"] is False:
        require(json_exact_equal(teardown, {
            "exact_child_terminated": False,
            "termination_method": "already-exited",
            "return_code": 0,
        }), "OBJ launcher did not exit naturally with status zero")
    else:
        require(teardown["exact_child_terminated"] is True
                and teardown["termination_method"] in {
                    "SIGTERM", "SIGKILL-after-SIGTERM-timeout",
                }
                and type(teardown["return_code"]) is int
                and teardown["return_code"] in {-15, -9},
                "OBJ exact-child teardown claim is invalid")

    return {
        **receipt,
        "receipt": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "offline_revalidated": True,
    }


def run_live(candidate: Path, output: Path, timeout: float) -> dict[str, Any]:
    """Run one serialized, candidate-bound scene-$0B OBJ route."""
    candidate = candidate.resolve()
    output = scratch_descendant(output, "OBJ evidence output")
    require(candidate.is_file(), f"candidate is missing: {candidate}")
    require(timeout == RUN_TIMEOUT_SECONDS,
            f"OBJ READY route timeout is fixed at {RUN_TIMEOUT_SECONDS:g}s")
    # Authenticate static authorities before owning the emulator slot.
    candidate_contract(candidate.read_bytes())
    tools = verify_probe_source()
    require(not output.exists(),
            f"fresh OBJ evidence output already exists: {output}")
    output.mkdir(parents=True)
    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "operator.ss0"
    shutil.copy2(candidate, runtime_rom)
    candidate_sha = sha256(candidate)
    require(sha256(runtime_rom) == candidate_sha,
            "isolated OBJ runtime candidate hash changed")
    retarget = retarget_operator_state(OPERATOR_CAPTURE, runtime_state, runtime_rom)

    prefix = output / "stage1-obj"
    trace = Path(str(prefix) + ".trace.tsv")
    report_path = Path(str(prefix) + ".report")
    startup = Path(str(prefix) + ".startup")
    core_ready = Path(str(prefix) + ".core-ready")
    done = Path(str(prefix) + ".done")
    log = output / "emulator.log"
    token = secrets.token_hex(32)
    environment = os.environ.copy()
    for key in (
        "PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN", "DISPLAY", "WAYLAND_DISPLAY",
    ):
        environment.pop(key, None)
    probe_environment = {
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "PENTA_STAGE1_OBJ_OUT": str(prefix),
        "PENTA_STAGE1_OBJ_STATE": str(runtime_state),
        "PENTA_STAGE1_OBJ_FRAME_LIMIT": str(FRAME_LIMIT),
        "PENTA_STAGE1_OBJ_BASELINE_FRAMES": str(PHASE_MINIMUMS["baseline"]),
        "PENTA_STAGE1_OBJ_MENU_HOLD_FRAMES": str(PHASE_MINIMUMS["menu_hold"]),
        "PENTA_STAGE1_OBJ_POST_CLOSE_FRAMES": str(
            PHASE_MINIMUMS["post_close"]
        ),
    }
    environment.update(probe_environment)
    environment["PENTA_STAGE1_OBJ_TOKEN"] = token
    command = [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        "--script", str(PROBE), str(runtime_rom),
    ]
    # Compare filesystem timestamps with the same filesystem clock. On this
    # host, a freshly written file can have mtime tens of microseconds behind
    # time.time_ns(); using the latter spuriously rejected a new contract.
    # The state was just generated in the fresh exclusive output directory,
    # before the contract, log, and nonce-authenticated emulator markers.
    # No timestamp is rewritten and no age tolerance is introduced.
    launch_started_at_ns = runtime_state.stat().st_mtime_ns
    launch_contract = {
        "schema": "penta-stage1-obj-visual-launch-v1",
        "command": command,
        "cwd": str(output),
        "candidate": str(runtime_rom),
        "candidate_sha256": candidate_sha,
        "source_candidate": str(candidate),
        "source_candidate_sha256": candidate_sha,
        "startup_token_sha256": sha256_bytes(token.encode()),
        "launch_started_at_ns": launch_started_at_ns,
        "frame_limit": FRAME_LIMIT,
        "timeout_seconds": timeout,
        "retarget": retarget,
        "tool_identity": tools,
        "probe_environment": probe_environment,
    }
    launch_path = output / "launch-contract.json"
    launch_path.write_text(json.dumps(
        launch_contract, indent=2, sort_keys=True
    ) + "\n")

    timed_out = False
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=output, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if done.is_file() or process.poll() is not None:
                break
            time.sleep(0.05)
        else:
            timed_out = True
        teardown = stop_exact_child(process)

    if timed_out:
        process_log = output / "timeout-process-check.log"
        run_process_check(process_log)
        raise ObjVisualError(
            f"guarded OBJ route timed out; read-only process check: {process_log}"
        )
    if process.returncode == 75:
        raise ObjVisualError("single-flight emulator slot is already owned (exit 75)")
    if not all(path.is_file() for path in (
        startup, core_ready, trace, report_path, done,
    )):
        process_log = output / "incomplete-process-check.log"
        run_process_check(process_log)
        raise ObjVisualError(
            "OBJ probe evidence is incomplete; read-only process check: "
            f"{process_log}"
        )
    for marker, label in ((startup, "startup"), (core_ready, "core-ready")):
        values = parse_key_values(marker, f"OBJ {label} marker")
        require(values.get("startup_token") == token,
                f"OBJ {label} marker token differs")
    completion = parse_key_values(done, "OBJ completion marker")
    report = parse_key_values(report_path, "OBJ producer report")
    if (completion.get("startup_token") == token
            and report.get("startup_token") == token
            and report.get("status") == "fail"):
        raise ObjVisualError(
            f"OBJ live probe failed: {report.get('reason', 'unknown')}; "
            f"report={report_path}"
        )
    require(completion.get("status") == "ok"
            and completion.get("startup_token") == token,
            "OBJ producer completion marker is not authenticated/pass")
    require(report.get("status") == "ok"
            and report.get("reason") == "complete"
            and report.get("startup_token") == token,
            "OBJ producer report is not authenticated/pass")
    require(int(report.get("menu_open_events", "-1")) == 1
            and int(report.get("menu_close_events", "-1")) == 1,
            "OBJ producer did not observe exactly one native open/close")
    require(
        int(report.get("obj_cram_restore_failures", "-1")) == 0
        and int(report.get("obj_cram_domain_samples", "-1"))
        + int(report.get("obj_cram_index_samples", "-1"))
        == int(report.get("samples", "-1")),
        "OBJ CRAM observer did not cover every sample and restore OCPS",
    )

    bound = bind_trace(runtime_rom, trace)
    bound.update({
        "source_candidate": str(candidate),
        "source_candidate_sha256": candidate_sha,
        "runtime_candidate": str(runtime_rom),
        "runtime_candidate_sha256": sha256(runtime_rom),
        "operator_state": retarget,
        "startup_marker": str(startup),
        "startup_marker_sha256": sha256(startup),
        "core_ready_marker": str(core_ready),
        "core_ready_marker_sha256": sha256(core_ready),
        "producer_report": str(report_path),
        "producer_report_sha256": sha256(report_path),
        "completion_marker": str(done),
        "completion_marker_sha256": sha256(done),
        "launch_contract": str(launch_path),
        "launch_contract_sha256": sha256(launch_path),
        "emulator_log": str(log),
        "emulator_log_sha256": sha256(log),
        "tool_identity": tools,
        "controlled_teardown": teardown,
        "launch_started_at_ns": launch_started_at_ns,
        "bound_at_ns": time.time_ns(),
    })
    receipt = output / "stage1-obj-visual.receipt.json"
    receipt.write_text(json.dumps(bound, indent=2, sort_keys=True) + "\n")
    return validate_live_receipt(receipt, candidate)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--run", action="store_true",
        help="run the guarded native scene-$0B menu route",
    )
    mode.add_argument(
        "--trace", type=Path,
        help="bind an existing producer trace without starting an emulator",
    )
    mode.add_argument(
        "--receipt", type=Path,
        help="strictly revalidate an existing live receipt offline",
    )
    parser.add_argument(
        "--output", type=Path,
        help="fresh repo tmp/ or /mnt/data/tmp/ output (required with --run)",
    )
    parser.add_argument("--timeout", type=float, default=RUN_TIMEOUT_SECONDS)
    args = parser.parse_args()
    try:
        if args.run:
            require(args.output is not None, "--run requires --output")
            result = run_live(args.candidate, args.output, args.timeout)
            print(
                "PASS: Stage-1 OAM, all OBJ CRAM, and referenced OBJ CHR are "
                f"exact; receipt={result['receipt']}"
            )
        elif args.receipt is not None:
            require(args.output is None,
                    "--receipt revalidation does not accept --output")
            result = validate_live_receipt(args.receipt, args.candidate)
            print(
                "PASS: live Stage-1 OBJ receipt strictly revalidated offline; "
                f"receipt={result['receipt']}"
            )
        else:
            result = bind_trace(args.candidate, args.trace)
            if args.output is not None:
                output = scratch_descendant(
                    args.output, "offline OBJ evidence output"
                )
                require(not output.exists(),
                        f"fresh offline output already exists: {output}")
                output.mkdir(parents=True)
                receipt = output / "stage1-obj-visual.core.json"
                receipt.write_text(json.dumps(
                    result, indent=2, sort_keys=True
                ) + "\n")
                print(
                    "PASS: offline Stage-1 OBJ evidence is exact; "
                    f"receipt={receipt}"
                )
            else:
                print(
                    "PASS: offline Stage-1 OBJ evidence is exact; "
                    f"samples={result['samples']}"
                )
        return 0
    except (ObjVisualError, OSError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
