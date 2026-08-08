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
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from cutscene_region_palettes import (  # noqa: E402
    load_cutscene_region_palettes,
    panel_mask,
)


DEFAULT_PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"

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


def analyze_manifest(
    path: Path,
    expected_story_attrs: dict[int, bytes],
) -> dict:
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
    previous_full_story_art: int | None = None
    story_repair_art: int | None = None
    story_repair_samples = 0
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
            attribute_hex = panel.get("attribute_hex")
            if not isinstance(attribute_hex, str):
                failures.append(
                    f"frame {panel['frame']}: manifest lacks attribute_hex; "
                    "regenerate it with inventory_final_cutscene.py"
                )
                continue
            try:
                attributes = bytes.fromhex(attribute_hex)
            except ValueError:
                attributes = b""
            if len(attributes) != 360:
                failures.append(
                    f"frame {panel['frame']}: attribute_hex is not 360 bytes"
                )
                continue
            art = state.get("dcf0", 0)
            art_committed = (
                state.get("dce8") == 0x05
                and state.get("dcea") == 0x01
                and art in {5, 6, 7}
                and ((state.get("dd07", 0) + 1) & 0xFF) == art
            )
            expected = (
                expected_story_attrs[art] if art_committed else bytes(360)
            )
            valid = attributes == expected
            if valid and art_committed:
                full_targets[phase].add(art)
                previous_full_story_art = art
                story_repair_art = None
                story_repair_samples = 0
            elif art_committed and previous_full_story_art is not None:
                previous = expected_story_attrs[previous_full_story_art]
                valid = (
                    previous_full_story_art != art
                    and attributes[160:] == bytes(200)
                    and all(
                        actual in {old, new}
                        for actual, old, new in zip(
                            attributes[:160],
                            previous[:160],
                            expected_story_attrs[art][:160],
                        )
                    )
                )
                same_art_repair = (
                    previous_full_story_art == art
                    and state.get("df4a", 0x20) < 0x20
                    and attributes[160:] == bytes(200)
                    and all(
                        actual in {0, final}
                        for actual, final in zip(
                            attributes[:160],
                            expected_story_attrs[art][:160],
                        )
                    )
                )
                if same_art_repair:
                    if story_repair_art != art:
                        story_repair_art = art
                        story_repair_samples = 0
                    story_repair_samples += 1
                    valid = story_repair_samples <= 1
            elif (
                not art_committed
                and art in {5, 6, 7}
                and previous_full_story_art is not None
                and attributes
                == expected_story_attrs[previous_full_story_art]
            ):
                # DCF0 announces the next stock page one render step before
                # DD07 commits it. The exact previous position mask is still
                # the correct visible layout during that bounded handoff.
                valid = True
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
    parser.add_argument(
        "--palette-yaml", type=Path, default=DEFAULT_PALETTES
    )
    args = parser.parse_args()

    panels = load_cutscene_region_palettes(args.palette_yaml)
    expected_story_attrs = {
        art_id: bytes(
            value for row in panel_mask(panel) for value in row
        ) + bytes(200)
        for art_id, panel in panels.items()
    }
    reports = [
        analyze_manifest(path, expected_story_attrs)
        for path in args.manifests
    ]
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
