#!/usr/bin/env python3
"""Verify the real title spotlight and the later gameplay demo in mGBA.

The title spotlight is D880=$1B. D880=$0A is a gameplay demo/miniboss scene,
not the spotlight reel. This distinction is the regression this gate exists
to preserve.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_attract_reel_inventory.lua"
PALETTE_SOURCE = ROOT / "palettes/penta_palettes_v097.yaml"
SPOTLIGHT_ACTORS = {
    0: ("Sara W", 2, "SaraWitch"),
    1: ("Sara D", 1, "SaraDragon"),
    2: ("resource 04 / crow family", 3, "SaraProjectileAndCrow"),
}


def parse_sprites(raw: str) -> list[tuple[int, int, int, int, int]]:
    if not raw:
        return []
    sprites = []
    for item in raw.split(","):
        slot, y, x, tile, attr = item.split(":")
        sprites.append((int(slot), int(y), int(x), int(tile, 16), int(attr, 16)))
    return sprites


def run_probe(mgba: str, rom: Path, output: Path, frames: int, timeout: float) -> None:
    done = Path(str(output) + ".done")
    output.unlink(missing_ok=True)
    done.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "ATTRACT_OUT": str(output),
        "ATTRACT_FRAMES": str(frames),
        "ATTRACT_SAMPLE_EVERY": "2",
    })
    proc = subprocess.Popen(
        [mgba, "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if done.exists():
                return
            if proc.poll() is not None:
                raise RuntimeError(f"mGBA exited with status {proc.returncode}")
            time.sleep(0.05)
        raise RuntimeError(f"title/demo inventory timed out after {timeout:g}s")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def load_rows(trace: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in trace.read_text().splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 13:
            continue
        (
            kind, frame, scene, ffc1, ffba, ffbf, ffbe, fff2,
            dd09, visible, hw, c000, c100,
        ) = fields
        rows.append({
            "kind": kind,
            "frame": int(frame),
            "scene": int(scene, 16),
            "ffc1": int(ffc1),
            "ffba": int(ffba, 16),
            "ffbf": int(ffbf, 16),
            "ffbe": int(ffbe, 16),
            "fff2": int(fff2, 16),
            "dd09": int(dd09, 16),
            "visible": int(visible),
            "hw": parse_sprites(hw),
            "c000": parse_sprites(c000),
            "c100": parse_sprites(c100),
        })
    return rows


def actor_body(row: dict[str, object]) -> list[tuple[int, int, int, int, int]]:
    body = [
        sprite
        for sprite in row["hw"]  # type: ignore[index]
        if sprite[0] < 4 and 0x08 <= sprite[3] <= 0x0F
    ]
    return body if len(body) == 4 else []


def shadow_matches(row: dict[str, object], body: list[tuple[int, int, int, int, int]]) -> bool:
    expected = {sprite[0]: sprite[1:] for sprite in body}
    for key in ("c000", "c100"):
        shadow = {
            sprite[0]: sprite[1:]
            for sprite in row[key]  # type: ignore[index]
            if sprite[0] < 4
        }
        if all(shadow.get(slot) == value for slot, value in expected.items()):
            return True
    return False


def summarize(trace: Path) -> int:
    rows = load_rows(trace)
    if not rows:
        print("FAIL: title/demo trace is empty")
        return 1

    yaml_data = yaml.safe_load(PALETTE_SOURCE.read_text())
    missing_yaml = [
        yaml_key
        for _name, _slot, yaml_key in SPOTLIGHT_ACTORS.values()
        if yaml_key not in yaml_data["obj_palettes"]
    ]

    transitions = [
        (row["frame"], row["scene"], row["ffc1"])
        for row in rows if row["kind"] == "scene"
    ]
    og_stage_frames = 1856
    og_gargoyle_frames = 395
    stage_transition = next(
        (
            transition for transition in transitions
            if transition[1] == 0x02 and transition[2] == 1
        ),
        None,
    )
    gargoyle_transition = next(
        (
            transition for transition in transitions
            if (
                transition[1] == 0x0A
                and transition[2] == 1
                and (
                    stage_transition is None
                    or transition[0] > stage_transition[0]
                )
            )
        ),
        None,
    )
    post_gargoyle_transition = next(
        (
            transition for transition in transitions
            if (
                gargoyle_transition is not None
                and transition[0] > gargoyle_transition[0]
            )
        ),
        None,
    )
    stage_frames = (
        gargoyle_transition[0] - stage_transition[0]
        if stage_transition is not None and gargoyle_transition is not None
        else None
    )
    gargoyle_frames = (
        post_gargoyle_transition[0] - gargoyle_transition[0]
        if gargoyle_transition is not None
        and post_gargoyle_transition is not None
        else None
    )
    print("Scene transitions:")
    print("  " + " ".join(
        f"f{frame}:{scene:02X}/g{ffc1}"
        for frame, scene, ffc1 in transitions
    ))

    actor_samples: dict[int, list[dict[str, object]]] = defaultdict(list)
    actor_x: dict[int, list[int]] = defaultdict(list)
    actor_attr_bad = 0
    actor_shadow_matches = 0
    for row in rows:
        if row["scene"] != 0x1B or row["ffc1"] != 0:
            continue
        identity = int(row["fff2"])
        if identity not in SPOTLIGHT_ACTORS:
            continue
        body = actor_body(row)
        if not body:
            continue
        actor_samples[identity].append(row)
        actor_x[identity].append(body[0][2])
        expected_palette = SPOTLIGHT_ACTORS[identity][1]
        actor_attr_bad += sum(
            (sprite[4] & 7) != expected_palette for sprite in body
        )
        actor_shadow_matches += shadow_matches(row, body)

    demo_samples = 0
    demo_sprites = 0
    demo_attr_bad = 0
    for row in rows:
        if row["scene"] != 0x0A or row["ffbf"] != 1:
            continue
        checked = [
            sprite
            for sprite in row["hw"]  # type: ignore[index]
            if sprite[3] >= 0x30
        ]
        if not checked:
            continue
        demo_samples += 1
        demo_sprites += len(checked)
        demo_attr_bad += sum((sprite[4] & 7) != 6 for sprite in checked)

    returned_banner = [
        row for row in rows
        if row["scene"] == 0x1C and row["ffc1"] == 1
    ]
    returned_menu = [
        row for row in rows
        if row["scene"] == 0x01 and row["ffc1"] == 1
    ]
    menu_start = min(
        (int(row["frame"]) for row in returned_menu),
        default=None,
    )
    late_menu_visible = []
    if menu_start is not None:
        late_menu_visible = [
            row for row in returned_menu
            if int(row["frame"]) >= menu_start + 4 and int(row["visible"]) > 0
        ]
    banner_start = min(
        (int(row["frame"]) for row in returned_banner),
        default=None,
    )
    late_banner_visible = []
    if banner_start is not None:
        late_banner_visible = [
            row for row in returned_banner
            if int(row["frame"]) >= banner_start + 4 and int(row["visible"]) > 0
        ]
    returned_spotlight_reached = any(
        row["scene"] == 0x1B and row["ffc1"] == 1 for row in rows
    )

    failures: list[str] = []
    if missing_yaml:
        failures.append(f"missing YAML palette keys: {missing_yaml}")
    for identity, (name, palette, yaml_key) in SPOTLIGHT_ACTORS.items():
        samples = actor_samples[identity]
        xs = actor_x[identity]
        if not samples:
            failures.append(f"{name} never reached hardware OAM")
            continue
        if max(xs) - min(xs) < 24 or xs[-1] >= xs[0]:
            failures.append(f"{name} did not visibly travel right-to-left")
        print(
            f"  spotlight {name}: samples={len(samples)} "
            f"x={min(xs)}..{max(xs)} palette={palette} YAML={yaml_key}"
        )
    if actor_attr_bad:
        failures.append(f"{actor_attr_bad} spotlight quadrant palette mismatches")
    if actor_shadow_matches == 0:
        failures.append("hardware spotlight OAM never matched either shadow buffer")
    if demo_samples < 20:
        failures.append(f"only {demo_samples} Gargoyle demo samples (need 20+)")
    if demo_attr_bad:
        failures.append(
            f"{demo_attr_bad}/{demo_sprites} demo miniboss sprites changed "
            "away from YAML boss slot 6"
        )
    if stage_frames is None or not 0.8 <= stage_frames / og_stage_frames <= 1.2:
        failures.append(
            "gameplay-demo duration is outside 20% of OG "
            f"({stage_frames} vs {og_stage_frames} frames)"
        )
    if (
        gargoyle_frames is None
        or not 0.8 <= gargoyle_frames / og_gargoyle_frames <= 1.2
    ):
        failures.append(
            "Gargoyle-demo duration is outside 20% of OG "
            f"({gargoyle_frames} vs {og_gargoyle_frames} frames)"
        )
    if (
        post_gargoyle_transition is None
        or post_gargoyle_transition[1:] != (0x01, 1)
    ):
        failures.append(
            "Gargoyle demo did not return directly to the active title menu"
        )
    if menu_start is None:
        failures.append("returned-title D880=01 menu was not reached")
    if late_menu_visible:
        failures.append(
            "returned title menu retained gameplay sprites in "
            f"{len(late_menu_visible)} samples"
        )
    if banner_start is None:
        failures.append("returned-title D880=1C was not reached")
    if late_banner_visible:
        failures.append(
            f"returned banner retained sprites in {len(late_banner_visible)} samples"
        )
    if not returned_spotlight_reached:
        failures.append("returned title did not advance from banner to D880=1B")

    summary = {
        "status": "failed" if failures else "ok",
        "trace": str(trace),
        "transitions": transitions,
        "spotlight": {
            SPOTLIGHT_ACTORS[identity][0]: {
                "samples": len(actor_samples[identity]),
                "x_min": min(actor_x[identity]) if actor_x[identity] else None,
                "x_max": max(actor_x[identity]) if actor_x[identity] else None,
                "palette": SPOTLIGHT_ACTORS[identity][1],
                "yaml": SPOTLIGHT_ACTORS[identity][2],
            }
            for identity in SPOTLIGHT_ACTORS
        },
        "spotlight_palette_mismatches": actor_attr_bad,
        "spotlight_shadow_matches": actor_shadow_matches,
        "demo_miniboss_samples": demo_samples,
        "demo_miniboss_sprites": demo_sprites,
        "demo_miniboss_palette_mismatches": demo_attr_bad,
        "demo_stage_frames": stage_frames,
        "demo_stage_og_frames": og_stage_frames,
        "demo_gargoyle_frames": gargoyle_frames,
        "demo_gargoyle_og_frames": og_gargoyle_frames,
        "post_gargoyle_transition": post_gargoyle_transition,
        "returned_menu_start": menu_start,
        "returned_menu_late_sprite_samples": len(late_menu_visible),
        "returned_banner_start": banner_start,
        "returned_banner_late_sprite_samples": len(late_banner_visible),
        "returned_spotlight_reached": returned_spotlight_reached,
        "failures": failures,
    }
    summary_path = Path(str(trace) + ".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")

    print(
        f"Demo Gargoyle: samples={demo_samples} sprites={demo_sprites} "
        f"palette6_mismatches={demo_attr_bad}; "
        f"timing stage={stage_frames}/{og_stage_frames} "
        f"gargoyle={gargoyle_frames}/{og_gargoyle_frames}"
    )
    print(
        f"Returned title: menu_start={menu_start} "
        f"menu_late_sprite_samples={len(late_menu_visible)} "
        f"banner_start={banner_start} "
        f"late_sprite_samples={len(late_banner_visible)} "
        f"advanced_to_1B={returned_spotlight_reached}"
    )
    print(f"Receipt: {summary_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: real D880=1B spotlight actors reach hardware OAM with "
        "YAML palette slots; D880=0A Gargoyle remains on boss slot 6."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-headless-singleflight")
    )
    parser.add_argument("--frames", type=int, default=14000)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()

    if args.keep:
        trace = args.keep.resolve()
        trace.parent.mkdir(parents=True, exist_ok=True)
        run_probe(args.mgba, args.rom.resolve(), trace, args.frames, args.timeout)
        return summarize(trace)

    with tempfile.TemporaryDirectory(prefix="penta-title-demo-") as directory:
        trace = Path(directory) / "inventory.tsv"
        run_probe(args.mgba, args.rom.resolve(), trace, args.frames, args.timeout)
        return summarize(trace)


if __name__ == "__main__":
    raise SystemExit(main())
