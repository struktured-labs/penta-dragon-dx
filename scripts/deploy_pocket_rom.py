#!/usr/bin/env python3
"""Hash-bound Pocket deployment with mandatory regression receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECEIPT = ROOT / "docs/release/verification/latest.json"
DEFAULT_MOUNT = Path("/media/struktured/POCKET-SD")
DEFAULT_POCKET_DEVICE = Path("/dev/sdc1")
DEFAULT_POCKET_LABEL = "POCKET-SD"
DEFAULT_POCKET_UUID = "6ED2-D7E0"
DEST_DIRECTORY = Path("Assets/gbc/common")
DEST_PREFIX = "Penta Dragon DX v3.01"
LATEST_ALIAS_NAME = "penta-dragon-latest.gbc"
NORTH_VERIFIER = ROOT / "scripts/diagnostics/verify_stage1_north_integrity.py"
HARDWARE_TEST_READY_SCHEMA = "penta-stage1-reported-regressions-ready-v10"
HARDWARE_TEST_READY_MAX_AGE_SECONDS = 24 * 60 * 60
HARDWARE_TEST_READY_FUTURE_SKEW_SECONDS = 5 * 60
HARDWARE_TEST_READY_GATE_STATUSES = {
    "stage1_menu_race_static_exhaustive": "PASS",
    "cold_and_returned_title_nightfall": "PASS",
    "captured_scene0b_transition_menu": "PASS",
    "stage1_tilemap_publication_oracle": "PASS",
    "natural_blank_sram_menu_and_art_loader": "PASS",
    "natural_room03_active_scroll_menu": "PASS",
    "native_select_menu_window_exact": "PASS",
    "blank_sram_stage1_handoff_no_cyan_partial_flash": "PASS",
    "independent_room01_wall_north_replay": "PASS",
    "stage1_current_pickup_state": "PASS",
    "stage1_current_pickup_host_palettes": "PASS",
    "natural_stage1_pickup_temporal_raster": "PASS",
    "rom_owned_natural_hazard_state": "PASS",
    "rom_owned_stationary_hazard_menu_replay": "PASS",
    "independent_rendered_continuity": "PASS",
    "release_speed_named_stages_95_stage6_strict99": (
        "PASS_RELEASE_95_NAMED_STAGE6_STRICT99_STAGE7_WORLD_MATCHED98"
    ),
    "tool_identity_reverification": "PASS",
}
HARDWARE_TEST_READY_GATES = frozenset(HARDWARE_TEST_READY_GATE_STATUSES)
HARDWARE_TEST_READY_COMMAND_GATES = (
    HARDWARE_TEST_READY_GATES - {"tool_identity_reverification"}
)
HARDWARE_TEST_READY_TOP_LEVEL_KEYS = frozenset({
    "schema",
    "status",
    "candidate",
    "candidate_sha256",
    "output",
    "gates",
    "reported_issue_coverage",
    "failures",
    "tool_identity",
})
HARDWARE_TEST_READY_REPORTED_ISSUES = frozenset({
    "blank_white_game_start_title_menu",
    "menu_exit_red_green_artifacts",
    "menu_exit_repeating_bottom_stage_tiles",
    "sarah_adjacent_transient_object_or_room_tile",
    "rotating_spike_flicker",
    "music_cadence_slowdown",
    "first_room_transition_wall_edges_and_entrances",
    "flashing_walls",
    "hazard_clear_tiles_or_nubs",
    "hazard_yellow_extension_retraction_trails",
    "hazard_gray_tip_and_wall_contact",
    "pickup_color_alignment",
    "pre_stage_cyan_or_purple_flash",
})
NORTH_RELEASE_PARAMETERS = {
    "gameplay_frames": 2400,
    "target_camera": 0x03A4,
    "target_room": 1,
    "target_settle_frames": 60,
    "dynamic_prefix_bytes": 0,
}
NORTH_REPLAY_ARTIFACTS = {
    "c1a0.bin",
    "trajectory.bin",
    "visible-tiles.bin",
    "visible-attrs.bin",
    "vram9800.bin",
    "vram9800-attrs.bin",
    "vram9c00.bin",
    "vram9c00-attrs.bin",
    "shadow-oam.bin",
    "hardware-oam.bin",
    "bg-cram.bin",
    "obj-cram.bin",
    "world-at-entry.bin",
    "world-final.bin",
    "metatiles-at-entry.bin",
    "metatiles-final.bin",
}


def write_json_atomic(path: Path, payload: dict) -> None:
    """Write a durable local receipt without exposing a partial JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}-",
        suffix=".pending",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hardware_test_ready_tool_paths() -> dict[str, Path]:
    """Return the exact tool inventory sealed by the reporting interceptor."""

    diagnostics = ROOT / "scripts" / "diagnostics"
    return {
        "reporting_interceptor": (
            diagnostics / "verify_stage1_reported_regressions_ready.py"
        ),
        "natural_menu_verifier": (
            diagnostics / "verify_stage1_natural_menu_bg.py"
        ),
        "natural_menu_probe": diagnostics / "probe_stage1_natural_menu_bg.lua",
        "natural_obj_verifier": diagnostics / "verify_natural_stage1_obj.py",
        "obj_visual_contract": diagnostics / "verify_stage1_obj_visual_contract.py",
        "native_menu_window_verifier": (
            diagnostics / "verify_menu_window_order.py"
        ),
        "native_menu_window_probe": diagnostics / "probe_menu_window_order.lua",
        "native_menu_commit_protocol": diagnostics / "menu_commit_protocol.py",
        "title_nightfall_verifier": (
            diagnostics / "verify_title_nightfall_mgba.py"
        ),
        "title_nightfall_probe": diagnostics / "probe_title_nightfall_mgba.lua",
        "menu_window_attribute_builder": (
            ROOT / "scripts" / "menu_icon_colorization.py"
        ),
        "stage1_hazard_art_contract": ROOT / "scripts" / "stage1_hazard_art.py",
        "stage1_hazard_art_yaml": ROOT / "palettes" / "bg_tile_categories.yaml",
        "stage1_hazard_palette_yaml": (
            ROOT / "palettes" / "penta_palettes_v097.yaml"
        ),
        "production_rom_builder": ROOT / "scripts" / "build_v302_title_fix.py",
        "menu_race_static_verifier": (
            diagnostics / "verify_stage1_menu_race_static.py"
        ),
        "stage_card_verifier": diagnostics / "verify_stage_card_stability.py",
        "stage_card_probe": diagnostics / "probe_stage_card_stability.lua",
        "stage_card_static_contract": (
            ROOT / "scripts" / "stage_card_palette_handoff.py"
        ),
        "stage1_north_verifier": (
            diagnostics / "verify_stage1_north_integrity.py"
        ),
        "stage1_north_probe": diagnostics / "probe_stage1_north_integrity.lua",
        "room01_wall_oracle": diagnostics / "stage1_room01_wall_oracle.py",
        "room01_wall_fixture": (
            diagnostics / "fixtures" / "stage1_room01_wall_oracle.json"
        ),
        "scene0b_receipt_binder": (
            diagnostics / "verify_stage1_scene0b_captured_menu_receipt.py"
        ),
        "scene0b_live_verifier": (
            diagnostics / "verify_stage1_scene0b_live_menu_roundtrip.py"
        ),
        "scene0b_live_probe": (
            diagnostics / "probe_stage1_scene0b_live_menu_roundtrip.lua"
        ),
        "scene0b_capture_fixture": (
            diagnostics / "fixtures" / "stage1_scene0b_capture_contract.json"
        ),
        "stage1_tilemap_publication_verifier": (
            diagnostics / "verify_stage1_tilemap_copy.py"
        ),
        "stage1_tilemap_publication_probe": (
            diagnostics / "probe_stage1_tilemap_copy.lua"
        ),
        "scene0b_state_retargeter": (
            diagnostics / "normalize_mgba_state_pc.py"
        ),
        "pickup_state_generator": (
            diagnostics / "generate_stage1_pickup_state.py"
        ),
        "pickup_state_probe": diagnostics / "probe_stage1_no_bleed.lua",
        "natural_pickup_raster_verifier": (
            diagnostics / "verify_stage1_no_bleed.py"
        ),
        "natural_pickup_raster_probe": (
            diagnostics / "probe_stage1_no_bleed.lua"
        ),
        "pickup_host_verifier": (
            diagnostics / "verify_pickup_current_host_palettes.py"
        ),
        "pickup_host_runner": diagnostics / "verify_pickup_live_palettes.py",
        "pickup_host_probe": diagnostics / "probe_pickup_live_palettes.lua",
        "pickup_class_inventory": (
            diagnostics / "verify_pickup_class_palettes.py"
        ),
        "pickup_art_verifier": diagnostics / "verify_stage1_pickup_art.py",
        "pickup_art_analyzer": diagnostics / "analyze_stage1_pickup_art.py",
        "pickup_table_builder": ROOT / "scripts" / "build_v301_gdma.py",
        "pickup_receipt_validator": (
            diagnostics / "verify_pocket_visual_receipts.py"
        ),
        "hazard_state_generator": diagnostics / "generate_stage1_hazard_state.py",
        "hazard_state_probe": diagnostics / "probe_stage1_north_integrity.lua",
        "hazard_menu_verifier": (
            diagnostics / "verify_stage1_current_hazard_menu.py"
        ),
        "hazard_menu_contract": diagnostics / "verify_stage1_hazard_menu.py",
        "hazard_live_verifier": diagnostics / "verify_stage1_spike_palettes.py",
        "hazard_menu_probe": diagnostics / "probe_stage1_spike_palettes.lua",
        "rendered_continuity_verifier": (
            diagnostics / "verify_stage1_rendered_continuity.py"
        ),
        "rendered_continuity_operator_capture_fixture": (
            diagnostics / "fixtures" / "stage1_rendered_operator_captures.json"
        ),
        "speed_qualifier": (
            diagnostics / "verify_split_stage_speed_qualification.py"
        ),
        "singleflight_launcher": ROOT / "scripts" / "mgba-qt-singleflight",
        "read_only_process_check": ROOT / "scripts" / "check_emulator_processes.sh",
    }


def is_allowed_scratch_child(path: Path) -> bool:
    """Return whether a path belongs to a project-approved scratch root."""

    resolved = path.resolve()
    for root in ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve()):
        if root.exists() and resolved != root and resolved.is_relative_to(root):
            return True
    return False


def require_hardware_test_ready_receipt(
    path: Path,
    rom: Path,
    rom_hash: str,
    *,
    now_timestamp: float | None = None,
) -> dict[str, object]:
    """Accept only a fresh, exact v10 reporting-interceptor READY receipt."""

    failures: list[str] = []
    try:
        canonical_rom = rom.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        canonical_rom = None
    if canonical_rom is None or sha256(canonical_rom) != rom_hash:
        failures.append("candidate ROM no longer matches the requested hash")
    if not path.is_file():
        raise SystemExit(
            f"REFUSED: Stage-1 hardware-test READY receipt is absent: {path}"
        )
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(
            f"REFUSED: Stage-1 hardware-test READY receipt is invalid: {error}"
        ) from error
    if not isinstance(data, dict):
        raise SystemExit(
            "REFUSED: Stage-1 hardware-test READY receipt is not a JSON object"
        )

    if set(data) != HARDWARE_TEST_READY_TOP_LEVEL_KEYS:
        failures.append("READY receipt top-level inventory is not exact")
    if data.get("schema") != HARDWARE_TEST_READY_SCHEMA:
        failures.append("READY receipt schema is unsupported")
    if data.get("status") != "READY":
        failures.append("reporting interceptor status is not READY")
    if data.get("candidate_sha256") != rom_hash:
        failures.append("READY receipt ROM hash mismatch")
    try:
        receipt_candidate = Path(str(data.get("candidate", ""))).resolve(
            strict=True
        )
    except (OSError, RuntimeError, ValueError):
        receipt_candidate = None
    if (
        receipt_candidate != canonical_rom
        or data.get("candidate") != str(canonical_rom)
    ):
        failures.append("READY receipt names another candidate path")
    if data.get("failures") != []:
        failures.append("READY receipt failure inventory is not exactly empty")

    try:
        receipt_output = Path(str(data.get("output", ""))).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        receipt_output = None
    if (
        receipt_output is None
        or path.resolve() != receipt_output / "receipt.json"
        or data.get("output") != str(receipt_output)
        or not is_allowed_scratch_child(path)
    ):
        failures.append("READY receipt is not bound to its approved scratch output")

    receipt_mtime = path.stat().st_mtime
    now = (
        datetime.now(timezone.utc).timestamp()
        if now_timestamp is None
        else now_timestamp
    )
    age_seconds = now - receipt_mtime
    if age_seconds > HARDWARE_TEST_READY_MAX_AGE_SECONDS:
        failures.append("READY receipt is older than 24 hours")
    if age_seconds < -HARDWARE_TEST_READY_FUTURE_SKEW_SECONDS:
        failures.append("READY receipt modification time is implausibly in the future")
    if receipt_mtime < rom.stat().st_mtime:
        failures.append("READY receipt predates the candidate ROM")

    gates = data.get("gates")
    if not isinstance(gates, dict) or set(gates) != HARDWARE_TEST_READY_GATES:
        failures.append("READY receipt gate inventory is not exact")
    else:
        failed_gates = sorted(
            name
            for name, gate in gates.items()
            if (
                not isinstance(gate, dict)
                or gate.get("status")
                != HARDWARE_TEST_READY_GATE_STATUSES[name]
            )
        )
        if failed_gates:
            failures.append(f"READY receipt gates are not PASS: {failed_gates}")

        command_gate_failures: list[str] = []
        for name in sorted(HARDWARE_TEST_READY_COMMAND_GATES):
            gate = gates[name]
            if not isinstance(gate, dict):
                command_gate_failures.append(name)
                continue
            if gate.get("exit_status") != 0 or gate.get("rom_sha256") != rom_hash:
                command_gate_failures.append(name)
                continue
            for evidence_name in ("receipt", "log"):
                raw_path = gate.get(evidence_name)
                recorded_hash = gate.get(f"{evidence_name}_sha256")
                if (
                    not isinstance(raw_path, str)
                    or not isinstance(recorded_hash, str)
                    or len(recorded_hash) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in recorded_hash
                    )
                ):
                    command_gate_failures.append(name)
                    break
                try:
                    evidence_path = Path(raw_path).resolve(strict=True)
                except (OSError, RuntimeError, ValueError):
                    command_gate_failures.append(name)
                    break
                if (
                    receipt_output is None
                    or not evidence_path.is_file()
                    or not evidence_path.is_relative_to(receipt_output)
                    or raw_path != str(evidence_path)
                    or evidence_path.stat().st_mtime > receipt_mtime
                    or sha256(evidence_path) != recorded_hash
                ):
                    command_gate_failures.append(name)
                    break
        if command_gate_failures:
            failures.append(
                "READY receipt command evidence is stale or malformed: "
                + ", ".join(sorted(set(command_gate_failures)))
            )

        issue_coverage = data.get("reported_issue_coverage")
        if (
            not isinstance(issue_coverage, dict)
            or set(issue_coverage) != HARDWARE_TEST_READY_REPORTED_ISSUES
        ):
            failures.append("reported-issue coverage inventory is not exact")
        else:
            malformed_issues = []
            for issue, coverage in issue_coverage.items():
                if not isinstance(coverage, dict) or set(coverage) != {
                    "status", "gates", "assertions",
                }:
                    malformed_issues.append(issue)
                    continue
                issue_gates = coverage.get("gates")
                assertions = coverage.get("assertions")
                if (
                    coverage.get("status") != "DETERMINISTIC_GATE"
                    or not isinstance(issue_gates, list)
                    or not issue_gates
                    or not set(issue_gates).issubset(HARDWARE_TEST_READY_GATES)
                    or not isinstance(assertions, list)
                    or not assertions
                    or not all(isinstance(item, str) and item for item in assertions)
                ):
                    malformed_issues.append(issue)
            if malformed_issues:
                failures.append(
                    "reported-issue coverage is malformed: "
                    + ", ".join(sorted(malformed_issues))
                )

    expected_tools = hardware_test_ready_tool_paths()
    tool_identity = data.get("tool_identity")
    if not isinstance(tool_identity, dict) or set(tool_identity) != set(expected_tools):
        failures.append("READY receipt tool identity inventory is not exact")
    else:
        tool_failures: list[str] = []
        for name, expected_path in expected_tools.items():
            item = tool_identity.get(name)
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                tool_failures.append(name)
                continue
            try:
                recorded_path = Path(str(item.get("path", ""))).resolve(strict=True)
            except (OSError, RuntimeError, ValueError):
                tool_failures.append(name)
                continue
            recorded_hash = item.get("sha256")
            if (
                recorded_path != expected_path.resolve(strict=True)
                or item.get("path") != str(recorded_path)
                or not isinstance(recorded_hash, str)
                or len(recorded_hash) != 64
                or any(character not in "0123456789abcdef" for character in recorded_hash)
                or sha256(expected_path) != recorded_hash
            ):
                tool_failures.append(name)
        if tool_failures:
            failures.append(
                "READY receipt tool identities are stale or malformed: "
                + ", ".join(sorted(tool_failures))
            )

    if isinstance(gates, dict):
        reverified = gates.get("tool_identity_reverification")
        if (
            not isinstance(reverified, dict)
            or set(reverified)
            != {"status", "all_tool_hashes_unchanged", "tool_identity"}
            or reverified.get("status") != "PASS"
            or reverified.get("all_tool_hashes_unchanged") is not True
            or reverified.get("tool_identity") != tool_identity
        ):
            failures.append("READY receipt lacks exact final tool re-verification")

    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "schema": HARDWARE_TEST_READY_SCHEMA,
        "status": "READY",
        "age_seconds": round(max(age_seconds, 0.0), 3),
        "candidate_sha256": rom_hash,
    }


def append_only_destination(mount: Path, rom_hash: str) -> Path:
    """Return a unique, content-addressed path; deployments never replace ROMs."""
    return mount / DEST_DIRECTORY / f"{DEST_PREFIX}-{rom_hash[:12]}.gbc"


def require_full_receipt(path: Path, rom: Path, rom_hash: str) -> None:
    data = json.loads(path.read_text())
    failures: list[str] = []
    if data.get("status") == "passed" and isinstance(data.get("matrix"), dict):
        receipt_hash = data.get("candidate", {}).get("sha256")
        matrix = data["matrix"]
        result_rows = matrix.get("results", [])
        if receipt_hash != rom_hash:
            failures.append(
                f"receipt ROM is {receipt_hash}, candidate is {rom_hash}"
            )
        if matrix.get("status") != "emulator-pass" or matrix.get("failures") != 0:
            failures.append("full emulator matrix did not pass")
    elif data.get("status") == "emulator-pass" and data.get("scope") == "full":
        # verify_release_candidate.py emits this native full-matrix manifest.
        # Bind it to the exact candidate through both the preserved source ROM
        # and the before/after MD5 fields; older release ledgers use SHA-256.
        result_rows = data.get("results", [])
        source = Path(str(data.get("source_rom", "")))
        if not source.is_file() or sha256(source) != rom_hash:
            failures.append("full-matrix source ROM is absent or does not match candidate")
        candidate_md5 = md5(rom)
        if data.get("rom_md5") != candidate_md5:
            failures.append("full-matrix initial ROM MD5 does not match candidate")
        if data.get("source_rom_md5_after") != candidate_md5:
            failures.append("full-matrix final source ROM MD5 does not match candidate")
        if data.get("source_fingerprint_after") != data.get("source_fingerprint"):
            failures.append("full-matrix source inputs changed during verification")
        selected = data.get("selected_gates", [])
        if len(selected) != len(result_rows) or len(selected) < 79:
            failures.append("full-matrix gate inventory is incomplete")
        failed_rows = [
            item.get("name") for item in result_rows if item.get("status") != "passed"
        ]
        if failed_rows:
            failures.append("full emulator matrix contains failed gates")
    else:
        result_rows = []
        failures.append(f"receipt status/schema is unsupported: {data.get('status')!r}")

    results = {item.get("name"): item.get("status") for item in result_rows}
    required_stage1_gates = (
        "stage_card_stability",
        "stage1_current_pickup_state",
        "stage1_current_pickup_host_palettes",
        "pocket_stage1_visual_incident",
        "menu_window_publish_order",
        "stage1_north_route_integrity",
        "stage1_current_hazard_state",
        "stage1_current_hazard_menu",
        "stage1_current_hazard_mutations",
        "stage1_exact_destination_mutation",
        "low_health_flicker",
    )
    for gate in required_stage1_gates:
        if results.get(gate) != "passed":
            failures.append(f"{gate} is not passed")
    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))


def require_visual_incident_receipt(path: Path, rom_hash: str) -> None:
    if not path.is_file():
        raise SystemExit(f"REFUSED: Pocket visual incident receipt is absent: {path}")
    data = json.loads(path.read_text())
    failures: list[str] = []
    if data.get("schema") != "penta-pocket-stage1-visual-incident-v6":
        failures.append("Pocket visual incident receipt schema is unsupported")
    if data.get("status") != "pass" or data.get("failures"):
        failures.append("Pocket visual incident gates did not pass")
    if data.get("rom_sha256") != rom_hash:
        failures.append("Pocket visual incident receipt ROM hash mismatch")
    required = {
        "stage1_no_color_bleed",
        "attract_pickup_palettes",
        "frame_flicker_gameplay",
        "frame_flicker_demo",
        "stage_card_palette_handoff",
        "stage1_current_hazard_menu",
        "stage1_current_pickup_state",
        "stage1_current_pickup_host_palettes",
        "stage1_north_route_integrity",
        "menu_window_order",
        "stage1_tilemap_integrity",
    }
    evidence = data.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != required:
        failures.append("Pocket visual incident evidence inventory is incomplete")
    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))


def require_hardware_receipt(path: Path, rom_hash: str) -> None:
    """Require human Pocket evidence after emulator-only r210 false passes."""
    if not path.is_file():
        raise SystemExit(f"REFUSED: Pocket hardware signoff is absent: {path}")
    data = json.loads(path.read_text())
    failures: list[str] = []
    if data.get("schema") != "penta-pocket-hardware-signoff-v1":
        failures.append("Pocket hardware signoff schema is unsupported")
    if data.get("status") != "passed":
        failures.append("Pocket hardware signoff did not pass")
    if data.get("rom_sha256") != rom_hash:
        failures.append("Pocket hardware signoff ROM hash mismatch")
    required = {
        "pickup_alignment",
        "wall_stability",
        "stage1_hazard_materials",
        "menu_item_close",
        "low_health_stability",
        "purple_splash_absent",
    }
    checks = data.get("checks")
    if not isinstance(checks, dict) or set(checks) != required:
        failures.append("Pocket hardware signoff inventory is incomplete")
    elif any(value != "passed" for value in checks.values()):
        failures.append("Pocket hardware signoff contains a failed check")
    if not str(data.get("tested_filename", "")).strip():
        failures.append("Pocket hardware signoff lacks the tested filename")
    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))


def north_receipt_failures(data: object, rom: Path, rom_hash: str) -> list[str]:
    """Return every reason a cached north receipt is weaker than release."""

    if not isinstance(data, dict):
        return ["north-route receipt is not a JSON object"]
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    require(data.get("status") == "pass", "north-route status is not pass")
    require(
        data.get("candidate_sha256") == rom_hash,
        "north-route candidate SHA-256 mismatch",
    )
    try:
        candidate_path_matches = (
            Path(str(data.get("candidate_rom", ""))).resolve() == rom
        )
    except (OSError, ValueError):
        candidate_path_matches = False
    require(candidate_path_matches, "north-route candidate path mismatch")
    for field, expected in NORTH_RELEASE_PARAMETERS.items():
        require(
            data.get(field) == expected,
            f"north-route {field} is not the release value {expected}",
        )
    require(data.get("target_only_policy") is True,
            "north-route target-only policy is absent")
    require(
        data.get("input_route")
        == "cold GAME START; hold UP; no gameplay memory writes",
        "north-route input is not the release cold UP-only route",
    )
    for label in ("candidate", "candidate_replay"):
        report = data.get(label)
        require(isinstance(report, dict), f"north-route {label} report is absent")
        if isinstance(report, dict):
            require(report.get("status") == "ok",
                    f"north-route {label} report is not complete")
            require(report.get("target_camera") == "03A4",
                    f"north-route {label} report missed target camera")
            require(report.get("target_settle_frames") == "60",
                    f"north-route {label} report used the wrong settle window")

    boolean_fields = (
        "candidate_replay_exact",
        "candidate_replay_attributes_exact",
        "settled_final_state_ok",
        "service_frame_presentations_exact",
        "candidate_attribute_trajectory_exact",
        "progress_route_geometry_exact",
        "progress_route_viewports_exact",
        "target_only_static_route_ok",
    )
    for field in boolean_fields:
        require(data.get(field) is True, f"north-route {field} is not true")

    require(data.get("packed_room_bytes") == 24 * 24,
            "north-route packed room is not 24x24")
    require(data.get("packed_room_differences") == 0,
            "north-route packed room differs from stock")
    require(data.get("terrain_differences") == 0,
            "north-route visible terrain differs from stock")

    world = data.get("world_template")
    if not isinstance(world, dict):
        failures.append("north-route world-template evidence is absent")
    else:
        require(world.get("bytes") == 0x880,
                "north-route world-template coverage is incomplete")
        require(world.get("entry_differences") == 0,
                "north-route world template differs at entry")
        require(world.get("exact_at_entry") is True,
                "north-route world template is not exact at entry")

    metatiles = data.get("metatile_table")
    if not isinstance(metatiles, dict):
        failures.append("north-route metatile evidence is absent")
    else:
        require(metatiles.get("bytes") == 0x400,
                "north-route metatile coverage is incomplete")
        require(metatiles.get("differences") == 0,
                "north-route metatile table differs from stock")
        require(metatiles.get("exact_at_entry") is True,
                "north-route metatile table is not exact at entry")

    terrain = data.get("visible_terrain_overlap")
    if not isinstance(terrain, dict):
        failures.append("north-route visible-terrain evidence is absent")
    else:
        require(
            type(terrain.get("compared_bytes")) is int
            and terrain["compared_bytes"] > 0,
            "north-route visible-terrain comparison is empty",
        )
        require(terrain.get("differences") == 0,
                "north-route visible-terrain comparison differs")
        for field in (
            "edge_signatures_stable",
            "edge_signatures_nonblank",
            "padding_stable_and_equal",
        ):
            require(terrain.get(field) is True,
                    f"north-route visible terrain lacks {field}")

    trajectory = data.get("full_route_viewport_integrity")
    if not isinstance(trajectory, dict):
        failures.append("north-route full-route viewport evidence is absent")
    else:
        require(
            type(trajectory.get("matched_records")) is int
            and trajectory["matched_records"] > 0,
            "north-route has no exact display-state matches",
        )
        require(
            type(trajectory.get("progress_matched_records")) is int
            and trajectory["progress_matched_records"] > 0,
            "north-route has no progress-state matches",
        )
        for field in (
            "unmatched_progress_records",
            "unexpected_logical_state_records",
            "unmatched_display_state_records",
            "unmatched_service_presentation_records",
            "maximum_viewport_tile_differences",
            "maximum_progress_viewport_tile_differences",
        ):
            require(trajectory.get(field) == 0,
                    f"north-route trajectory {field} is not zero")
        require(
            type(
                trajectory.get("maximum_service_viewport_tile_differences"),
            ) is int
            and trajectory["maximum_service_viewport_tile_differences"] <= 0,
            "north-route service-frame presentation differs",
        )
        attributes = trajectory.get("candidate_attribute_integrity")
        if not isinstance(attributes, dict):
            failures.append("north-route candidate attribute evidence is absent")
        else:
            require(
                type(attributes.get("records")) is int
                and attributes["records"] > 0,
                "north-route candidate attribute trajectory is empty",
            )
            require(
                type(attributes.get("visible_cells_checked")) is int
                and attributes["visible_cells_checked"] > 0,
                "north-route candidate checked no visible attributes",
            )
            require(attributes.get("mismatch_frames") == 0,
                    "north-route candidate has attribute mismatch frames")
            require(attributes.get("mismatch_cells") == 0,
                    "north-route candidate has attribute mismatch cells")
            require(attributes.get("unsafe_high_bit_cells") == 0,
                    "north-route candidate has unsafe attribute bits")
            require(attributes.get("exact") is True,
                    "north-route candidate attributes are not oracle-exact")

    settled_checks = {
        "scene_02",
        "gameplay_active",
        "hdma_idle",
        "svbk_readable",
        "gameplay_lcdc_active",
    }
    for label in (
        "candidate_settled_final_state",
        "candidate_replay_settled_final_state",
    ):
        settled = data.get(label)
        if not isinstance(settled, dict):
            failures.append(f"north-route {label} is absent")
            continue
        require(settled.get("passed") is True,
                f"north-route {label} did not pass")
        checks = settled.get("checks")
        require(
            isinstance(checks, dict)
            and set(checks) == settled_checks
            and all(value is True for value in checks.values()),
            f"north-route {label} hardware checks are incomplete",
        )

    replay_artifacts = data.get("candidate_replay_artifacts")
    if not isinstance(replay_artifacts, dict):
        failures.append("north-route deterministic replay artifacts are absent")
    else:
        require(
            set(replay_artifacts) == NORTH_REPLAY_ARTIFACTS,
            "north-route deterministic replay artifact inventory is incomplete",
        )
        require(
            all(
                isinstance(item, dict)
                and item.get("present") is True
                and item.get("exact") is True
                and isinstance(item.get("candidate_sha256"), str)
                and len(item["candidate_sha256"]) == 64
                and item.get("replay_sha256") == item["candidate_sha256"]
                for item in replay_artifacts.values()
            ),
            "north-route deterministic replay artifacts are incomplete",
        )
    return failures


def flatten_lsblk_devices(devices: object) -> list[dict[str, object]]:
    """Flatten lsblk's recursive JSON device inventory."""

    if not isinstance(devices, list):
        return []
    flattened: list[dict[str, object]] = []
    for device in devices:
        if not isinstance(device, dict):
            continue
        flattened.append(device)
        flattened.extend(flatten_lsblk_devices(device.get("children")))
    return flattened


def mount_identity_failures(
    findmnt_data: object,
    lsblk_data: object,
    *,
    mount: Path,
    expected_device: Path,
    expected_uuid: str,
    expected_label: str,
) -> list[str]:
    """Validate parsed mount metadata without touching a block device."""

    failures: list[str] = []
    expected_mount = Path(os.path.realpath(mount))
    expected_source = Path(os.path.realpath(expected_device))

    filesystems = (
        findmnt_data.get("filesystems")
        if isinstance(findmnt_data, dict)
        else None
    )
    if not isinstance(filesystems, list) or len(filesystems) != 1:
        failures.append("findmnt did not identify exactly one mounted filesystem")
    else:
        filesystem = filesystems[0]
        if not isinstance(filesystem, dict):
            failures.append("findmnt filesystem record is malformed")
        else:
            source = Path(os.path.realpath(str(filesystem.get("source", ""))))
            target = Path(os.path.realpath(str(filesystem.get("target", ""))))
            if source != expected_source:
                failures.append("mount source is not the expected Pocket partition")
            if target != expected_mount:
                failures.append("Pocket partition is mounted at an unexpected target")
            if filesystem.get("fstype") != "vfat":
                failures.append("Pocket partition is not mounted as vfat")
            options = filesystem.get("options")
            option_set = set(options.split(",")) if isinstance(options, str) else set()
            if "rw" not in option_set or "ro" in option_set:
                failures.append("Pocket partition is not mounted read-write")

    devices = flatten_lsblk_devices(
        lsblk_data.get("blockdevices") if isinstance(lsblk_data, dict) else None
    )
    matches = [
        device
        for device in devices
        if Path(os.path.realpath(str(device.get("path", "")))) == expected_source
    ]
    if len(matches) != 1:
        failures.append("lsblk did not identify exactly one expected Pocket partition")
    else:
        device = matches[0]
        if device.get("type") != "part":
            failures.append("expected Pocket device is not a partition")
        if device.get("fstype") != "vfat":
            failures.append("expected Pocket partition does not contain vfat")
        if device.get("label") != expected_label:
            failures.append("Pocket filesystem label mismatch")
        if device.get("uuid") != expected_uuid:
            failures.append("Pocket filesystem UUID mismatch")
        if device.get("ro") not in (False, 0, "0"):
            failures.append("Pocket block device is read-only")
        mountpoints = device.get("mountpoints")
        if not isinstance(mountpoints, list) or expected_mount not in {
            Path(os.path.realpath(str(item)))
            for item in mountpoints
            if item is not None
        }:
            failures.append("lsblk does not bind the expected mount to the Pocket")
    return failures


def require_mount_identity(
    mount: Path,
    expected_device: Path,
    expected_uuid: str,
    expected_label: str,
) -> dict[str, object]:
    """Fail closed unless the exact writable Pocket card owns the mount."""

    if not mount.is_dir():
        raise SystemExit(f"REFUSED: Pocket mount is unavailable: {mount}")
    try:
        device = expected_device.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise SystemExit(
            f"REFUSED: expected Pocket partition is unavailable: {expected_device}"
        ) from error
    try:
        mode = device.stat().st_mode
    except OSError as error:
        raise SystemExit(
            f"REFUSED: cannot inspect expected Pocket partition: {device}: {error}"
        ) from error
    if not stat.S_ISBLK(mode):
        raise SystemExit(f"REFUSED: expected Pocket path is not a block device: {device}")
    if not expected_uuid or not expected_label:
        raise SystemExit("REFUSED: expected Pocket UUID and label must be non-empty")

    commands = {
        "findmnt": [
            "findmnt", "--json", "--target", str(mount),
            "--output", "SOURCE,TARGET,FSTYPE,OPTIONS",
        ],
        "lsblk": [
            "lsblk", "--json", "--paths",
            "--output", "PATH,TYPE,FSTYPE,LABEL,UUID,RO,MOUNTPOINTS",
            str(device),
        ],
    }
    parsed: dict[str, object] = {}
    for name, command in commands.items():
        try:
            completed = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10.0,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise SystemExit(
                f"REFUSED: Pocket mount identity command failed: {name}: {error}"
            ) from error
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise SystemExit(
                f"REFUSED: Pocket mount identity command failed: {name}: {detail}"
            )
        try:
            parsed[name] = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise SystemExit(
                f"REFUSED: Pocket mount identity command returned invalid JSON: {name}"
            ) from error

    failures = mount_identity_failures(
        parsed["findmnt"],
        parsed["lsblk"],
        mount=mount,
        expected_device=device,
        expected_uuid=expected_uuid,
        expected_label=expected_label,
    )
    if failures:
        raise SystemExit("REFUSED: " + "; ".join(failures))
    return {
        "device": str(device),
        "mount": str(mount),
        "fstype": "vfat",
        "label": expected_label,
        "uuid": expected_uuid,
        "read_write": True,
    }


def previous_alias_destination(alias: Path, old_hash: str) -> Path:
    """Choose a new archival name without replacing an earlier ROM."""

    stem = f"{alias.stem}-{old_hash[:12]}-previous"
    destination = alias.with_name(f"{stem}{alias.suffix}")
    suffix = 2
    while destination.exists():
        destination = alias.with_name(f"{stem}-{suffix}{alias.suffix}")
        suffix += 1
    return destination


def stage_alias_copy(rom: Path, alias: Path, rom_hash: str) -> Path:
    """Fully stage and hash one alias beside its final Pocket pathname."""

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=alias.parent,
            prefix=f".{alias.stem}-{rom_hash[:12]}-",
            suffix=".pending",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
        shutil.copy2(rom, temporary_path)
        if sha256(temporary_path) != rom_hash:
            raise RuntimeError(f"staged Pocket alias hash mismatch: {alias}")
        return temporary_path
    except BaseException:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def update_mutable_aliases(
    rom: Path,
    aliases: tuple[Path, ...],
    rom_hash: str,
) -> dict[Path, Path | None]:
    """Stage all aliases, then commit them as one rollback-safe transaction."""

    if len(set(aliases)) != len(aliases):
        raise ValueError("Pocket mutable alias paths must be unique")
    staged: dict[Path, Path] = {}
    preserved: dict[Path, Path | None] = {alias: None for alias in aliases}
    changed: list[Path] = []
    moved_old: list[Path] = []
    installed: list[Path] = []
    try:
        # Do not mutate either public alias until both complete candidate files
        # exist and have already passed their source hash check.
        for alias in aliases:
            staged[alias] = stage_alias_copy(rom, alias, rom_hash)
        os.sync()
        for alias in aliases:
            if alias.exists() and sha256(alias) == rom_hash:
                continue
            changed.append(alias)
            if alias.exists():
                old_hash = sha256(alias)
                preserved[alias] = previous_alias_destination(alias, old_hash)

        try:
            for alias in changed:
                previous = preserved[alias]
                if previous is not None:
                    alias.rename(previous)
                    moved_old.append(alias)
            for alias in changed:
                staged[alias].rename(alias)
                installed.append(alias)

            # Flush the immutable copy and both aliases before trusting their
            # post-deployment digests. A failed digest enters the same rollback
            # path as a failed rename, restoring every former mutable alias.
            os.sync()
            mismatches = [
                alias for alias in aliases
                if not alias.is_file() or sha256(alias) != rom_hash
            ]
            if mismatches:
                raise RuntimeError(
                    "post-flush Pocket alias hash mismatch: "
                    + ", ".join(str(path) for path in mismatches)
                )
        except BaseException as error:
            rollback_errors: list[str] = []
            for alias in reversed(installed):
                try:
                    if not alias.exists():
                        raise FileNotFoundError(alias)
                    alias.rename(staged[alias])
                except OSError as rollback_error:
                    rollback_errors.append(f"{alias}: {rollback_error}")
            for alias in reversed(moved_old):
                previous = preserved[alias]
                try:
                    if previous is None or not previous.exists() or alias.exists():
                        raise FileNotFoundError(previous or alias)
                    previous.rename(alias)
                except OSError as rollback_error:
                    rollback_errors.append(f"{alias}: {rollback_error}")
            os.sync()
            if rollback_errors:
                raise RuntimeError(
                    "Pocket alias transaction failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from error
            raise
        return preserved
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy a verified ROM to the Pocket; failed-suite ROMs are refused."
    )
    parser.add_argument("rom", type=Path)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--visual-receipt",
        type=Path,
        help=(
            "formal-release exact-ROM aggregate receipt from "
            "verify_pocket_visual_receipts.py"
        ),
    )
    parser.add_argument(
        "--hardware-receipt",
        type=Path,
        help="formal-release hash-bound human Pocket signoff for the exact ROM",
    )
    parser.add_argument(
        "--hardware-test-ready-receipt",
        type=Path,
        help=(
            "explicit pre-signoff hardware-test mode: fresh exact-ROM READY "
            "receipt from verify_stage1_reported_regressions_ready.py"
        ),
    )
    parser.add_argument("--mount", type=Path, default=DEFAULT_MOUNT)
    parser.add_argument(
        "--expected-device",
        type=Path,
        default=DEFAULT_POCKET_DEVICE,
        help="block partition that must own --mount",
    )
    parser.add_argument(
        "--expected-uuid",
        default=DEFAULT_POCKET_UUID,
        help="filesystem UUID required on --expected-device",
    )
    parser.add_argument(
        "--expected-label",
        default=DEFAULT_POCKET_LABEL,
        help="filesystem label required on --expected-device",
    )
    parser.add_argument(
        "--deployment-receipt",
        type=Path,
        help=(
            "local post-copy manifest; defaults to "
            "tmp/pocket-deploy/<ROM hash>/deployment.json"
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rom = args.rom.resolve()
    if not rom.is_file():
        raise SystemExit(f"REFUSED: ROM does not exist: {rom}")
    rom_hash = sha256(rom)

    hardware_test = args.hardware_test_ready_receipt is not None
    hardware_test_ready: dict[str, object] | None = None
    if hardware_test:
        if args.visual_receipt is not None or args.hardware_receipt is not None:
            raise SystemExit(
                "REFUSED: hardware-test READY mode cannot be combined with "
                "formal visual or hardware receipts"
            )
        hardware_test_ready = require_hardware_test_ready_receipt(
            args.hardware_test_ready_receipt.resolve(), rom, rom_hash
        )
        deployment_mode = "hardware-test-awaiting-human-signoff"
    else:
        missing = []
        if args.visual_receipt is None:
            missing.append("--visual-receipt")
        if args.hardware_receipt is None:
            missing.append("--hardware-receipt")
        if missing:
            raise SystemExit(
                "REFUSED: formal release deployment requires " + ", ".join(missing)
            )
        require_full_receipt(args.receipt.resolve(), rom, rom_hash)
        require_visual_incident_receipt(args.visual_receipt.resolve(), rom_hash)
        require_hardware_receipt(args.hardware_receipt.resolve(), rom_hash)
        deployment_mode = "formal-release"

    mount = args.mount.resolve()
    mount_identity = require_mount_identity(
        mount,
        args.expected_device,
        args.expected_uuid,
        args.expected_label,
    )
    destination = append_only_destination(mount, rom_hash)
    alias = destination.parent / f"{DEST_PREFIX}.gbc"
    latest_alias = destination.parent / LATEST_ALIAS_NAME
    aliases = (alias, latest_alias)
    deployment_receipt = (
        args.deployment_receipt.resolve()
        if args.deployment_receipt is not None
        else ROOT / "tmp" / "pocket-deploy" / rom_hash[:12] / "deployment.json"
    )
    if not destination.parent.is_dir():
        raise SystemExit(
            f"REFUSED: Pocket SameBoy directory is unavailable: {destination.parent}"
        )
    if destination.exists() and sha256(destination) != rom_hash:
        raise SystemExit(
            f"REFUSED: append-only Pocket filename has different contents: {destination}"
        )

    # Re-run the historically fragile route on the exact bytes being deployed.
    north_output = ROOT / "tmp" / "pocket-deploy" / rom_hash[:12] / "stage1-north"
    north_output.mkdir(parents=True, exist_ok=True)
    north_receipt = north_output / "receipt.json"
    north = json.loads(north_receipt.read_text()) if north_receipt.is_file() else {}
    north_failures = north_receipt_failures(north, rom, rom_hash)
    if north_failures:
        subprocess.run(
            [
                sys.executable,
                str(NORTH_VERIFIER),
                str(rom),
                "--target-camera",
                "0x03A4",
                "--target-room",
                "1",
                "--target-settle",
                "60",
                "--frames",
                "3000",
                "--play-frames",
                "2400",
                "--dynamic-prefix",
                "0",
                "--target-only",
                "--output",
                str(north_output),
            ],
            cwd=ROOT,
            check=True,
        )
        north = json.loads(north_receipt.read_text())
        north_failures = north_receipt_failures(north, rom, rom_hash)
    else:
        print(f"PASS: reused hash-bound Stage 1 north receipt: {north_receipt}")
    if north_failures:
        raise SystemExit(
            "REFUSED: hash-bound Stage 1 north-route receipt is insufficient: "
            + "; ".join(north_failures)
        )

    if args.dry_run:
        dry_status = (
            "eligible-hardware-test-dry-run"
            if hardware_test
            else "eligible-formal-release-dry-run"
        )
        write_json_atomic(
            deployment_receipt,
            {
                "schema": "penta-pocket-deployment-v1",
                "status": dry_status,
                "deployment_mode": deployment_mode,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source": str(rom),
                "source_sha256": rom_hash,
                "mount": str(mount),
                "mount_identity": mount_identity,
                "immutable": str(destination),
                "alias": str(alias),
                "latest_alias": str(latest_alias),
                "mutable_aliases": [str(path) for path in aliases],
                "full_receipt": (
                    str(args.receipt.resolve()) if not hardware_test else None
                ),
                "visual_receipt": (
                    str(args.visual_receipt.resolve()) if not hardware_test else None
                ),
                "hardware_receipt": (
                    str(args.hardware_receipt.resolve()) if not hardware_test else None
                ),
                "hardware_test_ready_receipt": hardware_test_ready,
                "north_receipt": str(north_receipt),
                "north_receipt_sha256": sha256(north_receipt),
            },
        )
        print(
            f"PASS: {rom_hash} is eligible for Pocket deployment -> "
            f"{destination} + {alias} + {latest_alias} (dry run)"
        )
        print(f"  receipt:   {deployment_receipt}")
        return 0

    if not destination.exists():
        shutil.copy2(rom, destination)
        if sha256(destination) != rom_hash:
            raise SystemExit("ERROR: post-copy hash-qualified Pocket ROM mismatch")

    preserved_aliases = update_mutable_aliases(rom, aliases, rom_hash)

    deployed_hashes = {
        destination: sha256(destination),
        alias: sha256(alias),
        latest_alias: sha256(latest_alias),
    }
    mismatches = [path for path, value in deployed_hashes.items() if value != rom_hash]
    if mismatches:
        raise SystemExit(
            "ERROR: post-flush Pocket hash mismatch: "
            + ", ".join(str(path) for path in mismatches)
        )
    deployment = {
        "schema": "penta-pocket-deployment-v1",
        "status": (
            "deployed-awaiting-human-signoff"
            if hardware_test
            else "deployed"
        ),
        "deployment_mode": deployment_mode,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(rom),
        "source_sha256": rom_hash,
        "mount": str(mount),
        "mount_identity": mount_identity,
        "immutable": {
            "path": str(destination),
            "sha256": deployed_hashes[destination],
        },
        "alias": {
            "path": str(alias),
            "sha256": deployed_hashes[alias],
        },
        "latest_alias": {
            "path": str(latest_alias),
            "sha256": deployed_hashes[latest_alias],
        },
        "mutable_aliases": [
            {
                "path": str(path),
                "sha256": deployed_hashes[path],
            }
            for path in aliases
        ],
        "preserved_previous_alias": (
            {
                "path": str(preserved_aliases[alias]),
                "sha256": sha256(preserved_aliases[alias]),
            }
            if preserved_aliases[alias] is not None
            else None
        ),
        "preserved_previous_latest_alias": (
            {
                "path": str(preserved_aliases[latest_alias]),
                "sha256": sha256(preserved_aliases[latest_alias]),
            }
            if preserved_aliases[latest_alias] is not None
            else None
        ),
        "full_receipt": str(args.receipt.resolve()) if not hardware_test else None,
        "visual_receipt": (
            str(args.visual_receipt.resolve()) if not hardware_test else None
        ),
        "hardware_receipt": (
            str(args.hardware_receipt.resolve()) if not hardware_test else None
        ),
        "hardware_test_ready_receipt": hardware_test_ready,
        "north_receipt": str(north_receipt),
        "north_receipt_sha256": sha256(north_receipt),
    }
    write_json_atomic(deployment_receipt, deployment)
    print(f"PASS: deployed and verified {rom_hash}")
    print(f"  immutable: {destination}")
    print(f"  alias:     {alias}")
    print(f"  latest:    {latest_alias}")
    for public_alias, previous in preserved_aliases.items():
        if previous is not None:
            print(f"  previous {public_alias.name}: {previous}")
    print(f"  receipt:   {deployment_receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
