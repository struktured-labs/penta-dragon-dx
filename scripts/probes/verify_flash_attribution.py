#!/usr/bin/env python3
"""Verify Sara/first-monster OBJ attribution through guarded mGBA."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_teleport.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-headless-singleflight"
PROBE = Path(__file__).with_name("probe_flash_attribution_mgba.lua")


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def parse_distribution(value: str) -> dict[int, int]:
    return {
        int(palette): int(count)
        for item in value.split(",") if item
        for palette, count in [item.split(":", 1)]
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/flash-attribution")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rom, mgba, output = args.rom.resolve(), args.mgba.resolve(), args.output.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    prefix = output / "flash"
    environment = os.environ.copy()
    environment.update(
        FLASH_ATTR_OUT=str(prefix),
        FLASH_ATTR_MAX_FRAMES="4000",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [str(mgba), "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + args.timeout
        marker = prefix.with_suffix(".done")
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                detail = process.stderr.read().strip() if process.stderr else ""
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before receipt: {detail}"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"flash attribution timed out after {args.timeout:g}s")
    except Exception as error:
        print(f"HARNESS ERROR: {error}")
        return 2
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    report_path = prefix.with_suffix(".report")
    if not report_path.is_file():
        print("HARNESS ERROR: mGBA produced no report")
        return 2
    report = parse_report(report_path)
    slot0 = parse_distribution(report.get("slot0_distribution", ""))
    slot2 = parse_distribution(report.get("slot2_distribution", ""))
    receipt = {
        "schema": "penta-flash-attribution-mgba-v2",
        "status": report.get("status"),
        "rom": str(rom),
        "frames": int(report.get("capture_frames", "0")),
        "first_gameplay": int(report.get("first_gameplay", "-1")),
        "visible_wait": int(report.get("visible_wait", "-1")),
        "slot0_distribution": slot0,
        "slot2_distribution": slot2,
        "slot0_orange": int(report.get("slot0_orange", "-1")),
        "slot2_orange": int(report.get("slot2_orange", "-1")),
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(
        f"Gameplay frame={receipt['first_gameplay']}; visible sprites after "
        f"{receipt['visible_wait']} frames; captured={receipt['frames']}"
    )
    print(f"Slot 0 (Sara): {slot0}")
    print(f"Slot 2 (first monster): {slot2}")
    passed = (
        report.get("status") == "ok"
        and receipt["frames"] == 600
        and receipt["slot0_orange"] == 0
        and receipt["slot2_orange"] == 0
    )
    if not passed:
        print(f"FAIL: {report.get('message', 'invalid attribution receipt')}")
        return 1
    print("PASS: Palette 4 appeared on neither slot during all 600 frames.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
