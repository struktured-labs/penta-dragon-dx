#!/usr/bin/env python3
"""Qualify a Stage-7 speed run by covered route, not scroll event count.

The stock ROM commonly advances the camera by two pixels while DX advances it
by four.  ``verify_stage_speed_matrix.py`` deliberately records that cadence
difference as a raw scroll-parity failure.  This diagnostic is narrower: it
accepts that one known failure only when both deterministic replays cover the
same modular camera distance, end at the same camera, and retain the accepted
18-state semantic-map sequence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_stage7_scene08_router_static import (  # noqa: E402
    camera_contract,
    semantic_changes,
)


SCROLL_FAILURE = re.compile(r"^Stage 7: scroll mismatch \d+/\d+$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--candidate", type=Path,
        default=Path("tmp/stage7-scene08-pair-router-r264/candidate.gb"),
    )
    parser.add_argument(
        "--accepted-trace", type=Path,
        default=Path(
            "tmp/stage1-menu-hidden-repair-r264/all-stage-speed-right-r1/"
            "stage7-dx-a-right/attr-events.tsv"
        ),
    )
    parser.add_argument("--minimum-ratio", type=float, default=0.99)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    require(manifest.get("mode") == "right", "expected right-input fixture")
    require(manifest.get("frames") == 2800, "expected 2800-frame fixture")
    rows = manifest.get("rows", [])
    require(len(rows) == 1 and rows[0].get("stage") == 7,
            "manifest must contain only Stage 7")
    row = rows[0]
    require(row["ratio"] >= args.minimum_ratio,
            f"Stage7 ratio {row['ratio']:.4f} is below {args.minimum_ratio:.4f}")
    require(row["deterministic_replay"], "speed replay is not deterministic")
    require(row["candidate_scene_ok"], "candidate scene contract failed")
    require(row["candidate_scene_mismatch_frames"] == 0,
            "candidate has scene mismatch frames")
    require(row["candidate_non_dma_scene_mismatch_frames"] == 0,
            "candidate has non-DMA scene mismatches")
    require(row["baseline_continuity_ok"] and row["candidate_continuity_ok"],
            "main-loop continuity failed")
    require(row["central_output_telemetry_ok"],
            "central renderer output contract failed")
    require(row["candidate_dma_mode_ok"], "DMA mode contract failed")
    require(row["original"]["tile_copy_hits"] == row["dx"]["tile_copy_hits"]
            or abs(row["original"]["tile_copy_hits"]
                   - row["dx"]["tile_copy_hits"]) <= 1,
            "tile-copy coverage differs by more than one tail event")

    failures = manifest.get("failures", [])
    require(all(SCROLL_FAILURE.fullmatch(value) for value in failures),
            f"unexpected matrix failures: {failures}")

    run_root = args.manifest.parent
    mode = manifest["mode"]
    traces = {
        "original_a": run_root / f"stage7-original-a-{mode}/attr-events.tsv",
        "original_b": run_root / f"stage7-original-b-{mode}/attr-events.tsv",
        "dx_a": run_root / f"stage7-dx-a-{mode}/attr-events.tsv",
        "dx_b": run_root / f"stage7-dx-b-{mode}/attr-events.tsv",
    }
    require(all(path.is_file() for path in traces.values()),
            "one or more Stage7 attr-event traces are missing")
    routes = {name: camera_contract(path) for name, path in traces.items()}
    require(routes["original_a"] == routes["original_b"],
            "original route replay differs")
    require(routes["dx_a"] == routes["dx_b"], "DX route replay differs")
    for field in ("horizontal_modular_pixels", "vertical_modular_pixels"):
        require(routes["dx_a"][field] == routes["original_a"][field],
                f"covered route differs at {field}")
    for field in ("room", "scx", "scy"):
        require(routes["dx_a"]["last_camera_event"][field]
                == routes["original_a"]["last_camera_event"][field],
                f"final camera differs at {field}")
    require(routes["dx_a"]["horizontal_modular_pixels"] == 240,
            "unexpected Stage7 horizontal route distance")
    require(routes["dx_a"]["vertical_modular_pixels"] == 28,
            "unexpected Stage7 vertical route distance")

    accepted_semantics = semantic_changes(args.accepted_trace)
    candidate_semantics_a = semantic_changes(traces["dx_a"])
    candidate_semantics_b = semantic_changes(traces["dx_b"])
    require(candidate_semantics_a == candidate_semantics_b,
            "DX semantic replay differs")
    require(candidate_semantics_a == accepted_semantics,
            "DX semantic-map sequence differs from accepted r264")
    require(candidate_semantics_a["count"] == 18,
            "expected 18 legitimate Stage7 semantic changes")

    receipt = {
        "schema": "penta-stage7-route-distance-live-v1",
        "status": "PASS",
        "candidate_sha256": digest(args.candidate),
        "manifest": str(args.manifest),
        "ratio": row["ratio"],
        "hits": [row["dx"]["main_loop_hits"],
                 row["original"]["main_loop_hits"]],
        "raw_scroll_changes": [row["original"]["scroll_changes"],
                               row["dx"]["scroll_changes"]],
        "matrix_failures_accepted": failures,
        "route": routes,
        "semantic_changes": candidate_semantics_a,
        "finding": (
            "Raw scroll-event count differs only because the emulators use "
            "different step sizes; covered route and final camera are exact."
        ),
    }
    receipt_path = args.receipt or args.manifest.with_name(
        "stage7-route-distance-receipt.json"
    )
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
