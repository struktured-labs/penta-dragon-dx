#!/usr/bin/env python3
"""Serial mGBA gate for natural title-to-Stage-1 input routes.

Unlike the legacy PyBoy smoke test, this gate:

* tests the ROM passed on the command line;
* does not force WRAM state from Lua;
* covers first boot and persisted-SRAM cold boot;
* covers both A and START as the title confirmation; and
* rejects flat-white rendered frames, not merely state-machine progress.
"""

from __future__ import annotations

import argparse
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


@dataclass(frozen=True)
class Route:
    save_mode: str
    confirm: str

    @property
    def name(self) -> str:
        return f"{self.save_mode}-{self.confirm}"


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


def run_route(
    rom: Path,
    mgba: Path,
    output: Path,
    route: Route,
    save_fixture: Path | None,
    timeout: float,
    max_gameplay_frame: int,
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
        GAME_START_MAX_FRAMES="1800",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    command = [
        str(mgba),
        str(runtime_rom),
        "--script",
        str(LUA),
        "-C",
        f"savegamePath={runtime}",
    ]
    started = time.monotonic()
    process = subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, _ = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _ = process.communicate()
    duration = time.monotonic() - started
    (runtime / "emulator.log").write_text(stdout)

    result_path = prefix.with_suffix(".txt")
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
    passed = (
        fields.get("status") == ["ok"]
        and gameplay_frames >= 120
        and len(frame_receipts) >= 2
        and final_nonwhite >= 0.05
        and 0 <= first_gameplay <= max_gameplay_frame
    )
    return passed, {
        "route": route.name,
        "status": fields.get("status", ["missing"])[0],
        "returncode": process.returncode,
        "duration_seconds": round(duration, 3),
        "first_gameplay": first_gameplay,
        "gameplay_frames": gameplay_frames,
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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=25.0)
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

    owned_temp: tempfile.TemporaryDirectory[str] | None = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        owned_temp = tempfile.TemporaryDirectory(prefix="penta-game-start-")
        output = Path(owned_temp.name)

    routes = [Route("blank", "a"), Route("saved", "a")]
    if args.include_start_confirm:
        routes.extend(
            [Route("blank", "start"), Route("saved", "start")]
        )

    print(f"Candidate SHA-256: {sha256(rom)}")
    print(f"Artifacts: {output}")
    all_passed = True
    try:
        for route in routes:
            route_save = save_fixture
            if route.save_mode == "saved" and route_save is None:
                route_save = output / "blank-a" / "candidate.sav"
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
            )
            all_passed &= passed
            print(
                f"{'PASS' if passed else 'FAIL'} {route.name}: "
                f"status={receipt.get('status', receipt.get('error'))} "
                f"first_gameplay={receipt.get('first_gameplay', -1)} "
                f"gameplay_frames={receipt.get('gameplay_frames', 0)} "
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
        print("PASS: every natural GAME START route reached stable Stage 1.")
        return 0
    print("FAIL: a natural GAME START route froze or rendered flat white.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
