#!/usr/bin/env python3
"""Run the pre/post-final palette gate through mGBA's pixel pipeline."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = PROJECT_ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PROBE = PROJECT_ROOT / "scripts/diagnostics/probe_final_cutscene_mgba.lua"


def parse_result(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def red_dominant_pixels(path: Path) -> int:
    image = Image.open(path).convert("RGB")
    return sum(
        red > 90 and red > green * 1.35 and red > blue * 1.20
        for red, green, blue in image.getdata()
    )


def run_entry(
    mgba: str, rom: Path, output: Path, entry: str, max_frames: int
) -> tuple[dict[str, str], int]:
    result_path = output / f"{entry}.txt"
    screenshot_path = output / f"{entry}.png"
    stdout_path = output / f"{entry}.stdout.txt"
    environment = os.environ.copy()
    environment.update(
        {
            "FINAL_SCENE_ENTRY": entry,
            "FINAL_SCENE_OUT": str(result_path),
            "FINAL_SCENE_SCREENSHOT": str(screenshot_path),
            "FINAL_SCENE_MAX_FRAMES": str(max_frames),
            "FINAL_SCENE_ART_ID": "4" if entry == "pre-final" else "5",
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
        }
    )
    with stdout_path.open("w") as stdout:
        subprocess.run(
            [
                mgba,
                "--fastforward",
                "--script",
                str(PROBE),
                str(rom),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            timeout=45,
            check=False,
        )
    if not result_path.exists():
        raise RuntimeError(
            f"{entry}: mGBA produced no result; see {stdout_path}"
        )
    result = parse_result(result_path)
    if not screenshot_path.exists():
        raise RuntimeError(
            f"{entry}: mGBA produced no screenshot; see {stdout_path}"
        )
    with Image.open(screenshot_path) as image:
        if image.size != (160, 144):
            raise RuntimeError(
                f"{entry}: screenshot is {image.size}, expected 160x144"
            )
        image.verify()
    return result, red_dominant_pixels(screenshot_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba",
        default=str(PROJECT_ROOT / "scripts/mgba-qt-singleflight"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/penta-final-cutscene-mgba-gate"),
    )
    parser.add_argument(
        "--entry",
        action="append",
        choices=("post-final", "pre-final"),
        help="verify only this branch (repeatable; default: both)",
    )
    args = parser.parse_args()

    if not args.mgba:
        print("FAIL: mgba-qt was not found in PATH")
        return 1
    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    entries = (("post-final", 12000), ("pre-final", 16000))
    if args.entry:
        entries = tuple(item for item in entries if item[0] in args.entry)
    for entry, max_frames in entries:
        try:
            result, red_pixels = run_entry(
                args.mgba, rom, output, entry, max_frames
            )
        except Exception as exc:
            failures.append(str(exc))
            continue
        status = result.get("status")
        samples = int(result.get("samples", "0"))
        contaminated = int(result.get("contaminated_total", "-1"))
        mismatch = int(result.get("layout_mismatch_total", "-1"))
        table_bad = int(result.get("table_bad_samples", "-1"))
        transitions = result.get("transitions", "")
        expected = "19" if entry == "pre-final" else "1A"
        print(
            f"{entry:10s}: status={status} samples={samples} "
            f"attrs_nonzero={contaminated} layout_mismatch={mismatch} "
            f"table_bad={table_bad} "
            f"red_pixels={red_pixels} frames={result.get('frames')}"
        )
        if status != "ok":
            failures.append(f"{entry}: probe status is {status!r}")
        if samples <= 0:
            failures.append(f"{entry}: no scene samples")
        if mismatch != 0:
            failures.append(
                f"{entry}: {mismatch} position-aware palette mismatches"
            )
        if table_bad != 0:
            failures.append(
                f"{entry}: {table_bad} samples had a non-neutral active table"
            )
        if f">{expected}" not in transitions:
            failures.append(
                f"{entry}: transitions never reached D880={expected}"
            )
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    scope = "both final-story branches" if len(entries) == 2 else entries[0][0]
    print(
        f"PASS: {scope} keeps BG1..BG7 on committed artwork "
        f"and BG0 on dialogue in mGBA ({output})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
