#!/usr/bin/env python3
"""Prove stable runtime identities for the complete post-final sequence.

The dialogue artwork has its own committed D880/DCE8/DCEA/DCF0/DD07 guard.
Those story bytes become stale when the stock ending advances to credits, so
the direct-written tail needs independent phase bytes:

  D880=16, D889=01, DCE2=00, FFF9=00  credits
  D880=16, D889=01, DCE2=00, FFF9=01  terminal END page
  D880=00, D889=0C, DCE2=00, FFF9=01  epilogue preamble
  D880=00, D889=0C, DCE2=01, FFF9=01  epilogue text

Consumes full manifests emitted by inventory_final_cutscene.py.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


EXPECTED_SIGNATURE = [
    (0x1A, 0x01, 0x00, 0x00),
    (0x16, 0x01, 0x00, 0x00),
    (0x16, 0x01, 0x00, 0x01),
    (0x00, 0x0C, 0x00, 0x01),
    (0x00, 0x0C, 0x01, 0x01),
]

PHASE_NAMES = {
    EXPECTED_SIGNATURE[0]: "post_final_dialogue",
    EXPECTED_SIGNATURE[1]: "credits",
    EXPECTED_SIGNATURE[2]: "end_page",
    EXPECTED_SIGNATURE[3]: "epilogue_preamble",
    EXPECTED_SIGNATURE[4]: "epilogue_text",
}

PHASE_TARGETS = {
    "post_final_dialogue": {5, 6, 7},
    "credits": {1},
    "end_page": {2},
    "epilogue_preamble": {0},
    "epilogue_text": {3},
}


def compress(values: list[tuple[int, int, int, int]]) -> list[
    tuple[int, int, int, int]
]:
    result: list[tuple[int, int, int, int]] = []
    for value in values:
        if not result or result[-1] != value:
            result.append(value)
    return result


def analyze_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    if data.get("route") != "post-final":
        raise ValueError(f"{path}: expected a post-final manifest")
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"{path}: no panels")

    failures: list[str] = []
    signatures: list[tuple[int, int, int, int]] = []
    phase_counts: Counter[str] = Counter()
    phase_frames: dict[str, list[int]] = {}
    full_targets: dict[str, set[int]] = {
        phase: set() for phase in PHASE_TARGETS
    }
    for panel in panels:
        state = panel.get("story_state", {})
        missing = {"d889", "dce2", "fff9"} - state.keys()
        if missing:
            raise ValueError(
                f"{path}: frame {panel.get('frame')} lacks "
                f"{', '.join(sorted(missing))}; regenerate the inventory"
            )
        signature = (
            panel["scene"],
            state["d889"],
            state["dce2"],
            state["fff9"],
        )
        signatures.append(signature)
        phase = PHASE_NAMES.get(signature)
        if phase is None:
            failures.append(
                f"frame {panel['frame']}: unknown ending signature "
                f"{tuple(f'{value:02X}' for value in signature)}"
            )
            continue
        phase_counts[phase] += 1
        phase_frames.setdefault(phase, []).append(panel["frame"])
        if panel["ffc1"] != 0 or panel["ffe4"] != 1:
            failures.append(
                f"frame {panel['frame']}: {phase} escaped the ending context "
                f"(FFC1={panel['ffc1']:02X}, FFE4={panel['ffe4']:02X})"
            )
        unsafe = int(panel.get("unsafe_attr_cells", 0))
        if unsafe:
            failures.append(
                f"frame {panel['frame']}: {phase} has {unsafe} unsafe "
                "attribute bytes"
            )
        palettes = {
            int(palette): count
            for palette, count in panel.get("palettes", {}).items()
        }

        valid = False
        if phase == "post_final_dialogue":
            # A neutral setup panel is followed by a 160-cell art field over a
            # fixed 200-cell dialogue frame. A single inventory sample can
            # straddle an old->new art-page transition, so two art palettes may
            # share those 160 cells.
            art_keys = set(palettes) - {0}
            valid = (
                palettes == {0: 360}
                or (
                    palettes.get(0) == 200
                    and art_keys
                    and art_keys <= {5, 6, 7}
                    and sum(palettes[key] for key in art_keys) == 160
                )
            )
            for target in (5, 6, 7):
                if palettes == {0: 200, target: 160}:
                    full_targets[phase].add(target)
        else:
            transition_pairs = {
                "credits": {0, 1},
                "end_page": {1, 2},
                "epilogue_preamble": {0, 2},
                "epilogue_text": {0, 3},
            }
            allowed = transition_pairs[phase]
            valid = (
                set(palettes) <= allowed
                and sum(palettes.values()) == 360
            )
            target = next(iter(PHASE_TARGETS[phase]))
            if palettes == {target: 360}:
                full_targets[phase].add(target)

        if not valid:
            failures.append(
                f"frame {panel['frame']}: {phase} attributes are {palettes}"
            )

    compressed = compress(signatures)
    if compressed != EXPECTED_SIGNATURE:
        failures.append(
            "phase trajectory differs: expected "
            f"{EXPECTED_SIGNATURE}, observed {compressed}"
        )
    for phase, targets in PHASE_TARGETS.items():
        missing_targets = targets - full_targets[phase]
        if missing_targets:
            failures.append(
                f"{phase} never reached full palette page(s) "
                f"{sorted(missing_targets)}"
            )

    phases = {
        name: {
            "guard": {
                "d880": signature[0],
                "ffc1": 0,
                "ffe4": 1,
                "d889": signature[1],
                "dce2": signature[2],
                "fff9": signature[3],
            },
            "samples": phase_counts[name],
            "first_frame": phase_frames[name][0],
            "last_frame": phase_frames[name][-1],
            "full_targets": sorted(full_targets[name]),
        }
        for signature, name in PHASE_NAMES.items()
        if phase_frames.get(name)
    }
    return {
        "path": str(path.resolve()),
        "status": "failed" if failures else "ok",
        "panels": len(panels),
        "observed_signature": [list(values) for values in compressed],
        "expected_signature": [list(values) for values in EXPECTED_SIGNATURE],
        "phases": phases,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifests", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    reports = [analyze_manifest(path) for path in args.manifests]
    failures = [
        f"{report['path']}: {failure}"
        for report in reports
        for failure in report["failures"]
    ]
    trajectories = {
        tuple(tuple(values) for values in report["observed_signature"])
        for report in reports
    }
    repeatable = len(trajectories) == 1
    if not repeatable:
        failures.append("repeated inventories have different phase trajectories")

    result = {
        "status": "failed" if failures else "ok",
        "runtime_guard": ["D880", "FFC1", "FFE4", "D889", "DCE2", "FFF9"],
        "reports": reports,
        "repeatable": repeatable,
        "failures": failures,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n")

    for report in reports:
        phases = ", ".join(
            f"{name}:{details['samples']}"
            for name, details in report["phases"].items()
        )
        print(
            f"{'PASS' if report['status'] == 'ok' else 'FAIL'} "
            f"{Path(report['path']).name}: {report['panels']} panels | {phases}"
        )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "PASS: dialogue, credits, END, and epilogue have a complete stable "
        "D880/FFC1/FFE4/D889/DCE2/FFF9 trajectory."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
