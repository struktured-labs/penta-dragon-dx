#!/usr/bin/env python3
"""Gate the captured Stage 1 low-health warning path frame by frame."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import zlib

from PIL import Image, ImageChops, ImageStat

from normalize_mgba_state_pc import normalize, png_chunks, write_png


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATE = (
    ROOT / "save_states_for_claude" /
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
)
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_low_health_flicker.lua")
OAM_WRAM_SENTINEL = 0xDF51
SERIALIZED_VRAM0 = 0x400
SERIALIZED_VRAM1 = 0x2400
VRAM_MAP_BASES = (0x1800, 0x1C00)
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR = 0x281C
NEUTRAL_GAMEPLAY_BGP_ROUTINE = bytes.fromhex(
    "3E E4 E0 47 C9 3E E4 E0 47 C9 3E E4 E0 47 C9"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def normalize_fixture_attrs(state: Path, rom: Path) -> dict[str, int]:
    """Compile both legacy fixture maps through this candidate's Stage-1 LUT.

    The checked-in hazard state predates semantic attributes and serializes
    most offscreen cells as palette zero. Runtime settling repairs every tooth
    travel cell, but deliberately does not broad-sweep ordinary walls because
    that was the source of the miniboss flicker regression. Normalize only the
    test input here, then require zero semantic drift for the complete soak.
    """
    chunks = png_chunks(state.read_bytes())
    indices = [
        index for index, (kind, _) in enumerate(chunks) if kind == b"gbAs"
    ]
    if len(indices) != 1:
        raise RuntimeError(f"expected one gbAs chunk, found {len(indices)}")
    index = indices[0]
    raw = bytearray(zlib.decompress(chunks[index][1]))
    table = rom.read_bytes()[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 0x100]
    if len(table) != 0x100:
        raise RuntimeError("candidate Stage-1 LUT is incomplete")
    changed: dict[str, int] = {}
    for base in VRAM_MAP_BASES:
        tiles = raw[SERIALIZED_VRAM0 + base:SERIALIZED_VRAM0 + base + 0x400]
        tooth_positions: set[int] = set()

        def tooth(column: int, row: int) -> bool:
            tile = tiles[row * 32 + column] & 0xEF
            return 0x64 <= tile < 0x6A

        for row in range(24):
            start = width = None
            if tooth(0, row) or tooth(1, row):
                start = 0
                width = 11 if tooth(10, row) else 10 if tooth(9, row) else 9
            elif tiles[row * 32 + 4] == 0x6A:
                start, width = 5, 10
            elif tooth(4, row) or tooth(5, row):
                start, width = 4, 9
            if start is not None and width is not None:
                tooth_positions.update(row * 32 + column
                                       for column in range(start, start + width))
            elif tooth(6, row):
                tooth_positions.update(
                    row * 32 + column
                    for column in range(4, 14)
                    if tooth(column, row)
                )

        count = 0
        for offset in range(0x400):
            tile = tiles[offset]
            attr_offset = SERIALIZED_VRAM1 + base + offset
            expected = 0x0F if offset in tooth_positions else table[tile] & 0x07
            count += raw[attr_offset] != expected
            raw[attr_offset] = expected
        changed[f"{0x8000 + base:04X}"] = count
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(state, chunks)
    return changed


def frame_metrics(paths: list[Path]) -> dict[str, object]:
    near_white = []
    white = []
    means = []
    changed_pixels = []
    mean_rgb_deltas = []
    previous = None
    for path in paths:
        with Image.open(path) as source:
            image = source.convert("RGB")
            pixels = list(image.getdata())
        if previous is not None:
            difference = ImageChops.difference(image, previous)
            changed_pixels.append(sum(
                pixel != (0, 0, 0) for pixel in difference.getdata()
            ))
            mean_rgb_deltas.append(sum(ImageStat.Stat(difference).mean) / 3)
        previous = image
        near_white.append(sum(
            red >= 224 and green >= 224 and blue >= 224
            for red, green, blue in pixels
        ))
        white.append(sum(
            red >= 248 and green >= 248 and blue >= 248
            for red, green, blue in pixels
        ))
        means.append(sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3))
    median_near_white = statistics.median(near_white)
    median_mean = statistics.median(means)
    return {
        "frames": len(paths),
        "near_white_min": min(near_white),
        "near_white_median": median_near_white,
        "near_white_max": max(near_white),
        "near_white_max_above_median": max(near_white) - median_near_white,
        "white_min": min(white),
        "white_max": max(white),
        "mean_luma_min": round(min(means), 3),
        "mean_luma_median": round(median_mean, 3),
        "mean_luma_max": round(max(means), 3),
        "mean_luma_max_above_median": round(max(means) - median_mean, 3),
        "successive_changed_pixels_max": max(changed_pixels, default=0),
        "successive_changed_pixels_max_sample": (
            changed_pixels.index(max(changed_pixels)) + 2
            if changed_pixels else 0
        ),
        "successive_mean_rgb_delta_max": round(
            max(mean_rgb_deltas, default=0), 3
        ),
        "successive_mean_rgb_delta_max_sample": (
            mean_rgb_deltas.index(max(mean_rgb_deltas)) + 2
            if mean_rgb_deltas else 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "tmp/penta-low-health-flicker")
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--settle", type=int, default=120)
    parser.add_argument("--samples", type=int, default=240)
    parser.add_argument(
        "--pre-trigger", type=int, default=60,
        help=(
            "captured healthy frames before forcing the fixture across the "
            "low-health/music-warning threshold"
        ),
    )
    parser.add_argument(
        "--post-trigger-keys", type=lambda value: int(value, 0), default=0,
        help="input mask held after the deterministic health transition",
    )
    parser.add_argument(
        "--require-music-transition", action="store_true",
        help=(
            "require the Stage-1 to Gargoyle scene/song transition and its "
            "native $FFF7 pulse countdown while health is low"
        ),
    )
    parser.add_argument(
        "--require-pulse-countdown", action="store_true",
        help="also require the forced fixture to observe FFF7 count to zero",
    )
    parser.add_argument(
        "--require-hazard-attributes", action="store_true",
        help="also require every rotating-hazard tooth cell to be bank-1 art",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    rom_bytes = args.rom.read_bytes()

    args.output.mkdir(parents=True, exist_ok=True)
    prefix = args.output / "low-health"
    for path in args.output.glob("low-health.*"):
        path.unlink()
    normalized = args.output / "low-health-current.ss0"
    # Cross-ROM fixtures serialize the old candidate's executable DAxx/DBxx
    # helpers. Force the existing sentinel-gated initializer to refresh those
    # bytes from this ROM before the first atomic Stage-1 copy can use them.
    normalize(
        args.state.resolve(), normalized, 0x016C,
        [(OAM_WRAM_SENTINEL, 0), (0xDF5B, 0)],
        args.rom.resolve(),
    )
    fixture_attr_normalization = normalize_fixture_attrs(
        normalized, args.rom.resolve()
    )

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "LOW_HEALTH_OUT": str(prefix),
        "LOW_HEALTH_SETTLE": str(args.settle),
        "LOW_HEALTH_SAMPLES": str(args.samples),
        "LOW_HEALTH_PRE_TRIGGER": str(args.pre_trigger),
        "LOW_HEALTH_POST_TRIGGER_KEYS": str(args.post_trigger_keys),
    })
    log = args.output / "mgba.log"
    with log.open("w") as stream:
        completed = subprocess.run(
            [
                str(args.mgba.resolve()), "--fastforward", "-t",
                str(normalized), "--script", str(PROBE),
                str(args.rom.resolve()),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )
    marker = Path(str(prefix) + ".done")
    if completed.returncode != 0 or not marker.is_file():
        print(f"FAIL: mGBA status {completed.returncode}; see {log}")
        return 1

    frames = rows(Path(str(prefix) + ".frames.tsv"))
    writes = rows(Path(str(prefix) + ".writes.tsv"))
    screenshots = sorted(args.output.glob("low-health.frame*.png"))
    metrics = frame_metrics(screenshots)
    sampled_frame_numbers = {int(row["frame"]) for row in frames}
    sampled_writes = [
        row for row in writes if int(row["frame"]) in sampled_frame_numbers
    ]
    bad_writes = [row for row in sampled_writes if row["new"] != "E4"]
    dma_unreadable = [
        row for row in frames if row.get("dma_unreadable") == "1"
    ]
    compiler_unreadable = [
        row for row in frames if row.get("compiler_unreadable") == "1"
    ]
    readable_frames = [
        row for row in frames
        if row.get("dma_unreadable") == "0"
        and row.get("compiler_unreadable") == "0"
    ]
    pre_frames = [
        row for row in readable_frames if row["health_phase"] == "pre"
    ]
    low_frames = [
        row for row in readable_frames if row["health_phase"] == "low"
    ]
    scene_values = [row["d880"] for row in readable_frames]
    music_transition_sample = next((
        int(row["sample"]) for row in readable_frames if row["d880"] == "0A"
    ), 0)
    pulse_values = [int(row["fff7"], 16) for row in readable_frames]
    post_music_pulse_values = [
        int(row["fff7"], 16)
        for row in readable_frames
        if int(row["sample"]) >= music_transition_sample
    ] if music_transition_sample else []
    cram_values = {row["bg_cram"] for row in readable_frames}
    attr_layouts = {
        map_name: {
            row["attr_bytes"]
            for row in readable_frames
            if row["map"] == map_name
        }
        for map_name in {row["map"] for row in readable_frames}
    }
    checks = {
        "all requested consecutive frames captured": (
            len(frames) == args.samples == len(screenshots)
        ),
        "DMA-unreadable samples are exactly classified by HRAM PC/source": (
            all(
                0xFF80 <= int(row["pc"], 16) <= 0xFF9F
                and row["dma_source"] in {"C0", "C1"}
                and row["d880"] == "FF"
                for row in dma_unreadable
            )
        ),
        "private-WRAM compiler samples are exactly classified by PC/SVBK": (
            len(readable_frames) + len(dma_unreadable)
            + len(compiler_unreadable) == len(frames)
            and all(
                (
                    0x42A7 <= int(row["pc"], 16) <= 0x436D
                    or 0xD400 <= int(row["pc"], 16) <= 0xD478
                )
                for row in compiler_unreadable
            )
        ),
        "fixture stays in live Stage 1/Gargoyle gameplay": all(
            row["d880"] in (
                {"02", "0A"} if args.require_music_transition else {"02"}
            )
            and row["ffc1"] == "01"
            for row in readable_frames
        ),
        "fixture crosses the low-health warning threshold once": (
            0 < args.pre_trigger < args.samples
            and len(pre_frames) >= (
                args.pre_trigger
                - len(dma_unreadable)
                - len(compiler_unreadable)
            )
            and len(low_frames) >= (
                args.samples - args.pre_trigger
                - len(dma_unreadable)
                - len(compiler_unreadable)
            )
            and all(row["hp_main"] == "01" for row in pre_frames)
            and all(row["hp_main"] == "00" for row in low_frames)
        ),
        "BGP remains normal E4 at every rendered frame": all(
            row["bgp"] == "E4" for row in frames
        ),
        "gameplay pulse writers are statically neutralized to E4": (
            rom_bytes[
                NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR:
                NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR
                + len(NEUTRAL_GAMEPLAY_BGP_ROUTINE)
            ] == NEUTRAL_GAMEPLAY_BGP_ROUTINE
        ),
        "bank-1 bits occur only at exact Stage-1 tooth travel cells": (
            all(row["unsafe"] == "0" for row in readable_frames)
            and max(
                (int(row["approved_bank1"]) for row in readable_frames),
                default=0,
            ) > 0
        ),
        "visible non-tooth attributes never expose unsafe high bits": all(
            row["unsafe"] == "0" for row in readable_frames
        ),
        "BG CRAM is byte-stable after settling": len(cram_values) == 1,
        "no rendered near-white flash outlier": (
            metrics["near_white_max_above_median"] < 6000
            and metrics["mean_luma_max_above_median"] < 35
        ),
        "no rendered whole-background discontinuity at warning transition": (
            metrics["successive_changed_pixels_max"] < 12000
            and metrics["successive_mean_rgb_delta_max"] < 50
        ),
    }
    if args.require_music_transition:
        checks.update({
            "low-health run naturally enters the Gargoyle music scene": (
                bool(scene_values)
                and scene_values[0] == "02"
                and music_transition_sample > args.pre_trigger
                and "0A" in scene_values
            ),
            "music init and warning pulse arm while BGP stays neutral": (
                any(row["d885"] != "00" for row in readable_frames)
                and max(pulse_values, default=0) >= 0x28
                and all(row["bgp"] == "E4" for row in low_frames)
            ),
        })
    if args.require_pulse_countdown:
        checks["forced fixture observes the native pulse countdown to zero"] = (
            args.require_music_transition
            and len(set(post_music_pulse_values)) >= 40
            and max(post_music_pulse_values, default=0) >= 0x27
            and min(post_music_pulse_values, default=0xFF) == 0
        )
    if args.require_hazard_attributes:
        checks["rotating-hazard attributes remain semantically correct"] = all(
            row["unexpected_mismatches"] == "0"
            for row in readable_frames
        )
    receipt = {
        "rom": str(args.rom.resolve()),
        "rom_sha256": digest(args.rom),
        "state": str(args.state.resolve()),
        "state_sha256": digest(args.state),
        "fixture_attr_normalization": fixture_attr_normalization,
        "settle_frames": args.settle,
        "pre_trigger_frames": args.pre_trigger,
        "post_trigger_input_mask": args.post_trigger_keys,
        "music_transition_required": args.require_music_transition,
        "pulse_countdown_required": args.require_pulse_countdown,
        "hazard_attributes_required": args.require_hazard_attributes,
        "music_transition_sample": music_transition_sample,
        "native_pulse_timer_range": {
            "minimum": min(pulse_values, default=0),
            "maximum": max(pulse_values, default=0),
        },
        "healthy_samples": len(pre_frames),
        "low_health_frames": len(low_frames),
        "sample_frames": len(frames),
        "dma_unreadable_samples": len(dma_unreadable),
        "compiler_unreadable_samples": len(compiler_unreadable),
        "readable_samples": len(readable_frames),
        "bgp_writes_total": len(sampled_writes),
        "non_e4_bgp_writes": bad_writes[:32],
        "bg_cram_variants": len(cram_values),
        "visible_attr_layout_variants": {
            map_name: len(layouts)
            for map_name, layouts in sorted(attr_layouts.items())
        },
        "maximum_transitional_lut_mismatches": max(
            int(row["mismatches"]) for row in readable_frames
        ),
        "maximum_unexpected_lut_mismatches": max(
            int(row["unexpected_mismatches"])
            for row in readable_frames
        ),
        "approved_bank1_tooth_cells_visible": {
            "minimum": min(
                int(row["approved_bank1"]) for row in readable_frames
            ),
            "maximum": max(
                int(row["approved_bank1"]) for row in readable_frames
            ),
        },
        "render_metrics": metrics,
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = args.output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("FAIL: " + "; ".join(failed))
        print(f"Receipt: {receipt_path}")
        return 1
    print(
        f"PASS: crossed the warning threshold after {args.pre_trigger} healthy "
        f"frames and captured {len(low_frames)} low-health "
        "frames; BGP stayed E4, BG CRAM/attributes stayed stable, and no "
        "background-flash discontinuity rendered."
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
