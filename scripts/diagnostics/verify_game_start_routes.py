#!/usr/bin/env python3
"""Serial mGBA gate for natural title-to-Stage-1 input routes.

Unlike the legacy PyBoy smoke test, this gate:

* tests the ROM passed on the command line;
* does not force WRAM state from Lua;
* covers first boot and persisted-SRAM cold boot;
* can inventory either A or START as the title confirmation; and
* rejects flat-white rendered frames, not merely state-machine progress.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
LUA = Path(__file__).with_name("probe_game_start_route.lua")
MGBA_LOCK = Path(
    os.environ.get(
        "PENTA_MGBA_LOCK",
        "/tmp/penta-dragon-dx.mgba-singleflight.lock",
    )
)


@dataclass(frozen=True)
class Route:
    save_mode: str
    confirm: str
    timing: str
    down_frame: int
    confirm_frame: int
    press_frames: int = 6
    followups: bool = False
    stage_confirm_offset: int = -1
    after_attract: bool = False
    warm_reset: bool = False

    @property
    def name(self) -> str:
        boot = "warm" if self.warm_reset else "cold"
        schedule = (
            f"-d{self.down_frame}-c{self.confirm_frame}-p{self.press_frames}"
            if self.timing == "custom"
            else ""
        )
        stage_confirm = (
            f"-s{self.stage_confirm_offset}"
            if self.stage_confirm_offset >= 0
            else ""
        )
        attract = "-post-attract" if self.after_attract else ""
        return (
            f"{self.save_mode}-{self.confirm}-{self.timing}"
            f"{schedule}{stage_confirm}{attract}-{boot}"
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def nonwhite_ratio(path: Path) -> float:
    with Image.open(path) as image:
        pixels = list(image.convert("RGB").getdata())
    nonwhite = sum(
        pixel != (255, 255, 255)
        for pixel in pixels
    )
    return nonwhite / len(pixels)


def parse_result(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            result.setdefault(key, []).append(value)
    return result


def wait_for_mgba_slot(timeout: float = 3.0) -> None:
    """Wait for the prior serial Qt process to release the project lock."""
    deadline = time.monotonic() + timeout
    MGBA_LOCK.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(MGBA_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "guarded mGBA slot remained occupied after prior route"
                    )
                time.sleep(0.05)
    finally:
        os.close(descriptor)


def run_route(
    rom: Path,
    mgba: Path,
    output: Path,
    route: Route,
    save_fixture: Path | None,
    timeout: float,
    max_gameplay_frame: int,
    probe_max_frames: int,
) -> tuple[bool, dict]:
    runtime = output / route.name
    runtime.mkdir(parents=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    if route.save_mode == "saved":
        if save_fixture is None:
            raise ValueError("saved route requires --save-fixture")
        shutil.copy2(save_fixture, runtime / "candidate.sav")

    prefix = runtime / "route"
    env = os.environ.copy()
    env.update(
        GAME_START_OUT=str(prefix),
        GAME_START_CONFIRM=route.confirm,
        GAME_START_MAX_FRAMES=str(probe_max_frames),
        GAME_START_DOWN_FRAME=str(route.down_frame),
        GAME_START_CONFIRM_FRAME=str(route.confirm_frame),
        GAME_START_PRESS_FRAMES=str(route.press_frames),
        GAME_START_FOLLOWUPS="1" if route.followups else "0",
        GAME_START_STAGE_CONFIRM_OFFSET=str(route.stage_confirm_offset),
        GAME_START_AFTER_ATTRACT="1" if route.after_attract else "0",
        GAME_START_WARM_RESET="1" if route.warm_reset else "0",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    command = [str(mgba)]
    if route.after_attract:
        command.append("--fastforward")
    command += [
        str(runtime_rom),
        "--script",
        str(LUA),
        "-C",
        f"savegamePath={runtime}",
    ]
    result_path = prefix.with_suffix(".txt")
    wait_for_mgba_slot()
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = started + timeout
    while (
        time.monotonic() < deadline
        and process.poll() is None
        and not (result_path.is_file() and result_path.stat().st_size > 0)
    ):
        time.sleep(0.05)
    if process.poll() is None:
        process.terminate()
        try:
            stdout, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
    else:
        stdout, _ = process.communicate()
    duration = time.monotonic() - started
    (runtime / "emulator.log").write_text(stdout)

    if not result_path.is_file():
        return False, {
            "route": route.name,
            "error": "probe produced no result",
            "returncode": process.returncode,
            "duration_seconds": round(duration, 3),
        }

    fields = parse_result(result_path)
    captures = [Path(path) for path in fields.get("capture", [])]
    frame_receipts = [
        {
            "path": str(path),
            "sha256": sha256(path),
            "nonwhite_ratio": nonwhite_ratio(path),
        }
        for path in captures
        if path.is_file()
    ]
    minimum_nonwhite = min(
        (receipt["nonwhite_ratio"] for receipt in frame_receipts),
        default=0.0,
    )
    final_receipts = [
        receipt
        for receipt in frame_receipts
        if receipt["path"].endswith("-final.png")
    ]
    final_nonwhite = (
        final_receipts[0]["nonwhite_ratio"] if final_receipts else 0.0
    )
    first_gameplay = int(fields.get("first_gameplay", ["-1"])[0])
    gameplay_frames = int(fields.get("gameplay_frames", ["0"])[0])
    saw_attract = fields.get("saw_attract", ["0"])[0] == "1"
    demo_delay_hits = int(fields.get("demo_delay_hits", ["-1"])[0])
    live_demo_delay_hits = int(
        fields.get("live_demo_delay_hits", [str(demo_delay_hits)])[0]
    )
    passed = (
        fields.get("status") == ["ok"]
        and gameplay_frames >= 120
        and live_demo_delay_hits == 0
        and (not route.after_attract or saw_attract)
        and len(frame_receipts) >= 2
        and final_nonwhite >= 0.05
        and 0 <= first_gameplay <= max_gameplay_frame
    )
    return passed, {
        "route": route.name,
        "timing": route.timing,
        "down_frame": route.down_frame,
        "confirm_frame": route.confirm_frame,
        "press_frames": route.press_frames,
        "followups": route.followups,
        "stage_confirm_offset": route.stage_confirm_offset,
        "after_attract": route.after_attract,
        "saw_attract": saw_attract,
        "warm_reset": route.warm_reset,
        "status": fields.get("status", ["missing"])[0],
        "returncode": process.returncode,
        "duration_seconds": round(duration, 3),
        "first_gameplay": first_gameplay,
        "gameplay_frames": gameplay_frames,
        "demo_delay_hits": demo_delay_hits,
        "demo_delay_hits_before_route": int(
            fields.get("demo_delay_hits_before_route", ["0"])[0]
        ),
        "live_demo_delay_hits": live_demo_delay_hits,
        "final_d880": fields.get("final_d880", ["??"])[0],
        "final_ffc1": fields.get("final_ffc1", ["??"])[0],
        "final_dcfd": fields.get("final_dcfd", ["??"])[0],
        "transitions": fields.get("transitions", [""])[0],
        "minimum_nonwhite_ratio": minimum_nonwhite,
        "final_nonwhite_ratio": final_nonwhite,
        "frames": frame_receipts,
        "samples": fields.get("sample", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument(
        "--save-fixture",
        type=Path,
        help="optional real SRAM file; enables saved-A and saved-START routes",
    )
    parser.add_argument(
        "--save-mode",
        action="append",
        choices=("blank", "saved"),
        help=(
            "SRAM mode to cover; repeat for both. Defaults to blank and saved. "
            "A saved-only run requires --save-fixture"
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--probe-max-frames",
        type=int,
        default=1800,
        help="stop an unresolved route after this many emulated frames",
    )
    parser.add_argument(
        "--max-gameplay-frame",
        type=int,
        default=540,
        help=(
            "latest acceptable Stage 1 entry frame; stock mGBA baseline is "
            "489 for this exact schedule (default: 540)"
        ),
    )
    parser.add_argument(
        "--include-start-confirm",
        action="store_true",
        help=(
            "also inventory START as a title-menu confirmation; the stock "
            "game requires A, so this diagnostic route is not a release gate"
        ),
    )
    parser.add_argument(
        "--confirm",
        action="append",
        choices=("a", "start"),
        help=(
            "title confirmation button to cover; repeat for both. Defaults to "
            "A. --include-start-confirm remains as a compatibility alias"
        ),
    )
    parser.add_argument(
        "--include-warm-reset",
        action="store_true",
        help=(
            "also repeat each route after an in-process reset, preserving the "
            "power-on initialization that differentiates the reported path"
        ),
    )
    parser.add_argument(
        "--timing",
        action="append",
        choices=("delayed", "prompt", "rapid", "eager"),
        help=(
            "input timing to cover; repeat for multiple timings. Defaults to "
            "delayed and prompt. rapid and eager are diagnostic stress paths"
        ),
    )
    parser.add_argument(
        "--down-frame",
        type=int,
        help=(
            "exact custom frame to press Down; requires --confirm-frame and "
            "cannot be combined with --timing"
        ),
    )
    parser.add_argument(
        "--confirm-frame",
        type=int,
        help=(
            "exact custom frame to press the confirmation button; requires "
            "--down-frame and cannot be combined with --timing"
        ),
    )
    parser.add_argument(
        "--press-frames",
        type=int,
        default=6,
        help="number of frames to hold each scheduled button (default: 6)",
    )
    parser.add_argument(
        "--followups",
        action="store_true",
        help=(
            "inject legacy rescue inputs after confirmation; diagnostic only. "
            "Release routes send exactly Down and the confirmation button"
        ),
    )
    parser.add_argument(
        "--stage-confirm-offset",
        action="append",
        type=int,
        help=(
            "send exactly one A this many frames after the title confirmation; "
            "repeat to sweep offsets in separate cold processes"
        ),
    )
    parser.add_argument(
        "--after-attract",
        action="store_true",
        help=(
            "wait for a natural title attract demo to run and return before "
            "sending the requested GAME START route"
        ),
    )
    args = parser.parse_args()

    rom = args.rom.resolve()
    mgba = args.mgba.resolve()
    save_fixture = (
        args.save_fixture.resolve() if args.save_fixture else None
    )
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    if not mgba.is_file():
        parser.error(f"guarded mGBA frontend not found: {mgba}")
    if save_fixture is not None and not save_fixture.is_file():
        parser.error(f"save fixture not found: {save_fixture}")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.max_gameplay_frame <= 0:
        parser.error("--max-gameplay-frame must be positive")
    if args.probe_max_frames <= 0:
        parser.error("--probe-max-frames must be positive")
    if args.press_frames <= 0:
        parser.error("--press-frames must be positive")
    if args.followups and args.stage_confirm_offset:
        parser.error("--followups cannot be combined with --stage-confirm-offset")
    if args.stage_confirm_offset and min(args.stage_confirm_offset) < 0:
        parser.error("--stage-confirm-offset cannot be negative")
    if (args.down_frame is None) != (args.confirm_frame is None):
        parser.error("--down-frame and --confirm-frame must be provided together")
    if args.down_frame is not None:
        if args.timing:
            parser.error("custom frame options cannot be combined with --timing")
        if args.down_frame <= 0:
            parser.error("--down-frame must be positive")
        if args.confirm_frame <= args.down_frame:
            parser.error("--confirm-frame must be later than --down-frame")

    owned_temp: tempfile.TemporaryDirectory[str] | None = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        owned_temp = tempfile.TemporaryDirectory(prefix="penta-game-start-")
        output = Path(owned_temp.name)

    timing_frames = {
        "delayed": (180, 193),
        "prompt": (45, 58),
        "rapid": (45, 52),
        "eager": (20, 33),
    }
    if args.down_frame is not None:
        timing_frames["custom"] = (args.down_frame, args.confirm_frame)
        timing_names = ["custom"]
    else:
        timing_names = args.timing or ["delayed", "prompt"]
    confirm_names = args.confirm or ["a"]
    if args.include_start_confirm and "start" not in confirm_names:
        confirm_names.append("start")
    save_modes = args.save_mode or ["blank", "saved"]
    if save_modes == ["saved"] and save_fixture is None:
        parser.error("a saved-only run requires --save-fixture")
    reset_modes = (False, True) if args.include_warm_reset else (False,)
    stage_confirm_offsets = args.stage_confirm_offset or [-1]
    routes = [
        Route(
            save_mode,
            confirm,
            timing,
            *timing_frames[timing],
            args.press_frames,
            args.followups,
            stage_confirm_offset,
            args.after_attract,
            warm_reset,
        )
        for timing in timing_names
        for confirm in confirm_names
        for stage_confirm_offset in stage_confirm_offsets
        for warm_reset in reset_modes
        for save_mode in save_modes
    ]

    print(f"Candidate SHA-256: {sha256(rom)}")
    print(f"Artifacts: {output}")
    all_passed = True
    try:
        for route in routes:
            route_save = save_fixture
            if route.save_mode == "saved" and route_save is None:
                blank_route = Route(
                    "blank",
                    route.confirm,
                    route.timing,
                    route.down_frame,
                    route.confirm_frame,
                    route.press_frames,
                    route.followups,
                    route.stage_confirm_offset,
                    route.after_attract,
                    route.warm_reset,
                )
                route_save = (
                    output
                    / blank_route.name
                    / "candidate.sav"
                )
                if not route_save.is_file():
                    print(
                        "FAIL saved-a: blank route did not persist candidate.sav"
                    )
                    all_passed = False
                    break
            passed, receipt = run_route(
                rom,
                mgba,
                output,
                route,
                route_save,
                args.timeout,
                args.max_gameplay_frame,
                args.probe_max_frames,
            )
            all_passed &= passed
            print(
                f"{'PASS' if passed else 'FAIL'} {route.name}: "
                f"status={receipt.get('status', receipt.get('error'))} "
                f"first_gameplay={receipt.get('first_gameplay', -1)} "
                f"gameplay_frames={receipt.get('gameplay_frames', 0)} "
                f"live_demo_delay_hits="
                f"{receipt.get('live_demo_delay_hits', -1)} "
                f"final_nonwhite="
                f"{receipt.get('final_nonwhite_ratio', 0.0):.4f}"
            )
            if not passed:
                print(receipt)
                break
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()

    if all_passed:
        print(
            "PASS: every natural GAME START route reached stable Stage 1 "
            "without re-entering the completed attract route."
        )
        return 0
    print("FAIL: a natural GAME START route froze or rendered flat white.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
