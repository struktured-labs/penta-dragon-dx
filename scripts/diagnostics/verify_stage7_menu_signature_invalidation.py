#!/usr/bin/env python3
"""Bound fixed-candidate gate for the Stage-7 SELECT-menu attribute trail.

Static mode derives the isolated r265 (a4c7) fixture from the exact e048 r4a
publication state.  The immediate-base e048 duplicate r2 failure is the bound
negative detector.  The live mode runs duplicate single-flight replays with
the full helper/DMA/ABI contract and requires zero visible tile or semantic-
attribute trails.

The attempted aa4 native control is deliberately not authorized: a CRC-only
cross-build fixture retains e048's installed DA60 runtime and is not native
r264.  It is recorded as blocked evidence, not silently treated as a control.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import normalize_mgba_state_pc as normalizer
import verify_stage7_dual_plane_menu_roundtrip as menu


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
BASE_PROBE = ROOT / "scripts/diagnostics/probe_stage7_dual_plane_menu_roundtrip.lua"
BASE_VERIFIER = ROOT / "scripts/diagnostics/verify_stage7_dual_plane_menu_roundtrip.py"
CONTROL_PROBE = ROOT / "tmp/stage7-menu-signature-invalidation-r265/control-probe.lua"
SOURCE_FIXTURE = (
    ROOT / "tmp/stage7-dual-plane-hdma-r264/visual-soak-r4a/"
    "stage7.flip000009.ss0"
)
CONTROL_ROM = ROOT / "tmp/stage1-menu-hidden-repair-r264/candidate.gb"
CONTROL_BUILD_RECEIPT = ROOT / "tmp/stage1-menu-hidden-repair-r264/build-receipt.json"
CONTROL_FIXTURE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/fixtures/"
    "e048-retarget-aa4c.ss0"
)
FIXED_ROM = ROOT / "tmp/stage7-menu-signature-invalidation-r265/candidate.gb"
FIXED_BUILD_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/static-receipt.json"
)
FIXED_FIXTURE = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/fixtures/"
    "e048-retarget-a4c7.ss0"
)
R2_FAIL = ROOT / "tmp/stage7-dual-plane-hdma-r264/menu-roundtrip-live-r2/receipt.json"
DEFAULT_STATIC_RECEIPT = (
    ROOT / "tmp/stage7-menu-signature-invalidation-r265/"
    "menu-control-fix-static-receipt.json"
)
BASE_CANDIDATE = ROOT / "tmp/stage7-dual-plane-hdma-r264/candidate.gb"
BASE_STATIC_RECEIPT = ROOT / "tmp/stage7-dual-plane-hdma-r264/static-receipt.json"
BASE_MENU_STATIC_RECEIPT = (
    ROOT / "tmp/stage7-dual-plane-hdma-r264/menu-roundtrip-static-receipt.json"
)

BASE_PROBE_SHA = "f0242ac4982148e9d6110f55cc0ffdcea0c78f85e8e9aa156015e44053f0fd43"
BASE_VERIFIER_SHA = "e028fef1450aae52dd74e32940bee056ec643177b55a75f9ebfa4921b6e0f939"
NORMALIZER_SHA = "7718f668eeca9b390af84aad1357c9ffd8dc59723b700b536f86ac9a47b32b01"
SOURCE_FIXTURE_SHA = "68acf42ab87e4ac2da6163750d53847dbe0b91fd48f158a7cfb751ff08980ea2"
SOURCE_GBAS_SHA = "c878213ae2445aa6217b7aad7c2e338e1ae2250c9ad7ae34f5e9e28b90ed88b8"
CONTROL_ROM_SHA = "aa4c15602af5a1d0bf332c17de25fd2132d7fb45b327cc2d8d9bf25255dbf5a1"
CONTROL_RECEIPT_SHA = "71c4961aa8fd0298f3f5112738f4911bd297f5109e836136476839617e443846"
CONTROL_FIXTURE_SHA = "4227016c854284d38fd31e3a6360801f41cb55d2b0f0d6779d4c2aa9dc4f7575"
CONTROL_GBAS_SHA = "309032be2b130245271efe9fed5d5cb828e3d1aeaeabea7fed8e7e4dcf0ca50f"
FIXED_ROM_SHA = "a4c772624f16bc9ef23873726cbbafa169ee93869a95a17431367895273bd273"
FIXED_RECEIPT_SHA = "9567c8babe7be863ecbd5a7c6ba9a8234cd81aef7508a1f6e3c184773c3a6ab7"
FIXED_FIXTURE_SHA = "225b0ac7531f1c720558ad202dd2520107038452dde0a7bea8b619956d399a49"
FIXED_GBAS_SHA = "4d233fe8bf62a51a04e873e07fee4d1c33143295769940280f38d29994ce5144"
R2_FAIL_SHA = "61c95414b4f0b965ea775e1d86e12697679e23822ad6abb1a539b8997afaa4be"
BASE_CANDIDATE_SHA = "e04801c8b8b0c1eb5ddaddce31a9581ad5c1fc83e3f1b043c581afa33df216a0"
BASE_STATIC_RECEIPT_SHA = "b724cfae07e8e72cda8629778bef9d4f85a9ad7c3f1413eb691a06e6e1ef7272"
BASE_MENU_STATIC_RECEIPT_SHA = "266d3444269ad6eff9528cd8200a7e57c7c1d44e8e3e7d9234f75f0489a253ea"

AUDIO_RANGES = ((0x00AC, 0x00B0), (0x01E0, 0x0260))
ORIGINAL_REPORT_FAILURES = menu.report_failures
ORIGINAL_CANDIDATE_LUT = menu.candidate_lut


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def scratch(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            f"{label} must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def exact_control_probe_source() -> str:
    """Derive a native-r264 probe without inventing helper coverage."""

    source = BASE_PROBE.read_text()
    transforms = (
        (
            "    state_loaded = true\n"
            "    phase = \"pre\"\n"
            "    phase_frame = 0\n",
            "    state_loaded = true\n"
            "    phase = \"pre\"\n"
            "    pre_complete = true\n"
            "    phase_frame = 0\n",
        ),
        (
            "  if not state_loaded or state_save_pending or phase ~= \"post\" or not post_complete\n"
            "      or not post_outer_seen or helper_depth ~= 0 then return end\n",
            "  if not state_loaded or state_save_pending or phase ~= \"post\"\n"
            "      or helper_depth ~= 0 then return end\n",
        ),
    )
    for old, new in transforms:
        require(source.count(old) == 1,
                "native-control probe transform preimage is not unique")
        source = source.replace(old, new, 1)
    require("pre_complete = true" in source,
            "native-control probe does not arm clean fixture authority")
    require("phase ~= \"post\"\n      or helper_depth ~= 0" in source,
            "native-control probe does not save at the common publisher")
    return source


def prepare_fixtures() -> dict[str, Any]:
    for path, expected in (
        (SOURCE_FIXTURE, SOURCE_FIXTURE_SHA),
        (FIXED_ROM, FIXED_ROM_SHA),
    ):
        require(path.is_file() and sha256(path) == expected,
                f"exact input missing or changed: {relative(path)}")
    require(sha256(ROOT / "scripts/diagnostics/normalize_mgba_state_pc.py")
            == NORMALIZER_SHA, "machine-preserving normalizer changed")
    CONTROL_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    normalizer.normalize(
        SOURCE_FIXTURE, FIXED_FIXTURE, 0x016C, [], rom=FIXED_ROM,
        preserve_machine=True,
    )
    require(sha256(FIXED_FIXTURE) == FIXED_FIXTURE_SHA,
            "exact r265 normalized fixture changed")
    source = menu.serialized_state(SOURCE_FIXTURE)
    fixed = menu.serialized_state(FIXED_FIXTURE)
    require(sha256_bytes(source) == SOURCE_GBAS_SHA,
            "source fixture machine changed")
    require(sha256_bytes(fixed) == FIXED_GBAS_SHA,
            "r265 fixture machine changed")
    differences = [index for index, pair in enumerate(zip(source, fixed))
                   if pair[0] != pair[1]]
    require(differences == [4, 5, 6, 7],
            "r265 fixture changed more than serialized ROM CRC")
    return {
        "source": {"path": relative(SOURCE_FIXTURE),
                   "sha256": SOURCE_FIXTURE_SHA,
                   "gbAs_sha256": SOURCE_GBAS_SHA},
        "r265": {"path": relative(FIXED_FIXTURE),
                 "sha256": FIXED_FIXTURE_SHA,
                 "gbAs_sha256": FIXED_GBAS_SHA},
        "only_changed_gbAs_offsets": ["$0004-$0007 (ROM CRC)"],
    }


def audit_known_r2_failure() -> dict[str, Any]:
    require(sha256(R2_FAIL) == R2_FAIL_SHA, "known e048 r2 receipt changed")
    receipt = json.loads(R2_FAIL.read_text())
    require(receipt.get("status") == "FAIL", "known e048 r2 no longer fails")
    rows = []
    for replay in receipt.get("replays", []):
        report = replay.get("probe_report", {})
        row = {
            "visible_frames": int(report.get("intervening_visible_frames", -1)),
            "base_9800_frames": int(report.get("intervening_base_9800_frames", -1)),
            "base_9c00_frames": int(report.get("intervening_base_9c00_frames", -1)),
            "attr_mismatch_frames": int(report.get("intervening_attr_mismatch_frames", -1)),
            "attr_mismatch_cells": int(report.get("intervening_attr_mismatch_cells", -1)),
            "semantic_mismatch_frames": int(report.get("intervening_semantic_attr_mismatch_frames", -1)),
            "semantic_mismatch_cells": int(report.get("intervening_semantic_attr_mismatch_cells", -1)),
            "visible_map_write_events": int(report.get("intervening_visible_map_write_events", -1)),
            "tile_mismatch_cells": int(report.get("intervening_tile_mismatch_cells", -1)),
        }
        require(row == {
            "visible_frames": 18, "base_9800_frames": 7,
            "base_9c00_frames": 11, "attr_mismatch_frames": 7,
            "attr_mismatch_cells": 662, "semantic_mismatch_frames": 7,
            "semantic_mismatch_cells": 662, "visible_map_write_events": 0,
            "tile_mismatch_cells": 0,
        }, "known e048 r2 detector evidence changed")
        rows.append(row)
    require(len(rows) == 2 and rows[0] == rows[1],
            "known e048 r2 is not duplicate deterministic evidence")
    state1 = menu.serialized_state(R2_FAIL.parent / "replay-1/post-close.ss0")
    state2 = menu.serialized_state(R2_FAIL.parent / "replay-2/post-close.ss0")
    raw_differences = [index for index, pair in enumerate(zip(state1, state2))
                       if pair[0] != pair[1]]
    outside = [index for index in raw_differences
               if not any(start <= index < end for start, end in AUDIO_RANGES)]
    projection1, projection2 = projected_state(state1), projected_state(state2)
    require(len(raw_differences) == 68 and not outside,
            "known e048 r2 differs outside documented audio fields")
    require(projection1 == projection2 and len(projection1) == 71548,
            "known e048 r2 projected machine state is not exact")
    require(sha256_bytes(projection1)
            == "55fbc3a50722a79ee77b31f19ad3986b89e535acaf43c3b3cda81c0a1c7dc4cb",
            "known e048 r2 projected machine identity changed")
    return {"path": relative(R2_FAIL), "sha256": R2_FAIL_SHA,
            "duplicate_detector_rows": rows,
            "raw_gbAs_difference_count": len(raw_differences),
            "raw_differences_outside_audio_ranges": 0,
            "projected_gbAs_sha256": sha256_bytes(projection1)}


def audit_builds() -> dict[str, Any]:
    require(sha256(BASE_PROBE) == BASE_PROBE_SHA, "frozen menu probe changed")
    require(sha256(BASE_VERIFIER) == BASE_VERIFIER_SHA,
            "frozen menu verifier changed")
    require(sha256(BASE_CANDIDATE) == BASE_CANDIDATE_SHA,
            "immediate e048 base changed")
    require(sha256(BASE_STATIC_RECEIPT) == BASE_STATIC_RECEIPT_SHA,
            "e048 static receipt changed")
    require(sha256(BASE_MENU_STATIC_RECEIPT)
            == BASE_MENU_STATIC_RECEIPT_SHA,
            "frozen e048 menu static receipt changed")
    require(sha256(FIXED_BUILD_RECEIPT) == FIXED_RECEIPT_SHA,
            "r265 static receipt changed")
    fixed_receipt = json.loads(FIXED_BUILD_RECEIPT.read_text())
    require(fixed_receipt.get("candidate_sha256") == FIXED_ROM_SHA,
            "r265 receipt binds another ROM")
    require(fixed_receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED"
            and fixed_receipt.get("emulator_run") is False,
            "r265 static build is not green")
    menu_static = json.loads(BASE_MENU_STATIC_RECEIPT.read_text())
    controls = menu_static.get("mutation_controls", {})
    require(len(controls) == 97 and all(controls.values()),
            "frozen e048 menu fail-closed controls changed")
    base_rom = BASE_CANDIDATE.read_bytes()
    fixed_rom = FIXED_ROM.read_bytes()
    menu.audit_candidate_contract(base_rom)
    require(menu.candidate_lut(fixed_rom) == menu.candidate_lut(base_rom),
            "r265 changed the Stage-7 LUT")
    for address in (menu.ATTR_DMA_STORE, menu.TILE_DMA_STORE):
        offset = menu.bank_offset(menu.HELPER_BANK, address)
        require(fixed_rom[offset:offset + 2] == base_rom[offset:offset + 2]
                == b"\xE0\x55", "r265 changed an inline DMA store")
    return {
        "e048_immediate_base": {
            "rom": relative(BASE_CANDIDATE), "sha256": BASE_CANDIDATE_SHA,
            "static_receipt_sha256": BASE_STATIC_RECEIPT_SHA,
            "menu_static_receipt_sha256": BASE_MENU_STATIC_RECEIPT_SHA,
            "menu_mutation_controls": "97/97",
        },
        "r265": {"rom": relative(FIXED_ROM), "sha256": FIXED_ROM_SHA,
                 "static_receipt_sha256": FIXED_RECEIPT_SHA},
        "optimized_helper_and_lut_equal_e048": True,
    }


def projection_controls() -> dict[str, bool]:
    baseline = bytes(menu.GB_STATE_SIZE)
    inside = bytearray(baseline)
    inside[0x00AC] = 1
    outside = bytearray(baseline)
    outside[0x00AB] = 1
    mixed = bytearray(inside)
    mixed[0x0260] = 1
    controls = {
        "audio_capRight_excluded": projected_state(baseline)
        == projected_state(bytes(inside)),
        "outside_audio_changes_projection": projected_state(baseline)
        != projected_state(bytes(outside)),
        "audio_boundary_0260_not_excluded": projected_state(baseline)
        != projected_state(bytes(mixed)),
        "projection_length_exact": len(projected_state(baseline)) == 71548,
    }
    require(all(controls.values()), "audio projection mutation escaped")
    return controls


def build_static_receipt() -> dict[str, Any]:
    fixtures = prepare_fixtures()
    source = BASE_PROBE.read_text()
    menu.audit_probe_source(source)
    return {
        "schema": "penta-stage7-menu-signature-fixed-static-v2",
        "status": "STATIC_PASS_DUPLICATE_FIXED_LIVE_REQUIRED",
        "emulator_run": False,
        "builds": audit_builds(),
        "fixtures": fixtures,
        "known_e048_failure": audit_known_r2_failure(),
        "retired_r264_control": {
            "status": "BLOCKED_INVALID_CROSS_BUILD_RUNTIME",
            "reason": (
                "CRC-only aa4 fixture retained e048 DA60-DAFF runtime; its "
                "two timed-out runs are not native-r264 evidence"
            ),
            "e048_DA60_sha256": (
                "a8152a016148c2a497cd63cd8f4e9b5a6682c19d0300f9b49fc58253299b819c"
            ),
            "aa4_DA60_sha256": (
                "765d22df24f270dd5210500f05ae101278edab35ee0c8707bed26738f90c8b5a"
            ),
            "live_control_authorized": False,
        },
        "tools": {
            "wrapper": relative(SELF), "wrapper_sha256": sha256(SELF),
            "base_probe_sha256": BASE_PROBE_SHA,
            "base_verifier_sha256": BASE_VERIFIER_SHA,
            "normalizer_sha256": NORMALIZER_SHA,
            "fixed_probe_sha256": sha256_bytes(source.encode()),
            "single_flight_launcher_sha256": menu.EXPECTED_LAUNCHER_SHA256,
        },
        "live_contract": {
            "order": ["isolated-r265-fix"],
            "replays_per_variant": 2,
            "fix": (
                "full optimized helper/DMA/ABI contract before+after menu; "
                "zero tile/attr/C600-semantic trails"
            ),
            "state_determinism": (
                "reports/snapshots exact; gbAs exact after excluding only "
                "$00AC-$00AF audio.capRight and $01E0-$025F audio samples; "
                "every raw difference must lie inside those ranges"
            ),
        },
        "projection_mutation_controls": projection_controls(),
        "promotion_followups": [
            "candidate-bound Stage1 item-menu/hazard regression",
            "candidate-bound non-02/08 Window timing/headroom control",
        ],
        "decision": "STATIC_GO_FOR_DUPLICATE_R265_FIXED_ONLY",
    }


def write_static(path: Path) -> str:
    receipt = build_static_receipt()
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    path = scratch(path, label="static receipt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    return sha256_bytes(payload.encode())


def validate_static(path: Path, expected_sha: str) -> dict[str, Any]:
    require(path.is_file() and sha256(path) == expected_sha,
            "bound control/fix static receipt changed")
    receipt = json.loads(path.read_text())
    require(receipt == build_static_receipt(),
            "control/fix static receipt is stale")
    require(receipt.get("decision")
            == "STATIC_GO_FOR_DUPLICATE_R265_FIXED_ONLY",
            "static receipt does not authorize live variants")
    return receipt


def control_report_failures(
    report: dict[str, str], *, menu_hold: int, frame_limit: int,
) -> list[str]:
    failures: list[str] = []
    try:
        values = {key: int(report.get(key, ""), 10)
                  for key in menu.REPORT_INT_FIELDS}
    except ValueError:
        return ["missing/invalid integer report field"]

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(report.get("status") == "ok" and report.get("reason") == "complete",
          "native control did not complete")
    check(values["state_loaded"] == 1 and values["breakpoint_failures"] == 0
          and values["watchpoint_failures"] == 0,
          "native control instrumentation failed")
    check(0 < values["frames"] <= frame_limit, "invalid native frame count")
    check(values["menu_seen"] == values["menu_closed"] == 1,
          "native SELECT roundtrip incomplete")
    check(values["menu_visible_frames"] >= menu_hold
          and values["ffe4_nonzero_frames"] > 0,
          "native menu ownership/window nonvacuity failed")
    check(values["ffc1_non1_frames"] == 0,
          "native control left Stage-7 gameplay")
    check(values["pre_snapshot_ok"] == 1
          and values["pre_snapshot_refreshes"] == 1,
          "native clean pre-snapshot missing")
    check(values["pre_snapshot_semantic_checked_cells"] == 1152
          and values["pre_snapshot_semantic_mismatch_cells"] == 0,
          "native pre-snapshot is not dual-map semantically clean")
    check(values["intervening_visible_frames"] >= 1
          and values["intervening_attr_checked_frames"]
          == values["intervening_visible_frames"],
          "native close-to-publisher frames were not fully audited")
    check(values["intervening_base_9800_frames"]
          + values["intervening_base_9c00_frames"]
          == values["intervening_visible_frames"],
          "native physical-map partition incomplete")
    for key in (
        "window_mismatch_cells", "window_mismatch_frames",
        "worst_window_mismatches", "window_geometry_mismatch_frames",
        "map_alias_frames", "helper_active_menu_owned_frames",
        "menu_hardware_mismatch_frames", "menu_ff55_nonidle_frames",
        "menu_svbk_non1_frames", "menu_ie_non07_frames",
        "helper_entries_pre", "helper_entries_post",
        "helper_entries_menu_owned", "helper_entries_window_visible",
        "helper_exits_menu_owned", "fastpath_hits_pre", "fastpath_hits_post",
        "fastpath_hits_menu_owned", "fastpath_visible_target_hits",
        "helper_exits_pre", "helper_exits_post", "attr_dma_pre",
        "attr_dma_post", "tile_dma_pre", "tile_dma_post",
        "dma_menu_owned", "dma_window_visible", "invalid_dma_commands",
        "helper_command_shape_violations", "abi_violations",
        "scene_violations", "fallback_native_hits", "caller_reject_hits",
        "atomic_fallback_hits", "intervening_tile_mismatch_frames",
        "intervening_tile_mismatch_cells",
        "intervening_attr_unchecked_helper_frames",
        "intervening_attr_unjustified_frames",
        "intervening_visible_map_write_events", "stage7_lut_write_events",
    ):
        check(values[key] == 0, f"nonzero native containment field {key}")
    check(values["intervening_attr_mismatch_frames"]
          == values["intervening_semantic_attr_mismatch_frames"]
          and values["intervening_attr_mismatch_cells"]
          == values["intervening_semantic_attr_mismatch_cells"],
          "native attr drift is not the same C600-semantic bug class")
    check(values["state_save_request_ok"] == values["state_save_ok"] == 1
          and values["state_save_stable_frames"] >= 2,
          "native post state was not saved stably")
    check(menu.FINAL_HARDWARE_PATTERN.fullmatch(
        report.get("final_hardware", "")) is not None,
        "native final hardware was not restored")
    return failures


def classification(report: dict[str, str]) -> str:
    cells = int(report["intervening_semantic_attr_mismatch_cells"])
    frames = int(report["intervening_semantic_attr_mismatch_frames"])
    if cells > 0 and frames > 0:
        return "INHERITED_R264_MENU_SIGNATURE_DRIFT"
    if cells == 0 and frames == 0:
        return "R264_CLEAN_E048_TRANSPORT_INTERACTION"
    return "INCONCLUSIVE"


def projected_state(state: bytes) -> bytes:
    return state[:0x00AC] + state[0x00B0:0x01E0] + state[0x0260:]


def deterministic_projection(replays: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"passed": False, "error": None}
    if len(replays) != 2:
        result["error"] = "two complete replay records are required"
        return result
    try:
        first, second = replays
        first_state = menu.serialized_state(
            ROOT / first["path"] / "post-close.ss0"
        )
        second_state = menu.serialized_state(
            ROOT / second["path"] / "post-close.ss0"
        )
    except (AssertionError, KeyError, OSError) as error:
        result["error"] = f"post-state unavailable or invalid: {error}"
        return result
    raw_differences = [index for index, pair in enumerate(zip(first_state, second_state))
                       if pair[0] != pair[1]]
    outside = [index for index in raw_differences
               if not any(start <= index < end for start, end in AUDIO_RANGES)]
    first_projection = projected_state(first_state)
    second_projection = projected_state(second_state)
    snapshots_exact = (
        first.get("pre_menu_snapshot") == second.get("pre_menu_snapshot")
    )
    reports_exact = first.get("probe_report") == second.get("probe_report")
    result.update({
        "raw_difference_count": len(raw_differences),
        "raw_differences_outside_audio_ranges": len(outside),
        "allowed_audio_ranges": ["$00AC-$00AF", "$01E0-$025F"],
        "projection_length": len(first_projection),
        "projection_sha256_replay1": sha256_bytes(first_projection),
        "projection_sha256_replay2": sha256_bytes(second_projection),
        "parsed_reports_exact": reports_exact,
        "pre_menu_snapshots_exact": snapshots_exact,
        "projected_gbAs_exact": first_projection == second_projection,
    })
    result["passed"] = (
        not outside and reports_exact and snapshots_exact
        and first_projection == second_projection
    )
    return result


def configure_menu_module(variant: str) -> tuple[Path, Path, str]:
    require(variant == "fixed", "native r264 control is not authorized")
    rom, fixture, probe = FIXED_ROM, FIXED_FIXTURE, BASE_PROBE
    rom_sha, fixture_sha, gbas_sha = (
        FIXED_ROM_SHA, FIXED_FIXTURE_SHA, FIXED_GBAS_SHA,
    )
    candidate_receipt = FIXED_BUILD_RECEIPT
    candidate_receipt_sha = FIXED_RECEIPT_SHA
    menu.candidate_lut = ORIGINAL_CANDIDATE_LUT
    menu.report_failures = ORIGINAL_REPORT_FAILURES
    menu.CANDIDATE = rom
    menu.FIXTURE = fixture
    menu.PROBE = probe
    menu.STATIC_CANDIDATE_RECEIPT = candidate_receipt
    menu.EXPECTED_CANDIDATE_SHA256 = rom_sha
    menu.EXPECTED_FIXTURE_SHA256 = fixture_sha
    menu.EXPECTED_FIXTURE_GBAS_SHA256 = gbas_sha
    menu.EXPECTED_CANDIDATE_STATIC_RECEIPT_SHA256 = candidate_receipt_sha
    return rom, fixture, rom_sha


def run_variant(args: argparse.Namespace) -> int:
    require(args.static_receipt is not None and args.static_receipt_sha,
            "live mode requires --static-receipt and --static-receipt-sha")
    validate_static(args.static_receipt.resolve(), args.static_receipt_sha)
    prepare_fixtures()
    variant = "fixed"
    rom, fixture, rom_sha = configure_menu_module(variant)
    output = scratch(args.output, label="live output")
    require(not output.exists(), "live output must be a fresh path")
    output.mkdir(parents=True)
    run_args = SimpleNamespace(
        frames=args.frames, menu_hold=args.menu_hold, timeout=args.timeout,
    )
    replays: list[dict[str, Any]] = []
    for index in (1, 2):
        replay = menu.run_replay(output / f"replay-{index}", run_args)
        replays.append(replay)
        if replay["failures"] or replay.get("single_flight_busy"):
            break
    failures = [f"replay-{index}: {failure}"
                for index, replay in enumerate(replays, 1)
                for failure in replay["failures"]]
    projection = deterministic_projection(replays)
    if not projection["passed"]:
        failures.append("duplicate projected-state determinism failed")
    receipt = {
        "schema": "penta-stage7-menu-signature-control-fix-live-v1",
        "status": "PASS" if not failures else "FAIL",
        "variant": variant,
        "rom": relative(rom), "rom_sha256": rom_sha,
        "fixture": relative(fixture),
        "static_receipt": relative(args.static_receipt.resolve()),
        "static_receipt_sha256": args.static_receipt_sha,
        "replays": replays,
        "classification": "E048_NEGATIVE_TO_R265_FIXED_AB",
        "determinism": projection,
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(("PASS" if not failures else "FAIL") + f": Stage-7 menu {variant}")
    for failure in failures:
        print("  - " + failure)
    print("Receipt: " + str(receipt_path))
    return 0 if not failures else 1


def parse_sha(raw: str) -> str:
    value = raw.lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise argparse.ArgumentTypeError("SHA-256 must be 64 hex digits")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static-only", action="store_true")
    mode.add_argument("--run-fixed", action="store_true")
    parser.add_argument("--static-output", type=Path,
                        default=DEFAULT_STATIC_RECEIPT)
    parser.add_argument("--static-receipt", type=Path)
    parser.add_argument("--static-receipt-sha", type=parse_sha)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frames", type=int, default=1800)
    parser.add_argument("--menu-hold", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    require(300 <= args.frames <= 5000, "--frames must be 300..5000")
    require(40 <= args.menu_hold <= 600, "--menu-hold must be 40..600")
    if args.static_only:
        path = scratch(args.static_output, label="static receipt")
        receipt_sha = write_static(path)
        print("STATIC GO: duplicate isolated r265 fixed run")
        print("Receipt: " + relative(path))
        print("Receipt SHA-256: " + receipt_sha)
        print("Fixed command:")
        print(
            "python3 scripts/diagnostics/verify_stage7_menu_signature_invalidation.py "
            f"--run-fixed --static-receipt {relative(path)} "
            f"--static-receipt-sha {receipt_sha} --output "
            "tmp/stage7-menu-signature-invalidation-r265/menu-fixed-r1"
        )
        return 0
    require(args.output is not None, "live mode requires --output")
    return run_variant(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
