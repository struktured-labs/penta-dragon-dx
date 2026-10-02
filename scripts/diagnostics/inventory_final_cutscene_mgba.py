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
from analyze_story_panel_discriminators import (  # noqa: E402
    analyze_manifest as analyze_story_manifest,
)
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


def run_probe(
    mgba: Path, rom: Path, output: Path, entry: str,
    frames: int, timeout: float, pre_final_mask: bytes | None = None,
) -> dict[str, str]:
    stem = output / ("pre-final" if entry == "pre-final" else "ending")
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen", "SDL_AUDIODRIVER": "dummy",
        "ENDING_INVENTORY_OUT": str(stem),
        "ENDING_INVENTORY_MAX_FRAMES": str(frames),
        "ENDING_INVENTORY_ENTRY": entry,
    })
    if entry == "pre-final":
        if pre_final_mask is None or len(pre_final_mask) != 360:
            raise ValueError("pre-final capture requires its exact YAML return mask")
        environment["ENDING_INVENTORY_PRE_FINAL_MASK"] = pre_final_mask.hex().upper()
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
    parser.add_argument(
        "--entry", choices=("post-final", "pre-final"), default="post-final"
    )
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
    palette_panels = load_cutscene_region_palettes(args.palette_yaml)
    expected = {
        art_id: bytes(value for row in panel_mask(panel) for value in row) + bytes(200)
        for art_id, panel in palette_panels.items()
    }
    try:
        result = run_probe(
            args.mgba.resolve(), rom, output, args.entry,
            args.frames, args.timeout, expected[4],
        )
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    panels = []
    trace = output / (
        "pre-final.tsv" if args.entry == "pre-final" else "ending.tsv"
    )
    for line in trace.read_text().splitlines()[1:]:
        fields = line.split("\t")
        if len(fields) != 17:
            continue
        (
            frame, scene, ffc1, ffba, ffe4, palettes, unsafe, table_bad,
            tiles, attrs, window_tiles, window_attrs, oam, shadow_c000,
            shadow_c100, state, image,
        ) = fields
        state_values = parse_state(state)
        panels.append({
            "frame": int(frame), "scene": int(scene, 16),
            "ffc1": int(ffc1, 16), "ffba": int(ffba, 16),
            "ffe4": int(ffe4, 16), "palettes": parse_counts(palettes),
            "unsafe_attr_cells": int(unsafe), "table_bad": int(table_bad),
            "tilemap_hex": tiles, "attribute_hex": attrs,
            "window_tilemap_hex": window_tiles,
            "window_attribute_hex": window_attrs,
            "oam_hex": oam,
            "shadow_c000_hex": shadow_c000,
            "shadow_c100_hex": shadow_c100,
            "tilemap_crc32": f"{__import__('zlib').crc32(bytes.fromhex(tiles)):08X}",
            "image_crc32": None, "story_state": state_values,
            "image": Path(image).name,
            "image_sha256": sha256(Path(image)) if Path(image).is_file() else None,
        })

    manifest = {
        "schema": "penta-dragon-dx-final-cutscene-mgba-v5",
        "status": "pass", "verification_mode": "production",
        "route": args.entry,
        "rom": str(rom), "rom_sha256": sha256(rom),
        "palette_yaml": str(args.palette_yaml.resolve()),
        "palette_yaml_sha256": sha256(args.palette_yaml.resolve()),
        "checks": {
            "route_reached": any(
                p["scene"] == (0x19 if args.entry == "pre-final" else 0x1A)
                for p in panels
            ),
            "panels_captured": bool(panels),
            "unsafe_attributes_zero": int(result.get("unsafe_total", "-1")) == 0,
            "active_story_table_neutral": int(result.get("table_bad_samples", "-1")) == 0,
            "returned_to_title": (
                result.get("returned") == "1"
                if args.entry == "post-final" else None
            ),
        },
        "full_story_arts": [], "full_phases": [], "panels": panels,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    try:
        if args.entry == "pre-final":
            story = analyze_story_manifest(manifest_path)
            return_mask_exact = (
                panels[-1]["story_state"]["dcf0"] == 4
                and bytes.fromhex(panels[-1]["attribute_hex"]) == expected[4]
            )
            full_targets = sorted({
                panel["story_state"]["dcf0"]
                for panel in panels
                if panel["scene"] == 0x19
                and panel["story_state"]["dce8"] == 4
                and panel["story_state"]["dcea"] == 1
                and panel["story_state"]["dd07"] + 1
                    == panel["story_state"]["dcf0"]
                and bytes.fromhex(panel["attribute_hex"])
                    == expected.get(panel["story_state"]["dcf0"], b"")
            })
            analysis = {
                "status": "ok" if (
                    story["sequence_matches"]
                    and set(full_targets) >= {4, 7}
                    and return_mask_exact
                ) else "failed",
                "failures": [] if (
                    story["sequence_matches"]
                    and set(full_targets) >= {4, 7}
                    and return_mask_exact
                ) else [
                    "pre-final art sequence or exact full palette targets missing"
                ],
                "observed_signature": story["observed_art_sequence"],
                "phases": {"pre_final_dialogue": {
                    "full_targets": full_targets,
                }},
                "panels": len(panels),
                "story": story,
                "return_mask_exact": return_mask_exact,
            }
        else:
            analysis = analyze_manifest(manifest_path, expected)
    except ValueError as error:
        analysis = {
            "status": "failed", "failures": [str(error)],
            "observed_signature": [], "phases": {}, "panels": len(panels),
        }
    failures = list(analysis["failures"])
    failures.extend(
        f"probe {key} failed"
        for key, passed in manifest["checks"].items() if passed is False
    )
    if result.get("status") != "ok":
        failures.append(f"probe status {result.get('status')}: {result.get('message')}")
    manifest["status"] = "fail" if failures else "pass"
    manifest["checks"]["production_discriminators_exact"] = not analysis["failures"]
    phase_name = (
        "pre_final_dialogue"
        if args.entry == "pre-final" else "post_final_dialogue"
    )
    manifest["full_story_arts"] = analysis["phases"].get(
        phase_name, {}
    ).get("full_targets", [])
    manifest["full_phases"] = [
        name for name in ("credits", "end_page", "epilogue_preamble", "epilogue_text")
        if name in analysis["phases"]
    ]
    manifest["analysis"] = analysis
    manifest["failures"] = failures
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"{'PASS' if not failures else 'FAIL'}: {len(panels)} distinct "
        f"{args.entry} panels; trajectory={analysis['observed_signature']}"
    )
    print(f"Receipt: {manifest_path}")
    for failure in failures[:20]:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
