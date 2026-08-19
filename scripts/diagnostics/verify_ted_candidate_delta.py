#!/usr/bin/env python3
"""Reject a Ted candidate that worsens any authoritative replay invariant."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "penta-ted-candidate-delta-v4"
READINESS_SCHEMA = "penta-ted-release-readiness-v4"
BASELINE_SCHEMA = "penta-ted-qualified-baseline-v1"
LOWER_IS_BETTER = (
    "native_pose_mismatches", "numbered_identity_mismatches",
    "numbered_identity_mismatch_frames", "sparse_position_mismatches",
    "floor_lattice_mismatches", "floor_palette_mismatches",
    "crownless_pose_frames",
)
HIGHER_IS_BETTER = ("native_pose_matches",)
ADVISORY_READINESS_CHECKS = frozenset({"cadence_within_one_percent"})


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or not isinstance(value.get("metrics"), dict):
        raise ValueError(f"{path}: missing object-valued metrics")
    return value


def load_readiness(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema") != READINESS_SCHEMA:
        raise ValueError(f"{path}: expected {READINESS_SCHEMA}")
    if not isinstance(value.get("checks"), dict):
        raise ValueError(f"{path}: missing object-valued checks")
    return value


def compare(baseline: dict[str, object], candidate: dict[str, object]):
    old, new = baseline["metrics"], candidate["metrics"]
    assert isinstance(old, dict) and isinstance(new, dict)
    rows, failures = {}, []
    for key in LOWER_IS_BETTER:
        before, after = int(old.get(key, 0)), int(new.get(key, 0))
        passed = after <= before
        rows[key] = {"baseline": before, "candidate": after,
                     "delta": after - before, "non_regression": passed}
        if not passed:
            failures.append(key)
    for key in HIGHER_IS_BETTER:
        before, after = int(old.get(key, 0)), int(new.get(key, 0))
        passed = after >= before
        rows[key] = {"baseline": before, "candidate": after,
                     "delta": after - before, "non_regression": passed}
        if not passed:
            failures.append(key)
    before, after = int(old.get("frames", -1)), int(new.get("frames", -2))
    passed = before == after == 2800
    rows["frames"] = {"baseline": before, "candidate": after,
                      "delta": after - before, "non_regression": passed}
    if not passed:
        failures.append("frames")
    if candidate.get("deterministic_replay") is not True:
        failures.append("deterministic_replay")
    return rows, sorted(set(failures))


def compare_readiness(
    baseline: dict[str, object], candidate: dict[str, object]
) -> tuple[dict[str, object], list[str], list[str]]:
    old_checks = baseline["checks"]
    new_checks = candidate["checks"]
    assert isinstance(old_checks, dict) and isinstance(new_checks, dict)
    lost_checks = sorted(
        key for key, passed in old_checks.items()
        if key not in ADVISORY_READINESS_CHECKS
        and passed is True and new_checks.get(key) is not True
    )
    gained_checks = sorted(
        key for key, passed in new_checks.items()
        if passed is True and old_checks.get(key) is not True
    )

    old_cadence = abs(float(baseline.get("cadence", {}).get(
        "slowdown_percent", 999.0)))
    new_cadence = abs(float(candidate.get("cadence", {}).get(
        "slowdown_percent", 999.0)))
    cadence_ok = (
        candidate.get("cadence", {}).get("status") == "pass"
        and candidate.get("cadence", {}).get("phase_bound_met") is True
    )

    publication = {}
    publication_failures = []
    publication_improvements = []
    for key in ("partial_foreign_cells", "partial_not_complete_next_frame"):
        before = int(baseline.get("publication_sequence", {}).get(key, -1))
        after = int(candidate.get("publication_sequence", {}).get(key, -1))
        passed = before >= 0 and after >= 0 and after <= before
        publication[key] = {
            "baseline": before, "candidate": after, "delta": after - before,
            "non_regression": passed,
        }
        if not passed:
            publication_failures.append(key)
        elif after < before:
            publication_improvements.append(key)

    failures = [f"lost_check:{key}" for key in lost_checks]
    if not cadence_ok:
        failures.append("cadence_release_bound")
    failures.extend(f"publication:{key}" for key in publication_failures)
    if candidate.get("input_errors"):
        failures.append("candidate_input_errors")
    improvements = [f"gained_check:{key}" for key in gained_checks]
    if cadence_ok and new_cadence < old_cadence - 1e-9:
        improvements.append("cadence_absolute_deviation")
    improvements.extend(f"publication:{key}" for key in publication_improvements)
    details = {
        "lost_passing_checks": lost_checks,
        "gained_passing_checks": gained_checks,
        "cadence_absolute_deviation_percent": {
            "baseline": old_cadence, "candidate": new_cadence,
            "delta": new_cadence - old_cadence,
            "non_regression": cadence_ok,
            "comparison_kind": "target telemetry; release-bound status gates",
        },
        "publication": publication,
    }
    return details, failures, improvements


def validate_pair(
    label: str, determinism: dict[str, object], readiness: dict[str, object]
) -> list[str]:
    failures = []
    identity = readiness.get("identity", {})
    geometry = readiness.get("geometry", {})
    metrics = determinism.get("metrics", {})
    if not isinstance(identity, dict) or not isinstance(geometry, dict):
        return [f"{label}_receipt_identity"]
    if (
        identity.get("rom_sha256") != determinism.get("rom_sha256")
        or identity.get("determinism_rom_sha256") != determinism.get("rom_sha256")
        or identity.get("state_sha256") != determinism.get("state_sha256")
        or identity.get("trace_sha256") != determinism.get("trace_sha256")
    ):
        failures.append(f"{label}_receipt_identity")
    if not isinstance(metrics, dict) or any(
        geometry.get(key) != metrics.get(key)
        for key in (
            "frames", "native_pose_matches", "native_pose_mismatches",
            "numbered_identity_mismatches", "sparse_position_mismatches",
            "floor_lattice_mismatches", "floor_palette_mismatches",
        )
    ):
        failures.append(f"{label}_geometry_payload")
    return failures


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_baseline_pin(
    pin_path: Path,
    determinism_path: Path,
    readiness_path: Path,
    determinism: dict[str, object],
    readiness: dict[str, object],
) -> list[str]:
    pin = json.loads(pin_path.read_text())
    return compare_baseline_pin(
        pin, file_sha256(determinism_path), file_sha256(readiness_path),
        determinism, readiness,
    )


def compare_baseline_pin(
    pin: object,
    determinism_receipt_sha256: str,
    readiness_receipt_sha256: str,
    determinism: dict[str, object],
    readiness: dict[str, object],
) -> list[str]:
    if not isinstance(pin, dict) or pin.get("schema") != BASELINE_SCHEMA:
        return ["baseline_pin_schema"]
    failures = []
    if pin.get("determinism_receipt_sha256") != determinism_receipt_sha256:
        failures.append("baseline_pin_determinism_receipt")
    if pin.get("readiness_receipt_sha256") != readiness_receipt_sha256:
        failures.append("baseline_pin_readiness_receipt")
    identity = readiness.get("identity", {})
    if (
        pin.get("rom_sha256") != determinism.get("rom_sha256")
        or pin.get("state_sha256") != determinism.get("state_sha256")
        or pin.get("trace_sha256") != determinism.get("trace_sha256")
        or not isinstance(identity, dict)
        or pin.get("rom_sha256") != identity.get("rom_sha256")
    ):
        failures.append("baseline_pin_identity")
    metrics = determinism.get("metrics", {})
    pinned_metrics = pin.get("metrics", {})
    if (
        not isinstance(metrics, dict) or not isinstance(pinned_metrics, dict)
        or pin.get("frames") != metrics.get("frames")
        or any(metrics.get(key) != value for key, value in pinned_metrics.items())
    ):
        failures.append("baseline_pin_metrics")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-readiness", type=Path, required=True)
    parser.add_argument("--candidate-readiness", type=Path, required=True)
    parser.add_argument("--baseline-pin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-improvement", action="store_true")
    args = parser.parse_args()
    baseline = load(args.baseline)
    candidate = load(args.candidate)
    baseline_readiness = load_readiness(args.baseline_readiness)
    candidate_readiness = load_readiness(args.candidate_readiness)
    comparisons, failures = compare(baseline, candidate)
    failures.extend(validate_pair("baseline", baseline, baseline_readiness))
    failures.extend(validate_pair("candidate", candidate, candidate_readiness))
    failures.extend(validate_baseline_pin(
        args.baseline_pin, args.baseline, args.baseline_readiness,
        baseline, baseline_readiness,
    ))
    readiness, readiness_failures, readiness_improvements = compare_readiness(
        baseline_readiness, candidate_readiness,
    )
    failures.extend(readiness_failures)
    improvements = sorted(
        key for key, row in comparisons.items()
        if key != "frames" and (
            (key in LOWER_IS_BETTER and int(row["delta"]) < 0)
            or (key in HIGHER_IS_BETTER and int(row["delta"]) > 0)
        )
    )
    improvements.extend(readiness_improvements)
    improvements = sorted(set(improvements))
    if args.require_improvement and not improvements:
        failures.append("no_authoritative_improvement")
    receipt = {
        "schema": SCHEMA, "status": "pass" if not failures else "fail",
        "baseline": str(args.baseline.resolve()),
        "candidate": str(args.candidate.resolve()),
        "baseline_readiness": str(args.baseline_readiness.resolve()),
        "candidate_readiness": str(args.candidate_readiness.resolve()),
        "baseline_pin": str(args.baseline_pin.resolve()),
        "baseline_pin_sha256": file_sha256(args.baseline_pin),
        "comparisons": comparisons, "improvements": improvements,
        "readiness_comparisons": readiness,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
