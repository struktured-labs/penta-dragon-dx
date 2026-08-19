#!/usr/bin/env python3
"""Build and validate the human-visible exception ledger for suite receipts.

Passing a release gate can still mean that a measured target miss was accepted
by explicit policy.  This module lifts those decisions out of deeply nested
artifacts so a green top-level receipt cannot hide them.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "penta-release-ledger-v1"
HEX64 = set("0123456789abcdef")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read release-ledger evidence {path}: {exc}")
    if not isinstance(value, dict):
        raise RuntimeError(f"release-ledger evidence is not an object: {path}")
    return value


def canonical_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def collect_release_ledger(matrix_dir: Path, *, expanded: bool) -> dict[str, Any]:
    """Extract every accepted target miss from a completed release matrix."""

    artifacts_dir = matrix_dir / "artifacts"
    evidence_paths = {
        "title_attract": artifacts_dir / "title-idle-reel.summary.json",
        "gameplay_speed": artifacts_dir / "gameplay-speed/manifest.json",
        "boss_speed": artifacts_dir / "boss-speed-parity.json",
        "boss_trajectory": artifacts_dir / "boss-trajectory-pairing.json",
        "boss_trajectory_null": (
            artifacts_dir / "boss-trajectory-pairing-null.json"
        ),
    }
    if expanded:
        evidence_paths["ted_readiness"] = (
            artifacts_dir / "ted-release-readiness/report.json"
        )
    documents = {name: load_json(path) for name, path in evidence_paths.items()}
    evidence = {
        name: {
            "path": path.relative_to(matrix_dir).as_posix(),
            "sha256": sha256(path),
        }
        for name, path in evidence_paths.items()
    }

    deviations: list[dict[str, Any]] = []

    title = documents["title_attract"]
    title_ratio = title["demo_combined_frames"] / title["demo_combined_og_frames"]
    deviations.append({
        "id": "title_attract_combined_duration",
        "scope": "title_attract_demo",
        "measurement": "combined_route_duration",
        "direction": "slower",
        "ratio_dx_over_og": title_ratio,
        "deviation_percent": (title_ratio - 1.0) * 100.0,
        "release_envelope_percent": (
            title["demo_combined_duration_tolerance"] * 100.0
        ),
        "policy": "accepted_combined_route_envelope",
        "evidence": "title_attract",
    })

    gameplay = documents["gameplay_speed"]
    for row in gameplay.get("rows", []):
        if (
            row.get("target_met") is False
            and row.get("accepted_slowdown_deviation") is True
            and row.get("throughput_accepted") is True
        ):
            ratio = float(row["ratio"])
            deviations.append({
                "id": f"stage_{row['stage']}_speed",
                "scope": f"stage_{row['stage']}",
                "measurement": "input_identical_gameplay_throughput",
                "direction": "slower",
                "ratio_dx_over_og": ratio,
                "deviation_percent": (1.0 - ratio) * 100.0,
                "target_percent": float(gameplay["tolerance"]) * 100.0,
                "accepted_floor_ratio": float(
                    gameplay["accepted_slowdown_floor"]
                ),
                "policy": "accepted_slowdown_floor",
                "evidence": "gameplay_speed",
            })

    boss_speed = documents["boss_speed"]
    for row in boss_speed.get("bosses", []):
        if (
            row.get("target_met") is False
            and row.get("accepted_slowdown_deviation") is True
            and row.get("throughput_accepted") is True
        ):
            deviations.append({
                "id": f"boss_{row['boss']}_speed",
                "scope": row["boss"],
                "measurement": "arena_loop_throughput",
                "direction": "slower",
                "ratio_dx_over_og": float(row["speed_ratio"]),
                "deviation_percent": float(row["slowdown_percent"]),
                "target_percent": float(
                    boss_speed["maximum_slowdown_percent"]
                ),
                "accepted_floor_ratio": float(
                    boss_speed["accepted_slow_bosses"][row["boss"]]
                ),
                "policy": "operator_accepted_slow_boss",
                "evidence": "boss_speed",
            })

    if expanded:
        ted = documents["ted_readiness"]["cadence"]
        if (
            ted.get("target_met") is False
            and ted.get("accepted_phase_deviation") is True
            and ted.get("phase_bound_met") is True
        ):
            deviations.append({
                "id": "ted_publication_cadence",
                "scope": "ted",
                "measurement": "publication_event_rate",
                "direction": "slower",
                "ratio_dx_over_og": float(ted["speed_ratio"]),
                "deviation_percent": float(ted["slowdown_percent"]),
                "target_percent": float(
                    ted["maximum_speed_deviation_percent"]
                ),
                "policy": "accepted_phase_deviation",
                "evidence": "ted_readiness",
            })

    null_rows = documents["boss_trajectory_null"].get("bosses", [])
    if len(null_rows) != 1:
        raise RuntimeError("trajectory null receipt must contain exactly one boss")
    null_alignment = null_rows[0].get("alignment", {})
    null_slowdown = null_alignment.get("slowdown_percent")
    null_transition_slowdown = null_alignment.get(
        "matched_transition_span", {}
    ).get("slowdown_percent")
    if (
        null_rows[0].get("status") != "paired"
        or null_slowdown is None
        or abs(float(null_slowdown)) > 1e-12
        or null_transition_slowdown is None
        or abs(float(null_transition_slowdown)) > 1e-12
    ):
        raise RuntimeError(
            "phase-shifted same-ROM trajectory null did not measure 0.00%"
        )

    trajectory_rows: list[dict[str, Any]] = []
    for row in documents["boss_trajectory"].get("bosses", []):
        alignment = row.get("alignment", {})
        if row.get("status") != "paired" or alignment.get("slowdown_percent") is None:
            raise RuntimeError(
                f"boss trajectory is not magnitude-valid for {row.get('boss')}"
            )
        slowdown = float(alignment["slowdown_percent"])
        transition_span = alignment.get("matched_transition_span", {})
        transition_slowdown = transition_span.get("slowdown_percent")
        if transition_slowdown is None:
            raise RuntimeError(
                f"boss trajectory lacks transition cadence for {row.get('boss')}"
            )
        transition_slowdown = float(transition_slowdown)
        trajectory_rows.append({
            "boss": row["boss"],
            "classification": "paired",
            "matched_transitions": int(alignment["matched_transitions"]),
            "slip_aware_matched": int(alignment["slip_aware_matched"]),
            "ratio_dx_over_og_frames_per_iter": float(
                alignment["dx_over_og_frames_per_iter"]
            ),
            "slowdown_percent": slowdown,
            "within_two_percent": abs(slowdown) <= 2.0,
            "transition_slowdown_percent": transition_slowdown,
            "transition_within_two_percent": abs(transition_slowdown) <= 2.0,
            "pairing_confidence": alignment["pairing_confidence"],
            "policy_status": (
                "within_target" if abs(slowdown) <= 2.0
                else "accepted_bounded_speedup" if slowdown < -2.0
                else "accepted_operator_slowdown"
            ),
            "interpretation": (
                "arena_loop_throughput_and_player_facing_transition_cadence"
            ),
        })
    trajectory_rows.sort(key=lambda row: row["boss"])
    expected_bosses = {
        "shalamar", "riff", "crystal_dragon", "cameo", "ted",
        "troop", "faze", "angela", "penta_dragon",
    }
    if {row["boss"] for row in trajectory_rows} != expected_bosses:
        raise RuntimeError("trajectory receipt does not contain all nine bosses")

    # Do not bury accepted fast boss cadence behind a green policy gate. The
    # matched-transition instrument proves this is real boss-cycle pacing,
    # rather than the old phase-mismatched loop-rate artifact. Lift every
    # >2% faster result into the same human-visible exception list as slower
    # gameplay and Crystal/Ted policy exceptions.
    for row in trajectory_rows:
        transition_slowdown = row["transition_slowdown_percent"]
        if transition_slowdown < -2.0:
            deviations.append({
                "id": f"boss_{row['boss']}_matched_transition_cadence",
                "scope": row["boss"],
                "measurement": "matched_player_facing_transition_cadence",
                "direction": "faster",
                "ratio_dx_over_og": 1.0 + transition_slowdown / 100.0,
                "deviation_percent": abs(transition_slowdown),
                "target_percent": 2.0,
                "pairing_confidence": row["pairing_confidence"],
                "policy": "accepted_bounded_speedup",
                "evidence": "boss_trajectory",
            })

    deviations.sort(key=lambda item: item["id"])
    ledger: dict[str, Any] = {
        "schema": SCHEMA,
        "accepted_deviation_count": len(deviations),
        "accepted_deviations": deviations,
        "boss_matched_work_timing": trajectory_rows,
        "trajectory_null_control": {
            "boss": null_rows[0]["boss"],
            "phase_shifted": True,
            "slowdown_percent": float(null_slowdown),
            "transition_slowdown_percent": float(null_transition_slowdown),
            "result": "exact_zero",
            "evidence": "boss_trajectory_null",
        },
        "evidence": evidence,
    }
    ledger["ledger_sha256"] = canonical_sha256(ledger)
    return ledger


def validate_release_ledger(value: object, *, expanded: bool) -> list[str]:
    """Return structural/integrity errors for a receipt-embedded ledger."""

    if not isinstance(value, dict):
        return ["release_ledger is not an object"]
    errors: list[str] = []
    if value.get("schema") != SCHEMA:
        errors.append("release_ledger schema mismatch")
    body = dict(value)
    recorded_hash = body.pop("ledger_sha256", None)
    if recorded_hash != canonical_sha256(body):
        errors.append("release_ledger canonical hash mismatch")
    deviations = value.get("accepted_deviations")
    if not isinstance(deviations, list):
        return errors + ["accepted_deviations is not a list"]
    if value.get("accepted_deviation_count") != len(deviations):
        errors.append("accepted_deviation_count mismatch")
    ids = [item.get("id") for item in deviations if isinstance(item, dict)]
    if len(ids) != len(deviations) or len(ids) != len(set(ids)):
        errors.append("accepted deviation IDs are missing or duplicated")
    required = {
        "title_attract_combined_duration",
        "stage_1_speed",
        "stage_5_speed",
        "stage_7_speed",
        "boss_crystal_dragon_speed",
    }
    if expanded:
        required.add("ted_publication_cadence")
    required.update({
        "boss_riff_matched_transition_cadence",
        "boss_cameo_matched_transition_cadence",
        "boss_troop_matched_transition_cadence",
        "boss_faze_matched_transition_cadence",
        "boss_angela_matched_transition_cadence",
        "boss_penta_dragon_matched_transition_cadence",
    })
    missing = sorted(required - set(ids))
    if missing:
        errors.append("accepted deviations omitted: " + ", ".join(missing))
    for item in deviations:
        if not isinstance(item, dict):
            continue
        if item.get("direction") not in {"slower", "faster"}:
            errors.append(f"invalid deviation direction for {item.get('id')}")
        if not isinstance(item.get("ratio_dx_over_og"), (int, float)):
            errors.append(f"missing deviation ratio for {item.get('id')}")

    timing = value.get("boss_matched_work_timing")
    if not isinstance(timing, list) or len(timing) != 9:
        errors.append("matched-work timing does not contain all nine bosses")
    elif any(row.get("classification") != "paired" for row in timing):
        errors.append("matched-work timing contains an unpaired boss")
    elif any(
        row.get("pairing_confidence") not in {"thin", "moderate", "deep"}
        or not isinstance(row.get("transition_slowdown_percent"), (int, float))
        for row in timing
    ):
        errors.append("matched-work timing lacks transition cadence/confidence")
    null = value.get("trajectory_null_control", {})
    if (
        null.get("phase_shifted") is not True
        or null.get("result") != "exact_zero"
        or null.get("slowdown_percent") != 0.0
        or null.get("transition_slowdown_percent") != 0.0
    ):
        errors.append("trajectory null control is not exact zero")
    evidence = value.get("evidence")
    required_evidence = {
        "title_attract", "gameplay_speed", "boss_speed",
        "boss_trajectory", "boss_trajectory_null",
    }
    if expanded:
        required_evidence.add("ted_readiness")
    if not isinstance(evidence, dict):
        errors.append("release-ledger evidence map is missing")
    else:
        for name in sorted(required_evidence):
            item = evidence.get(name, {})
            digest = item.get("sha256")
            path = item.get("path")
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in HEX64 for char in digest)
            ):
                errors.append(f"invalid evidence hash for {name}")
            if not isinstance(path, str) or not path.startswith("artifacts/"):
                errors.append(f"invalid evidence path for {name}")
    return errors
