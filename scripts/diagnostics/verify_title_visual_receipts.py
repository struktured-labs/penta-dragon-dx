#!/usr/bin/env python3
"""Create cold/returned title and demo-miniboss receipts through mGBA."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v302_title_fix import (  # noqa: E402
    PERIOD_TILE,
    TITLE_FOOTER,
    map_title_string_to_tiles,
)


PROBE = Path(__file__).with_name("probe_title_visual_receipts_mgba.lua")
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def red_dominant_pixels(path: Path) -> int:
    with Image.open(path) as image:
        return sum(
            red > 96 and red > green * 1.4 and red > blue * 1.4
            for red, green, blue in image.convert("RGB").getdata()
        )


def run_probe(rom: Path, output: Path, mgba: Path, timeout: float) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        TITLE_VISUAL_OUT=str(output),
        TITLE_VISUAL_MAX_FRAMES="26000",
        TITLE_VISUAL_FOOTER_HEX=bytes(
            map_title_string_to_tiles(TITLE_FOOTER)
        ).hex(),
        TITLE_VISUAL_PERIOD_HEX=PERIOD_TILE.hex(),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [str(mgba), "--fastforward", "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        marker = output / "DONE"
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before the title receipt"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"title visual inventory timed out after {timeout:g}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    report = output / "report.txt"
    if not report.is_file():
        raise RuntimeError("mGBA produced no title visual report")
    return parse_report(report)


def parse_counts(value: str) -> dict[int, int]:
    return {
        int(key): int(count)
        for item in value.split(",") if item
        for key, count in [item.split(":", 1)]
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path, nargs="?", default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/title-visual-receipts")
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    rom, output, mgba = args.rom.resolve(), args.output.resolve(), args.mgba.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    failures: list[str] = []
    try:
        report = run_probe(rom, output, mgba, args.timeout)
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    footer_hex = bytes(map_title_string_to_tiles(TITLE_FOOTER)).hex().upper()
    period_hex = PERIOD_TILE.hex().upper()
    captures: dict[str, dict[str, object]] = {}
    for key in ("cold_footer", "returned_footer", "cold_banner", "returned_banner"):
        frame = int(report.get(f"{key}_frame", "-1"))
        screenshot = Path(report.get(f"{key}_screenshot", ""))
        if frame < 0 or not screenshot.is_file():
            failures.append(f"missing {key} receipt")
            continue
        value: dict[str, object] = {
            "frame": frame,
            "screenshot": str(screenshot),
            "red_dominant_pixels": red_dominant_pixels(screenshot),
            "visible_oam": report.get(f"{key}_visible_oam", ""),
        }
        if key.endswith("footer"):
            value["footer_tiles"] = report.get(f"{key}_footer_hex", "")
            value["period_tile"] = report.get(f"{key}_period_hex", "")
            if str(value["footer_tiles"]).upper() != footer_hex:
                failures.append(f"{key} footer bytes differ")
            if str(value["period_tile"]).upper() != period_hex:
                failures.append(f"{key} period glyph differs")
        else:
            value["attribute_palettes"] = parse_counts(
                report.get(f"{key}_attr_counts", "")
            )
            value["unsafe_attributes"] = int(report.get(f"{key}_unsafe", "-1"))
            if value["attribute_palettes"] != {0: 2048, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0}:
                failures.append(f"{key} attributes={value['attribute_palettes']}")
            if value["unsafe_attributes"] != 0:
                failures.append(f"{key} unsafe attrs={value['unsafe_attributes']}")
        if value["red_dominant_pixels"] != 0:
            failures.append(f"{key} has {value['red_dominant_pixels']} red pixels")
        if value["visible_oam"]:
            failures.append(f"{key} retained visible OAM")
        captures[key] = value

    demo_samples = int(report.get("demo_samples", "0"))
    demo_sprites = int(report.get("demo_sprites", "0"))
    demo_mismatches = int(report.get("demo_mismatches", "-1"))
    if demo_samples < 10:
        failures.append(f"only {demo_samples} demo miniboss samples")
    if demo_mismatches:
        failures.append(f"{demo_mismatches}/{demo_sprites} demo palette mismatches")
    if report.get("live_scene1b") != "1":
        failures.append("returned title never advanced to live D880=1B")
    if report.get("status") != "ok":
        failures.append(
            f"probe status={report.get('status')}: {report.get('message')}"
        )

    transitions = []
    for item in report.get("transitions", "").split(","):
        if not item:
            continue
        frame, scene, ffc1 = item.split(":")
        transitions.append({"frame": int(frame), "d880": int(scene, 16), "ffc1": int(ffc1, 16)})
    receipt = {
        "schema": "penta-title-visual-receipts-mgba-v2",
        "status": "failed" if failures else "ok",
        "rom": str(rom),
        "title_footer": TITLE_FOOTER,
        "transitions": transitions,
        "captures": captures,
        "demo_miniboss": {
            "samples": demo_samples,
            "sprites": demo_sprites,
            "expected_palette_slots": {"tiles_20_2F": 2, "tiles_30_4F": 6},
            "palette_mismatches": demo_mismatches,
        },
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for key, value in captures.items():
        print(f"{key}: frame={value['frame']} screenshot={value['screenshot']}")
    print(
        f"demo_miniboss: samples={demo_samples} sprites={demo_sprites} "
        f"palette_mismatches={demo_mismatches}"
    )
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: footer bytes/glyph, cold+returned banner pixels/attributes/OAM, "
        "and stable demo-miniboss palette are verified through mGBA."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
