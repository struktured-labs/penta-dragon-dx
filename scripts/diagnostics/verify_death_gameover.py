#!/usr/bin/env python3
"""Verify neutral, artifact-free death/game-over rendering from stock arenas."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PROBE = Path(__file__).with_name("probe_death_gameover.lua")
STATE_GENERATOR = Path(__file__).with_name("generate_stream_boss_states.py")
# Riff, Crystal Dragon, and Angela use multi-phase boss-local HP semantics at
# the generated arena checkpoint; DCBB=0 does not yet enter the common stock
# death path for those three. These six independently cover every observed
# arena-attribute carryover shape through an unmodified D880=$17 transition.
STOCK_DEATH_CASES = (
    (0, "shalamar"),
    (3, "cameo"),
    (4, "ted"),
    (5, "troop"),
    (6, "faze"),
    (8, "penta_dragon"),
)


def parse_report(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in path.read_text().split():
        if "=" in token:
            key, value = token.split("=", 1)
            result[key] = value
    return result


def image_metrics(path: Path) -> dict[str, int]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.size != (160, 144):
            raise RuntimeError(
                f"{path.name}: screenshot is {image.size}, expected 160x144"
            )
        pixels = list(image.getdata())
        return {
            "colors": len(set(pixels)),
            "chromatic": sum(
                max(pixel) - min(pixel) > 4 for pixel in pixels
            ),
            "near_white": sum(min(pixel) >= 248 for pixel in pixels),
            # The stock CGB grayscale ramp bottoms at RGB(82), not black.
            "dark": sum(max(pixel) <= 96 for pixel in pixels),
            "red": sum(
            red > 90 and red > green * 1.35 and red > blue * 1.20
                for red, green, blue in pixels
            ),
        }


def run_boss(
    mgba: str,
    rom: Path,
    state: Path,
    output: Path,
    timeout: float,
) -> tuple[dict[str, str], dict[str, int], dict[str, int], dict[str, int]]:
    prefix = output / state.stem
    stdout = prefix.with_suffix(".stdout.txt")
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        DEATH_OUT=str(prefix),
    )
    with stdout.open("w") as stream:
        completed = subprocess.run(
            [
                mgba,
                "--fastforward",
                "-t",
                str(state),
                "--script",
                str(PROBE),
                str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    report_path = prefix.with_suffix(".report")
    if not report_path.is_file():
        raise RuntimeError(
            f"{state.name}: no report (mGBA status {completed.returncode}); "
            f"see {stdout}"
        )
    art_path = Path(str(prefix) + ".art.png")
    fade_path = Path(str(prefix) + ".fade-white.png")
    gameover_path = Path(str(prefix) + ".gameover.png")
    if (
        not art_path.is_file()
        or not fade_path.is_file()
        or not gameover_path.is_file()
    ):
        raise RuntimeError(f"{state.name}: missing rendered capture; see {stdout}")
    return (
        parse_report(report_path),
        image_metrics(art_path),
        image_metrics(fade_path),
        image_metrics(gameover_path),
    )


def generate_states(
    mgba: str,
    rom: Path,
    output: Path,
    timeout: float,
) -> None:
    log = output / "state-generation.log"
    with log.open("w") as stream:
        completed = subprocess.run(
            [
                sys.executable,
                str(STATE_GENERATOR),
                str(rom),
                "--output",
                str(output),
                "--mgba",
                mgba,
                "--timeout",
                str(timeout),
            ],
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=max(300.0, timeout * 20),
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"release-ROM boss state generation failed with status "
            f"{completed.returncode}; see {log}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--states",
        type=Path,
        help=(
            "use an existing exact-ROM boss-state directory; by default a "
            "fresh/cache-validated set is generated beneath the output"
        ),
    )
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--only",
        type=int,
        action="append",
        choices=[index for index, _ in STOCK_DEATH_CASES],
        help="verify only this boss index (repeatable for split receipt runs)",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="capture and report contamination without enforcing neutrality",
    )
    args = parser.parse_args()

    if not args.mgba:
        print("FAIL: mgba-qt was not found")
        return 2
    rom = args.rom.resolve()

    temporary = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="penta-death-gameover-")
        output = Path(temporary.name)

    failures: list[str] = []
    try:
        states_root = (
            args.states.resolve()
            if args.states
            else output / "generated-states"
        )
        if not args.states:
            states_root.mkdir(parents=True, exist_ok=True)
            try:
                generate_states(
                    args.mgba, rom, states_root, args.timeout
                )
            except Exception as exc:
                print(f"FAIL: {exc}")
                return 2
        selected_cases = [
            case for case in STOCK_DEATH_CASES
            if not args.only or case[0] in args.only
        ]
        states = [
            states_root / f"boss{index}_{name}.ss0"
            for index, name in selected_cases
        ]
        missing = [state for state in states if not state.is_file()]
        if missing:
            print("FAIL: missing generated release-ROM boss states:")
            for state in missing:
                print(f"  - {state}")
            return 2

        for state in states:
            try:
                result, art_visual, fade_visual, gameover_visual = run_boss(
                    args.mgba, rom, state, output, args.timeout
                )
            except Exception as exc:
                failures.append(str(exc))
                continue
            art_nonzero = int(result.get("art_nonzero", "-1"))
            future_nonzero = int(
                result.get("art_future_window_nonzero", "-1")
            )
            window_begin_nonzero = int(
                result.get("window_begin_nonzero", "-1")
            )
            gameover_nonzero = int(result.get("gameover_nonzero", "-1"))
            unsafe = sum(
                int(result.get(key, "-1"))
                for key in (
                    "art_unsafe",
                    "art_future_window_unsafe",
                    "window_begin_unsafe",
                    "gameover_unsafe",
                )
            )
            print(
                f"{state.stem:30s} "
                f"art={art_nonzero:3d} pre-window={future_nonzero:3d} "
                f"window-start={window_begin_nonzero:3d} "
                f"gameover={gameover_nonzero:3d} unsafe={unsafe:2d} "
                f"chromatic={art_visual['chromatic']:4d}/"
                f"{fade_visual['chromatic']:4d}/"
                f"{gameover_visual['chromatic']:4d}"
            )
            if result.get("status") != "ok":
                failures.append(
                    f"{state.name}: probe status {result.get('status')!r}"
                )
            if result.get("d880") != "17" or result.get("ffe4") != "01":
                failures.append(
                    f"{state.name}: original death guard was not retained"
                )
            if not args.inventory_only:
                # The future window is still invisible at the art snapshot and
                # may be receiving stock transition writes. It must be fully
                # neutral on the exact frame LCDC enables it, not eight art
                # frames earlier.
                if (
                    window_begin_nonzero
                    or gameover_nonzero
                    or unsafe
                    or art_visual["chromatic"]
                    or art_visual["colors"] > 4
                    or fade_visual["chromatic"]
                    or fade_visual["near_white"] < 22800
                    or gameover_visual["chromatic"]
                    or gameover_visual["colors"] < 2
                    or gameover_visual["colors"] > 4
                    or gameover_visual["dark"] < 32
                ):
                    failures.append(
                        f"{state.name}: death fade/GAME OVER retained visible "
                        "CGB color, stale attributes, or missing text"
                    )

        if failures:
            print("FAIL:")
            for failure in failures:
                print(f"  - {failure}")
            print(f"Artifacts: {output}")
            return 1
        mode = "inventory" if args.inventory_only else "gate"
        scope = (
            "all six"
            if len(selected_cases) == len(STOCK_DEATH_CASES)
            else f"the selected {len(selected_cases)}"
        )
        print(
            f"PASS ({mode}): {scope} naturally transitioning stock arena "
            "carryover variants rendered neutrally and retained their "
            "original control-flow guard."
        )
        if args.output:
            print(f"Artifacts: {output}")
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
