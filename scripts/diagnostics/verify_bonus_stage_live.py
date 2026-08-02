#!/usr/bin/env python3
"""Verify the Stage-1 bonus SHMUP in the exact current ROM under mGBA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATE = (
    ROOT / "save_states_for_claude/level1_sara_w_in_jet_form_secret_stage.ss0"
)
PROBE = ROOT / "scripts/diagnostics/probe_bonus_stage_live.lua"
BANK13 = 13 * 0x4000
WITCH_JET_ADDR = 0x68D0
DRAGON_JET_ADDR = 0x68D8


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def palette_words(rom: bytes, address: int) -> list[int]:
    offset = BANK13 + address - 0x4000
    data = rom[offset:offset + 8]
    return [data[index] | (data[index + 1] << 8) for index in range(0, 8, 2)]


def parse_report(path: Path) -> dict:
    result: dict[str, object] = {"objcram": {}}
    for line in path.read_text().splitlines():
        if line.startswith("objcram="):
            values = line.removeprefix("objcram=").split(",")
            result["objcram"][int(values[0])] = [
                int(value, 16) for value in values[1:]
            ]
        elif "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def image_receipt(path: Path) -> dict:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != (160, 144):
        raise RuntimeError(f"{path.name}: {image.size}, expected 160x144")
    pixels = list(image.getdata())
    nonwhite = sum(pixel != (255, 255, 255) for pixel in pixels) / len(pixels)
    chromatic = sum(max(pixel) - min(pixel) >= 24 for pixel in pixels)
    return {
        "path": str(path),
        "sha256": digest(path),
        "nonwhite_ratio": nonwhite,
        "chromatic_pixels": chromatic,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--mgba", type=Path,
        default=ROOT / "scripts/mgba-qt-singleflight",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rom = args.rom.resolve()
    state = args.state.resolve()
    if not state.is_file():
        print(f"FAIL: missing bonus-stage state {state}")
        return 2

    temporary = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="penta-bonus-live-")
        output = Path(temporary.name)
    report = output / "bonus-stage.report.txt"
    stdout = output / "bonus-stage.mgba.log"
    shot_prefix = output / "bonus-stage"
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "BONUS_LIVE_OUT": str(report),
        "BONUS_LIVE_SHOT_PREFIX": str(shot_prefix),
    })
    try:
        with stdout.open("w") as stream:
            completed = subprocess.run(
                [
                    str(args.mgba.resolve()), "--fastforward",
                    "-t", str(state), "--script", str(PROBE), str(rom),
                ],
                cwd=ROOT,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=args.timeout,
                check=False,
            )
        if completed.returncode != 0 or not report.is_file():
            print(
                f"FAIL: bonus probe status {completed.returncode}; see {stdout}"
            )
            return 1

        observed = parse_report(report)
        rom_bytes = rom.read_bytes()
        expected_cram = {
            1: palette_words(rom_bytes, DRAGON_JET_ADDR),
            2: palette_words(rom_bytes, WITCH_JET_ADDR),
        }
        screenshots = sorted(output.glob("bonus-stage-*.png"))
        images = [image_receipt(path) for path in screenshots]
        checks = {
            "current ROM executes after the historical state resumes": (
                int(observed.get("main_loop_hits", "0")) > 0
            ),
            "state remains live Stage-1 bonus gameplay": (
                observed.get("FFD0") == "01"
                and observed.get("FFC1") == "01"
                and int(observed.get("stage_samples", "0")) >= 100
                and int(observed.get("bad_state_frames", "-1")) == 0
            ),
            "both jet OBJ palette rows equal the candidate ROM": (
                observed["objcram"] == expected_cram
            ),
            "visible Sara hardware OAM uses her jet slot": (
                int(observed.get("sara_oam_checked", "0")) > 0
                and observed.get("sara_oam_checked")
                == observed.get("sara_oam_matched")
            ),
            "visible bonus BG attributes stay hardware-safe": (
                int(observed.get("unsafe_attrs", "-1")) == 0
            ),
            "three native rendered frames are nonwhite and chromatic": (
                len(images) == 3
                and all(image["nonwhite_ratio"] > 0.10 for image in images)
                and all(image["chromatic_pixels"] > 100 for image in images)
            ),
        }
        failures = [name for name, passed in checks.items() if not passed]
        receipt = {
            "schema": "penta-dragon-dx-bonus-stage-live-v1",
            "status": "pass" if not failures else "fail",
            "rom": str(rom),
            "rom_md5": digest(rom, "md5"),
            "rom_sha256": digest(rom),
            "state": str(state),
            "state_sha256": digest(state),
            "checks": checks,
            "observed": observed,
            "expected_obj_cram": expected_cram,
            "screenshots": images,
            "failures": failures,
        }
        receipt_path = output / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        for name, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'}: {name}")
        print(f"Receipt: {receipt_path}")
        if failures:
            return 1
        print("PASS: Stage-1 bonus SHMUP is live, colored, and render-safe.")
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
