#!/usr/bin/env python3
"""Prove prerecorded Stage 1 colors visible pickups from the YAML LUT."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from PIL import Image

from verify_pickup_class_palettes import BG_TABLE_OFFSET, PICKUPS


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_attract_pickup_palettes.lua")
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
OG_DEMO_STAGE_FRAMES = 1856
MAX_DEMO_STAGE_DRIFT = round(OG_DEMO_STAGE_FRAMES * 0.10)


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def stop_owned(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def parse_report(path: Path) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result.setdefault(key, []).append(value)
    return result


def parse_capture_specs(values: list[str]) -> dict[str, list[tuple[int, ...]]]:
    """Map each native screenshot to its visible pickup-cell rectangles."""
    result: dict[str, list[tuple[int, ...]]] = {}
    for value in values:
        path, separator, encoded = value.partition("|")
        if not separator:
            continue
        cells = []
        for item in encoded.split(";"):
            if item:
                cells.append(tuple(int(field, 16 if index == 3 else 10)
                                   for index, field in enumerate(item.split(","))))
        result[path] = cells
    return result


def pickup_pixel_metrics(
    image: Image.Image,
    cells: list[tuple[int, ...]],
) -> tuple[int, int]:
    """Count rendered chromatic pixels inside the audited pickup tiles."""
    coordinates: set[tuple[int, int]] = set()
    for screen_x, screen_y, _palette, _tile in cells:
        for y in range(max(0, screen_y), min(144, screen_y + 8)):
            for x in range(max(0, screen_x), min(160, screen_x + 8)):
                coordinates.add((x, y))
    chromatic = sum(
        max(image.getpixel(point)) - min(image.getpixel(point)) >= 24
        for point in coordinates
    )
    return len(coordinates), chromatic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-frames", type=int, default=10000)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    mgba = args.mgba.resolve()
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / "attract-pickups"
    report_path = Path(str(prefix) + ".txt")
    done_path = Path(str(prefix) + ".done")
    for path in (report_path, done_path):
        path.unlink(missing_ok=True)
    for path in output.glob("attract-pickups-*.png"):
        path.unlink()

    rom_bytes = rom.read_bytes()
    if len(rom_bytes) < 0x40000 or len(rom_bytes) % 0x4000:
        parser.error(
            f"ROM is {len(rom_bytes)} bytes; expected at least 262144 "
            "and a whole number of 16 KiB banks"
        )
    lut = rom_bytes[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    pickup_ids = bytearray(256)
    for pickup in PICKUPS:
        for tile in pickup.tiles:
            pickup_ids[tile] = 1
    lut_path = output / "stage1-bg-lut.bin"
    pickup_path = output / "pickup-ids.bin"
    lut_path.write_bytes(lut)
    pickup_path.write_bytes(pickup_ids)

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "ATTRACT_PICKUP_OUT": str(prefix),
        "ATTRACT_PICKUP_LUT": str(lut_path),
        "ATTRACT_PICKUP_IDS": str(pickup_path),
        "ATTRACT_PICKUP_MAX_FRAMES": str(args.max_frames),
    })
    if "ATTRACT_PICKUP_TRACE_LAYOUTS" in os.environ:
        environment["ATTRACT_PICKUP_TRACE_LAYOUTS"] = os.environ[
            "ATTRACT_PICKUP_TRACE_LAYOUTS"
        ]
    log_path = output / "mgba.log"
    with log_path.open("w") as stream:
        process = subprocess.Popen(
            [
                str(mgba), "--fastforward",
                "-C", f"savegamePath={output}",
                str(rom), "--script", str(PROBE),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        deadline = time.monotonic() + args.timeout
        try:
            while time.monotonic() < deadline:
                if report_path.is_file() and done_path.is_file():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            stop_owned(process)

    if not report_path.is_file():
        print(f"FAIL: natural demo produced no report; see {log_path}")
        return 1
    fields = parse_report(report_path)
    one = lambda key, default="": fields.get(key, [default])[0]
    captures = [Path(value) for value in fields.get("capture", [])]
    capture_specs = parse_capture_specs(fields.get("capture_spec", []))
    capture_receipts = []
    for capture in captures:
        if not capture.is_file():
            continue
        with Image.open(capture) as source:
            image = source.convert("RGB")
        chromatic = sum(
            max(pixel) - min(pixel) >= 24 for pixel in image.getdata()
        )
        cells = capture_specs.get(str(capture), [])
        pickup_pixels, pickup_chromatic = pickup_pixel_metrics(image, cells)
        capture_receipts.append({
            "path": str(capture),
            "sha256": sha256(capture),
            "size": list(image.size),
            "chromatic_pixels": chromatic,
            "pickup_cells": [list(cell) for cell in cells],
            "pickup_region_pixels": pickup_pixels,
            "pickup_chromatic_pixels": pickup_chromatic,
        })

    target_frames = int(one("target_frames", "0"))
    target_start = int(one("target_start", "-1"))
    visible = int(one("visible_pickup_cells", "0"))
    colored = int(one("colored_pickup_cells", "0"))
    neutral = int(one("neutral_pickup_cells", "0"))
    mismatches = int(one("pickup_mismatches", "0"))
    visible_background = int(one("visible_background_cells", "0"))
    background_mismatches = int(one("background_palette_mismatches", "0"))
    nonpickup_mismatches = int(one("nonpickup_palette_mismatches", "0"))
    unsafe_attributes = int(one("unsafe_attribute_cells", "0"))
    mismatch_frames = int(one("background_mismatch_frames", "0"))
    last_mismatch_frame = int(one("last_background_mismatch_frame", "-1"))
    clean_after_entry_boundary = (
        mismatch_frames == 0
        or (
            target_start >= 0
            and mismatch_frames <= 4
            and last_mismatch_frame <= target_start + 3
        )
    )
    pickup_capture_receipts = [
        receipt for receipt in capture_receipts if receipt["pickup_cells"]
    ]
    late_capture_receipts = [
        receipt for receipt in capture_receipts
        if "-late-clean-" in receipt["path"]
    ]
    checks = {
        "natural prerecorded Stage 1 was reached and exited": (
            one("status") == "ok" and target_frames >= 1000
        ),
        "prerecorded Stage 1 stays within 10% of OG timing": (
            abs(target_frames - OG_DEMO_STAGE_FRAMES)
            <= MAX_DEMO_STAGE_DRIFT
        ),
        "the natural demo exposed semantic pickup tiles": visible > 0,
        "every visible pickup cell selected its YAML palette": (
            visible > 0 and colored == visible and mismatches == 0
        ),
        "no visible pickup cell remained on neutral BG0": (
            visible > 0 and neutral == 0
        ),
        "the full demo BG reaches the compiled YAML LUT within four hidden entry frames": (
            visible_background > 0 and clean_after_entry_boundary
        ),
        "pickup palettes leave no persistent trails on non-pickup tiles": (
            visible_background > 0
            and clean_after_entry_boundary
            and last_mismatch_frame < target_start + 4
        ),
        "demo BG attributes contain no unsafe priority/bank/flip bits": (
            visible_background > 0 and unsafe_attributes == 0
        ),
        "six native pickup screenshots render chroma inside pickup cells": (
            len(pickup_capture_receipts) >= 6
            and all(
                receipt["size"] == [160, 144]
                and receipt["chromatic_pixels"] > 100
                and receipt["pickup_region_pixels"] > 0
                and receipt["pickup_chromatic_pixels"] >= 4
                for receipt in pickup_capture_receipts
            )
        ),
        "three late-demo screenshots cover the formerly corrupted route": (
            len(late_capture_receipts) == 3
            and all(receipt["size"] == [160, 144]
                    for receipt in late_capture_receipts)
        ),
    }
    receipt = {
        "schema": "penta-dragon-dx-attract-pickups-v5",
        "status": "pass" if all(checks.values()) else "fail",
        "rom": str(rom),
        "rom_sha256": sha256(rom),
        "route": "cold boot; no input; D880=02/FFC1=1/DCFD=0",
        "target_start": target_start,
        "target_frames": target_frames,
        "og_demo_stage_frames": OG_DEMO_STAGE_FRAMES,
        "max_demo_stage_drift": MAX_DEMO_STAGE_DRIFT,
        "first_pickup_frame": int(one("first_pickup_frame", "-1")),
        "visible_pickup_cells": visible,
        "colored_pickup_cells": colored,
        "neutral_pickup_cells": neutral,
        "pickup_mismatches": mismatches,
        "first_mismatch": one("first_mismatch"),
        "visible_background_cells": visible_background,
        "background_palette_mismatches": background_mismatches,
        "nonpickup_palette_mismatches": nonpickup_mismatches,
        "unsafe_attribute_cells": unsafe_attributes,
        "max_background_mismatches_per_frame": int(
            one("max_background_mismatches_per_frame", "0")
        ),
        "background_mismatch_frames": int(
            one("background_mismatch_frames", "0")
        ),
        "last_background_mismatch_frame": int(
            one("last_background_mismatch_frame", "-1")
        ),
        "background_mismatch_trace": fields.get(
            "background_mismatch_frame", []
        ),
        "background_mismatch_cells": fields.get(
            "background_mismatch_cell", []
        ),
        "first_background_mismatch": one("first_background_mismatch"),
        "pickup_tiles": [
            tile for tile in one("pickup_tiles").split(",") if tile
        ],
        "captures": capture_receipts,
        "checks": checks,
        "failures": [name for name, passed in checks.items() if not passed],
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(("PASS" if passed else "FAIL") + ": " + name)
    print(
        f"INFO: pickup cells={visible}, colored={colored}, neutral={neutral}, "
        f"mismatches={mismatches}; first={receipt['first_mismatch']}"
    )
    print(
        "INFO: demo BG cells="
        f"{visible_background}, mismatches={background_mismatches}, "
        f"nonpickup={nonpickup_mismatches}, unsafe={unsafe_attributes}; "
        f"first={receipt['first_background_mismatch']}"
    )
    print(f"Receipt: {receipt_path}")
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
