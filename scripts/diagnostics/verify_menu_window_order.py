#!/usr/bin/env python3
"""Require the visible hardware Window to match the native HUD buffer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_menu_window_order.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1280)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--key", choices=("select", "start", "combo"), default="select"
    )
    parser.add_argument("--open-frame", type=int, default=1200)
    parser.add_argument("--close-frame", type=int, default=-1)
    parser.add_argument("--save-fixture", type=Path)
    parser.add_argument(
        "--move",
        choices=("none", "right", "left", "up", "down"),
        default="none",
    )
    parser.add_argument("--fire-every", type=int, default=0)
    parser.add_argument("--inject-stale-frame", type=int, default=-1)
    parser.add_argument(
        "--inject-stale-scene",
        type=lambda value: int(value, 0),
        help="scene byte to use for a stale-Window boundary fixture",
    )
    args = parser.parse_args()
    if args.inject_stale_scene is not None and not 0 <= args.inject_stale_scene <= 0xFF:
        parser.error("--inject-stale-scene must fit in one byte")
    if args.inject_stale_scene is not None and args.inject_stale_frame < 0:
        parser.error("--inject-stale-scene requires --inject-stale-frame")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    screenshot = output.with_suffix(".first_visible.png")
    screenshot.unlink(missing_ok=True)

    runtime = output.parent / f"{output.stem}.runtime"
    runtime.mkdir(exist_ok=True)
    runtime_rom = runtime / "candidate.gb"
    (runtime / "candidate.sav").unlink(missing_ok=True)
    (runtime / "candidate.gb.ram").unlink(missing_ok=True)
    shutil.copy2(args.rom.resolve(), runtime_rom)
    if args.save_fixture:
        shutil.copy2(args.save_fixture.resolve(), runtime / "candidate.sav")
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "MENU_WINDOW_ORDER_OUT": str(output),
            "MENU_WINDOW_ORDER_SCREENSHOT": str(screenshot),
            "MENU_WINDOW_ORDER_FRAMES": str(args.frames),
            "MENU_WINDOW_ORDER_KEY": args.key,
            "MENU_WINDOW_ORDER_OPEN_FRAME": str(args.open_frame),
            "MENU_WINDOW_ORDER_CLOSE_FRAME": str(args.close_frame),
            "MENU_WINDOW_ORDER_MOVE": args.move,
            "MENU_WINDOW_ORDER_FIRE_EVERY": str(args.fire_every),
            "MENU_WINDOW_ORDER_STALE_FRAME": str(args.inject_stale_frame),
            "MENU_WINDOW_ORDER_STALE_SCENE": (
                "" if args.inject_stale_scene is None
                else str(args.inject_stale_scene)
            ),
        }
    )
    command = [
        str(MGBA),
        "--fastforward",
        str(runtime_rom),
        "--script",
        str(PROBE),
        "-C",
        f"savegamePath={runtime}",
    ]
    try:
        subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    if not output.is_file():
        print(f"FAIL: no report within {args.timeout:.1f}s")
        return 1

    report = parse_report(output)
    print(f"ROM: {args.rom.resolve()}")
    for key, value in report.items():
        print(f"{key}={value}")
    if int(report.get("window_frames", "0")) == 0:
        print("FAIL: SELECT route never exposed the hardware Window")
        return 1
    allowed_bad_frames = 1 if args.inject_stale_frame >= 0 else 0
    if int(report.get("bad_frames", "0")) > allowed_bad_frames:
        print(
            "FAIL: visible hardware Window did not match the native "
            "C4E0 HUD buffer"
        )
        return 1
    if (
        args.close_frame >= 0
        and int(report.get("window_frames_after_close", "0")) != 0
    ):
        print("FAIL: hardware Window remained visible after closing the menu")
        return 1
    if args.inject_stale_frame >= 0:
        if report.get("stale_injected") != "1":
            print("FAIL: stale-Window fixture was not injected")
            return 1
        expected_scene = (
            "native" if args.inject_stale_scene is None
            else f"{args.inject_stale_scene:02X}"
        )
        if report.get("stale_scene") != expected_scene:
            print("FAIL: stale-Window fixture used the wrong scene")
            return 1
        if int(report.get("stale_window_frames_after_grace", "-1")) != 0:
            print("FAIL: stale gameplay Window survived the next VBlank")
            return 1
    if args.inject_stale_frame >= 0:
        print("PASS: stale gameplay Window was hidden by the next VBlank.")
    else:
        print("PASS: every visible Window frame matched the native 6x20 HUD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
