#!/usr/bin/env python3
"""Bind the Pocket Stage-1 visual incident gates to one exact ROM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from verify_pickup_class_palettes import PICKUPS
from verify_stage1_hazard_menu import hazard_coverage_is_complete
from verify_menu_window_order import expected_window_lut, sha256_bytes
from menu_commit_protocol import NAME as COMMIT_PROTOCOL_NAME
from verify_stage1_tilemap_copy import (
    ORDINARY_ATTRIBUTE_SCOPE,
    PUBLICATION_ORACLE_SCHEMA,
    SEMANTIC_OVERLAY_OWNER,
    publication_oracle_report_failures,
    reviewed_stage1_lut,
    reviewed_postcomputed_copier,
)


ROOT = Path(__file__).resolve().parents[2]
PICKUP_GENERATOR_SCHEMA = "penta-stage1-current-pickup-state-v1"
PICKUP_HOST_SCHEMA = "penta-dragon-dx-pickup-current-host-palettes-v1"
STAGE_CARD_SCHEMA = "penta-stage-card-stability-v1"
PICKUP_GENERATOR_CHECKS = (
    "state CRC is bound to candidate",
    "state is active Stage 1 gameplay",
    "candidate WRAM helper is initialized",
    "hardware is settled at save",
    "semantic pickup was visible with no mismatch",
    "terminal probe sample remains Stage 1-owned",
    "saved state independently records active Stage 1",
)
PICKUP_HOST_CHECKS = (
    "current state is candidate-bound",
    "coordinate host is source/map exact and visible",
    "all 73 target VRAM graphics match the candidate offline",
    "candidate Stage-1 helper and semantic LUT are internally exact",
    "all 19 pickup form replays completed",
    "all 19 pickup forms passed every live gate",
    "both physical hosts use exact raw semantic attrs with no BG0 fallback",
    "all form runs hit the main loop at least 8 times",
    "all form runs execute a current-ROM tile copy",
    "all form runs execute the coordinate-host decision",
    "all form runs remain in Stage 1",
    "all form runs load candidate BG0-BG5 CRAM exactly",
    "all live pickup graphics remain candidate-exact",
    "one valid screenshot per pickup form",
    "contact sheet covers all 19 pickup forms",
)
PICKUP_FORM_GATES = (
    "main_loop_hits_at_least_8",
    "tile_copy_executed",
    "coordinate_host_decision_executed",
    "stage1_gameplay",
    "candidate_cram_bg0_bg5_exact",
    "candidate_vbk0_pickup_gfx_exact",
    "both_physical_hosts_exact_raw_semantic_attrs_no_bg0_fallback",
    "displayed_host_fully_visible",
)
STAGE_CARD_CHECKS = (
    "rendered STAGE card retires without exposing overwritten glyph graphics",
    "outgoing title never becomes a nonuniform monochrome image",
    "exact map-flip palette handoff is installed",
    "first route completed",
    "replay route completed",
    "selector observed",
    "splash observed",
    "frame-state replay exact",
    "rendered-frame replay exact",
    "stock saved-game route completed",
    "saved-game route stays within stock timing bound",
    "selector attributes remain palette 0",
    "splash attributes remain palette 0",
    "selector BG0 is temporally stable",
    "splash keeps the reviewed colored card or a raster-verified terminal black fade",
    "selector never becomes monochrome",
    "gameplay handoff preserves only the complete final STAGE card",
    "first dungeon handoff has no partial map frames",
    "Stage-1 BG0 is resident before the first dungeon tile appears",
    "blank-SRAM routes start without save artifacts or fixture writes",
    "blank-SRAM natural routes reach the Stage splash and gameplay",
    "blank-SRAM pregame captures every consecutive rendered frame",
    "blank-SRAM pregame frame-state and raster replay are exact",
    "blank-SRAM STAGE splash attrs remain stable through retirement",
    "blank-SRAM splash keeps the reviewed card or raster-verified terminal black",
    "blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state",
    "blank-SRAM first dungeon map and attributes are atomic",
    "blank-SRAM Stage-1 BG0 precedes the first dungeon tile",
)


def file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing visual receipt: {path}")
    return json.loads(path.read_text())


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_report(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing visual report: {path}")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def report_int(report: dict[str, str], field: str) -> int | None:
    try:
        return int(report[field])
    except (KeyError, ValueError):
        return None


def validate_tilemap_reports(
    tilemaps: list[tuple[Path, dict[str, str]]],
    rom_sha256: str,
    failures: list[str],
    rom_bytes: bytes,
) -> dict[str, int]:
    """Bind ordinary pre-overlay publications to independent owned models."""
    # Authenticate against the reviewed layout allowlists, not arbitrary
    # candidate bytes or the receipt's self-declared expected identities.
    copier_sha = sha256_bytes(reviewed_postcomputed_copier(rom_bytes))
    lut_sha = sha256_bytes(reviewed_stage1_lut(rom_bytes))
    for path, report in tilemaps:
        failures.extend(publication_oracle_report_failures(
            report,
            expected_rom_sha256=rom_sha256,
            expected_copier_sha256=copier_sha,
            expected_lut_sha256=lut_sha,
            require_atomic=True,
            label=f"Stage-1 tilemap {path.name}",
        ))

    def total(field: str) -> int:
        return sum((report_int(report, field) or 0) for _, report in tilemaps)

    evidence = {
        "exact_copies": total("exact_copies"),
        "atomic_completions": total("atomic_completions"),
        "pure_completions": total("pure_completions"),
        "publication_model_copies": total("publication_model_copies"),
        "ordinary_attribute_model_copies": total(
            "ordinary_attribute_model_copies"
        ),
        "mismatch_copies": total("mismatch_copies"),
        "attribute_mismatch_copies": total("attribute_mismatch_copies"),
    }
    destinations = {
        destination
        for _, report in tilemaps
        for destination in report.get("destinations", "").split(",")
        if destination
    }
    require(len(tilemaps) >= 3,
            "Stage-1 tilemap audit lacks terrain/hazard/miniboss fixtures",
            failures)
    require(evidence["exact_copies"] >= 3000,
            "Stage-1 tilemap copy coverage is below 3000 publications",
            failures)
    require(evidence["atomic_completions"] >= len(tilemaps),
            "Stage-1 tilemap fixtures lack dirty two-plane publications",
            failures)
    require(
        evidence["publication_model_copies"]
        == evidence["atomic_completions"] + evidence["pure_completions"],
        "Stage-1 tile publications lack entry-owned source models",
        failures,
    )
    require(
        evidence["ordinary_attribute_model_copies"]
        == evidence["atomic_completions"],
        "Stage-1 dirty publications lack canonical ordinary attr models",
        failures,
    )
    require(evidence["mismatch_copies"] == 0,
            "Stage-1 wall/tile publication mismatch observed", failures)
    require(evidence["attribute_mismatch_copies"] == 0,
            "Stage-1 wall attribute publication mismatch observed", failures)
    require(destinations == {"9800", "9C00"},
            "Stage-1 tilemap audit did not exercise both physical maps",
            failures)
    return evidence


def runtime_lut_contract(probe: dict) -> bool:
    """Accept only clean LUTs or the four independently reviewed wall roles.

    Room-$01 temporarily specializes tiles24/27/30/33 from BG0 to BG6.
    The independent north-wall gate remains mandatory. Diagnostic mismatch
    counters alone are not unexpected corruption when they name these roles.
    Missing, unreadable, unknown or inconsistent evidence remains a failure.
    """
    fields = ('runtime_lut_mismatch_frames', 'runtime_lut_mismatch_cells',
              'runtime_lut_mismatch_max')
    values = [probe.get(key) for key in fields]
    if any(type(value) is not int or value < 0 for value in values):
        return False
    frames, cells, maximum = values
    pairs = probe.get('runtime_lut_mismatch_pairs')
    if not isinstance(pairs, dict):
        return False
    if probe.get('runtime_lut_dma_unreadable_frames') != 0:
        return False
    if probe.get('first_runtime_lut_dma_unreadable', '') != '':
        return False
    if values == [0, 0, 0]:
        return pairs == {}
    expected = {'24/6/0', '27/6/0', '30/6/0', '33/6/0'}
    return (set(pairs) == expected and frames > 0 and 0 < maximum <= 4
            and all(type(n) is int and 0 < n <= frames for n in pairs.values())
            and sum(pairs.values()) == cells
            and frames <= cells <= frames * maximum)


def menu_window_report_failures(
    report: dict[str, str],
    *,
    rom: Path,
    rom_sha256: str,
    attr_mode: str,
    attr_lut_sha256: str,
) -> list[str]:
    """Validate candidate and route binding for the two-plane Window gate."""
    failures: list[str] = []
    report_rom = report.get("rom")
    try:
        rom_bound = bool(report_rom) and Path(report_rom).resolve() == rom
    except (OSError, ValueError):
        rom_bound = False
    window_frames = report_int(report, "window_frames")
    attr_checked_frames = report_int(report, "attr_checked_frames")
    force_alias_frame = report_int(report, "route_force_alias_frame")
    force_commit_frame = report_int(report, "route_force_commit_frame")
    map_alias_frames = report_int(report, "map_alias_frames")
    route_open_frame = report_int(report, "route_open_frame")
    route_close_frame = report_int(report, "route_close_frame")
    route_frame_limit = report_int(report, "route_frame_limit")

    require(rom_bound, "menu Window receipt ROM path mismatch", failures)
    require(report.get("rom_sha256") == rom_sha256,
            "menu Window receipt ROM hash mismatch", failures)
    require(report.get("attr_mode") == attr_mode,
            "menu Window receipt palette mode mismatch", failures)
    require(report.get("attr_lut_sha256") == attr_lut_sha256,
            "menu Window receipt palette LUT mismatch", failures)
    require(window_frames is not None and window_frames > 0,
            "menu Window route has no visible frames", failures)
    require(window_frames is not None and attr_checked_frames == window_frames,
            "menu Window VBK1 coverage is incomplete", failures)
    require(report_int(report, "bad_frames") == 0,
            "menu Window tile publication mismatch observed", failures)
    require(report_int(report, "attr_bad_frames") == 0,
            "menu Window VBK1 mismatch observed", failures)
    require(report_int(report, "attr_mismatch_cells") == 0,
            "menu Window contains noncanonical palette cells", failures)
    require(report_int(report, "attr_unsafe_cells") == 0,
            "menu Window contains unsafe VBK1 bits", failures)
    require((report_int(report, "attr_entry_frames") or 0) > 0,
            "menu Window entry edge lacks VBK1 coverage", failures)
    require((report_int(report, "attr_settled_frames") or 0) > 0,
            "settled menu Window lacks VBK1 coverage", failures)
    require(
        (report_int(report, "attr_exit_frames") or 0) > 0
        or (report_int(report, "window_hidden_at_close_frames") or 0) > 0,
        "menu Window exit edge lacks VBK1 coverage",
        failures,
    )
    require(report_int(report, "route_stale_frame") == -1,
            "aggregate menu Window evidence uses a stale-Window fixture", failures)
    require(
        route_open_frame is not None
        and route_close_frame is not None
        and route_frame_limit is not None
        and route_open_frame >= 0
        and route_close_frame > route_open_frame
        and route_frame_limit > route_close_frame,
        "aggregate menu Window route does not cross menu close",
        failures,
    )
    require(report_int(report, "window_frames_after_close") == 0,
            "hardware Window remained visible after menu close", failures)
    require(
        force_commit_frame is not None
        and route_close_frame is not None
        and force_commit_frame == route_close_frame,
        "menu Window evidence did not force the completed-map close-edge race",
        failures,
    )
    require(
        report_int(report, "forced_commit") == 1
        and report_int(report, "forced_commit_consumed") == 1
        and report.get("forced_commit_protocol") == COMMIT_PROTOCOL_NAME,
        "menu Window completed-map close-edge fixture was not consumed",
        failures,
    )
    require((report_int(report, "post_close_selector_checked_frames") or 0) > 0,
            "menu Window evidence lacks stationary post-close selector coverage",
            failures)
    require(report_int(report, "post_close_selector_alias_frames") == 0,
            "post-close gameplay BG aliases the former Window map", failures)
    require(report_int(report, "post_close_hud_leak_frames") == 0,
            "post-close gameplay contains native menu HUD rows", failures)
    require(report.get("first_post_close_alias") == "none",
            "post-close selector alias was recorded", failures)
    require(
        map_alias_frames is not None
        and force_alias_frame is not None
        and map_alias_frames >= 0
        and (
            (force_alias_frame < 0 and map_alias_frames == 0)
            or (
                force_alias_frame >= 0
                and route_frame_limit is not None
                and force_alias_frame < route_frame_limit
                and map_alias_frames <= 1
            )
        ),
        "menu Window aliased the visible gameplay map",
        failures,
    )
    return failures


def sha256_text_is_valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def paths_match(value: object, expected: Path) -> bool:
    try:
        return isinstance(value, str) and Path(value).resolve() == expected.resolve()
    except (OSError, ValueError):
        return False


def require_all_checks(
    receipt: dict,
    required_names: tuple[str, ...],
    label: str,
    failures: list[str],
) -> dict:
    checks = receipt.get("checks")
    require(isinstance(checks, dict) and bool(checks),
            f"{label} checks are missing", failures)
    if not isinstance(checks, dict):
        return {}
    missing = sorted(set(required_names) - set(checks))
    require(not missing,
            f"{label} required checks are missing: {', '.join(missing)}",
            failures)
    require(all(value is True for value in checks.values()),
            f"{label} contains a non-passing check", failures)
    return checks


def validate_sha256_file(
    path: Path,
    expected_sha256: object,
    label: str,
    failures: list[str],
) -> str | None:
    require(path.is_file(), f"{label} is missing: {path}", failures)
    require(sha256_text_is_valid(expected_sha256),
            f"{label} has no valid receipt SHA-256", failures)
    if not path.is_file():
        return None
    observed = file_digest(path, "sha256")
    require(observed == expected_sha256,
            f"{label} SHA-256 mismatch", failures)
    return observed


def validate_bound_artifact(
    value: object,
    directory: Path,
    expected_sha256: object,
    label: str,
    failures: list[str],
    *,
    expected_name: str | None = None,
) -> Path | None:
    if not isinstance(value, str) or not value:
        require(False, f"{label} path is missing", failures)
        return None
    path = Path(value)
    if not path.is_absolute():
        path = directory / path
    try:
        resolved = path.resolve()
        expected_directory = directory.resolve()
    except (OSError, ValueError):
        require(False, f"{label} path is invalid", failures)
        return None
    require(resolved.parent == expected_directory,
            f"{label} is not owned by its receipt directory", failures)
    if expected_name is not None:
        require(resolved.name == expected_name,
                f"{label} filename is not {expected_name}", failures)
    validate_sha256_file(resolved, expected_sha256, label, failures)
    return resolved


def validate_pickup_generator(
    receipt: dict,
    receipt_path: Path,
    rom_sha256: str,
    failures: list[str],
) -> dict[str, Any]:
    label = "candidate-owned pickup-state generator"
    require(receipt.get("schema") == PICKUP_GENERATOR_SCHEMA,
            f"{label} schema mismatch", failures)
    require(receipt.get("status") == "pass",
            f"{label} status is not pass", failures)
    require(receipt.get("passed") is True,
            f"{label} passed flag is not true", failures)
    require(receipt.get("rom_sha256") == rom_sha256,
            f"{label} ROM hash mismatch", failures)
    checks = require_all_checks(
        receipt, PICKUP_GENERATOR_CHECKS, label, failures,
    )
    state = validate_bound_artifact(
        receipt.get("state"), receipt_path.parent,
        receipt.get("state_sha256"), f"{label} state", failures,
        expected_name="current-pickup.ss0",
    )
    screenshot = validate_bound_artifact(
        receipt.get("screenshot"), receipt_path.parent,
        receipt.get("screenshot_sha256"), f"{label} screenshot", failures,
        expected_name="current-pickup.png",
    )
    return {
        "path": str(receipt_path),
        "sha256": file_digest(receipt_path, "sha256"),
        "schema": receipt.get("schema"),
        "state": str(state) if state is not None else None,
        "state_sha256": (
            file_digest(state, "sha256")
            if state is not None and state.is_file() else None
        ),
        "screenshot": str(screenshot) if screenshot is not None else None,
        "screenshot_sha256": (
            file_digest(screenshot, "sha256")
            if screenshot is not None and screenshot.is_file() else None
        ),
        "passing_checks": sum(value is True for value in checks.values()),
    }


def safe_decimal(value: object) -> int | None:
    try:
        return int(str(value), 10)
    except (TypeError, ValueError):
        return None


def validate_pickup_host(
    receipt: dict,
    receipt_path: Path,
    generator: dict,
    generator_receipt_path: Path,
    rom_sha256: str,
    failures: list[str],
) -> dict[str, Any]:
    label = "candidate current-host pickup gate"
    require(receipt.get("schema") == PICKUP_HOST_SCHEMA,
            f"{label} schema mismatch", failures)
    require(receipt.get("status") == "pass",
            f"{label} status is not pass", failures)
    require(receipt.get("passed") is True,
            f"{label} passed flag is not true", failures)
    require(receipt.get("failures") == [],
            f"{label} contains failures", failures)
    require(receipt.get("rom_sha256") == rom_sha256,
            f"{label} ROM hash mismatch", failures)
    checks = require_all_checks(receipt, PICKUP_HOST_CHECKS, label, failures)

    state = receipt.get("state")
    require(isinstance(state, dict), f"{label} state binding is missing", failures)
    if not isinstance(state, dict):
        state = {}
    generator_state_sha = generator.get("state_sha256")
    require(sha256_text_is_valid(generator_state_sha),
            "pickup generator state artifact is not hashable", failures)
    require(state.get("sha256") == generator_state_sha,
            f"{label} state does not link the generator artifact", failures)
    require(paths_match(state.get("path"), generator_receipt_path.parent
                        / "current-pickup.ss0"),
            f"{label} state path does not link the generator artifact", failures)
    require(state.get("binding")
            == "receipt-sha256+gbas-crc32+cartridge-title",
            f"{label} state binding is not receipt-backed", failures)
    state_receipt = state.get("receipt")
    require(isinstance(state_receipt, dict),
            f"{label} generator-receipt link is missing", failures)
    if not isinstance(state_receipt, dict):
        state_receipt = {}
    generator_receipt_sha = file_digest(generator_receipt_path, "sha256")
    require(state_receipt.get("schema") == PICKUP_GENERATOR_SCHEMA,
            f"{label} generator-receipt schema mismatch", failures)
    require(state_receipt.get("sha256") == generator_receipt_sha,
            f"{label} generator-receipt hash mismatch", failures)
    require(paths_match(state_receipt.get("path"), generator_receipt_path),
            f"{label} generator-receipt path mismatch", failures)
    target_vram = state.get("target_vram")
    require(isinstance(target_vram, dict)
            and target_vram.get("expected_count") == 73
            and target_vram.get("observed_count") == 73
            and target_vram.get("all_vbk0_exact") is True,
            f"{label} offline 73-tile VRAM proof is incomplete", failures)
    require(receipt.get("host") == {
        "row": 4, "column": 16, "source_base": "C1A0",
    }, f"{label} coordinate host changed", failures)

    payloads = receipt.get("candidate_payloads")
    require(isinstance(payloads, dict),
            f"{label} candidate payload metadata is missing", failures)
    if not isinstance(payloads, dict):
        payloads = {}
    payload_artifacts = (
        ("candidate-stage1-runtime.bin", "runtime_sha256"),
        ("candidate-stage1-helper.bin", "helper_sha256"),
        ("candidate-stage1-lut.bin", "lut_sha256"),
    )
    payload_hashes = {}
    for filename, field in payload_artifacts:
        path = receipt_path.parent / filename
        payload_hashes[filename] = validate_sha256_file(
            path, payloads.get(field), f"{label} {filename}", failures,
        )

    forms = receipt.get("forms")
    require(isinstance(forms, list) and len(forms) == len(PICKUPS) == 19,
            f"{label} does not contain exactly 19 forms", failures)
    if not isinstance(forms, list):
        forms = []
    expected = {pickup.name: pickup for pickup in PICKUPS}
    names = [form.get("name") for form in forms if isinstance(form, dict)]
    require(len(names) == 19 and len(set(names)) == 19
            and set(names) == set(expected),
            f"{label} form names are missing or duplicated", failures)
    screenshot_hashes = {}
    for index, raw_form in enumerate(forms):
        form_label = f"{label} form {index + 1}"
        require(isinstance(raw_form, dict),
                f"{form_label} is not an object", failures)
        if not isinstance(raw_form, dict):
            continue
        name = raw_form.get("name")
        pickup = expected.get(name)
        require(pickup is not None,
                f"{form_label} has an unknown pickup name", failures)
        if pickup is None:
            continue
        form_label = f"{label} {name}"
        require(raw_form.get("status") == "pass",
                f"{form_label} status is not pass", failures)
        require(raw_form.get("failures") == [],
                f"{form_label} contains failures", failures)
        require(raw_form.get("palette") == pickup.palette,
                f"{form_label} palette class mismatch", failures)
        require(raw_form.get("tiles")
                == [f"{tile:02X}" for tile in pickup.tiles],
                f"{form_label} tile signature mismatch", failures)
        gates = raw_form.get("gates")
        require(isinstance(gates, dict),
                f"{form_label} gates are missing", failures)
        if not isinstance(gates, dict):
            gates = {}
        require(all(gates.get(gate) is True for gate in PICKUP_FORM_GATES),
                f"{form_label} is missing a strongest passing gate", failures)
        report = raw_form.get("report")
        require(isinstance(report, dict),
                f"{form_label} report is missing", failures)
        if not isinstance(report, dict):
            report = {}
        require((safe_decimal(report.get("main_loop_hits")) or -1) >= 8,
                f"{form_label} has fewer than eight main-loop hits", failures)
        require((safe_decimal(report.get("tile_copy_hits")) or -1) >= 1,
                f"{form_label} has no tile-copy hit", failures)
        require((safe_decimal(report.get("host_decision_hits")) or -1) >= 1,
                f"{form_label} has no coordinate-host decision hit", failures)
        require(report.get("D880") == "02" and report.get("FFC1") == "01",
                f"{form_label} report is outside Stage 1", failures)
        screenshot = validate_bound_artifact(
            raw_form.get("screenshot"), receipt_path.parent,
            raw_form.get("screenshot_sha256"),
            f"{form_label} screenshot", failures,
        )
        screenshot_hashes[name] = (
            file_digest(screenshot, "sha256")
            if screenshot is not None and screenshot.is_file() else None
        )

    sheet = validate_bound_artifact(
        receipt.get("contact_sheet"), receipt_path.parent,
        receipt.get("contact_sheet_sha256"), f"{label} contact sheet", failures,
        expected_name="pickup-current-host-palettes.png",
    )
    return {
        "path": str(receipt_path),
        "sha256": file_digest(receipt_path, "sha256"),
        "schema": receipt.get("schema"),
        "generator_state_sha256": generator_state_sha,
        "forms": len(forms),
        "unique_forms": len(set(names)),
        "passing_checks": sum(value is True for value in checks.values()),
        "payload_artifacts": payload_hashes,
        "screenshot_sha256": screenshot_hashes,
        "contact_sheet": str(sheet) if sheet is not None else None,
        "contact_sheet_sha256": (
            file_digest(sheet, "sha256")
            if sheet is not None and sheet.is_file() else None
        ),
    }


def validate_north_receipt(
    receipt: dict,
    receipt_path: Path,
    rom: Path,
    rom_sha256: str,
    failures: list[str],
) -> dict[str, Any]:
    label = "Stage-1 north-route integrity"
    require(receipt.get("status") == "pass",
            f"{label} status is not pass", failures)
    require(receipt.get("candidate_sha256") == rom_sha256,
            f"{label} candidate hash mismatch", failures)
    require(paths_match(receipt.get("candidate_rom"), rom),
            f"{label} candidate path mismatch", failures)
    require(receipt.get("input_route")
            == "cold GAME START; hold UP; no gameplay memory writes",
            f"{label} did not use the release UP-only route", failures)
    route_fields = {
        "target_only_policy": True,
        "target_camera": 0x03A4,
        "target_room": 1,
        "target_settle_frames": 60,
        "dynamic_prefix_bytes": 0,
    }
    for field, expected in route_fields.items():
        require(receipt.get(field) == expected,
                f"{label} {field} is not {expected!r}", failures)
    require(isinstance(receipt.get("gameplay_frames"), int)
            and receipt["gameplay_frames"] >= 2400,
            f"{label} gameplay coverage is below 2400 frames", failures)
    strongest = (
        "candidate_replay_exact",
        "candidate_replay_attributes_exact",
        "settled_final_state_ok",
        "service_frame_presentations_exact",
        "candidate_attribute_trajectory_exact",
        "progress_route_geometry_exact",
        "progress_route_viewports_exact",
        "target_only_static_route_ok",
    )
    require(all(receipt.get(field) is True for field in strongest),
            f"{label} is missing a strongest passing route predicate", failures)
    require(receipt.get("world_template", {}).get("exact_at_entry") is True,
            f"{label} world template differs at entry", failures)
    require(receipt.get("metatile_table", {}).get("exact_at_entry") is True,
            f"{label} metatile table differs at entry", failures)
    require(receipt.get("terrain_differences") == 0,
            f"{label} contains terrain differences", failures)
    return {
        "path": str(receipt_path),
        "sha256": file_digest(receipt_path, "sha256"),
        "target_camera": receipt.get("target_camera"),
        "target_room": receipt.get("target_room"),
        "target_settle_frames": receipt.get("target_settle_frames"),
        "gameplay_frames": receipt.get("gameplay_frames"),
        "dynamic_prefix_bytes": receipt.get("dynamic_prefix_bytes"),
        "strongest_predicates": {
            field: receipt.get(field) for field in strongest
        },
    }


def validate_stage_card_receipt(
    receipt: dict,
    rom_sha256: str,
    failures: list[str],
) -> dict:
    label = "STAGE-card palette handoff"
    require(receipt.get("schema") == STAGE_CARD_SCHEMA,
            f"{label} schema mismatch", failures)
    require(receipt.get("status") == "pass",
            f"{label} status is not pass", failures)
    require(receipt.get("rom_sha256") == rom_sha256,
            f"{label} ROM hash mismatch", failures)
    require(receipt.get("observe_only") is False,
            f"{label} was produced in observe-only mode", failures)
    return require_all_checks(receipt, STAGE_CARD_CHECKS, label, failures)


def self_test() -> int:
    """Mutation-test the new receipt links and strongest boolean gates."""

    (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="penta-pocket-receipt-self-test-", dir=ROOT / "tmp",
    ) as temporary:
        work = Path(temporary)
        rom = work / "candidate.gbc"
        rom.write_bytes(b"aggregate-self-test-rom")
        rom_sha256 = file_digest(rom, "sha256")

        generator_root = work / "stage1-current-pickup-state"
        generator_root.mkdir()
        state = generator_root / "current-pickup.ss0"
        screenshot = generator_root / "current-pickup.png"
        state.write_bytes(b"candidate-owned-state")
        screenshot.write_bytes(b"candidate-owned-state-screenshot")
        generator_receipt = {
            "schema": PICKUP_GENERATOR_SCHEMA,
            "status": "pass",
            "passed": True,
            "rom_sha256": rom_sha256,
            "state": str(state),
            "state_sha256": file_digest(state, "sha256"),
            "screenshot": str(screenshot),
            "screenshot_sha256": file_digest(screenshot, "sha256"),
            "checks": {name: True for name in PICKUP_GENERATOR_CHECKS},
        }
        generator_path = generator_root / "receipt.json"
        generator_path.write_text(json.dumps(generator_receipt))
        failures: list[str] = []
        generator_evidence = validate_pickup_generator(
            generator_receipt, generator_path, rom_sha256, failures,
        )
        if failures:
            raise AssertionError(f"valid generator receipt rejected: {failures}")

        host_root = work / "stage1-current-pickup-host-palettes"
        host_root.mkdir()
        payload_hashes = {}
        for filename, field in (
            ("candidate-stage1-runtime.bin", "runtime_sha256"),
            ("candidate-stage1-helper.bin", "helper_sha256"),
            ("candidate-stage1-lut.bin", "lut_sha256"),
        ):
            artifact = host_root / filename
            artifact.write_bytes(filename.encode())
            payload_hashes[field] = file_digest(artifact, "sha256")
        forms = []
        for index, pickup in enumerate(PICKUPS):
            form_screenshot = host_root / f"form-{index:02d}.png"
            form_screenshot.write_bytes(f"form-{index}".encode())
            forms.append({
                "name": pickup.name,
                "palette": pickup.palette,
                "tiles": [f"{tile:02X}" for tile in pickup.tiles],
                "status": "pass",
                "screenshot": str(form_screenshot),
                "screenshot_sha256": file_digest(form_screenshot, "sha256"),
                "gates": {gate: True for gate in PICKUP_FORM_GATES},
                "report": {
                    "main_loop_hits": "8",
                    "tile_copy_hits": "1",
                    "host_decision_hits": "1",
                    "D880": "02",
                    "FFC1": "01",
                },
                "failures": [],
            })
        sheet = host_root / "pickup-current-host-palettes.png"
        sheet.write_bytes(b"contact-sheet")
        host_receipt = {
            "schema": PICKUP_HOST_SCHEMA,
            "status": "pass",
            "passed": True,
            "failures": [],
            "rom_sha256": rom_sha256,
            "state": {
                "path": str(state),
                "sha256": file_digest(state, "sha256"),
                "binding": "receipt-sha256+gbas-crc32+cartridge-title",
                "receipt": {
                    "path": str(generator_path),
                    "sha256": file_digest(generator_path, "sha256"),
                    "schema": PICKUP_GENERATOR_SCHEMA,
                },
                "target_vram": {
                    "expected_count": 73,
                    "observed_count": 73,
                    "all_vbk0_exact": True,
                },
            },
            "candidate_payloads": payload_hashes,
            "host": {"row": 4, "column": 16, "source_base": "C1A0"},
            "checks": {name: True for name in PICKUP_HOST_CHECKS},
            "forms": forms,
            "contact_sheet": sheet.name,
            "contact_sheet_sha256": file_digest(sheet, "sha256"),
        }
        host_path = host_root / "receipt.json"
        host_path.write_text(json.dumps(host_receipt))
        failures = []
        validate_pickup_host(
            host_receipt, host_path, generator_evidence, generator_path,
            rom_sha256, failures,
        )
        if failures:
            raise AssertionError(f"valid host receipt rejected: {failures}")

        mutated_host = json.loads(json.dumps(host_receipt))
        mutated_host["forms"][0]["gates"][PICKUP_FORM_GATES[0]] = False
        mutation_failures: list[str] = []
        validate_pickup_host(
            mutated_host, host_path, generator_evidence, generator_path,
            rom_sha256, mutation_failures,
        )
        if not mutation_failures:
            raise AssertionError("mutated host form gate was accepted")

        first_screenshot = Path(host_receipt["forms"][0]["screenshot"])
        original_screenshot = first_screenshot.read_bytes()
        first_screenshot.write_bytes(b"mutated-form-screenshot")
        mutation_failures = []
        validate_pickup_host(
            host_receipt, host_path, generator_evidence, generator_path,
            rom_sha256, mutation_failures,
        )
        if not any("screenshot SHA-256 mismatch" in item
                   for item in mutation_failures):
            raise AssertionError("mutated host screenshot artifact was accepted")
        first_screenshot.write_bytes(original_screenshot)

        north_path = work / "north.json"
        north_receipt = {
            "status": "pass",
            "candidate_rom": str(rom),
            "candidate_sha256": rom_sha256,
            "input_route": "cold GAME START; hold UP; no gameplay memory writes",
            "target_only_policy": True,
            "target_camera": 0x03A4,
            "target_room": 1,
            "target_settle_frames": 60,
            "gameplay_frames": 2400,
            "dynamic_prefix_bytes": 0,
            "candidate_replay_exact": True,
            "candidate_replay_attributes_exact": True,
            "settled_final_state_ok": True,
            "service_frame_presentations_exact": True,
            "candidate_attribute_trajectory_exact": True,
            "progress_route_geometry_exact": True,
            "progress_route_viewports_exact": True,
            "target_only_static_route_ok": True,
            "world_template": {"exact_at_entry": True},
            "metatile_table": {"exact_at_entry": True},
            "terrain_differences": 0,
        }
        north_path.write_text(json.dumps(north_receipt))
        failures = []
        validate_north_receipt(
            north_receipt, north_path, rom, rom_sha256, failures,
        )
        if failures:
            raise AssertionError(f"valid north receipt rejected: {failures}")
        mutated_north = dict(north_receipt)
        mutated_north["candidate_attribute_trajectory_exact"] = False
        mutation_failures = []
        validate_north_receipt(
            mutated_north, north_path, rom, rom_sha256, mutation_failures,
        )
        if not mutation_failures:
            raise AssertionError("mutated north strongest predicate was accepted")

        stage_card = {
            "schema": STAGE_CARD_SCHEMA,
            "status": "pass",
            "observe_only": False,
            "rom_sha256": rom_sha256,
            "checks": {name: True for name in STAGE_CARD_CHECKS},
        }
        failures = []
        validate_stage_card_receipt(stage_card, rom_sha256, failures)
        if failures:
            raise AssertionError(f"valid STAGE-card receipt rejected: {failures}")
        stage_card["checks"][STAGE_CARD_CHECKS[-1]] = False
        mutation_failures = []
        validate_stage_card_receipt(stage_card, rom_sha256, mutation_failures)
        if not mutation_failures:
            raise AssertionError("mutated STAGE-card check was accepted")

    print("PASS: aggregate v6 receipt validators reject strongest-gate mutations")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--menu-window-report", type=Path,
                        help="explicit fresh menu receipt; exact tested-ROM path/hash still required")
    parser.add_argument(
        "--self-test", action="store_true",
        help="run static receipt-mutation tests without launching an emulator",
    )
    args = parser.parse_args()

    if args.self_test:
        if args.rom is not None or args.root is not None or args.output is not None:
            parser.error("--self-test does not accept ROM, --root, or --output")
        return self_test()
    if args.rom is None or args.root is None or args.output is None:
        parser.error("ROM, --root, and --output are required")

    rom = args.rom.resolve()
    root = args.root.resolve()
    output = args.output.resolve()
    rom_sha256 = file_digest(rom, "sha256")
    rom_md5 = file_digest(rom, "md5")

    no_bleed_path = root / "stage1-no-color-bleed" / "receipt.json"
    attract_path = root / "attract-pickup-palettes" / "receipt.json"
    gameplay_path = root / "frame-flicker" / "gameplay.receipt.json"
    demo_path = root / "frame-flicker" / "demo.receipt.json"
    stage_card_path = root / "stage-card-stability" / "receipt.json"
    hazard_menu_path = root / "stage1-current-hazard-menu" / "receipt.json"
    pickup_generator_path = (
        root / "stage1-current-pickup-state" / "receipt.json"
    )
    pickup_host_path = (
        root / "stage1-current-pickup-host-palettes" / "receipt.json"
    )
    north_path = root / "stage1-north-route-integrity" / "receipt.json"
    menu_window_path = (args.menu_window_report.resolve() if args.menu_window_report
                        else root / "menu-window-order" / "report.txt")
    tilemap_root = root / "stage1-tilemap-integrity"
    tilemap_paths = [
        tilemap_root / "level1_sara_w_alone.report",
        tilemap_root / "level1_sara_w_spike_hazard.report",
        tilemap_root / "level1_sara_w_healpotion1_poison_cure_slow_cure.report",
    ]
    missing_tilemaps = [path for path in tilemap_paths if not path.is_file()]
    if missing_tilemaps:
        raise SystemExit(
            "FAIL: missing required Stage-1 tilemap reports: "
            + ", ".join(str(path) for path in missing_tilemaps)
        )
    no_bleed = load(no_bleed_path)
    attract = load(attract_path)
    gameplay = load(gameplay_path)
    demo = load(demo_path)
    stage_card = load(stage_card_path)
    hazard_menu = load(hazard_menu_path)
    pickup_generator = load(pickup_generator_path)
    pickup_host = load(pickup_host_path)
    north = load(north_path)
    menu_window = load_report(menu_window_path)
    tilemaps = [(path, load_report(path)) for path in tilemap_paths]
    failures: list[str] = []

    menu_lut, menu_mode = expected_window_lut(rom.read_bytes())
    window_frames = report_int(menu_window, "window_frames")
    attr_checked_frames = report_int(menu_window, "attr_checked_frames")

    pickup_generator_evidence = validate_pickup_generator(
        pickup_generator, pickup_generator_path, rom_sha256, failures,
    )
    pickup_host_evidence = validate_pickup_host(
        pickup_host, pickup_host_path, pickup_generator_evidence,
        pickup_generator_path, rom_sha256, failures,
    )
    north_evidence = validate_north_receipt(
        north, north_path, rom, rom_sha256, failures,
    )

    no_bleed_checks = no_bleed.get("checks", {})
    no_bleed_probe = no_bleed.get("probe", {})
    require(no_bleed.get("status") == "pass", "two-axis no-bleed gate failed", failures)
    require(no_bleed.get("rom_sha256") == rom_sha256, "no-bleed ROM hash mismatch", failures)
    require(no_bleed.get("route", {}).get("play_frames_requested", 0) >= 3600,
            "no-bleed route is shorter than 3600 frames", failures)
    require(no_bleed_probe.get("raster_capture_count", 0) >= 1000,
            "no-bleed raster coverage is below 1000 transitions", failures)
    require(no_bleed_checks.get("route exercised horizontal scrolling") is True,
            "no-bleed receipt lacks horizontal scrolling", failures)
    require(no_bleed_checks.get("route exercised vertical scrolling") is True,
            "no-bleed receipt lacks vertical scrolling", failures)
    require(no_bleed_checks.get(
        "no detached pickup colors or floor-pattern bleed in rendered raster"
    ) is True, "detached pickup/floor bleed check failed", failures)
    require(runtime_lut_contract(no_bleed_probe)
            and no_bleed_checks.get(
                "runtime Stage 1 LUT changes are exact reviewed wall roles") is True,
            "runtime Stage-1 palette LUT changed", failures)

    attract_checks = attract.get("checks", {})
    require(attract.get("status") == "pass", "attract pickup gate failed", failures)
    require(attract.get("rom_sha256") == rom_sha256, "attract ROM hash mismatch", failures)
    require(attract.get("pickup_mismatches") == 0, "attract pickup palettes misaligned", failures)
    require(attract.get("visible_pickup_cells", 0) > 0,
            "attract receipt contains no direct pickup-cell evidence", failures)
    require(attract.get("colored_pickup_cells") == attract.get("visible_pickup_cells"),
            "not every visible attract pickup is colorized", failures)
    require(attract.get("neutral_pickup_cells") == 0,
            "an attract pickup remained on the background palette", failures)
    require(attract.get("unsafe_attribute_cells") == 0, "unsafe attract attributes observed", failures)
    require(attract.get("rendered_pickup_capture_count", 0) >= 9,
            "late-demo screenshot coverage is incomplete", failures)
    require(attract.get("last_background_mismatch_frame", 0)
            < attract.get("first_pickup_frame", -1),
            "background mismatch persisted into visible pickup play", failures)
    require(attract_checks.get("pickup palettes leave no persistent trails on non-pickup tiles") is True,
            "purple/pickup trail cleanup failed", failures)

    for label, receipt in (("gameplay", gameplay), ("demo", demo)):
        require(receipt.get("status") == "ok", f"{label} flicker gate failed", failures)
        require(receipt.get("rom_md5") == rom_md5, f"{label} flicker ROM hash mismatch", failures)
        require(receipt.get("samples", 0) >= 2400, f"{label} flicker coverage is short", failures)
        require(not receipt.get("failures"), f"{label} flicker receipt has failures", failures)
        require(not receipt.get("lcd_off_samples"), f"{label} unexpectedly disabled LCD", failures)
        require(not receipt.get("steady_active_bg_palette_changes"),
                f"{label} changed active BG palettes during steady play", failures)
        require(not receipt.get("steady_all_white_active_bg_palettes"),
                f"{label} produced steady all-white BG palettes", failures)
        require(not receipt.get("steady_all_white_active_obj_palettes"),
                f"{label} produced steady all-white OBJ palettes", failures)
        # Semantic pickups and animated hazards intentionally differ from the
        # one-dimensional tile LUT. Their alignment is gated above by the
        # raster no-bleed receipt, so do not misclassify those cells as flicker.

    stage_card_checks = validate_stage_card_receipt(
        stage_card, rom_sha256, failures,
    )
    require(stage_card.get("static_handoff", {}).get("installed") is True,
            "exact map-flip palette handoff is not installed", failures)
    require(stage_card_checks.get("exact map-flip palette handoff is installed") is True,
            "palette phase is not bound to the atomic map flip", failures)
    require(stage_card_checks.get("gameplay handoff preserves only the complete final STAGE card") is True,
            "STAGE-card handoff exposed a partial/purple frame", failures)
    require(stage_card_checks.get("first dungeon handoff has no partial map frames") is True,
            "first dungeon handoff exposed a partial map", failures)
    require(stage_card_checks.get("Stage-1 BG0 is resident before the first dungeon tile appears") is True,
            "Stage-1 palette was not resident at first dungeon publication", failures)
    require(stage_card_checks.get("blank-SRAM routes start without save artifacts or fixture writes") is True,
            "STAGE-card gate did not use a genuinely blank-SRAM route", failures)
    require(stage_card_checks.get("blank-SRAM pregame captures every consecutive rendered frame") is True,
            "blank-SRAM pregame receipt sampled around an entry frame", failures)
    require(stage_card_checks.get("blank-SRAM pregame frame-state and raster replay are exact") is True,
            "blank-SRAM title-to-Stage-1 replay is nondeterministic", failures)
    require(stage_card_checks.get("blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state") is True,
            "blank-SRAM Stage-1 entry exposed a cyan or partial frame", failures)
    require(stage_card_checks.get("blank-SRAM first dungeon map and attributes are atomic") is True,
            "blank-SRAM Stage-1 entry exposed a partial dungeon map", failures)
    require(stage_card_checks.get("blank-SRAM Stage-1 BG0 precedes the first dungeon tile") is True,
            "blank-SRAM Stage-1 palette missed the atomic map flip", failures)

    hazard_checks = hazard_menu.get("checks", {})
    replays = hazard_menu.get("replays", [])
    require(hazard_menu.get("passed") is True,
            "menu/item/close/low-health hazard gate failed", failures)
    require(hazard_menu.get("rom_sha256") == rom_sha256,
            "menu/item/close/low-health ROM hash mismatch", failures)
    require(len(replays) == 2,
            "menu/item/close/low-health gate lacks two replays", failures)
    require(hazard_checks.get("cold state is hash-bound to the candidate ROM") is True,
            "hazard fixture is not candidate-owned", failures)
    require(hazard_checks.get("both menu/item/close/low-health replays are clean") is True,
            "pickup/wall/hazard attrs regress after item use or warning health", failures)
    require(hazard_checks.get("replays are byte-deterministic") is True,
            "menu/item/close/low-health replay is nondeterministic", failures)
    require(all(replay.get("map_flip_events", 0) >= 30 for replay in replays),
            "menu/item/movement route lacks native map-flip coverage", failures)
    require(all(replay.get("unsafe_map_flip_events") == 0 for replay in replays),
            "a native map flip exposed an active/incomplete transfer", failures)
    require(all(hazard_coverage_is_complete(replay) for replay in replays),
            "stationary menu/item/low-health hazard coverage is incomplete", failures)

    failures.extend(menu_window_report_failures(
        menu_window,
        rom=rom,
        rom_sha256=rom_sha256,
        attr_mode=menu_mode,
        attr_lut_sha256=sha256_bytes(menu_lut),
    ))

    tilemap_evidence = validate_tilemap_reports(
        tilemaps, rom_sha256, failures, rom.read_bytes(),
    )

    receipt = {
        "schema": "penta-pocket-stage1-visual-incident-v6",
        "status": "pass" if not failures else "fail",
        "passed": not failures,
        "rom": str(rom),
        "rom_sha256": rom_sha256,
        "rom_md5": rom_md5,
        "failures": failures,
        "evidence": {
            "stage1_no_color_bleed": {
                "path": str(no_bleed_path),
                "sha256": file_digest(no_bleed_path, "sha256"),
                "raster_captures": no_bleed_probe.get("raster_capture_count"),
            },
            "attract_pickup_palettes": {
                "path": str(attract_path),
                "sha256": file_digest(attract_path, "sha256"),
                "visible_pickup_cells": attract.get("visible_pickup_cells"),
                "colored_pickup_cells": attract.get("colored_pickup_cells"),
                "neutral_pickup_cells": attract.get("neutral_pickup_cells"),
                "pickup_mismatches": attract.get("pickup_mismatches"),
            },
            "frame_flicker_gameplay": {
                "path": str(gameplay_path),
                "sha256": file_digest(gameplay_path, "sha256"),
                "samples": gameplay.get("samples"),
            },
            "frame_flicker_demo": {
                "path": str(demo_path),
                "sha256": file_digest(demo_path, "sha256"),
                "samples": demo.get("samples"),
            },
            "stage_card_palette_handoff": {
                "path": str(stage_card_path),
                "sha256": file_digest(stage_card_path, "sha256"),
                "schema": stage_card.get("schema"),
                "observe_only": stage_card.get("observe_only"),
                "passing_checks": sum(
                    value is True for value in stage_card_checks.values()
                ),
                "helper_size": stage_card.get("static_handoff", {}).get("helper_size"),
            },
            "stage1_current_hazard_menu": {
                "path": str(hazard_menu_path),
                "sha256": file_digest(hazard_menu_path, "sha256"),
                "replays": len(replays),
                "map_flips": sum(
                    replay.get("map_flip_events", 0) for replay in replays
                ),
                "unsafe_map_flips": sum(
                    replay.get("unsafe_map_flip_events", 0)
                    for replay in replays
                ),
            },
            "menu_window_order": {
                "path": str(menu_window_path),
                "sha256": file_digest(menu_window_path, "sha256"),
                "window_frames": window_frames,
                "attr_checked_frames": attr_checked_frames,
                "entry_frames": report_int(menu_window, "attr_entry_frames"),
                "settled_frames": report_int(
                    menu_window, "attr_settled_frames"
                ),
                "exit_frames": report_int(menu_window, "attr_exit_frames"),
            },
            "stage1_tilemap_integrity": {
                "reports": [
                    {"path": str(path), "sha256": file_digest(path, "sha256")}
                    for path, _ in tilemaps
                ],
                "exact_copies": tilemap_evidence["exact_copies"],
                "atomic_completions": tilemap_evidence[
                    "atomic_completions"
                ],
                "pure_completions": tilemap_evidence["pure_completions"],
                "publication_model_copies": tilemap_evidence[
                    "publication_model_copies"
                ],
                "ordinary_attribute_model_copies": (
                    tilemap_evidence["ordinary_attribute_model_copies"]
                ),
                "mismatch_copies": tilemap_evidence["mismatch_copies"],
                "attribute_mismatch_copies": tilemap_evidence[
                    "attribute_mismatch_copies"
                ],
                "oracle_schema": PUBLICATION_ORACLE_SCHEMA,
                "ordinary_attribute_scope": ORDINARY_ATTRIBUTE_SCOPE,
                "semantic_overlay_owner": SEMANTIC_OVERLAY_OWNER,
            },
            "stage1_current_pickup_state": pickup_generator_evidence,
            "stage1_current_pickup_host_palettes": pickup_host_evidence,
            "stage1_north_route_integrity": north_evidence,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"Receipt: {output}")
        return 1
    print(f"PASS: Pocket visual incident gates are hash-bound to {rom_sha256}")
    print(f"Receipt: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
