#!/usr/bin/env python3
"""Quickly shortlist Stage-7 timing variants against a frozen stock replay.

This is a diagnostic accelerator, not a release gate: it replays each DX ROM
twice through the checked-in single-flight launcher while reusing the exact
stock result from a prior full verifier receipt.  A selected ROM must then run
the normal verifier, including two fresh stock replays.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import verify_stage_speed_matrix as speed


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = (
    ROOT / "tmp/stage7-pointer-advance-r278/"
    "stage7-speed-right-strict99-r2/manifest.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def names(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values:
        raise argparse.ArgumentTypeError("variant list is empty")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--variants-root", type=Path,
        default=ROOT / "tmp/stage7-helper-timing-sweep",
    )
    parser.add_argument("--variants", type=names, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-helper-timing-sweep/live",
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--stop-on-match", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.baseline.read_text())
    if manifest.get("schema") != "penta-stage-speed-matrix-v2":
        raise AssertionError("baseline schema changed")
    if manifest.get("frames") != 2800 or manifest.get("mode") != "right":
        raise AssertionError("baseline is not the exact right/2800 contract")
    baseline_row = next(row for row in manifest["rows"] if row["stage"] == 7)
    if not baseline_row.get("deterministic_replay"):
        raise AssertionError("baseline receipt did not prove replay determinism")
    baseline = baseline_row["original"]
    if baseline.get("main_loop_hits") != 806:
        raise AssertionError("stock Stage-7 hit baseline changed")
    if sha256(speed.PROBE) != manifest["probe_sha256"]:
        raise AssertionError("Lua probe drifted from frozen baseline")
    if sha256(Path(speed.__file__)) != manifest["verifier_sha256"]:
        raise AssertionError("speed verifier drifted from frozen baseline")

    args.output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    summary_path = args.output / "summary.json"
    for name in args.variants:
        rom = args.variants_root / name / "candidate.gb"
        if not rom.is_file():
            raise AssertionError(f"missing variant ROM: {rom}")
        run_output = args.output / name
        candidates = [
            speed.run_one(
                str(ROOT / "scripts/mgba-qt-singleflight"),
                rom.resolve(), f"dx-{replay}", 6, "right", 2800,
                0, [], 0x16, 0x6C80, 0x7232, "", "native", False,
                run_output, args.timeout,
            )
            for replay in ("a", "b")
        ]
        candidate = candidates[0]
        deterministic = (
            speed.deterministic_payload(candidates[0])
            == speed.deterministic_payload(candidates[1])
        )
        ratio = candidate["main_loop_hits"] / baseline["main_loop_hits"]
        throughput = speed.classify_throughput(ratio, 0.01, None)
        route = speed.compare_route_coverage(
            baseline["route_coverage"], candidate["route_coverage"]
        )
        central_x = (
            candidate.get("central_x_entry_11a2", 0)
            + candidate.get("central_x_entry_11a5", 0)
        )
        central_ok = speed.central_output_telemetry_contract(
            candidate.get("central_emitter_hits", 0),
            central_x,
            candidate.get("central_attr_samples", 0),
        )[0]
        scene_ok = (
            candidate.get("final_scene") == 8
            and candidate.get("expected_scene_frames") == 2800
            and candidate.get("non_dma_scene_mismatch_frames") == 0
        )
        continuity_ok = (
            candidate.get("max_main_loop_gap", 31) <= 30
            and candidate.get("last_main_loop_frame", -1) >= 2770
        )
        matched = bool(
            deterministic
            and throughput["throughput_accepted"]
            and route["passed"]
            and central_ok
            and scene_ok
            and continuity_ok
        )
        row = {
            "variant": name,
            "candidate_sha256": sha256(rom),
            "main_loop_hits": candidate["main_loop_hits"],
            "ratio_exact": ratio,
            "throughput_target_met": throughput["target_met"],
            "horizontal_distance": candidate["route_coverage"][
                "horizontal_mod16_distance"
            ],
            "vertical_distance": candidate["route_coverage"][
                "vertical_mod16_distance"
            ],
            "route_exact": route["passed"],
            "deterministic": deterministic,
            "central_output_ok": central_ok,
            "scene_ok": scene_ok,
            "continuity_ok": continuity_ok,
            "diagnostic_match": matched,
            "dx_replay_receipt_sha256": [
                speed.payload_sha256(result) for result in candidates
            ],
        }
        rows.append(row)
        summary = {
            "schema": "penta-stage7-speed-timing-sweep-v1",
            "status": "DIAGNOSTIC_ONLY_FULL_GATE_REQUIRED",
            "baseline_manifest": str(args.baseline.resolve()),
            "baseline_manifest_sha256": sha256(args.baseline),
            "baseline_hits": baseline["main_loop_hits"],
            "baseline_route": baseline["route_coverage"],
            "rows": rows,
        }
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
        print(
            f"{name}: hits={candidate['main_loop_hits']} "
            f"ratio={ratio:.4f} "
            f"H={row['horizontal_distance']} V={row['vertical_distance']} "
            f"route={'PASS' if route['passed'] else 'MISS'} "
            f"{'MATCH' if matched else 'continue'}",
            flush=True,
        )
        if matched and args.stop_on_match:
            break
    print(f"Receipt: {summary_path}")
    return 0 if any(row["diagnostic_match"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
