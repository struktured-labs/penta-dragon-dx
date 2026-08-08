#!/usr/bin/env python3
"""Verify later-stage semantic pickups, materials, and vetted lava overrides."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage_integrity.lua"


def parse_meta(path: Path) -> dict[str, int]:
    first_line = path.read_text().splitlines()[0]
    values: dict[str, int] = {}
    hex_keys = {
        "expected_scene", "D880", "FFC1", "FF91", "DF02", "DF0D", "FFBA",
        "LCDC", "SCX", "SCY", "active_map",
    }
    for key, raw in re.findall(r"([A-Za-z0-9_]+)=([0-9A-Fa-f]+)", first_line):
        values[key] = int(raw, 16 if key in hex_keys else 10)
    return values


def capture(mgba: str, rom: Path, target: int, prefix: Path, timeout: float) -> None:
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE_TARGET": str(target),
        "STAGE_OUT": str(prefix),
        "STAGE_SHOT": "0",
    })
    proc = subprocess.Popen(
        [mgba, "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    meta = prefix.with_suffix(".meta")
    try:
        while time.monotonic() < deadline:
            if meta.exists() and meta.stat().st_size:
                return
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"stage {target + 1} capture timed out")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def visible_cells(prefix: Path, meta: dict[str, int]) -> list[tuple[int, int]]:
    attrs = prefix.with_suffix(".attr.bin").read_bytes()
    tiles = prefix.with_suffix(".map0.bin").read_bytes()
    offset = 0x400 if meta["active_map"] == 0x9C00 else 0
    first_col, first_row = meta["SCX"] // 8, meta["SCY"] // 8
    cols = 20 if meta["SCX"] & 7 == 0 else 21
    rows = 18 if meta["SCY"] & 7 == 0 else 19
    indexes = [
        offset
        + ((first_row + row) & 31) * 32
        + ((first_col + col) & 31)
        for row in range(rows)
        for col in range(cols)
    ]
    return [(tiles[index], attrs[index]) for index in indexes]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-headless-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=7.0)
    parser.add_argument("--require-semantic-pickups", action="store_true")
    parser.add_argument(
        "--stages", default="2,3,4,5,6,7",
        help="comma-separated stage numbers to capture (default: 2..7)",
    )
    args = parser.parse_args()
    try:
        stages = [int(value) for value in args.stages.split(",") if value]
    except ValueError:
        parser.error("--stages must be a comma-separated list of integers")
    if not stages or any(stage < 2 or stage > 7 for stage in stages):
        parser.error("--stages entries must be between 2 and 7")

    failures: list[str] = []
    # Only corpus-proven semantic pickups/materials plus the separately audited
    # Stage 5/7 lava IDs may be nonzero.
    health_pickups = {
        0x88: 1, 0x89: 1, 0x96: 1, 0x98: 1, 0x99: 1,
    }
    rare_pickups = {
        0xAE: 2, 0xAF: 2, 0xBE: 2, 0xBF: 2,
        0xC6: 2, 0xC7: 2, 0xD6: 2, 0xD7: 2,
    }
    arrow_pickups = {
        0xA0: 4, 0xA1: 4, 0xB0: 4, 0xB1: 4,
    }
    semantic_by_target = {
        1: rare_pickups,
        2: health_pickups,
        3: {},
        4: health_pickups | rare_pickups,
        5: health_pickups,
        6: arrow_pickups | rare_pickups,
    }
    material_by_target = {
        # Stage 4: diamond floor, then the thin bridge/platform accent.
        3: {
            **{tile: 4 for tile in range(0x01, 0x09)},
            0x2D: 2,
            0x2E: 2,
        },
    }
    lava_tiles = {
        4: {0x02, 0x03, 0x04, 0x05, 0x12, 0x13, 0x14, 0x15},
        6: {0x19, 0x1A},
    }

    semantic_seen = 0
    with tempfile.TemporaryDirectory(prefix="penta-stage-integrity-") as temp:
        temp_path = Path(temp)
        for target, stage_semantic in semantic_by_target.items():
            if target + 1 not in stages:
                continue
            stage_material = material_by_target.get(target, {})
            stage_expected = stage_semantic | stage_material
            allowed = {0, *stage_expected.values()}
            if target in lava_tiles:
                allowed.add(5)
            prefix = temp_path / f"stage{target + 1}"
            try:
                capture(args.mgba, args.rom.resolve(), target, prefix, args.timeout)
                meta = parse_meta(prefix.with_suffix(".meta"))
                cells = visible_cells(prefix, meta)
                attrs = [attr for _, attr in cells]
                all_attrs = prefix.with_suffix(".attr.bin").read_bytes()
                all_tiles = prefix.with_suffix(".map0.bin").read_bytes()
                lut = prefix.with_suffix(".bg-lut.bin").read_bytes()
            except Exception as exc:
                failures.append(str(exc))
                continue

            counts = {value: attrs.count(value) for value in sorted(set(attrs))}
            bad = sorted(value for value in counts if value not in allowed)
            unsafe = sum(1 for value in attrs if value & 0xF8)
            semantic_cells = [
                (tile, attr, stage_semantic[tile])
                for tile, attr in cells if tile in stage_semantic
            ]
            semantic_seen += len(semantic_cells)
            pickup_mismatches = sum(
                attr != wanted for _, attr, wanted in semantic_cells
            )
            material_cells = [
                (tile, attr, stage_material[tile])
                for tile, attr in cells if tile in stage_material
            ]
            material_mismatches = sum(
                attr != wanted for _, attr, wanted in material_cells
            )
            containment_mismatches = sum(
                attr in {1, 2, 4} and stage_expected.get(tile) != attr
                for tile, attr in cells
            )
            expected_lut = {
                tile: palette for tile, palette in stage_expected.items()
            }
            expected_lut.update({tile: 5 for tile in lava_tiles.get(target, set())})
            lut_mismatches = sum(
                value != expected_lut.get(tile, 0)
                for tile, value in enumerate(lut)
            )
            lava_count = sum(value == 5 for value in all_attrs)
            lava_mismatches = sum(
                attr == 5 and tile not in lava_tiles.get(target, set())
                for attr, tile in zip(all_attrs, all_tiles)
            )
            if meta.get("D880") != target + 2:
                failures.append(
                    f"stage {target + 1}: D880={meta.get('D880')} expected {target + 2}"
                )
            if bad:
                failures.append(f"stage {target + 1}: unexpected attrs {bad}")
            if unsafe:
                failures.append(f"stage {target + 1}: {unsafe} unsafe attribute bytes")
            if pickup_mismatches or material_mismatches or containment_mismatches:
                failures.append(
                    f"stage {target + 1}: semantic pickup mismatch="
                    f"{pickup_mismatches} material={material_mismatches} "
                    f"containment={containment_mismatches}"
                )
            if lut_mismatches:
                failures.append(
                    f"stage {target + 1}: {lut_mismatches} semantic LUT mismatches"
                )
            if 5 in allowed and lava_count == 0:
                failures.append(f"stage {target + 1}: audited lava palette is absent")
            if lava_mismatches:
                failures.append(
                    f"stage {target + 1}: {lava_mismatches} lava attrs map to non-lava tiles"
                )
            print(
                f"Stage {target + 1}: attrs={counts} "
                f"ff91={meta.get('FF91', -1):02X} "
                f"df0d={meta.get('DF0D', -1):02X} unsafe={unsafe} "
                f"lava={lava_count} lava_mismatch={lava_mismatches} "
                f"pickup_expected={len(semantic_cells)} "
                f"pickup_mismatch={pickup_mismatches} "
                f"material_expected={len(material_cells)} "
                f"material_mismatch={material_mismatches} "
                f"containment={containment_mismatches} "
                f"lut_mismatch={lut_mismatches} df02={meta.get('DF02', -1):02X}"
            )

    if args.require_semantic_pickups and semantic_seen == 0:
        failures.append("no collision-audited later-stage pickup tile was observed")

    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "\nPASS: later stages contain only audited semantic pickups, "
        "materials, and Stage 5/7 lava."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
