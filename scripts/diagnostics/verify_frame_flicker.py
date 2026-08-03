#!/usr/bin/env python3
"""Capture and analyze every mGBA frame in the demo or Stage 1 gameplay."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

from PIL import Image, ImageChops, ImageStat

from analyze_stage1_pickup_art import TARGETS
from stage1_hazard_art import load_stage1_hazard_config


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_frame_flicker.lua")
BANK13 = 13 * 0x4000
BG0_SOURCE_ADDR = 0x6800
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000


def tile_indices(tile: bytes) -> set[int]:
    values: set[int] = set()
    for row in range(0, 16, 2):
        low, high = tile[row:row + 2]
        for bit in range(8):
            mask = 1 << bit
            values.add(
                (1 if low & mask else 0) | (2 if high & mask else 0)
            )
    return values


def reserved_pickup_art_contract(path: Path) -> bool:
    """Recognize the native-attribute pickup-art replacement contract."""
    rom = path.read_bytes()
    hazard_tiles = load_stage1_hazard_config().art_tiles
    palette = BANK13 + BG0_SOURCE_ADDR - 0x4000
    if rom[palette + 2:palette + 4] != bytes.fromhex("FF 03"):
        return False
    for tile in range(0x100):
        offset = (
            STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
            if tile < 0x80
            else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
        )
        indices = tile_indices(rom[offset:offset + 16])
        if tile in TARGETS:
            if 1 not in indices or 2 in indices:
                return False
        elif tile in hazard_tiles:
            # The rotating-spike material masks intentionally reserve index 1
            # under scene-local semantic attributes instead of the base LUT.
            continue
        elif 1 in indices:
            return False
    return len(TARGETS) == 73


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def stop_owned_process_group(process: subprocess.Popen) -> None:
    """Stop only the emulator session created by this probe."""

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


def run_probe(
    mgba: str,
    rom: Path,
    output: Path,
    mode: str,
    frames: int,
    timeout: float,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / mode
    for path in output.glob(f"{mode}.*"):
        path.unlink()
    environment = os.environ.copy()
    environment.update(
        FLICKER_OUT=str(prefix),
        FLICKER_MODE=mode,
        FLICKER_SAMPLE_FRAMES=str(frames),
        FLICKER_MAX_FRAMES="18000",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    log = output / f"{mode}.mgba.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                mgba, "--fastforward",
                "-C", f"savegamePath={output}",
                "-C", f"savestatePath={output}",
                "--script", str(PROBE), str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        marker = Path(str(prefix) + ".done")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() or process.poll() is not None:
                break
            time.sleep(0.05)
        stop_owned_process_group(process)
    if not marker.is_file():
        raise RuntimeError(f"{mode}: no completion marker; see {log}")
    status = marker.read_text().strip()
    if status != "ok":
        raise RuntimeError(f"{mode}: probe status {status}; see {log}")


def parse_oam(raw: str) -> list[dict[str, int]]:
    result = []
    if not raw:
        return result
    for item in raw.split(","):
        slot, y, x, tile, attr = item.split(":")
        result.append({
            "slot": int(slot),
            "y": int(y),
            "x": int(x),
            "tile": int(tile, 16),
            "attr": int(attr, 16),
        })
    return result


def colors(raw: str, slot: int) -> tuple[int, int, int, int]:
    data = bytes.fromhex(raw)[slot * 8:(slot + 1) * 8]
    return tuple(data[index] | (data[index + 1] << 8)
                 for index in range(0, 8, 2))


def slots(raw: str) -> list[int]:
    return [int(value) for value in raw.split(",") if value]


def all_white(palette: tuple[int, int, int, int]) -> bool:
    return all((value & 0x7FFF) == 0x7FFF for value in palette)


def image_metrics(path: Path, previous: Image.Image | None) -> dict[str, object]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        pixels = list(image.getdata())
        white = sum(r >= 248 and g >= 248 and b >= 248 for r, g, b in pixels)
        near_white = sum(r >= 224 and g >= 224 and b >= 224
                         for r, g, b in pixels)
        mean = tuple(round(value, 3) for value in ImageStat.Stat(image).mean)
        changed = 0
        delta_mean = 0.0
        if previous is not None:
            difference = ImageChops.difference(image, previous)
            changed = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
            delta_mean = round(sum(ImageStat.Stat(difference).mean) / 3, 3)
        return {
            "white_pixels": white,
            "near_white_pixels": near_white,
            "mean_rgb": mean,
            "changed_pixels": changed,
            "delta_mean": delta_mean,
            "_image": image.copy(),
        }


def red_pixel_attribution(
    path: Path,
    sprites: list[dict[str, int]],
    lcdc: int,
) -> dict[str, object]:
    """Separate warm red/magenta pixels inside OAM from background pixels."""
    sprite_height = 16 if lcdc & 0x04 else 8
    rectangles = [
        (
            sprite["x"] - 8,
            sprite["y"] - 16,
            sprite["x"],
            sprite["y"] - 16 + sprite_height,
        )
        for sprite in sprites
    ]
    inside = 0
    outside = 0
    outside_examples: list[list[int]] = []
    with Image.open(path) as source:
        image = source.convert("RGB")
        for y in range(image.height):
            for x in range(image.width):
                red, green, blue = image.getpixel((x, y))
                warm_red = (
                    red >= 96
                    and red > green * 1.30
                    and red >= blue * 0.72
                )
                if not warm_red:
                    continue
                in_oam = any(
                    left <= x < right and top <= y < bottom
                    for left, top, right, bottom in rectangles
                )
                if in_oam:
                    inside += 1
                else:
                    outside += 1
                    if len(outside_examples) < 12:
                        outside_examples.append([x, y, red, green, blue])
    return {
        "red_obj_pixels": inside,
        "red_bg_pixels": outside,
        "red_bg_examples": outside_examples,
    }


def analyze(output: Path, mode: str, rom: Path) -> dict[str, object]:
    trace = output / f"{mode}.tsv"
    rows = list(csv.DictReader(trace.open(), delimiter="\t"))
    delay_hits = int((output / f"{mode}.delay_hits").read_text().strip())
    frames: list[dict[str, object]] = []
    previous_image = None
    previous_obj: str | None = None
    previous_bg: str | None = None
    normal_bgp_run = 0
    active_palette_changes: list[dict[str, object]] = []
    all_white_active: list[dict[str, object]] = []
    active_bg_palette_changes: list[dict[str, object]] = []
    all_white_active_bg: list[dict[str, object]] = []
    lcd_off: list[int] = []
    gameplay_bgp_pulses: list[dict[str, object]] = []

    for row in rows:
        sample = int(row["sample"])
        bgp = int(row["bgp"], 16)
        normal_bgp_run = normal_bgp_run + 1 if bgp == 0xE4 else 0
        transition_phase = (
            "fade" if bgp != 0xE4
            else "steady" if normal_bgp_run >= 32
            else "recovery"
        )
        # The stock $281C effect routine used to alternate $90/$E4/$F9 every
        # eight-ish frames.  Demo sampling begins after its entry transition;
        # gameplay sampling needs 64 frames for the normal GAME START fade to
        # settle.  Bound the pulse gate before the demo's terminal fade.
        pulse_window = (
            sample <= 160 if mode == "demo"
            else 64 <= sample <= 240
        )
        if pulse_window and bgp in (0x90, 0xF9):
            gameplay_bgp_pulses.append({
                "sample": sample,
                "emulated_frame": int(row["frame"]),
                "d880": row["d880"],
                "bgp": row["bgp"],
            })
        path = output / f"{mode}.frame{sample:04d}.png"
        metrics = image_metrics(path, previous_image)
        previous_image = metrics.pop("_image")  # type: ignore[assignment]
        sprites = parse_oam(row["visible_oam"])
        red_metrics = red_pixel_attribution(
            path, sprites, int(row["lcdc"], 16)
        )
        active_slots = sorted({sprite["attr"] & 7 for sprite in sprites})
        active_bg_slots = slots(row["visible_bg_slots"])
        if not (int(row["lcdc"], 16) & 0x80):
            lcd_off.append(sample)
        for slot in active_slots:
            palette = colors(row["obj_cram"], slot)
            if all_white(palette):
                all_white_active.append({
                    "sample": sample,
                    "slot": slot,
                    "phase": transition_phase,
                })
            if previous_obj is not None:
                before = colors(previous_obj, slot)
                if before != palette:
                    active_palette_changes.append({
                        "sample": sample,
                        "slot": slot,
                        "before": [f"{value:04X}" for value in before],
                        "after": [f"{value:04X}" for value in palette],
                    })
        for slot in active_bg_slots:
            palette = colors(row["bg_cram"], slot)
            if all_white(palette):
                all_white_active_bg.append({
                    "sample": sample,
                    "slot": slot,
                    "phase": transition_phase,
                })
            if previous_bg is not None:
                before = colors(previous_bg, slot)
                if before != palette:
                    active_bg_palette_changes.append({
                        "sample": sample,
                        "slot": slot,
                        "phase": transition_phase,
                        "before": [f"{value:04X}" for value in before],
                        "after": [f"{value:04X}" for value in palette],
                    })
        frame_row = {
            "sample": sample,
            "emulated_frame": int(row["frame"]),
            "d880": row["d880"],
            "ffc1": row["ffc1"],
            "ffba": row["ffba"],
            "ffbe": row["ffbe"],
            "ffbf": row["ffbf"],
            "df4c": row["df4c"],
            "lcdc": row["lcdc"],
            "bgp": row["bgp"],
            "bgp_phase": transition_phase,
            "normal_bgp_run": normal_bgp_run,
            "bg_mismatch": int(row["bg_mismatch"]),
            "blank_bg": int(row["blank_bg"]),
            "attr_only_flips": int(row["attr_only_flips"]),
            "tile_only_changes": int(row["tile_only_changes"]),
            "bg_examples": row["bg_examples"],
            "bg_transition_examples": row["bg_transition_examples"],
            "active_obj_slots": active_slots,
            "active_bg_slots": active_bg_slots,
            **metrics,
            **red_metrics,
            "screenshot": str(path),
        }
        frames.append(frame_row)
        previous_obj = row["obj_cram"]
        previous_bg = row["bg_cram"]

    white_values = [int(frame["near_white_pixels"]) for frame in frames]
    delta_values = [float(frame["delta_mean"]) for frame in frames[1:]]
    mismatch_values = [int(frame["bg_mismatch"]) for frame in frames]
    attr_flip_values = [int(frame["attr_only_flips"]) for frame in frames]
    tile_only_values = [int(frame["tile_only_changes"]) for frame in frames]
    red_bg_values = [int(frame["red_bg_pixels"]) for frame in frames]
    red_obj_values = [int(frame["red_obj_pixels"]) for frame in frames]
    fade_frames = [frame for frame in frames if frame["bgp_phase"] == "fade"]
    recovery_frames = [
        frame for frame in frames if frame["bgp_phase"] == "recovery"
    ]
    steady_frames = [
        frame for frame in frames if frame["bgp_phase"] == "steady"
    ]
    suspicious = sorted(
        frames[1:],
        key=lambda frame: (
            int(frame["bg_mismatch"]),
            int(frame["attr_only_flips"]),
            float(frame["delta_mean"]),
            int(frame["near_white_pixels"]),
        ),
        reverse=True,
    )[:12]
    steady_active_bg_palette_changes = [
        change for change in active_bg_palette_changes
        if change["phase"] == "steady"
    ]
    steady_all_white_active_bg = [
        event for event in all_white_active_bg
        if event["phase"] == "steady"
    ]
    steady_gameplay_bg_mismatches = [
        {
            "sample": frame["sample"],
            "emulated_frame": frame["emulated_frame"],
            "lcdc": frame["lcdc"],
            "count": frame["bg_mismatch"],
            "examples": frame["bg_examples"],
        }
        for frame in frames
        if (
            mode == "gameplay"
            and 64 <= int(frame["sample"]) <= 240
            and frame["d880"] == "02"
            and frame["ffc1"] == "01"
            and int(frame["bg_mismatch"]) > 0
        )
    ]
    demo_return_sample = next(
        (
            int(frame["sample"])
            for frame in frames
            if mode == "demo" and frame["d880"] == "01"
        ),
        None,
    )
    native_pickup_art = reserved_pickup_art_contract(rom)
    failures = []
    if mode == "gameplay" and delay_hits != 0:
        failures.append(
            f"live Stage 1 entered the attract-only scanline wait "
            f"{delay_hits} times"
        )
    if mode == "demo" and (
        demo_return_sample is None
        or not 300 <= demo_return_sample <= 500
    ):
        failures.append(
            "attract miniboss reel did not return to title in the OG-parity "
            f"300..500-frame window (observed {demo_return_sample})"
        )
    if gameplay_bgp_pulses:
        failures.append(
            f"{len(gameplay_bgp_pulses)} $90/$F9 whole-BG pulse frames "
            "inside the active-play audit window"
        )
    if all_white_active:
        failures.append(
            f"{len(all_white_active)} visible all-white OBJ palette samples"
        )
    if steady_all_white_active_bg:
        failures.append(
            f"{len(steady_all_white_active_bg)} steady all-white BG "
            "palette samples"
        )
    if steady_active_bg_palette_changes:
        failures.append(
            f"{len(steady_active_bg_palette_changes)} steady active-BG "
            "palette changes"
        )
    # Position-aware pickups and animated hazards deliberately override the
    # one-dimensional C600 tile LUT. Keep mismatches in the receipt for
    # diagnosis, but gate their semantics in pickup_live_palettes and the
    # Stage-1 hazard tests; flicker correctness is expressed here by stable
    # active CRAM, normal BGP, and absence of white-palette/render outliers.

    receipt = {
        "status": "failed" if failures else "ok",
        "failures": failures,
        "rom": str(rom),
        "rom_md5": md5(rom),
        "mode": mode,
        "background_contract": (
            "native-attributes-reserved-pickup-art"
            if native_pickup_art else "semantic-position-attributes"
        ),
        "samples": len(frames),
        "demo_delay_hits": delay_hits,
        "near_white_min": min(white_values, default=0),
        "near_white_max": max(white_values, default=0),
        "delta_mean_max": max(delta_values, default=0),
        "bg_mismatch_samples": sum(value > 0 for value in mismatch_values),
        "bg_mismatch_max": max(mismatch_values, default=0),
        "attr_only_flip_samples": sum(value > 0 for value in attr_flip_values),
        "attr_only_flips": sum(attr_flip_values),
        "attr_only_flip_max": max(attr_flip_values, default=0),
        "fade_attr_only_flips": sum(
            int(frame["attr_only_flips"]) for frame in fade_frames
        ),
        "recovery_attr_only_flips": sum(
            int(frame["attr_only_flips"]) for frame in recovery_frames
        ),
        "steady_attr_only_flips": sum(
            int(frame["attr_only_flips"]) for frame in steady_frames
        ),
        "tile_only_change_samples": sum(value > 0 for value in tile_only_values),
        "tile_only_changes": sum(tile_only_values),
        "tile_only_change_max": max(tile_only_values, default=0),
        "red_bg_samples": sum(value > 0 for value in red_bg_values),
        "red_bg_pixels_max": max(red_bg_values, default=0),
        "red_obj_samples": sum(value > 0 for value in red_obj_values),
        "red_obj_pixels_max": max(red_obj_values, default=0),
        "lcd_off_samples": lcd_off,
        "active_obj_palette_changes": active_palette_changes,
        "all_white_active_obj_palettes": all_white_active,
        "active_bg_palette_changes": active_bg_palette_changes,
        "steady_active_bg_palette_changes": steady_active_bg_palette_changes,
        "all_white_active_bg_palettes": all_white_active_bg,
        "steady_all_white_active_bg_palettes": steady_all_white_active_bg,
        "steady_gameplay_bg_mismatches": steady_gameplay_bg_mismatches,
        "gameplay_bgp_pulses": gameplay_bgp_pulses,
        "demo_return_sample": demo_return_sample,
        "most_changed_frames": suspicious,
        "trace": str(trace),
    }
    (output / f"{mode}.receipt.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--mode", choices=("demo", "gameplay", "both"),
                        default="both")
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if not args.mgba:
        parser.error("mgba-qt was not found")
    rom = args.rom.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    modes = ("demo", "gameplay") if args.mode == "both" else (args.mode,)
    receipts = []
    failed = False
    try:
        for mode in modes:
            sample_frames = (
                max(args.frames, 500) if mode == "demo" else args.frames
            )
            run_probe(
                args.mgba, rom, output, mode, sample_frames, args.timeout
            )
            receipt = analyze(output, mode, rom)
            receipts.append(receipt)
            if receipt["status"] != "ok":
                failed = True
            print(
                f"{mode}: samples={receipt['samples']} "
                f"near_white={receipt['near_white_min']}.."
                f"{receipt['near_white_max']} "
                f"max_delta={receipt['delta_mean_max']} "
                f"bg_mismatch="
                f"{receipt['bg_mismatch_samples']}/{receipt['samples']} "
                f"(max {receipt['bg_mismatch_max']}) "
                f"attr_only_flips={receipt['attr_only_flips']} "
                f"tile_only_changes={receipt['tile_only_changes']} "
                f"active_palette_changes="
                f"{len(receipt['active_obj_palette_changes'])} "
                f"demo_delay_hits={receipt['demo_delay_hits']} "
                f"bgp_pulses={len(receipt['gameplay_bgp_pulses'])} "
                f"lcd_off={len(receipt['lcd_off_samples'])}"
            )
            for failure in receipt["failures"]:
                print(f"  FAIL: {failure}")
            print(f"Receipt: {output / f'{mode}.receipt.json'}")
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    manifest = {
        "status": "failed" if failed else "ok",
        "rom": str(rom),
        "rom_md5": md5(rom),
        "modes": receipts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
