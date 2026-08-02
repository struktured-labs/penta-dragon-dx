#!/usr/bin/env python3
"""Gate the save-present GAME START level-select screen in mGBA."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
LUA = Path(__file__).with_name("probe_levelselect_attrs.lua")


def parse_fields(line: str) -> dict[str, str]:
    return dict(field.split("=", 1) for field in line.split() if "=" in field)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    with tempfile.TemporaryDirectory(prefix="penta-levelselect-") as tmp:
        out = Path(tmp) / "result"
        env = os.environ.copy()
        env.update(
            OUT=str(out),
            QT_QPA_PLATFORM="offscreen",
            SDL_AUDIODRIVER="dummy",
        )
        process = subprocess.Popen(
            [args.mgba, str(args.rom.resolve()), "--script", str(LUA)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + args.timeout
        result_path = out.with_suffix(".txt")
        try:
            while time.monotonic() < deadline and not result_path.exists():
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        if not result_path.exists():
            print("FAIL: mGBA did not reach the level-select screen")
            return 1

        raw = result_path.read_text().strip()
        fields = parse_fields(raw)
        print(raw)

        checks = {
            "score screen reached": "status" not in fields,
            "scene is the colorizer-dark level-select": (
                fields.get("d880") == "00" and fields.get("ffc1") == "0"
            ),
            "save-present GAME START path": fields.get("dcfd") == "01",
            # Validate the executable byte itself. DF0E was a historical copy
            # sentinel, but the title path intentionally trusts CFAA instead
            # because attract teardown can overwrite one without the other.
            "WRAM clear stub was installed": fields.get("cfaa") == "E5",
            "score rows are populated": int(fields.get("populated", "0")) >= 10,
            "all visible attributes are palette 0": (
                fields.get("checked") == "360" and fields.get("nonzero") == "0"
            ),
            "rendered screenshot exists": (
                out.with_suffix(".png").is_file()
                and out.with_suffix(".png").stat().st_size > 100
            ),
        }
        for name, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'}: {name}")

        if all(checks.values()):
            print("PASS: save-present GAME START level-select attributes are clean.")
            return 0
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
