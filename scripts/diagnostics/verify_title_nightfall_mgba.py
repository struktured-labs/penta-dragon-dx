#!/usr/bin/env python3
"""Require the reviewed Nightfall treatment on cold and returned title menus.

This is the renderer-level regression gate that the prior title checks lacked.
It runs exactly one mGBA instance through the checked-in single-flight wrapper,
binds every artifact to the candidate SHA-256, and rejects a readable but
white/grayscale title as well as stale palette or attribute payloads.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_title_color_prototype as title  # noqa: E402


SCHEMA = "penta-title-nightfall-mgba-v2"
PROBE = DIAGNOSTICS / "probe_title_nightfall_mgba.lua"
SINGLEFLIGHT = ROOT / "scripts" / "mgba-qt-singleflight"
PROCESS_CHECK = ROOT / "scripts" / "check_emulator_processes.sh"
LOCK_BUSY = 75
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
EXPECTED_RENDERED_COLOURS = {
    (24, 33, 99),
    (198, 231, 255),
    (255, 247, 181),
    (148, 165, 214),
    (255, 222, 16),
}


class GateFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_output(path: Path) -> Path:
    resolved = path.resolve()
    scratch = (ROOT / "tmp").resolve()
    bulky = Path("/mnt/data/tmp").resolve()
    require(
        (resolved != scratch and resolved.is_relative_to(scratch))
        or (bulky.exists() and resolved != bulky
            and resolved.is_relative_to(bulky)),
        "output must be below repository tmp/ or /mnt/data/tmp/",
    )
    if resolved.exists():
        require(resolved.is_dir(), f"output is not a directory: {resolved}")
        require(not any(resolved.iterdir()),
                f"refusing to reuse non-empty output: {resolved}")
    else:
        resolved.mkdir(parents=True)
    return resolved


def parse_exact_key_values(path: Path, expected: set[str]) -> dict[str, str]:
    require(path.is_file(), f"missing report: {path}")
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        require("=" in line, f"{path.name}:{line_number}: malformed line")
        key, value = line.split("=", 1)
        require(key not in values, f"{path.name}: duplicate key {key}")
        values[key] = value
    require(set(values) == expected,
            f"{path.name}: keys differ: {sorted(set(values) ^ expected)}")
    return values


def expected_title_payload(rom: bytes) -> tuple[bytes, bytes]:
    require(title.ACTIVE_SCHEME == "Nightfall",
            "palette YAML no longer selects Nightfall")
    attributes, _ = title.build_attribute_image(title.parse_title_list(rom))
    palettes = title.build_palette_block(title.SCHEMES["Nightfall"])
    return bytes(attributes), palettes


def analyze_snapshot(
    *, label: str, text_path: Path, png_path: Path,
    expected_attributes: bytes, expected_palettes: bytes,
) -> dict[str, Any]:
    keys = {
        "frame", "d880", "ffc1", "lcdc", "scx", "scy", "base",
        "bgcram", *(f"r{row:02d}" for row in range(1, 19)),
    }
    report = parse_exact_key_values(text_path, keys)
    require(report["d880"] == "01", f"{label}: not on title scene")
    expected_ffc1 = "1" if label == "returned" else "0"
    require(report["ffc1"] == expected_ffc1,
            f"{label}: FFC1 is {report['ffc1']}, expected {expected_ffc1}")
    require(report["scx"] == "8" and report["scy"] == "8",
            f"{label}: title scroll changed")
    require(report["lcdc"] == "83" and report["base"] == "9800",
            f"{label}: title LCDC/map changed")

    cram = bytes.fromhex(report["bgcram"])
    require(len(cram) == 64, f"{label}: BG CRAM length changed")
    require(cram[8:56] == expected_palettes,
            f"{label}: BG1..BG6 do not match reviewed Nightfall")

    mismatches: list[dict[str, int]] = []
    unsafe = 0
    histogram: Counter[int] = Counter()
    for row in range(1, 19):
        actual = bytes.fromhex(report[f"r{row:02d}"].replace(" ", ""))
        require(len(actual) == 21,
                f"{label}: row {row} does not contain 21 cells")
        expected = expected_attributes[(row - 1) * 32:row * 32][:21]
        for column, (got, want) in enumerate(zip(actual, expected, strict=True)):
            histogram[got & 7] += 1
            unsafe += bool(got & 0xF8)
            if got != want and len(mismatches) < 16:
                mismatches.append({
                    "row": row, "column": column,
                    "expected": want, "actual": got,
                })
    require(unsafe == 0, f"{label}: {unsafe} unsafe title attributes")
    require(not mismatches,
            f"{label}: title attributes differ: {mismatches[:4]}")
    require(set(histogram) == {1, 2, 3, 4, 5, 6},
            f"{label}: not all six title roles are visible")

    require(png_path.is_file(), f"{label}: missing renderer capture")
    with Image.open(png_path) as source:
        image = source.convert("RGB")
        require(image.size == (160, 144),
                f"{label}: renderer size is {image.size}")
        pixels = list(image.getdata())
    colours = Counter(pixels)
    field, field_count = colours.most_common(1)[0]
    # The CRAM proof above is exact.  These renderer assertions independently
    # ensure those values reached pixels; in particular, the old 90%-white
    # grayscale menu cannot satisfy the indigo-field or chroma requirements.
    # All six attribute roles and their complete CRAM rows are authenticated
    # above.  At this deterministic cursor phase the BG5/orange role is bound
    # to a blank glyph cell, so the exact raster contains the other five
    # reviewed colours and must not invent an orange pixel.
    require(len(colours) >= 5,
            f"{label}: only {len(colours)} rendered colours")
    require(set(colours) == EXPECTED_RENDERED_COLOURS,
            f"{label}: rendered Nightfall colour set changed: "
            f"{sorted(colours)}")
    require(field[2] >= 72 and field[2] > field[0] * 2
            and field[2] > field[1] * 1.5 and max(field) < 160,
            f"{label}: dominant field is not dark indigo: {field}")
    require(field_count >= 18000,
            f"{label}: dominant title field covers only {field_count} pixels")
    chromatic = sum(
        count for colour, count in colours.items()
        if max(colour) - min(colour) >= 24
    )
    require(chromatic >= 22000,
            f"{label}: only {chromatic} chromatic pixels")

    return {
        "frame": int(report["frame"]),
        "scene": report["d880"],
        "base": report["base"],
        "attribute_histogram": {
            str(key): value for key, value in sorted(histogram.items())
        },
        "unsafe_attributes": unsafe,
        "rendered_colours": len(colours),
        "dominant_field": list(field),
        "dominant_field_pixels": field_count,
        "chromatic_pixels": chromatic,
        "png": str(png_path),
        "png_sha256": sha256(png_path),
        "report": str(text_path),
        "report_sha256": sha256(text_path),
        "rgb_sha256": hashlib.sha256(bytes(
            channel for pixel in pixels for channel in pixel
        )).hexdigest(),
    }


def run_probe(rom: Path, output: Path, timeout: float) -> dict[str, str]:
    stem = output / "title"
    environment = os.environ.copy()
    environment.update(
        PENTA_TITLE_NIGHTFALL_OUT=str(stem),
        PENTA_TITLE_NIGHTFALL_SETTLE="300",
        PENTA_TITLE_NIGHTFALL_LIMIT="12000",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    command = [
        str(SINGLEFLIGHT), "--fastforward", "--script", str(PROBE), str(rom)
    ]
    try:
        completed = subprocess.run(
            command, cwd=ROOT, env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as error:
        process_check = subprocess.run(
            [str(PROCESS_CHECK)], cwd=ROOT,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=10.0, check=False,
        )
        (output / "process-check.log").write_text(process_check.stdout)
        raise GateFailure(
            f"mGBA timed out; process check exit {process_check.returncode}"
        ) from error
    (output / "emulator.log").write_text(completed.stdout)
    if completed.returncode == LOCK_BUSY:
        raise GateFailure("mGBA single-flight lock is busy (exit 75)")
    require(completed.returncode == 0,
            f"mGBA exited {completed.returncode}; see emulator.log")
    return parse_exact_key_values(
        stem.with_suffix(".report"),
        {"status", "message", "frames", "transitions",
         "deferred_wram_frames", "cold_captured", "left_title",
         "returned_captured"},
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    receipt_path: Path | None = None
    try:
        candidate = args.rom.resolve()
        require(candidate.is_file(), f"ROM is missing: {candidate}")
        require(SHA256_PATTERN.fullmatch(args.expected_sha256) is not None,
                "--expected-sha256 is malformed")
        candidate_sha = sha256(candidate)
        require(candidate_sha == args.expected_sha256,
                f"candidate SHA mismatch: {candidate_sha}")
        output = checked_output(args.output)
        receipt_path = output / "receipt.json"
        probe = run_probe(candidate, output, args.timeout)
        require(probe["status"] == "ok",
                f"probe status is {probe['status']}: {probe['message']}")
        require(probe["cold_captured"] == "true"
                and probe["left_title"] == "true"
                and probe["returned_captured"] == "true",
                "probe did not capture both title epochs")
        rom = candidate.read_bytes()
        expected_attributes, expected_palettes = expected_title_payload(rom)
        snapshots = {
            label: analyze_snapshot(
                label=label,
                text_path=output / f"title.{label}.txt",
                png_path=output / f"title.{label}.png",
                expected_attributes=expected_attributes,
                expected_palettes=expected_palettes,
            )
            for label in ("cold", "returned")
        }
        require(
            snapshots["cold"]["rgb_sha256"]
            == snapshots["returned"]["rgb_sha256"],
            "cold and returned title rasters differ",
        )
        checks = {
            "exact candidate SHA is authenticated": True,
            "cold title uses all six exact Nightfall attribute roles": True,
            "returned title uses all six exact Nightfall attribute roles": True,
            "cold title BG1..BG6 CRAM matches palette YAML": True,
            "returned title BG1..BG6 CRAM matches palette YAML": True,
            "cold title renders a dark indigo chromatic field": True,
            "returned title renders a dark indigo chromatic field": True,
            "cold and returned title rasters are byte-identical": True,
            "white or grayscale title menus are rejected": True,
        }
        receipt: dict[str, Any] = {
            "schema": SCHEMA,
            "status": "pass",
            "candidate": str(candidate),
            "candidate_sha256": candidate_sha,
            "palette_yaml": str(title.PALETTE_YAML.resolve()),
            "palette_yaml_sha256": sha256(title.PALETTE_YAML.resolve()),
            "active_scheme": title.ACTIVE_SCHEME,
            "probe": probe,
            "snapshots": snapshots,
            "checks": checks,
            "tool_identity": {
                "verifier_sha256": sha256(Path(__file__).resolve()),
                "probe_sha256": sha256(PROBE),
                "singleflight_sha256": sha256(SINGLEFLIGHT),
            },
            "failures": [],
        }
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(
            "PASS: cold and returned title menus render the exact reviewed "
            "Nightfall attributes and CRAM on a dark chromatic field"
        )
        print(f"Receipt: {receipt_path}")
        return 0
    except (GateFailure, OSError, ValueError, subprocess.SubprocessError) as error:
        if receipt_path is not None:
            receipt_path.write_text(json.dumps({
                "schema": SCHEMA, "status": "fail",
                "failures": [str(error)],
            }, indent=2, sort_keys=True) + "\n")
        print(f"FAIL: {error}")
        return LOCK_BUSY if "exit 75" in str(error) else 1


if __name__ == "__main__":
    raise SystemExit(main())
