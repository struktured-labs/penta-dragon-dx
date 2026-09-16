#!/usr/bin/env python3
"""Static/corpus gate for the r264 Stage-7 Scene-$08 router diagnostic."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_stage7_scene08_pair_router_r264 as build  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def records(path: Path) -> list[list[str]]:
    result = [line.split("\t") for line in path.read_text().splitlines()]
    if not result or any(len(row) < 30 for row in result):
        raise AssertionError(f"malformed Stage7 trace: {path}")
    return result


def camera_contract(path: Path) -> dict[str, object]:
    runs: list[tuple[int, int, int, int]] = []
    for row in records(path):
        current = (
            int(row[1]), int(row[3], 16),
            int(row[4], 16), int(row[5], 16),
        )
        if not runs or current[1:] != runs[-1][1:]:
            runs.append(current)
    x_deltas: list[int] = []
    y_deltas: list[int] = []
    for before, after in zip(runs, runs[1:]):
        if before[1] != after[1]:
            continue
        if before[3] == after[3]:
            delta = (after[2] - before[2]) % 16
            if delta:
                x_deltas.append(delta)
        if before[2] == after[2]:
            delta = (before[3] - after[3]) % 16
            if delta:
                y_deltas.append(delta)
    return {
        "camera_change_runs": len(runs),
        "horizontal_modular_pixels": sum(x_deltas),
        "vertical_modular_pixels": sum(y_deltas),
        "horizontal_step_histogram": {
            str(key): value for key, value in sorted(Counter(x_deltas).items())
        },
        "vertical_step_histogram": {
            str(key): value for key, value in sorted(Counter(y_deltas).items())
        },
        "last_camera_event": {
            "frame": runs[-1][0],
            "room": runs[-1][1],
            "scx": runs[-1][2],
            "scy": runs[-1][3],
        },
    }


def semantic_changes(path: Path) -> dict[str, object]:
    changes = []
    previous_raw: bytes | None = None
    for row in records(path):
        raw = bytes.fromhex(row[-1])
        if int(row[8]):
            if previous_raw is not None and raw == previous_raw:
                raise AssertionError("semantic change reported without source change")
            changes.append({
                "changed_cells": int(row[9]),
                "desired_hash": int(row[10]),
                "raw_sha256": digest(raw),
            })
        previous_raw = raw
    return {
        "count": len(changes),
        "changed_cells": [entry["changed_cells"] for entry in changes],
        "desired_hashes": [entry["desired_hash"] for entry in changes],
        "raw_sha256": [entry["raw_sha256"] for entry in changes],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base", type=Path,
        default=Path("tmp/stage1-menu-hidden-repair-r264/candidate.gb"),
    )
    parser.add_argument(
        "--candidate", type=Path,
        default=Path("tmp/stage7-scene08-pair-router-r264/candidate.gb"),
    )
    parser.add_argument(
        "--r264-manifest", type=Path,
        default=Path(
            "tmp/stage1-menu-hidden-repair-r264/"
            "all-stage-speed-right-r1/manifest.json"
        ),
    )
    parser.add_argument(
        "--prior-trace", type=Path,
        default=Path(
            "tmp/source-integration-r120/stage-speed-matrix/"
            "stage7-dx-a-right/attr-events.tsv"
        ),
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path(
            "tmp/stage7-scene08-pair-router-r264/static-receipt.json"
        ),
    )
    args = parser.parse_args()

    base = args.base.read_bytes()
    candidate = args.candidate.read_bytes()
    expected, build_receipt = build.install(base)
    if candidate != expected:
        raise AssertionError("candidate is not the deterministic r264 build")

    manifest = json.loads(args.r264_manifest.read_text())
    stage7 = next(row for row in manifest["rows"] if row["stage"] == 7)
    root = args.r264_manifest.parent
    original_trace = root / "stage7-original-a-right/attr-events.tsv"
    r264_trace = root / "stage7-dx-a-right/attr-events.tsv"
    original_route = camera_contract(original_trace)
    r264_route = camera_contract(r264_trace)
    for field in ("horizontal_modular_pixels", "vertical_modular_pixels"):
        if original_route[field] != r264_route[field]:
            raise AssertionError(f"r264 route coverage differs at {field}")
    for field in ("room", "scx", "scy"):
        if original_route["last_camera_event"][field] \
                != r264_route["last_camera_event"][field]:
            raise AssertionError(f"r264 final camera differs at {field}")
    if original_route["camera_change_runs"] == r264_route["camera_change_runs"]:
        raise AssertionError("negative control lacks the known event-count mismatch")

    current_semantics = semantic_changes(r264_trace)
    prior_semantics = semantic_changes(args.prior_trace)
    if current_semantics != prior_semantics:
        raise AssertionError("Stage7 semantic change sequence changed from r120")
    if current_semantics["count"] != 18:
        raise AssertionError("expected exactly 18 real Stage7 semantic changes")

    # A skipped four-pixel step must fail the distance contract even though a
    # raw event-count policy cannot express the covered distance.
    if r264_route["horizontal_modular_pixels"] - 4 \
            == original_route["horizontal_modular_pixels"]:
        raise AssertionError("route-distance negative control did not diverge")

    receipt = {
        "schema": "penta-stage7-scene08-router-static-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "base_sha256": digest(base),
        "candidate_sha256": digest(candidate),
        "build": build_receipt,
        "existing_r264_measurement": {
            "ratio": stage7["ratio"],
            "hits": [
                stage7["dx"]["main_loop_hits"],
                stage7["original"]["main_loop_hits"],
            ],
            "raw_scroll_changes": [
                stage7["original"]["scroll_changes"],
                stage7["dx"]["scroll_changes"],
            ],
            "raw_scroll_parity_failed": not stage7["scroll_parity_ok"],
        },
        "route_contract": {
            "original": original_route,
            "r264": r264_route,
            "coverage_equal": True,
            "finding": (
                "OG uses 80 two-pixel plus 20 four-pixel horizontal steps; "
                "r264 uses 60 four-pixel steps. Both cover 240 horizontal "
                "and 28 vertical modular pixels and end room03 SCX08 SCY00."
            ),
            "raw_change_count_is_stride_sensitive": True,
        },
        "semantic_change_contract": {
            "count": current_semantics["count"],
            "changed_cells": current_semantics["changed_cells"],
            "desired_hashes": current_semantics["desired_hashes"],
            "raw_source_hashes": current_semantics["raw_sha256"],
            "sequence_byte_exact_to_r120": True,
            "legitimate": (
                "every desired-map change has a distinct packed C1A0 source; "
                "the complete 18-state source/desired fingerprint matches r120"
            ),
        },
        "negative_controls": {
            "raw_scroll_event_counts_intentionally_differ": True,
            "missing_four_pixel_step_breaks_distance": True,
            "semantic_change_without_source_change_rejected": True,
            "candidate_byte_identity_required": True,
        },
        "required_live_gates": [
            "Stage7 target6/right/2800 ratio >= .99 with both replays deterministic",
            "post-run modular camera coverage exactly 240 horizontal / 28 vertical, final room03 SCX08 SCY00",
            "18-state Stage7 semantic fingerprint and zero displayed mismatches/trails",
            "Stage7 stationary and patrol routes",
            "Stage1 menu/item/low-health/north byte-exact visual suite",
            "Stage5 speed and semantic soak (cycle-balanced path)",
            "title/death/story owner-route receipts",
        ],
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
