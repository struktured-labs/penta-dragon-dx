#!/usr/bin/env python3
"""Bind the release-speed profiles into one seven-stage qualification.

Stage 2's optimized compiler lives in bank $15 and has an HBlank command-site
contract.  The remaining optimized dungeon compiler lives in bank $16.  The
speed-matrix verifier intentionally accepts one compiler profile per run, so
Stages 1--6 use two serialized manifests.  Stage 7 uses the current
world-position-matched patrol oracle: its old frame-keyed right-input route is
phase-confounded and is retained only as diagnostic telemetry.

The operator-approved release floor is 0.95 for named Stages 1/2/3/4/5 while
Stage 6 retains the strict 0.99--1.01 target.  Stage 7 must pass its strict
0.98--1.02 matched-work target.  Every exception remains visible in the
classification and cannot be promoted to a global or unnamed-stage waiver.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
STAGE7_MATRIX = ROOT / "scripts/diagnostics/verify_stage_speed_matrix.py"
STAGE7_BASE_PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
STAGE7_STATE_PROBE = (
    ROOT / "scripts/diagnostics/probe_stage7_state_patrol.lua"
)
STAGE7_VERIFIER = (
    ROOT / "scripts/diagnostics/verify_stage7_state_patrol.py"
)
ORIGINAL_ROM = ROOT / "rom/Penta Dragon (J).gb"
EXPECTED_STAGES = frozenset(range(1, 8))
FIXED_INPUT_STAGES = frozenset(range(1, 7))
MAIN_STAGES = frozenset({1, 3, 4, 5, 6})
STAGE2_STAGES = frozenset({2})
STRICT_LOWER = 0.99
STRICT_UPPER = 1.01
NAMED_RELEASE_FLOOR = 0.95
NAMED_RELEASE_STAGES = frozenset({1, 2, 3, 4, 5})
MAIN_RELEASE_STAGES = NAMED_RELEASE_STAGES & MAIN_STAGES
STAGE2_RELEASE_STAGES = NAMED_RELEASE_STAGES & STAGE2_STAGES
STAGE7_LOWER = 0.98
STAGE7_UPPER = 1.02
STAGE7_CLASSIFICATION = "STRICT_WORLD_POSITION_MATCHED_98_TO_102"
SCHEMA = "penta-split-stage-speed-qualification-v4"
STATUS = "PASS_RELEASE_95_NAMED_STAGE6_STRICT99_STAGE7_WORLD_MATCHED98"
STRICT_CLASSIFICATION = "STRICT_99_TO_101"
NAMED_RELEASE_CLASSIFICATION = "NAMED_STAGE_RELEASE_FLOOR_95"

BASE_POLICY_CONTROLS = frozenset({
    "target_center_passes",
    "target_lower_edge_passes",
    "target_upper_edge_passes",
    "strict_rejects_just_below_target",
    "strict_rejects_just_above_target",
})
def release_policy_controls(stages: frozenset[int]) -> frozenset[str]:
    labels = tuple(f"stage_{stage}" for stage in sorted(stages)) or ("synthetic",)
    return BASE_POLICY_CONTROLS | frozenset(
        f"accepted_floor_{label}_{suffix}"
        for label in labels
        for suffix in (
            "passes_at_equality",
            "classification_is_explicit",
            "rejects_below_floor",
            "never_excuses_speedup",
        )
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_manifest(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"speed manifest is missing: {path}")
    value = json.loads(path.read_text())
    require(isinstance(value, dict), f"speed manifest is not an object: {path}")
    return value


def require_all_true(value: Any, label: str) -> None:
    require(isinstance(value, dict) and value, f"{label} is missing")
    failed = sorted(key for key, passed in value.items() if passed is not True)
    require(not failed, f"{label} failed: {','.join(failed)}")


def require_exact_true_controls(
    value: Any, expected: frozenset[str], label: str
) -> None:
    require(isinstance(value, dict), f"{label} is missing")
    actual = set(value)
    require(
        actual == expected,
        f"{label} schema changed; missing={sorted(expected - actual)}, "
        f"unexpected={sorted(actual - expected)}",
    )
    require_all_true(value, label)


def validate_profile(
    manifest: dict[str, Any],
    *,
    label: str,
    candidate_sha256: str,
    expected_stages: frozenset[int],
    compiler_bank: int,
    compiler_start: int,
    compiler_end: int,
    dma_command_addrs: list[int],
    expected_dma_mode: str | None,
    release_floor_stages: frozenset[int],
) -> list[dict[str, Any]]:
    require(manifest.get("schema") == "penta-stage-speed-matrix-v2",
            f"{label}: wrong schema")
    require(manifest.get("status") == "pass" and not manifest.get("failures"),
            f"{label}: speed matrix did not pass cleanly")
    require(manifest.get("dx_rom_sha256") == candidate_sha256,
            f"{label}: manifest targets another candidate")
    require(manifest.get("mode") == "right" and manifest.get("frames") == 2800,
            f"{label}: wrong route or measurement length")
    require(manifest.get("tolerance") == 0.01,
            f"{label}: strict tolerance changed")
    require(manifest.get("target_ratio_floor") == STRICT_LOWER
            and manifest.get("target_ratio_ceiling") == STRICT_UPPER,
            f"{label}: strict target band changed")
    require(manifest.get("accepted_slowdown_floor") is None,
            f"{label}: global slowdown waiver is not allowed")
    expected_slow_stages = {
        str(stage): NAMED_RELEASE_FLOOR for stage in release_floor_stages
    }
    require(manifest.get("accepted_slow_stages") == expected_slow_stages,
            f"{label}: per-stage release floor policy changed")
    require(manifest.get("compiler_bank") == compiler_bank
            and manifest.get("compiler_start") == compiler_start
            and manifest.get("compiler_end") == compiler_end,
            f"{label}: compiler instrumentation profile changed")
    require(manifest.get("dma_command_addrs") == dma_command_addrs
            and manifest.get("expected_dma_mode") == expected_dma_mode,
            f"{label}: DMA command contract changed")

    require_all_true(manifest.get("input_identity_controls"),
                     f"{label} input identities")
    require_exact_true_controls(
        manifest.get("policy_controls"),
        release_policy_controls(release_floor_stages),
        f"{label} ratio policy controls",
    )
    require_all_true(manifest.get("route_policy_controls"),
                     f"{label} route policy controls")
    require_all_true(manifest.get("central_output_policy_controls"),
                     f"{label} output policy controls")
    require_all_true(manifest.get("dma_command_policy_controls"),
                     f"{label} DMA policy controls")

    rows = manifest.get("rows")
    require(isinstance(rows, list), f"{label}: rows are missing")
    stages = [row.get("stage") for row in rows]
    require(len(stages) == len(set(stages)), f"{label}: duplicate stage row")
    require(frozenset(stages) == expected_stages,
            f"{label}: stages {sorted(stages)} != {sorted(expected_stages)}")

    qualified: list[dict[str, Any]] = []
    for row in rows:
        stage = row["stage"]
        original = row.get("original", {})
        candidate = row.get("dx", {})
        original_hits = original.get("main_loop_hits")
        candidate_hits = candidate.get("main_loop_hits")
        require(isinstance(original_hits, int) and original_hits > 0,
                f"{label} Stage {stage}: invalid original hit count")
        require(isinstance(candidate_hits, int) and candidate_hits > 0,
                f"{label} Stage {stage}: invalid candidate hit count")
        ratio = candidate_hits / original_hits
        require(abs(ratio - row.get("ratio_exact", -1.0)) < 1e-15,
                f"{label} Stage {stage}: ratio is not recomputable")
        has_release_floor = stage in release_floor_stages
        row_floor = NAMED_RELEASE_FLOOR if has_release_floor else None
        require(row.get("accepted_slowdown_floor") == row_floor,
                f"{label} Stage {stage}: effective slowdown floor changed")
        strict_target_met = (
            abs(1.0 - ratio) <= (1.0 - STRICT_LOWER) + 1e-9
        )
        accepted_release_deviation = (
            has_release_floor
            and not strict_target_met
            and NAMED_RELEASE_FLOOR - 1e-9 <= ratio < 1.0
        )
        throughput_accepted = strict_target_met or accepted_release_deviation
        require(row.get("target_met") is strict_target_met,
                f"{label} Stage {stage}: strict-target classification changed")
        require(
            row.get("accepted_slowdown_deviation")
            is accepted_release_deviation,
            f"{label} Stage {stage}: release-floor classification changed",
        )
        require(row.get("throughput_accepted") is throughput_accepted,
                f"{label} Stage {stage}: throughput classification changed")
        lower_bound = (
            NAMED_RELEASE_FLOOR if has_release_floor else STRICT_LOWER
        )
        require(lower_bound <= ratio <= STRICT_UPPER,
                f"{label} Stage {stage}: ratio {ratio:.9f} is below its "
                "release threshold or above the strict ceiling")
        for key in (
            "passed",
            "deterministic_replay",
            "candidate_scene_ok",
            "baseline_continuity_ok",
            "candidate_continuity_ok",
            "route_coverage_ok",
            "central_output_telemetry_ok",
            "candidate_dma_mode_ok",
        ):
            require(row.get(key) is True,
                    f"{label} Stage {stage}: {key} did not pass")
        require(row.get("candidate_dma_command_contract", {}).get("passed") is True,
                f"{label} Stage {stage}: DMA command contract did not pass")
        for replay_key in ("original_replay_receipt_sha256",
                           "dx_replay_receipt_sha256"):
            replay_hashes = row.get(replay_key)
            require(isinstance(replay_hashes, list) and len(replay_hashes) == 2
                    and replay_hashes[0] == replay_hashes[1],
                    f"{label} Stage {stage}: replay payloads differ")
        qualified.append({
            "stage": stage,
            "original_main_loop_hits": original_hits,
            "candidate_main_loop_hits": candidate_hits,
            "ratio_exact": ratio,
            "ratio_percent": round(100.0 * ratio, 6),
            "accepted_slowdown_floor": row_floor,
            "target_met": strict_target_met,
            "accepted_slowdown_deviation": accepted_release_deviation,
            "throughput_accepted": throughput_accepted,
            "qualification_class": (
                STRICT_CLASSIFICATION
                if strict_target_met else NAMED_RELEASE_CLASSIFICATION
            ),
            "deterministic_replay": True,
            "route_coverage_ok": True,
            "scene_ok": True,
        })
    return qualified


def validate_stage7_payload(
    receipt: dict[str, Any], candidate_sha256: str,
) -> dict[str, Any]:
    """Revalidate the current equal-world-position Stage-7 speed receipt."""
    require(receipt.get("schema") == "penta-stage7-state-patrol-v2",
            "Stage-7 world-position receipt has the wrong schema")
    require(receipt.get("status") == "PASS",
            "Stage-7 world-position receipt is not passing")
    require(receipt.get("candidate_sha256") == candidate_sha256,
            "Stage-7 world-position receipt targets another candidate")
    require(receipt.get("original_sha256") == sha256(ORIGINAL_ROM),
            "Stage-7 world-position receipt targets another original ROM")
    require(
        receipt.get("frames") == 4000
        and receipt.get("tolerance") == 0.02
        and receipt.get("maximum_settle_half_cycle") == 24
        and receipt.get("minimum_measured_half_cycles") == 20
        and receipt.get("classification")
        == "EQUAL_WORLD_ENDPOINTS_AFTER_BOUNDED_VERTICAL_SETTLE",
        "Stage-7 world-position measurement policy changed",
    )
    require(receipt.get("input_identities_unchanged") is True,
            "Stage-7 world-position tool identities changed during the run")
    identities = receipt.get("input_identities")
    require(isinstance(identities, dict),
            "Stage-7 world-position input identities are missing")
    require(identities == {
        "candidate": candidate_sha256,
        "original": sha256(ORIGINAL_ROM),
        "matrix": sha256(STAGE7_MATRIX),
        "base_probe": sha256(STAGE7_BASE_PROBE),
        "state_probe": sha256(STAGE7_STATE_PROBE),
        "verifier": sha256(STAGE7_VERIFIER),
    }, "Stage-7 world-position receipt has stale input identities")
    for key in ("deterministic_replay", "mutation_controls",
                "metric_policy_controls"):
        require_all_true(receipt.get(key), f"Stage-7 {key}")

    capture = receipt.get("capture")
    require(isinstance(capture, dict), "Stage-7 nested capture is missing")
    require_all_true(capture.get("nested_checks"),
                     "Stage-7 nested capture checks")
    manifest_path = Path(str(capture.get("manifest", ""))).resolve()
    require(manifest_path.is_file(),
            "Stage-7 nested speed manifest is missing")
    require(capture.get("manifest_sha256") == sha256(manifest_path),
            "Stage-7 nested speed manifest hash changed")

    metric = receipt.get("metric")
    require(isinstance(metric, dict), "Stage-7 matched-work metric is missing")
    require(
        metric.get("strict_target_met") is True
        and metric.get("target_floor") == STAGE7_LOWER
        and metric.get("target_ceiling") == STAGE7_UPPER
        and metric.get("endpoint_route_exact") is True
        and metric.get("post_settle_vertical_exact") is True
        and isinstance(metric.get("measured_half_cycles"), int)
        and metric["measured_half_cycles"] >= 20,
        "Stage-7 matched-work metric did not pass its exact policy",
    )
    ratios = metric.get("throughput_ratio_by_replay")
    require(
        isinstance(ratios, dict)
        and set(ratios) == {"a", "b"}
        and isinstance(ratios["a"], (int, float))
        and not isinstance(ratios["a"], bool)
        and ratios["a"] == ratios["b"]
        and STAGE7_LOWER <= ratios["a"] <= STAGE7_UPPER,
        "Stage-7 matched-work replay ratios differ or miss the target",
    )
    elapsed = metric.get("elapsed_frames")
    require(isinstance(elapsed, dict),
            "Stage-7 matched-work elapsed frames are missing")
    require(
        set(elapsed) == {"original_a", "original_b", "dx_a", "dx_b"}
        and all(isinstance(value, int) and value > 0
                for value in elapsed.values())
        and elapsed["original_a"] == elapsed["original_b"]
        and elapsed["dx_a"] == elapsed["dx_b"]
        and abs(ratios["a"]
                - elapsed["original_a"] / elapsed["dx_a"]) < 1e-15,
        "Stage-7 matched-work ratio is not recomputable",
    )
    return {
        "stage": 7,
        "ratio_exact": ratios["a"],
        "ratio_percent": round(100.0 * ratios["a"], 6),
        "target_floor": STAGE7_LOWER,
        "target_ceiling": STAGE7_UPPER,
        "qualification_class": STAGE7_CLASSIFICATION,
        "deterministic_replay": True,
        "endpoint_route_exact": True,
        "post_settle_vertical_exact": True,
        "measured_half_cycles": metric["measured_half_cycles"],
        "elapsed_frames": elapsed,
        "fixed_frame_loop_ratio_diagnostic": capture.get(
            "fixed_frame_loop_ratio"
        ),
    }


def validate_pair(
    candidate_sha256: str,
    main_manifest: dict[str, Any],
    stage2_manifest: dict[str, Any],
    stage7_receipt: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    main_rows = validate_profile(
        main_manifest,
        label="bank-22 main profile",
        candidate_sha256=candidate_sha256,
        expected_stages=MAIN_STAGES,
        compiler_bank=0x16,
        compiler_start=0x6C80,
        compiler_end=0x7232,
        dma_command_addrs=[],
        expected_dma_mode=None,
        release_floor_stages=MAIN_RELEASE_STAGES,
    )
    stage2_rows = validate_profile(
        stage2_manifest,
        label="bank-21 Stage-2 profile",
        candidate_sha256=candidate_sha256,
        expected_stages=STAGE2_STAGES,
        compiler_bank=0x15,
        compiler_start=0x4C00,
        compiler_end=0x582D,
        dma_command_addrs=[0x5816],
        expected_dma_mode="hblank",
        release_floor_stages=STAGE2_RELEASE_STAGES,
    )
    rows = sorted(main_rows + stage2_rows, key=lambda row: row["stage"])
    require({row["stage"] for row in rows} == FIXED_INPUT_STAGES,
            "fixed-input qualification does not cover Stages 1--6 exactly once")
    require(
        main_manifest.get("original_rom_sha256")
        == stage2_manifest.get("original_rom_sha256"),
        "speed profiles use different original ROMs",
    )
    require(main_manifest.get("tool_identity") == stage2_manifest.get("tool_identity"),
            "speed profiles use different verifier/probe/launcher identities")
    stage7 = validate_stage7_payload(stage7_receipt, candidate_sha256)
    require({row["stage"] for row in rows} | {stage7["stage"]}
            == EXPECTED_STAGES,
            "combined qualification does not cover every stage exactly once")
    return rows, stage7


def rejects(
    candidate_sha256: str,
    main: dict[str, Any],
    stage2: dict[str, Any],
    stage7: dict[str, Any],
    mutation: str,
) -> bool:
    changed_main = copy.deepcopy(main)
    changed_stage2 = copy.deepcopy(stage2)
    changed_stage7 = copy.deepcopy(stage7)
    if mutation == "candidate":
        changed_main["dx_rom_sha256"] = "0" * 64
    elif mutation == "missing_stage1_waiver":
        changed_main["accepted_slow_stages"].pop("1")
    elif mutation == "wrong_stage1_waiver":
        changed_main["accepted_slow_stages"] = {"1": 0.96}
    elif mutation == "global_waiver":
        changed_main["accepted_slowdown_floor"] = NAMED_RELEASE_FLOOR
    elif mutation == "other_stage_waiver":
        changed_main["accepted_slow_stages"]["6"] = NAMED_RELEASE_FLOOR
    elif mutation == "classification":
        stage1 = next(row for row in changed_main["rows"] if row["stage"] == 1)
        stage1["accepted_slowdown_deviation"] = not stage1.get(
            "accepted_slowdown_deviation", False
        )
    elif mutation == "missing_stage":
        changed_main["rows"] = changed_main["rows"][:-1]
    elif mutation == "duplicate_stage":
        changed_main["rows"].append(copy.deepcopy(changed_main["rows"][0]))
    elif mutation == "ratio":
        changed_main["rows"][0]["dx"]["main_loop_hits"] = 1
    elif mutation == "stage2_profile":
        changed_stage2["compiler_bank"] = 0x16
    elif mutation == "stage2_dma":
        changed_stage2["dma_command_addrs"] = []
    elif mutation == "stage7_candidate":
        changed_stage7["candidate_sha256"] = "0" * 64
    elif mutation == "stage7_status":
        changed_stage7["status"] = "FAIL"
    elif mutation == "stage7_ratio":
        changed_stage7["metric"]["throughput_ratio_by_replay"]["a"] = 0.97
    elif mutation == "stage7_tool":
        changed_stage7["input_identities"]["verifier"] = "0" * 64
    else:
        raise ValueError(mutation)
    try:
        validate_pair(
            candidate_sha256, changed_main, changed_stage2, changed_stage7
        )
    except AssertionError:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--main-manifest", type=Path, required=True)
    parser.add_argument("--stage2-manifest", type=Path, required=True)
    parser.add_argument("--stage7-state-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    main_path = args.main_manifest.resolve()
    stage2_path = args.stage2_manifest.resolve()
    stage7_path = args.stage7_state_receipt.resolve()
    require(candidate.is_file(), f"candidate is missing: {candidate}")
    candidate_before = sha256(candidate)
    main_manifest = load_manifest(main_path)
    stage2_manifest = load_manifest(stage2_path)
    stage7_receipt = load_manifest(stage7_path)
    rows, stage7 = validate_pair(
        candidate_before, main_manifest, stage2_manifest, stage7_receipt
    )

    mutation_names = (
        "candidate",
        "missing_stage1_waiver",
        "wrong_stage1_waiver",
        "global_waiver",
        "other_stage_waiver",
        "classification",
        "missing_stage",
        "duplicate_stage",
        "ratio",
        "stage2_profile",
        "stage2_dma",
        "stage7_candidate",
        "stage7_status",
        "stage7_ratio",
        "stage7_tool",
    )
    mutation_controls = {
        f"rejects_{name}": rejects(
            candidate_before, main_manifest, stage2_manifest,
            stage7_receipt, name,
        )
        for name in mutation_names
    }
    require_all_true(mutation_controls, "roll-up mutation controls")
    require(sha256(candidate) == candidate_before,
            "candidate changed during qualification")

    receipt = {
        "schema": SCHEMA,
        "status": STATUS,
        "candidate": str(candidate),
        "candidate_sha256": candidate_before,
        "original_rom_sha256": main_manifest["original_rom_sha256"],
        "measurement": {
            "input_mode": "right",
            "frames": 2800,
            "strict_ratio_floor": STRICT_LOWER,
            "strict_ratio_ceiling": STRICT_UPPER,
            "named_stage_operator_release_floor": NAMED_RELEASE_FLOOR,
            "named_floor_stages": sorted(NAMED_RELEASE_STAGES),
            "named_floors_are_per_stage_only": True,
            "strict_target_misses_remain_explicit": True,
            "strict_fixed_input_stages": [6],
            "stage7_world_position_ratio_floor": STAGE7_LOWER,
            "stage7_world_position_ratio_ceiling": STAGE7_UPPER,
            "stage7_fixed_frame_route_is_diagnostic_only": True,
            "global_slowdown_waivers": False,
            "other_stage_slowdown_waivers": False,
            "stages_covered_exactly_once": list(range(1, 8)),
            "scroll_change_count_policy": (
                "diagnostic-only; exact route distance, endpoints, and ordered "
                "room transitions are gated by route_coverage_ok"
            ),
        },
        "profiles": {
            "stages_1_3_4_5_6": {
                "manifest": str(main_path),
                "manifest_sha256": sha256(main_path),
                "compiler_bank": 0x16,
                "compiler_range": [0x6C80, 0x7232],
                "accepted_slowdown_floor": None,
                "accepted_slow_stages": {
                    str(stage): NAMED_RELEASE_FLOOR
                    for stage in sorted(MAIN_RELEASE_STAGES)
                },
            },
            "stage_2": {
                "manifest": str(stage2_path),
                "manifest_sha256": sha256(stage2_path),
                "compiler_bank": 0x15,
                "compiler_range": [0x4C00, 0x582D],
                "dma_command_addr": 0x5816,
                "expected_dma_mode": "hblank",
                "accepted_slowdown_floor": None,
                "accepted_slow_stages": {
                    str(stage): NAMED_RELEASE_FLOOR
                    for stage in sorted(STAGE2_RELEASE_STAGES)
                },
            },
            "stage_7_world_position": {
                "receipt": str(stage7_path),
                "receipt_sha256": sha256(stage7_path),
                **stage7,
                "input_identities": stage7_receipt["input_identities"],
            },
        },
        "tool_identity": main_manifest["tool_identity"],
        "rows": rows,
        "mutation_controls": mutation_controls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        "PASS: exact candidate meets the operator-approved 95% floor on "
        "named Stages 1/2/3/4/5, strict 99-101% speed on Stage 6, and "
        "strict matched-work speed on Stage 7"
    )
    for row in rows:
        print(
            f"Stage {row['stage']}: {row['candidate_main_loop_hits']}/"
            f"{row['original_main_loop_hits']} = {row['ratio_percent']:.3f}%"
        )
    print(
        f"Stage 7 matched work: {stage7['ratio_percent']:.3f}% "
        f"over {stage7['measured_half_cycles']} uncontested legs"
    )
    print(f"Receipt: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
