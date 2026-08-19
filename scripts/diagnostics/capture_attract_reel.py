#!/usr/bin/env python3
"""Capture one direct-seeded visual receipt for every spotlight identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v302_title_fix import (  # noqa: E402
    SPOTLIGHT_ROSTER_SIZE,
    SPOTLIGHT_ROSTER_TABLE_ADDR,
    compile_spotlight_palette_map,
)


PROBE = Path(__file__).with_name("probe_spotlight_roster_mgba.lua")
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def parse_oam(raw: str) -> list[tuple[int, int, int, int]]:
    return [
        tuple(int(value, 16 if offset >= 2 else 10) for offset, value in enumerate(item.split(":")))
        for item in raw.split(",") if item
    ]


def run_roster(
    mgba: Path, rom: Path, output: Path, frames: int, timeout: float,
) -> list[dict[str, object]]:
    stem = output / "roster"
    stem.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".txt", ".tsv", ".done", ".pre-banner.ss0"):
        Path(str(stem) + suffix).unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "SPOTLIGHT_ROSTER_OUT": str(stem),
        "SPOTLIGHT_ROSTER_LIMIT": str(frames),
    })
    process = subprocess.Popen(
        [str(mgba), "--fastforward", "--script", str(PROBE), str(rom)],
        cwd=ROOT, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    marker = Path(str(stem) + ".done")
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode} during roster capture")
            time.sleep(0.025)
        else:
            raise TimeoutError(f"roster capture timed out after {timeout:g}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
    report_path = Path(str(stem) + ".txt")
    if not report_path.is_file():
        raise RuntimeError("roster capture produced no report")
    report = parse_report(report_path)
    if report.get("status") != "ok" or int(report.get("captured", "-1")) != SPOTLIGHT_ROSTER_SIZE:
        raise RuntimeError(f"roster capture failed: {report.get('message', 'invalid receipt')}")
    rows: list[dict[str, object]] = []
    trace = Path(str(stem) + ".tsv")
    for line in trace.read_text().splitlines()[1:]:
        identity, frame, screenshot_raw, oam = line.split("\t")
        screenshot = Path(screenshot_raw)
        sprites = parse_oam(oam)
        if not screenshot.is_file() or len(sprites) != 4:
            raise RuntimeError(f"identity {int(identity):02d} has an invalid visual receipt")
        with Image.open(screenshot) as image:
            name_region = image.convert("RGB").crop((50, 80, 150, 104))
            name_pixels = sum(
                min(pixel) >= 160 and max(pixel) - min(pixel) <= 80
                for pixel in name_region.getdata()
            )
        rows.append({
            "identity": int(identity), "frame": int(frame), "sprites": sprites,
            "name_pixels": name_pixels, "screenshot": screenshot,
            "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
        })
    if [row["identity"] for row in rows] != list(range(SPOTLIGHT_ROSTER_SIZE)):
        raise RuntimeError("roster capture did not return identities 0..37 in order")
    return rows


def create_contact_sheet(actors: list[dict[str, object]], output: Path) -> None:
    columns = 6
    label_height = 14
    cell_width, cell_height = 160, 144 + label_height
    rows = (len(actors) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, actor in enumerate(actors):
        screenshot = Image.open(str(actor["screenshot"])).convert("RGB")
        x = index % columns * cell_width
        y = index // columns * cell_height
        sheet.paste(screenshot, (x, y + label_height))
        draw.text(
            (x + 2, y + 2),
            (
                f"id {int(actor['identity']):02d} "
                f"res {int(actor['resource_id']):02X} "
                f"OBJ{int(actor['expected_palette_slot'])}"
            ),
            fill="black",
        )
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp/penta-title-spotlight",
    )
    parser.add_argument("--frames-per-identity", type=int, default=4_500)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--replays", type=int, default=2)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    _packed, palette_slots, yaml_resources = compile_spotlight_palette_map()
    rom_bytes = rom.read_bytes()
    rom_resources = list(
        rom_bytes[
            SPOTLIGHT_ROSTER_TABLE_ADDR:
            SPOTLIGHT_ROSTER_TABLE_ADDR + SPOTLIGHT_ROSTER_SIZE
        ]
    )
    if rom_resources != yaml_resources:
        raise SystemExit("ROM spotlight roster does not match palette YAML")

    mgba = args.mgba.resolve()
    captured: list[dict[str, object]] = []
    failures: list[str] = []
    try:
        replays = [
            run_roster(
                mgba, rom, output / f"replay-{replay}",
                args.frames_per_identity * SPOTLIGHT_ROSTER_SIZE,
                args.timeout,
            )
            for replay in range(1, args.replays + 1)
        ]
    except Exception as error:
        replays = []
        failures.append(str(error))
    for target in range(SPOTLIGHT_ROSTER_SIZE):
        if not replays:
            break
        runs = [replay[target] for replay in replays]
        canonical = [
            (
                run["sprites"], run["name_pixels"],
                run["screenshot_sha256"],
            )
            for run in runs
        ]
        if len(set(map(repr, canonical))) != 1:
            failures.append(f"identity {target:02d} is nondeterministic: {canonical}")
            continue
        frame = int(runs[0]["frame"])
        sprites = runs[0]["sprites"]
        name_pixels = int(runs[0]["name_pixels"])
        expected = palette_slots[target]
        actual = [entry[3] & 7 for entry in sprites]
        path = output / (
            f"id{target:02d}_res{rom_resources[target]:02X}"
            f"_obj{expected}_f{frame}.png"
        )
        shutil.copy2(runs[0]["screenshot"], path)
        captured.append(
            {
                "identity": target,
                "resource_id": rom_resources[target],
                "frame": frame,
                "expected_palette_slot": expected,
                "hardware_palette_slots": actual,
                "hardware_oam": sprites,
                "name_glyph_pixels": name_pixels,
                "screenshot_sha256": runs[0]["screenshot_sha256"],
                "screenshot": str(path),
                "deterministic_replays": args.replays,
            }
        )
        if actual != [expected] * 4:
            failures.append(
                f"identity {target:02d} palette {actual}, expected OBJ{expected}"
            )
        if target < SPOTLIGHT_ROSTER_SIZE - 1 and name_pixels < 24:
            failures.append(
                f"identity {target:02d} name is not visibly rendered "
                f"({name_pixels} bright glyph pixels)"
            )
        print(
            f"id={target:02d} resource={rom_resources[target]:02X} "
            f"frame={frame} palette={actual} name_pixels={name_pixels} "
            f"screenshot={path}"
        )

    contact_sheet = output / "spotlight-roster-contact-sheet.png"
    if captured:
        create_contact_sheet(captured, contact_sheet)
    receipt = {
        "status": "failed" if failures else "ok",
        "rom": str(rom),
        "captured": len(captured),
        "expected": SPOTLIGHT_ROSTER_SIZE,
        "actors": captured,
        "determinism_basis": (
            "exact rendered PNG, hardware OAM, and visible name glyphs; "
            "host callback frame counters are informational because mGBA "
            "queues in-process savestate reloads"
        ),
        "contact_sheet": str(contact_sheet),
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: all 38 spotlight actors captured with YAML-derived hardware "
        f"palettes. Contact sheet: {contact_sheet}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
