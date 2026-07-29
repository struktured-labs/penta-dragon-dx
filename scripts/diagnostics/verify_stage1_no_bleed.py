#!/usr/bin/env python3
"""Prove Stage 1 has no red BG-palette bleeding during sustained play."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage1_no_bleed.lua"
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
FPS = 59.7275
BANK13 = 13 * 0x4000
DUNGEON_TABLE_OFFSET = BANK13 + (0x7000 - 0x4000)


def stop_owned_process_group(process: subprocess.Popen) -> None:
    """Stop only the xvfb/mGBA session created by this probe."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait(timeout=2)


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def parse_probe(path: Path) -> dict:
    result: dict[str, object] = {"captures": []}
    for line in path.read_text().splitlines():
        if not line:
            continue
        key, value = line.split("=", 1)
        if key == "capture":
            frame, screenshot, histogram, pal1, unexpected, unsafe = value.split("|")
            result["captures"].append(
                {
                    "play_frame": int(frame),
                    "elapsed_seconds": round(int(frame) / FPS, 3),
                    "screenshot": screenshot,
                    "attribute_histogram": {
                        item.split(":")[0]: int(item.split(":")[1])
                        for item in histogram.split(",")
                    },
                    "palette_1_cells": int(pal1),
                    "unexpected_palette_cells": int(unexpected),
                    "unsafe_attribute_cells": int(unsafe),
                }
            )
        elif key == "pal1_tiles":
            result[key] = {
                tile: int(count)
                for tile, count in (
                    item.split(":") for item in value.split(",") if item
                )
            }
        elif key == "pal1_capture":
            result.setdefault("pal1_captures", []).append(value)
        elif key in {"first_unexpected_screenshot", "first_unexpected_details"}:
            result[key] = value
        else:
            result[key] = int(value)
    return result


def create_contact_sheet(captures: list[dict], output: Path) -> None:
    scale = 3
    label_height = 24
    columns = 3
    rows = (len(captures) + columns - 1) // columns
    cell_width, cell_height = 160 * scale, 144 * scale + label_height
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), "white")
    draw = ImageDraw.Draw(sheet)
    for index, capture in enumerate(captures):
        source = Image.open(capture["screenshot"]).convert("RGB")
        if source.size != (160, 144):
            raise RuntimeError(
                f"{capture['screenshot']} is {source.size}, expected native 160x144"
            )
        scaled = source.resize((160 * scale, 144 * scale), Image.Resampling.NEAREST)
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        sheet.paste(scaled, (x, y + label_height))
        draw.text(
            (x + 6, y + 6),
            (
                f"play frame {capture['play_frame']}  "
                f"{capture['elapsed_seconds']:.1f}s  "
                f"BG1={capture['palette_1_cells']}"
            ),
            fill="black",
        )
    sheet.save(output)


def run_probe(
    mgba: str,
    rom: Path,
    output: Path,
    frames: int,
    mode: str,
    timeout: float,
) -> Path:
    for stale in (
        output / "probe.txt",
        output / "DONE",
        output / "receipt.json",
        output / "actual-play-stage1.png",
    ):
        stale.unlink(missing_ok=True)
    for stale in output.glob("play-*.png"):
        stale.unlink()

    environment = os.environ.copy()
    lut_path = output / "stage1_bg_table.bin"
    lut_path.write_bytes(
        rom.read_bytes()[
            DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 256
        ]
    )
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE1_BLEED_OUT": str(output),
            "STAGE1_BLEED_FRAMES": str(frames),
            "STAGE1_BLEED_MODE": mode,
            "STAGE1_BLEED_LUT": str(lut_path),
        }
    )
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    log = output / "mgba.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                "xvfb-run",
                "-a",
                mgba,
                "--fastforward",
                "-C",
                f"savegamePath={output}",
                "-C",
                f"savestatePath={output}",
                str(rom),
                "--script",
                str(PROBE),
                "-l",
                "0",
            ],
            cwd=output,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if (output / "probe.txt").is_file() and (output / "DONE").is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        stop_owned_process_group(process)
    receipt = output / "probe.txt"
    if not receipt.is_file():
        raise RuntimeError(f"Stage 1 play probe produced no receipt; see {log}")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--mode", choices=("right", "patrol"), default="right")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.mgba:
        parser.error("mgba-qt was not found")
    if args.frames < 1200:
        parser.error("--frames must be at least 1200 for the six play receipts")

    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    rom_bytes = rom.read_bytes()
    dungeon_table = rom_bytes[
        DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 256
    ]
    table_histogram = {
        str(palette): dungeon_table.count(palette) for palette in sorted(set(dungeon_table))
    }
    if set(dungeon_table) - {0, 1, 6}:
        failures.append(
            "Stage 1 ROM table contains palettes outside floor/pickup/wall "
            f"set {{0,1,6}}: {table_histogram}"
        )
    if dungeon_table.count(1) != 48:
        failures.append(
            "Stage 1 ROM table should map exactly 48 confirmed pickup tile "
            f"IDs to red BG1, found {dungeon_table.count(1)}"
        )

    try:
        probe = parse_probe(
            run_probe(args.mgba, rom, output, args.frames, args.mode, args.timeout)
        )
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    captures: list[dict] = probe["captures"]
    for capture in captures:
        screenshot = Path(capture["screenshot"])
        if not screenshot.is_file() or screenshot.stat().st_size <= 100:
            failures.append(f"missing rendered screenshot {screenshot}")
            continue
        capture["screenshot_sha256"] = digest(screenshot)
        capture["native_size"] = list(Image.open(screenshot).size)

    checks = {
        "1200+ continuous actual gameplay frames": (
            probe.get("frames", 0) >= args.frames
            and probe.get("scene_frames", 0) >= args.frames
            and probe.get("active_frames", 0) >= args.frames
        ),
        "every actual-play frame sampled": (
            probe.get("sampled_frames", 0) >= args.frames
        ),
        "route visibly scrolled": probe.get("scroll_changes", 0) > 0,
        "intentional red pickup cells observed": probe.get("pal1_cells", 0) > 0,
        "every visible tile matches the compiled palette LUT on every frame": (
            probe.get("unexpected_cells", -1) == 0
            and probe.get("first_unexpected_frame", 0) == -1
        ),
        "all six visual receipts match the compiled palette LUT": (
            len(captures) == 6
            and all(
                capture["unexpected_palette_cells"] == 0
                for capture in captures
            )
        ),
        "no tile-bank/flip/priority leakage": probe.get("unsafe_cells", -1) == 0,
        "six native screenshots": (
            len(captures) == 6
            and all(capture.get("native_size") == [160, 144] for capture in captures)
        ),
        "final state remains Stage 1 gameplay": (
            probe.get("final_scene") == 2 and probe.get("final_ffc1") == 1
        ),
    }
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        if not passed:
            failures.append(name)
    print(
        "INFO: tile/attribute mismatches across every frame="
        f"{probe.get('unexpected_cells', 0)}; first visual receipt="
        f"{probe.get('first_unexpected_screenshot', '')}"
    )

    contact_sheet = output / "actual-play-stage1.png"
    if captures and all(Path(c["screenshot"]).is_file() for c in captures):
        create_contact_sheet(captures, contact_sheet)

    # Keep the JSON portable when a receipt directory is copied into docs/.
    for capture in captures:
        capture["screenshot"] = Path(capture["screenshot"]).name

    report = {
        "schema": "penta-dragon-dx-stage1-no-bleed-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom),
        "rom_md5": digest(rom, "md5"),
        "rom_sha256": digest(rom),
        "route": {
            "source": "cold boot; native Stage 1 selection; continuous input",
            "mode": args.mode,
            "play_frames_requested": args.frames,
            "emulated_seconds": round(args.frames / FPS, 3),
        },
        "stage1_table_histogram": table_histogram,
        "probe": probe,
        "checks": checks,
        "contact_sheet": contact_sheet.name,
        "contact_sheet_sha256": (
            digest(contact_sheet) if contact_sheet.is_file() else None
        ),
        "failures": failures,
    }
    report_path = output / "receipt.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Receipt: {report_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: Stage 1 completed 20+ seconds of continuous play with "
        "every visible tile matching the compiled palette LUT."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
