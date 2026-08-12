#!/usr/bin/env python3
"""Capture comparable animated receipts for all nine boss arenas.

The input states must already belong to the candidate ROM (or have been
machine-preservingly retargeted with ``normalize_mgba_state_pc.py``).  This
driver deliberately disables the receipt probe's scene rearm: changing the
scene cache after loading a live boss state restarts arena setup and can turn a
valid cross-build comparison into synthetic corruption.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageDraw

from boss_geometry_contract import BOSSES


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_boss_state_receipt.lua"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
def report_fields(path: Path) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in path.read_text().split()
        if "=" in field
    )


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def capture(
    mgba: Path,
    rom: Path,
    state: Path,
    prefix: Path,
    target: int,
    frames: int,
    timeout: float,
    rearm_palettes: bool,
) -> dict[str, str]:
    marker = Path(f"{prefix}.audit.done")
    for suffix in (
        ".audit.done", ".audit.report", ".audit.trace", ".map0.bin",
        ".vram0.bin", ".attr.bin", ".source.bin", ".png",
    ):
        Path(f"{prefix}{suffix}").unlink(missing_ok=True)
    for fraction in (frames // 4, frames // 2, frames * 3 // 4):
        Path(f"{prefix}.f{fraction:03d}.png").unlink(missing_ok=True)

    env = os.environ.copy()
    env.update({
        "BOSS_RECEIPT_OUT": str(prefix),
        "BOSS_RECEIPT_FRAMES": str(frames),
        "BOSS_RECEIPT_REARM": "0",
        "BOSS_RECEIPT_PALETTE_REARM": "1" if rearm_palettes else "0",
        "BOSS_RECEIPT_KEEPALIVE": "1",
        "BOSS_TARGET": str(target),
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
    })
    process = subprocess.Popen(
        [
            str(mgba), "-t", str(state),
            "-C", f"savegamePath={prefix.parent}",
            "-C", f"savestatePath={prefix.parent}",
            str(rom), "--script", str(PROBE),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text().strip():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"boss {target}: mGBA exited {process.returncode}"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"boss {target}: capture timed out")
    finally:
        terminate(process)

    if marker.read_text().strip() != "ok":
        raise RuntimeError(f"boss {target}: capture probe rejected state")
    return report_fields(Path(f"{prefix}.audit.report"))


def staging_violations(
    prefix: Path,
    lcdc: int,
    neutral_rectangles: tuple[tuple[int, int, int, int], ...],
    neutral_tile_ids: frozenset[int],
) -> tuple[int, list[str]]:
    """Check stock-clear lower fields in the final active physical map."""
    if not neutral_rectangles:
        return 0, []
    maps = Path(f"{prefix}.map0.bin").read_bytes()
    if len(maps) != 0x800:
        raise ValueError(f"{prefix}: expected $800 tilemap bytes, got {len(maps)}")
    offset = 0x400 if lcdc & 0x08 else 0
    examples: list[str] = []
    violations = 0
    visited: set[tuple[int, int]] = set()
    for row_start, row_stop, col_start, col_stop in neutral_rectangles:
        for row in range(row_start, row_stop):
            for col in range(col_start, col_stop):
                if (row, col) in visited:
                    continue
                visited.add((row, col))
                tile = maps[offset + row * 32 + col]
                if tile not in neutral_tile_ids:
                    violations += 1
                    if len(examples) < 12:
                        examples.append(f"r{row}c{col}:${tile:02X}")
    return violations, examples


def build_contact_sheet(output: Path, frames: int) -> Path:
    sample_paths: list[tuple[str, str, Path]] = []
    for index, boss in enumerate(BOSSES):
        prefix = output / f"boss{index}_{boss.name}"
        for frame in (frames // 4, frames // 2, frames * 3 // 4, frames):
            suffix = f".f{frame:03d}.png" if frame != frames else ".png"
            sample_paths.append((boss.name, boss.material, Path(f"{prefix}{suffix}")))

    tile_width, tile_height = 160, 144
    label_height = 28
    sheet = Image.new("RGB", (tile_width * 4, (tile_height + label_height) * 9))
    draw = ImageDraw.Draw(sheet)
    for sample_index, (name, material, path) in enumerate(sample_paths):
        row, col = divmod(sample_index, 4)
        x, y = col * tile_width, row * (tile_height + label_height)
        with Image.open(path) as source:
            sheet.paste(source.convert("RGB"), (x, y))
        draw.rectangle((x, y + tile_height, x + tile_width, y + tile_height + label_height), fill="black")
        if col == 0:
            draw.text((x + 3, y + tile_height + 2), name, fill="white")
            draw.text((x + 3, y + tile_height + 14), material, fill=(180, 220, 255))
        else:
            draw.text((x + 3, y + tile_height + 8), f"phase {col + 1}/4", fill="white")
    destination = output / "all-boss-material-phases.png"
    sheet.save(destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--rearm-palettes",
        action="store_true",
        help=(
            "diagnostically rerun the full DX CRAM pass; ordinary candidate "
            "states are already phase-settled and preserve their palette state"
        ),
    )
    parser.add_argument(
        "--require-clean-staging",
        action="store_true",
        help="fail when a boss violates a defined stock-clear tile region",
    )
    parser.add_argument(
        "--reuse-captures",
        action="store_true",
        help="rebuild/audit an existing output directory without mGBA",
    )
    args = parser.parse_args()

    rom, states = args.rom.resolve(), args.states.resolve()
    output, mgba = args.output.resolve(), args.mgba.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipts: list[dict[str, object]] = []
    for target, boss in enumerate(BOSSES):
        name, material = boss.name, boss.material
        state = states / f"boss{target}_{name}.ss0"
        if not state.is_file():
            raise FileNotFoundError(state)
        prefix = output / f"boss{target}_{name}"
        if args.reuse_captures:
            report_path = Path(f"{prefix}.audit.report")
            if not report_path.is_file():
                raise FileNotFoundError(report_path)
            fields = report_fields(report_path)
        else:
            fields = capture(
                mgba, rom, state, prefix, target, args.frames, args.timeout,
                args.rearm_palettes,
            )
        lcdc = int(fields.get("lcdc", "0"), 16)
        violation_count, violation_examples = staging_violations(
            prefix,
            lcdc,
            boss.neutral_rectangles,
            boss.neutral_tile_ids,
        )
        crystal_cached = name == "crystal_dragon"
        receipts.append({
            "boss": name,
            "expected_material": material,
            "contract_kind": (
                "cached-atomic-camera-wrap" if crystal_cached else "tile-lut"
            ),
            "scene": fields.get("d880"),
            "attribute_samples": int(fields.get("attr_samples", "0")),
            # Crystal's animated portal deliberately moves tile IDs through a
            # cached material lattice. Its semantic contract lives in
            # verify_boss_geometry.py; expose raw disagreements here without
            # mislabeling them as geometry corruption.
            "tile_geometry_mismatches": (
                None
                if crystal_cached
                else int(fields.get("attr_mismatches", "0"))
            ),
            "raw_tile_lut_mismatches": int(
                fields.get("raw_lut_mismatches", "0")
            ),
            "alternating_tile_ids": int(fields.get("alternating_tiles", "0")),
            "staging_tile_violations": violation_count,
            "staging_violation_examples": violation_examples,
            "image": str(prefix.with_suffix(".png")),
        })
        geometry_label = (
            "n/a(cached-portal)"
            if crystal_cached else fields.get("attr_mismatches")
        )
        print(
            f"CAPTURE {target}: {name:15s} material={material:10s} "
            f"geometry_mismatches={geometry_label} "
            f"raw_lut_mismatches={fields.get('raw_lut_mismatches')} "
            f"staging_violations={violation_count}"
        )

    blockers = {
        receipt["boss"]: receipt["staging_tile_violations"]
        for receipt in receipts
        if receipt["staging_tile_violations"]
    }
    report = {
        "boss_count": len(BOSSES),
        "phases_per_boss": 4,
        "visual_review_required": True,
        "publishable": not blockers,
        "note": "Screenshots are evidence for review, not an automatic pass.",
        "bosses": receipts,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.require_clean_staging and blockers:
        (output / "all-boss-material-phases.png").unlink(missing_ok=True)
        print(f"FAIL: stock-clear staging blockers: {blockers}")
        return 1
    gallery = build_contact_sheet(output, args.frames)
    print(f"gallery: {gallery}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
