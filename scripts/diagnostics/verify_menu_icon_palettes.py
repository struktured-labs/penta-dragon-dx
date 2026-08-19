#!/usr/bin/env python3
"""Verify YAML-owned item icon colors across every native menu group."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_menu_icon_palettes.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
BANK_SIZE = 0x4000
BANK13_LUT = 13 * BANK_SIZE + (0x7000 - 0x4000)
BANK20_LUT = 20 * BANK_SIZE + (0x4100 - 0x4000)
MENU_FIRST_ENTRY = 0x1B48
MENU_WRAPPER_PREFIX = bytes.fromhex("F0 99 F5 3E 14 CD 61 00 CD 00 40")
EXPECTED_GROUPS = ("MEDICAL", "SPECIAL", "PROTECT", "MEDICAL", "SPECIAL")
GROUP_LABEL_TAILS = {
    "MEDICAL": bytes.fromhex("E0 D5 E1 E3 E4 E5 E6 EF"),
    "SPECIAL": bytes.fromhex("EC ED E2 EB EE E5 E6 EF"),
    "PROTECT": bytes.fromhex("E7 E8 E9 EA E2 EB EA EF"),
}


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def row_bytes(report: dict[str, str], page: int, plane: str, row: int) -> bytes:
    value = report.get(f"page{page}_{plane}{row}", "")
    if len(value) != 40:
        raise ValueError(
            f"page {page} {plane} row {row} has {len(value) // 2} cells"
        )
    return bytes.fromhex(value)


def run_probe(rom: Path, output: Path, run_name: str) -> tuple[dict[str, str], list[Path]]:
    runtime = output / f"{run_name}.runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    report_path = output / f"{run_name}.txt"
    report_path.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "MENU_ICON_PALETTE_OUT": str(report_path),
        "MENU_ICON_PALETTE_FRAMES": "1510",
    })
    command = [
        str(MGBA), "--fastforward", str(runtime_rom),
        "--script", str(PROBE), "-C", f"savegamePath={runtime}",
    ]
    try:
        subprocess.run(
            command, cwd=ROOT, env=env, capture_output=True,
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        pass
    if not report_path.is_file():
        raise RuntimeError(f"{run_name}: no report within 60 seconds")
    screenshots = [
        Path(f"{report_path}.page-{page:02d}.png") for page in range(5)
    ]
    if not all(path.is_file() for path in screenshots):
        raise RuntimeError(f"{run_name}: incomplete screenshot set")
    return parse_report(report_path), screenshots


def audit_report(
    report: dict[str, str], expected_lut: bytes, require_colored: bool
) -> tuple[list[str], dict[str, object]]:
    failures: list[str] = []
    pages: list[dict[str, object]] = []
    if report.get("pages") != "5":
        failures.append(f"captured {report.get('pages', '0')} pages, expected 5")
    for page in range(5):
        page_mismatches = 0
        tile_mismatches = 0
        colored_cells = 0
        seen_colored_tiles: set[int] = set()
        rows: list[bytes] = []
        try:
            for row in range(6):
                packed = row_bytes(report, page, "packed", row)
                tiles = row_bytes(report, page, "tiles", row)
                attrs = row_bytes(report, page, "attrs", row)
                rows.append(tiles)
                tile_mismatches += sum(a != b for a, b in zip(packed, tiles))
                for tile, attr in zip(tiles, attrs):
                    expected = expected_lut[tile]
                    page_mismatches += attr != expected
                    if expected:
                        colored_cells += 1
                        seen_colored_tiles.add(tile)
        except ValueError as error:
            failures.append(str(error))
            continue
        expected_group = EXPECTED_GROUPS[page]
        label_tail = GROUP_LABEL_TAILS[expected_group]
        label_exact = rows[0].endswith(label_tail)
        if not label_exact:
            failures.append(
                f"page {page} does not expose the native {expected_group} label"
            )
        if tile_mismatches:
            failures.append(
                f"page {page} has {tile_mismatches} Window/C4E0 tile mismatches"
            )
        if page_mismatches:
            failures.append(
                f"page {page} has {page_mismatches} canonical palette mismatches"
            )
        pages.append({
            "page": page,
            "expected_group": expected_group,
            "label_tail": label_tail.hex().upper(),
            "label_exact": label_exact,
            "tile_mismatches": tile_mismatches,
            "palette_mismatches": page_mismatches,
            "colored_cells": colored_cells,
            "colored_tile_ids": [f"{tile:02X}" for tile in sorted(seen_colored_tiles)],
        })

    # The populated cold-start MEDICAL page is the release receipt that proves
    # the colored tiles are real icons, rather than only neutral menu chrome.
    medical = pages[0] if pages else {}
    if require_colored and int(medical.get("colored_cells", 0)) < 16:
        failures.append("MEDICAL page exposed fewer than sixteen colored icon cells")
    return failures, {"pages": pages}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--negative-control", action="store_true")
    parser.add_argument(
        "--expect", choices=("auto", "canonical", "neutral"), default="auto",
        help="auto-detect the optional bank-20 publisher, or require a mode",
    )
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")

    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data = rom.read_bytes()
    if len(data) != 32 * BANK_SIZE:
        print(f"FAIL: expected a 512 KiB ROM, got {len(data)} bytes")
        return 1
    canonical_lut = data[BANK13_LUT:BANK13_LUT + 0x100]
    private_lut = data[BANK20_LUT:BANK20_LUT + 0x100]
    publisher_present = data[
        MENU_FIRST_ENTRY:MENU_FIRST_ENTRY + len(MENU_WRAPPER_PREFIX)
    ] == MENU_WRAPPER_PREFIX
    expected_mode = args.expect
    if expected_mode == "auto":
        expected_mode = "canonical" if publisher_present else "neutral"
    expected_lut = canonical_lut if expected_mode == "canonical" else bytes(0x100)
    failures: list[str] = []
    if expected_mode == "canonical" and not publisher_present:
        failures.append("canonical menu publisher is absent from the fixed entry")
    if expected_mode == "neutral" and publisher_present:
        failures.append("neutral mode requested but the canonical publisher is present")
    if expected_mode == "canonical" and private_lut != canonical_lut:
        failures.append("bank-20 menu LUT differs from canonical bank-13 YAML LUT")

    receipts: list[dict[str, object]] = []
    raw_reports: list[dict[str, str]] = []
    for run in range(args.runs):
        report, screenshots = run_probe(rom, output, f"run-{run + 1}")
        run_failures, receipt = audit_report(
            report, expected_lut, expected_mode == "canonical"
        )
        failures.extend(f"run {run + 1}: {item}" for item in run_failures)
        receipt.update({
            "run": run + 1,
            "report": str(output / f"run-{run + 1}.txt"),
            "screenshots": [str(path) for path in screenshots],
        })
        receipts.append(receipt)
        raw_reports.append(report)
    if len(raw_reports) > 1 and any(
        report != raw_reports[0] for report in raw_reports[1:]
    ):
        failures.append("A/B emulator reports are not deterministic")

    negative_control: dict[str, object] | None = None
    if args.negative_control:
        if expected_mode != "canonical":
            parser.error("--negative-control requires canonical mode")
        mutated = bytearray(data)
        original = mutated[BANK20_LUT + 0x88]
        mutated[BANK20_LUT + 0x88] = (original + 1) & 7
        negative_rom = output / "negative-control-tile88.gb"
        negative_rom.write_bytes(mutated)
        report, _ = run_probe(negative_rom, output, "negative-control")
        negative_failures, _ = audit_report(report, canonical_lut, True)
        caught = bool(negative_failures)
        negative_control = {
            "tile": "88",
            "original_palette": original,
            "mutated_palette": mutated[BANK20_LUT + 0x88],
            "caught": caught,
            "failures": negative_failures,
        }
        if not caught:
            failures.append("negative LUT mutation was not detected")

    manifest = {
        "schema": "penta-menu-icon-palettes-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom),
        "rom_sha256": hashlib.sha256(data).hexdigest(),
        "canonical_lut_sha256": hashlib.sha256(canonical_lut).hexdigest(),
        "expected_mode": expected_mode,
        "publisher_present": publisher_present,
        "private_lut_matches": private_lut == canonical_lut,
        "runs": receipts,
        "negative_control": negative_control,
        "failures": failures,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    if failures:
        print(f"FAIL: {len(failures)} menu-icon regression(s)")
        return 1
    print("PASS: every menu page is canonical, deterministic, and YAML-owned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
