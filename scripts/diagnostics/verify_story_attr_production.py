#!/usr/bin/env python3
"""Gate ROM-native OPENING/final-story/ending palette attributes in mGBA."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import time

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATES = ROOT / "tmp/palette_session/story_states"
PROBE = Path(__file__).with_name("probe_story_attr_production.lua")
SPECS = (
    ("opening", "neutral", 0, 0x15, {}),
    ("opening_book", "story", 1, 0x15, {"SEQUENCE": 0x02}),
    ("opening_sara", "story", 2, 0x15, {"SEQUENCE": 0x02}),
    ("opening_dragon_eye", "story", 3, 0x15, {"SEQUENCE": 0x02}),
    ("pre_final", "story", 4, 0x19, {"SEQUENCE": 0x04}),
    ("pre_final_sara", "story", 7, 0x19, {"SEQUENCE": 0x04}),
    ("post_final", "story", 5, 0x1A, {"SEQUENCE": 0x05}),
    ("post_final_lisa", "story", 6, 0x1A, {"SEQUENCE": 0x05}),
    ("post_final_sara", "story", 7, 0x1A, {"SEQUENCE": 0x05}),
    (
        "ending_credits", "ending", 1, 0x16,
        {"D889": 0x01, "DCE2": 0x00, "FFF9": 0x00, "WAIT": 140},
    ),
    (
        "ending_end", "ending", 2, 0x16,
        {"D889": 0x01, "DCE2": 0x00, "FFF9": 0x01, "WAIT": 140},
    ),
    (
        "ending_epilogue", "ending", 3, 0x00,
        {"D889": 0x0C, "DCE2": 0x01, "FFF9": 0x01, "WAIT": 180},
    ),
)


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in path.read_text().split()
        if "=" in field
    )


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_one(
    mgba: str,
    rom: Path,
    state: Path,
    output: Path,
    kind: str,
    palette: int,
    d880: int,
    guards: dict[str, int],
    timeout: float,
) -> dict[str, str]:
    report = output.with_suffix(".report")
    done = output.with_suffix(".done")
    screenshot = output.with_suffix(".png")
    for path in (report, done, screenshot):
        path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        STORY_ATTR_OUT=str(output),
        STORY_ATTR_KIND=kind,
        STORY_ATTR_PALETTE=str(palette),
        STORY_ATTR_D880=str(d880),
        STORY_ATTR_WAIT="90",
    )
    for name, value in guards.items():
        environment[f"STORY_ATTR_{name}"] = str(value)
    process = subprocess.Popen(
        [
            mgba,
            "-t",
            str(state),
            "--script",
            str(PROBE),
            str(rom),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if done.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before {state.name} report"
                )
            time.sleep(0.02)
        else:
            raise TimeoutError(f"{state.name} timed out")
    finally:
        terminate(process)
    if not report.is_file():
        raise RuntimeError(f"{state.name} produced no report")
    values = parse_report(report)
    if values.get("status") != "ok":
        raise RuntimeError(
            f"{state.name}: {values.get('message', 'probe failed')} "
            f"({report.read_text().strip()})"
        )
    if not screenshot.is_file():
        raise RuntimeError(f"{state.name} produced no screenshot")
    with Image.open(screenshot) as image:
        if image.size != (160, 144):
            raise RuntimeError(
                f"{state.name} screenshot is {image.size}, expected 160x144"
            )
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=DEFAULT_STATES)
    parser.add_argument("--output", type=Path, default=Path(
        "/tmp/penta-story-attr-production"
    ))
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")
    args.output.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    results: list[tuple[str, dict[str, str]]] = []
    for stem, kind, palette, d880, guards in SPECS:
        state = args.states / f"{stem}.ss0"
        if not state.is_file():
            failures.append(f"{stem}: missing {state}")
            continue
        try:
            values = run_one(
                args.mgba,
                args.rom.resolve(),
                state.resolve(),
                args.output / stem,
                kind,
                palette,
                d880,
                guards,
                args.timeout,
            )
            results.append((stem, values))
            print(
                f"{stem:19s} {kind:7s} BG{palette} "
                f"target={values['target']} neutral={values['neutral']} "
                f"row={values['row']} key={values['key']}"
            )
        except Exception as error:
            failures.append(f"{stem}: {error}")

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if len(results) != len(SPECS):
        print(f"FAIL: verified {len(results)}/{len(SPECS)} states")
        return 1
    print(
        "PASS: 8 committed story panels use BG1..BG7 only above the "
        "dialogue separator; credits/END/epilogue use BG1/BG2/BG3 across "
        "the viewport; the uncommitted opening remains neutral."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
