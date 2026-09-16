#!/usr/bin/env python3
"""Independently audit the Stage-1 release-candidate receipt bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ZERO_REPLAY_FIELDS = (
    "active_violation_frames",
    "clear_tile_frames",
    "late_tile_art_mismatch_frames",
    "postsettle_immutable_tile_mismatch_frames",
    "postsettle_red_green_artifact_frames",
    "postsettle_semantic_attr_mismatch_frames",
    "postsettle_wall_edge_artifact_frames",
    "postsettle_weird_edge_tile_frames",
    "runtime_lut_mutation_frames",
    "scene_violation_frames",
)

DENSE_ZERO_FIELDS = (
    "endpoint_mismatch_frames",
    "floor_mismatch_frames",
    "menu_map_alias_frames",
    "palette_mismatch_frames",
    "post_menu_endpoint_mismatch_frames",
    "post_menu_floor_mismatch_frames",
    "post_menu_palette_mismatch_frames",
    "post_menu_transient_mismatch_frames",
    "post_menu_visible_attr_mismatch_frames",
    "rendered_wrong_palette0_tooth_cells",
    "transient_mismatch_frames",
    "unsafe_map_flip_events",
    "visible_attr_mismatch_frames",
)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("scene0b", type=Path)
    parser.add_argument("dense_hazards", type=Path)
    parser.add_argument("north", type=Path)
    parser.add_argument("speed", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rom_sha = hashlib.sha256(args.rom.read_bytes()).hexdigest()
    live, dense, north, speed = map(
        load, (args.scene0b, args.dense_hazards, args.north, args.speed)
    )
    checks: dict[str, bool] = {}
    checks["all receipts bind the audited ROM"] = all(
        value == rom_sha
        for value in (
            live.get("candidate_sha256"),
            dense.get("rom_sha256"),
            north.get("candidate_sha256"),
            speed.get("dx_rom_sha256"),
        )
    )
    checks["scene-$0B receipt passes every declared check"] = (
        live.get("status") == "PASS"
        and not live.get("failures")
        and len(live.get("replays", [])) == 4
        and all(live.get("checks", {}).values())
    )
    checks["scene-$0B replays have zero reported visual regressions"] = all(
        replay.get(field) == 0
        for replay in live.get("replays", [])
        for field in ZERO_REPLAY_FIELDS
    ) and all(
        replay.get("final_bg_chr", {}).get("byte_mismatches") == 0
        for replay in live.get("replays", [])
    )
    checks["dense hazard/menu receipt passes every declared check"] = (
        dense.get("passed") is True
        and len(dense.get("replays", [])) == 2
        and all(dense.get("checks", {}).values())
        and all(all(replay.get("checks", {}).values()) for replay in dense.get("replays", []))
    )
    checks["dense hazard/menu replays have zero artifact counters"] = all(
        replay.get(field) == 0
        for replay in dense.get("replays", [])
        for field in DENSE_ZERO_FIELDS
    )
    checks["north entrance and wall publication are exact"] = (
        north.get("status") == "pass"
        and north.get("terrain_differences") == 0
        and all(
            north.get(field) is True
            for field in (
                "reviewed_room01_wall_oracle_ok",
                "reviewed_room01_wall_replay_exact",
                "candidate_replay_exact",
                "candidate_replay_attributes_exact",
                "candidate_physical_page_ownership_exact",
                "physical_page_owner_reports_exact",
                "progress_route_geometry_exact",
                "progress_route_viewports_exact",
                "service_frame_presentations_exact",
                "settled_final_state_ok",
            )
        )
        and all(
            artifact.get("present") is True and artifact.get("exact") is True
            for artifact in north.get("candidate_replay_artifacts", {}).values()
        )
    )
    stage1_rows = [row for row in speed.get("rows", []) if row.get("stage") == 1]
    checks["speed gate passes the approved 95-percent floor"] = (
        speed.get("status") == "pass"
        and not speed.get("failures")
        and bool(stage1_rows)
        and all(row.get("ratio", 0) >= 0.95 for row in stage1_rows)
    )

    report = {
        "schema": "penta.stage1.independent-release-audit.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "audited_rom_sha256": rom_sha,
        "checks": checks,
        "failures": [name for name, ok in checks.items() if not ok],
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
