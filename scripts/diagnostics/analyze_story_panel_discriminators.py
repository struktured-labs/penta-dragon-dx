#!/usr/bin/env python3
"""Prove stable runtime identities for Penta Dragon's story artwork.

Consumes manifests emitted by inventory_opening_cutscene.py and
inventory_final_cutscene.py. The game's stock cutscene engine exposes:

  DCE8  story sequence (2=OPENING, 4=pre-final, 5=post-final)
  DCEA  initialized flag
  DCF0  active artwork ID (1..7)
  DD07  committed artwork index (DCF0 - 1)

The DCF0/DD07 agreement is important: during a page transition DCF0 can change
before the art copy commits. A release colorizer must keep the neutral fallback
until both bytes agree.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


ROUTES = {
    "opening": {
        "scene": 0x15,
        "sequence": 2,
        "art_sequence": [1, 2, 3],
    },
    "pre-final": {
        "scene": 0x19,
        "sequence": 4,
        "art_sequence": [4, 7, 4],
    },
    "post-final": {
        "scene": 0x1A,
        "sequence": 5,
        "art_sequence": [5, 7, 6, 7],
    },
}

ART_NAMES = {
    1: "opening_book",
    2: "opening_sara",
    3: "opening_dragon_eye",
    4: "penta_three_heads",
    5: "post_final_dragon",
    6: "lisa_portrait",
    7: "sara_portrait",
}


def compress(values: list[int]) -> list[int]:
    result: list[int] = []
    for value in values:
        if not result or result[-1] != value:
            result.append(value)
    return result


def analyze_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    route = data.get("route")
    if route not in ROUTES:
        raise ValueError(f"{path}: unsupported route {route!r}")
    rule = ROUTES[route]
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"{path}: no panels")

    stable: list[dict] = []
    transitional: list[dict] = []
    stale_tail: list[dict] = []
    for panel in panels:
        tilemap = bytes.fromhex(panel["tilemap_hex"])
        if len(tilemap) != 360:
            raise ValueError(
                f"{path}: frame {panel['frame']} has {len(tilemap)} tile cells"
            )
        state = panel["story_state"]
        in_scene = panel["scene"] == rule["scene"]
        initialized = (
            state["dce8"] == rule["sequence"]
            and state["dcea"] == 1
        )
        committed_art = (
            1 <= state["dcf0"] <= 7
            and state["dd07"] + 1 == state["dcf0"]
        )
        if in_scene and initialized and committed_art:
            stable.append(panel)
        elif in_scene:
            transitional.append(panel)
        elif initialized and state["dcf0"] != 0:
            # DCE8/DCF0/DD07 survive into credits/final art. They describe the
            # last dialogue portrait there, not the new direct-written page.
            stale_tail.append(panel)

    if not stable:
        raise ValueError(f"{path}: no committed art samples")
    sequence = compress([panel["story_state"]["dcf0"] for panel in stable])
    groups: dict[int, list[dict]] = defaultdict(list)
    for panel in stable:
        groups[panel["story_state"]["dcf0"]].append(panel)

    return {
        "path": str(path.resolve()),
        "route": route,
        "scene": rule["scene"],
        "sequence_byte": rule["sequence"],
        "observed_art_sequence": sequence,
        "expected_art_sequence": rule["art_sequence"],
        "sequence_matches": sequence == rule["art_sequence"],
        "stable_samples": len(stable),
        "transitional_samples": len(transitional),
        "stale_tail_samples": len(stale_tail),
        "art": {
            str(art_id): {
                "name": ART_NAMES[art_id],
                "samples": len(group),
                "first_frame": group[0]["frame"],
                "last_frame": group[-1]["frame"],
                "unique_tilemaps": len(
                    {panel["tilemap_crc32"] for panel in group}
                ),
                "guard": {
                    "d880": rule["scene"],
                    "dce8": rule["sequence"],
                    "dcea": 1,
                    "dcf0": art_id,
                    "dd07": art_id - 1,
                },
            }
            for art_id, group in sorted(groups.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    reports = [analyze_manifest(path) for path in args.manifests]
    failures: list[str] = []
    by_route: dict[str, list[dict]] = defaultdict(list)
    for report in reports:
        by_route[report["route"]].append(report)
        if not report["sequence_matches"]:
            failures.append(
                f"{report['route']}: expected "
                f"{report['expected_art_sequence']}, observed "
                f"{report['observed_art_sequence']}"
            )

    repeatability: dict[str, bool] = {}
    for route, route_reports in sorted(by_route.items()):
        signatures = {
            tuple(report["observed_art_sequence"])
            for report in route_reports
        }
        repeatability[route] = len(signatures) == 1
        if len(signatures) != 1:
            failures.append(
                f"{route}: repeated inventories disagree: {sorted(signatures)}"
            )

    result = {
        "status": "failed" if failures else "ok",
        "runtime_guard": ["D880", "DCE8", "DCEA", "DCF0", "DD07"],
        "safe_art_rows": {"first": 0, "last": 7, "dialogue_rows": [8, 17]},
        "reports": reports,
        "repeatability": repeatability,
        "failures": failures,
        "credits_warning": (
            "DCE8/DCF0/DD07 are stale after D880 leaves the dialogue scene; "
            "D880=16 and D880=00+FFE4=1 need an independent page discriminator."
        ),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")

    for report in reports:
        art = ", ".join(
            f"{info['name']}:{info['samples']} samples/"
            f"{info['unique_tilemaps']} maps"
            for info in report["art"].values()
        )
        print(
            f"{'PASS' if report['sequence_matches'] else 'FAIL'} "
            f"{report['route']}: art sequence "
            f"{report['observed_art_sequence']} | {art}"
        )
        if report["stale_tail_samples"]:
            print(
                f"  note: {report['stale_tail_samples']} later non-dialogue "
                "samples retain stale dialogue art bytes"
            )
    for route, stable in repeatability.items():
        if len(by_route[route]) > 1:
            print(
                f"{'PASS' if stable else 'FAIL'} {route}: "
                f"{len(by_route[route])} inventories agree"
            )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "PASS: stock story art has a committed D880/DCE8/DCEA/DCF0/DD07 "
        "runtime discriminator."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
