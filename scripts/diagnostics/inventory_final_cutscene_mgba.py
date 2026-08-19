#!/usr/bin/env python3
"""Fast deterministic full post-final production inventory through mGBA."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_ending_page_discriminators import analyze_manifest  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
from cutscene_region_palettes import load_cutscene_region_palettes, panel_mask  # noqa: E402


PROBE = Path(__file__).with_name("probe_ending_inventory_mgba.lua")
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_YAML = ROOT / "palettes/penta_palettes_v097.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_key_values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1) for line in path.read_text().splitlines() if "=" in line
    )


def parse_counts(value: str) -> dict[int, int]:
    return {
        int(item.split(":")[0]): int(item.split(":")[1])
        for item in value.split(",") if item
    }


def parse_state(value: str) -> dict[str, int]:
    return {
        item.split(":")[0]: int(item.split(":")[1], 16)
        for item in value.split(",") if item
    }


def run_probe(mgba: Path, rom: Path, output: Path, frames: int, timeout: float) -> dict[str, str]:
    stem = output / "ending"
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen", "SDL_AUDIODRIVER": "dummy",
        "ENDING_INVENTORY_OUT": str(stem),
        "ENDING_INVENTORY_MAX_FRAMES": str(frames),
    })
    process = subprocess.Popen(
        [str(mgba), "--fastforward", "--script", str(PROBE), str(rom)],
        cwd=ROOT, env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    marker = Path(str(stem) + ".done")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode} before ending receipt")
            time.sleep(0.025)
        else:
            raise TimeoutError(f"mGBA ending inventory timed out after {timeout:g}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)
    result_path = Path(str(stem) + ".txt")
    if not result_path.is_file():
        raise RuntimeError("mGBA ending inventory produced no result")
    return parse_key_values(result_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--entry", choices=("post-final",), default="post-final")
    parser.add_argument("--frames", type=int, default=32000)
    parser.add_argument("--expect-production", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()

    rom, output = args.rom.resolve(), args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    try:
        result = run_probe(args.mgba.resolve(), rom, output, args.frames, args.timeout)
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    panels = []
    trace = output / "ending.tsv"
    for line in trace.read_text().splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 12:
            continue
        frame, scene, ffc1, ffba, ffe4, palettes, unsafe, table_bad, tiles, attrs, state, image = fields
        state_values = parse_state(state)
        panels.append({
            "frame": int(frame), "scene": int(scene, 16),
            "ffc1": int(ffc1, 16), "ffba": int(ffba, 16),
            "ffe4": int(ffe4, 16), "palettes": parse_counts(palettes),
            "unsafe_attr_cells": int(unsafe), "table_bad": int(table_bad),
            "tilemap_hex": tiles, "attribute_hex": attrs,
            "tilemap_crc32": f"{__import__('zlib').crc32(bytes.fromhex(tiles)):08X}",
            "image_crc32": None, "story_state": state_values,
            "image": Path(image).name,
            "image_sha256": sha256(Path(image)) if Path(image).is_file() else None,
        })

    manifest = {
        "schema": "penta-dragon-dx-final-cutscene-mgba-v4",
        "status": "pass", "verification_mode": "production", "route": "post-final",
        "rom": str(rom), "rom_sha256": sha256(rom),
        "palette_yaml": str(args.palette_yaml.resolve()),
        "palette_yaml_sha256": sha256(args.palette_yaml.resolve()),
        "checks": {
            "route_reached": ">1A" in result.get("transitions", "") or any(p["scene"] == 0x1A for p in panels),
            "panels_captured": bool(panels),
            "unsafe_attributes_zero": int(result.get("unsafe_total", "-1")) == 0,
            "active_story_table_neutral": int(result.get("table_bad_samples", "-1")) == 0,
            "returned_to_title": result.get("returned") == "1",
        },
        "full_story_arts": [], "full_phases": [], "panels": panels,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    palette_panels = load_cutscene_region_palettes(args.palette_yaml)
    expected = {
        art_id: bytes(value for row in panel_mask(panel) for value in row) + bytes(200)
        for art_id, panel in palette_panels.items()
    }
    try:
        analysis = analyze_manifest(manifest_path, expected)
    except ValueError as error:
        analysis = {
            "status": "failed", "failures": [str(error)],
            "observed_signature": [], "phases": {}, "panels": len(panels),
        }
    failures = list(analysis["failures"])
    failures.extend(
        f"probe {key} failed"
        for key, passed in manifest["checks"].items() if not passed
    )
    if result.get("status") != "ok":
        failures.append(f"probe status {result.get('status')}: {result.get('message')}")
    manifest["status"] = "fail" if failures else "pass"
    manifest["checks"]["production_discriminators_exact"] = not analysis["failures"]
    manifest["full_story_arts"] = analysis["phases"].get("post_final_dialogue", {}).get("full_targets", [])
    manifest["full_phases"] = [
        name for name in ("credits", "end_page", "epilogue_preamble", "epilogue_text")
        if name in analysis["phases"]
    ]
    manifest["analysis"] = analysis
    manifest["failures"] = failures
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"{'PASS' if not failures else 'FAIL'}: {len(panels)} distinct ending "
        f"panels; trajectory={analysis['observed_signature']}"
    )
    print(f"Receipt: {manifest_path}")
    for failure in failures[:20]:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
