#!/usr/bin/env python3
"""Verify the title cursor on mGBA's CGB renderer and native input path.

The former PyBoy-only gate was a false negative for the colorized title: its
renderer omitted a cursor that mGBA visibly drew. This verifier instead uses
the checked-in single-flight mGBA wrapper, authenticates selector-tile blink
ownership at both menu rows, drives DOWN then UP, and requires a contrasting
renderer capture for every selected position.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "diagnostics" / "probe_title_cursor_mgba.lua"
SINGLEFLIGHT = ROOT / "scripts" / "mgba-qt-singleflight"
PROCESS_CHECK = ROOT / "scripts" / "check_emulator_processes.sh"
DEFAULT_ROM = ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp" / "penta-title-cursor-gate"
LOCK_BUSY = 75
SCHEMA = "penta-title-cursor-mgba-v2"
PHASES = (("opening", 65), ("game", 81), ("restored", 65))


class GateFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_output(path: Path) -> Path:
    output = path.resolve()
    scratch = (ROOT / "tmp").resolve()
    bulky = Path("/mnt/data/tmp").resolve()
    allowed = ((output != scratch and output.is_relative_to(scratch))
               or (bulky.exists() and output != bulky
                   and output.is_relative_to(bulky)))
    require(allowed, "output must be below repository tmp/ or /mnt/data/tmp/")
    if output.exists():
        require(output.is_dir(), "output is not a directory")
        require(not any(output.iterdir()), "refusing to reuse non-empty output")
    else:
        output.mkdir(parents=True)
    return output


def parse_report(path: Path) -> dict[str, str]:
    require(path.is_file(), "missing mGBA cursor report")
    fields: dict[str, str] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        require("=" in line, f"report:{number}: malformed line")
        key, value = line.split("=", 1)
        require(key not in fields, f"report: duplicate key {key}")
        fields[key] = value
    expected = {"status", "message", "frames"}
    for phase, _ in PHASES:
        expected.update({f"{phase}_expected_hits", f"{phase}_wrong_hits",
                         f"{phase}_context_failures", f"{phase}_screenshot"})
    require(set(fields) == expected,
            f"report keys differ: {sorted(set(fields) ^ expected)}")
    return fields


def contrasting_pixels(path: Path, y: int) -> int:
    require(path.is_file(), f"missing renderer capture: {path.name}")
    with Image.open(path) as source:
        image = source.convert("RGB")
        require(image.size == (160, 144),
                f"{path.name}: renderer size is {image.size}")
        colours: dict[tuple[int, int, int], int] = {}
        for scan_y in range(0, image.height, 4):
            for x in range(0, image.width, 4):
                value = image.getpixel((x, scan_y))
                colours[value] = colours.get(value, 0) + 1
        field = max(colours, key=colours.get)
        return sum(
            sum(abs(channel - base) for channel, base in zip(
                image.getpixel((x, row)), field, strict=True)) > 48
            for row in range(y, y + 7)
            for x in range(24, 32)
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    receipt_path: Path | None = None
    try:
        rom = args.rom.resolve()
        require(rom.is_file(), f"ROM not found: {rom}")
        output = checked_output(args.output)
        receipt_path = output / "receipt.json"
        stem = output / "title-cursor"
        env = os.environ.copy()
        env.update({"PENTA_TITLE_CURSOR_OUT": str(stem),
                    "QT_QPA_PLATFORM": "offscreen", "SDL_AUDIODRIVER": "dummy"})
        result = subprocess.run(
            [str(SINGLEFLIGHT), "--fastforward", "--script", str(PROBE), str(rom)],
            cwd=ROOT, env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=args.timeout, check=False,
        )
        (output / "emulator.log").write_text(result.stdout)
        require(result.returncode != LOCK_BUSY,
                "mGBA single-flight lock is busy (exit 75)")
        terminal_marker = stem.with_suffix(".done")
        terminal_ok = (terminal_marker.is_file()
                       and terminal_marker.read_text() == "ok\n")
        # Qt/mGBA can fault during teardown after this owned probe has written
        # its terminal report and captures.  Accept only that known teardown
        # status and only with the explicit, content-verified terminal marker;
        # no timeout, missing artifact, or other return code can qualify.
        require(result.returncode == 0 or (result.returncode == -11 and terminal_ok),
                f"mGBA exited {result.returncode}; see emulator.log")
        fields = parse_report(stem.with_suffix(".report"))
        require(fields["status"] == "ok", fields["message"])
        receipt: dict[str, object] = {
            "schema": SCHEMA, "rom": str(rom), "rom_sha256": digest(rom),
            "probe": str(PROBE), "probe_sha256": digest(PROBE), "phases": {},
        }
        for phase, y in PHASES:
            expected = int(fields[f"{phase}_expected_hits"])
            wrong = int(fields[f"{phase}_wrong_hits"])
            context = int(fields[f"{phase}_context_failures"])
            screenshot = Path(fields[f"{phase}_screenshot"])
            require(expected > 0, f"{phase}: selector tile never blinked")
            require(wrong == 0, f"{phase}: selector tile appeared on wrong row")
            require(context == 0, f"{phase}: left the title context")
            contrast = contrasting_pixels(screenshot, y)
            require(contrast >= 12,
                    f"{phase}: renderer cursor contrast is only {contrast} pixels")
            receipt["phases"][phase] = {
                "selector_tile_hits": expected, "wrong_row_hits": wrong,
                "context_failures": context, "renderer_contrast_pixels": contrast,
                "png": str(screenshot), "png_sha256": digest(screenshot),
            }
        subprocess.run([str(PROCESS_CHECK), "--require-none"], cwd=ROOT,
                       check=True, timeout=10.0)
        receipt["status"] = "passed"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(f"PASS: native mGBA title cursor route; receipt: {receipt_path}")
        return 0
    except (GateFailure, subprocess.TimeoutExpired, ValueError) as error:
        if receipt_path is not None:
            receipt_path.write_text(json.dumps({"schema": SCHEMA, "status": "failed",
                                                 "error": str(error)}, indent=2) + "\n")
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
