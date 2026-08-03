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

from PIL import Image

from normalize_mgba_state_pc import normalize


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATE = (
    ROOT / "save_states_for_claude" /
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
)
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_low_health_flicker.lua")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def frame_metrics(paths: list[Path]) -> dict[str, object]:
    near_white = []
    white = []
    means = []
    for path in paths:
        with Image.open(path) as source:
            image = source.convert("RGB")
            pixels = list(image.getdata())
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
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path,
                        default=Path("/tmp/penta-low-health-flicker"))
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--settle", type=int, default=120)
    parser.add_argument("--samples", type=int, default=240)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    prefix = args.output / "low-health"
    for path in args.output.glob("low-health.*"):
        path.unlink()
    normalized = args.output / "low-health-current.ss0"
    normalize(args.state.resolve(), normalized, 0x016C, [], args.rom.resolve())

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "LOW_HEALTH_OUT": str(prefix),
        "LOW_HEALTH_SETTLE": str(args.settle),
        "LOW_HEALTH_SAMPLES": str(args.samples),
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
    readable_frames = [
        row for row in frames if row.get("dma_unreadable") == "0"
    ]
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
            len(readable_frames) + len(dma_unreadable) == len(frames)
            and all(
                0xFF80 <= int(row["pc"], 16) <= 0xFF9F
                and row["dma_source"] in {"C0", "C1"}
                and row["d880"] == "FF"
                for row in dma_unreadable
            )
        ),
        "fixture stays in live Stage 1": all(
            row["d880"] == "02" and row["ffc1"] == "01"
            for row in readable_frames
        ),
        "fixture remains in low-health warning band": all(
            row["hp_main"] == "00" for row in readable_frames
        ),
        "BGP remains normal E4 at every rendered frame": all(
            row["bgp"] == "E4" for row in frames
        ),
        "no non-E4 BGP write occurs in the sampled interval": not bad_writes,
        "rotating-hazard attributes remain semantically correct": all(
            row["unexpected_mismatches"] == "0"
            for row in readable_frames
        ),
        "visible attributes never expose unsafe high bits": all(
            row["unsafe"] == "0" for row in readable_frames
        ),
        "BG CRAM is byte-stable after settling": len(cram_values) == 1,
        "no rendered near-white flash outlier": (
            metrics["near_white_max_above_median"] < 6000
            and metrics["mean_luma_max_above_median"] < 35
        ),
    }
    receipt = {
        "rom": str(args.rom.resolve()),
        "rom_sha256": digest(args.rom),
        "state": str(args.state.resolve()),
        "state_sha256": digest(args.state),
        "settle_frames": args.settle,
        "sample_frames": len(frames),
        "dma_unreadable_samples": len(dma_unreadable),
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
        f"PASS: {len(frames)} low-health frames; BGP stayed E4, "
        "BG CRAM/attributes stayed stable, and no white-flash outlier rendered."
    )
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
