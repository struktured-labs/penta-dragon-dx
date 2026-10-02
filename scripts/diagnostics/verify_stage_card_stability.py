#!/usr/bin/env python3
"""Frame-by-frame gate for level-select and STAGE-01 color stability."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from stage_card_palette_handoff import (  # noqa: E402
    TITLE_BG0_OFFSET,
    inspect_stage_card_palette_handoff,
)
PROBE = Path(__file__).with_name("probe_stage_card_stability.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
SCHEMA = "penta-stage-card-stability-v1"
MARKER = ".penta-stage-card-stability-owned"
STAGE1_BG0_OFFSET = 13 * 0x4000 + (0x6800 - 0x4000)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_owned_process_group(process: subprocess.Popen[str]) -> None:
    """Stop only the guarded emulator process created by this verifier."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def prepare_owned_directory(path: Path) -> None:
    if path.exists():
        marker = path / MARKER
        if not marker.is_file() or marker.read_text().strip() != SCHEMA:
            raise RuntimeError(f"refusing to replace unowned directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / MARKER).write_text(SCHEMA + "\n")


def parse_fields(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def image_metrics(path: Path) -> dict[str, int | float | str]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.size != (160, 144):
            raise RuntimeError(f"unexpected screenshot size {image.size}: {path}")
        pixels = list(image.getdata())
    chromatic = sum(max(pixel) - min(pixel) >= 12 for pixel in pixels)
    nonwhite = sum(pixel != (255, 255, 255) for pixel in pixels)
    return {
        "sha256": sha256(path),
        "distinct_colors": len(set(pixels)),
        "chromatic_pixels": chromatic,
        "nonwhite_pixels": nonwhite,
        "chromatic_fraction": chromatic / len(pixels),
    }


def run_route(
    rom: Path,
    output: Path,
    timeout: float,
    *,
    force_save: bool = True,
) -> tuple[dict, list[dict]]:
    prepare_owned_directory(output)
    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom.resolve(), runtime_rom)
    save_artifacts_before_launch = sorted(
        path.name for path in runtime.iterdir()
        if path.suffix in {".sav", ".ram"}
    )
    if not force_save and save_artifacts_before_launch:
        raise RuntimeError(
            "blank-SRAM route unexpectedly owns save data before launch: "
            + ", ".join(save_artifacts_before_launch)
        )
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("STAGE_CARD_"):
            env.pop(key)
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        env.pop(key, None)
    env.update(
        STAGE_CARD_OUT=str(output),
        STAGE_CARD_FORCE_SAVE="1" if force_save else "0",
        STAGE_CARD_CAPTURE_START="170",
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    command = [
        str(MGBA),
        "--fastforward",
        "-C",
        f"savegamePath={runtime}",
        "-C",
        f"savestatePath={runtime}",
        str(runtime_rom),
        "--script",
        str(PROBE),
    ]
    result_path = output / "result.txt"
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if result_path.is_file() and result_path.stat().st_size > 0:
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        stop_owned_process_group(process)
    stdout = process.stdout.read() if process.stdout is not None else ""
    (output / "emulator.log").write_text(stdout)
    if not result_path.is_file():
        raise RuntimeError(
            f"stage-card probe produced no report (exit {process.returncode}): "
            f"{stdout.rstrip()}"
        )
    result = parse_fields(result_path)
    result["blank_sram_at_launch"] = (
        "1" if not save_artifacts_before_launch else "0"
    )
    result["route_mode"] = "forced-save-selector" if force_save else "blank-sram"
    with (output / "frames.tsv").open(newline="") as handle:
        frames = list(csv.DictReader(handle, delimiter="\t"))
    for row in frames:
        screenshot = output / row["screenshot"]
        row["visual"] = image_metrics(screenshot)
    return result, frames


def frame_int(row: dict, key: str, base: int = 10) -> int:
    return int(row[key], base)


def title_exit_color_integrity(frames: list[dict]) -> dict:
    """Reject an outgoing colored title becoming a visible monochrome title.

    D880 stops identifying the title before its pixels leave the display.
    Track the actual tile geometry across that scene change instead. Uniform
    fade/blank frames are allowed, but a recognizable multicolor title must
    not become a nonuniform grayscale picture before the next map replaces it.
    This targets color loss, not timing or every possible palette mismatch.
    """
    title = [r for r in frames if r["d880"] == "01"]
    if len(title) < 2 or any(r["visual"]["chromatic_pixels"] <= 0 for r in title):
        return {"passed": False, "reason": "missing-colored-title-baseline"}
    geometries = {r["tiles"] for r in title}
    last_title = frame_int(title[-1], "frame")
    tail = [r for r in frames if frame_int(r, "frame") > last_title]
    replacement = next((r for r in tail if r["tiles"] not in geometries), None)
    if replacement is None:
        return {"passed": False, "reason": "missing-title-replacement"}
    end = frame_int(replacement, "frame")
    interval = [r for r in tail if frame_int(r, "frame") <= end]
    consecutive = [frame_int(r, "frame") for r in interval] == list(range(last_title + 1, end + 1))
    visible = [r for r in interval if r["tiles"] in geometries
               and frame_int(r, "lcdc", 16) & 0x80
               and r["visual"]["distinct_colors"] > 1]
    bad = [frame_int(r, "frame") for r in visible
           if r["visual"]["chromatic_pixels"] == 0]
    return {
        "passed": consecutive and not bad,
        "reason": "missing-transition-frame" if not consecutive else
                  ("outgoing-title-became-monochrome" if bad else "ok"),
        "last_title_scene_frame": last_title,
        "first_replacement_frame": end,
        "consecutive": consecutive,
        "visible_outgoing_title_frames": len(visible),
        "monochrome_frames": bad,
    }


def stage_card_raster_integrity(frames: list[dict], capture_dir: Path) -> dict:
    """Reject visible CHR replacement behind an unchanged STAGE tilemap.

    Use the first three identical, nonuniform complete-card rasters as the
    reference, never a late/loading frame. A global palette remap (including
    a uniform blank fade) may merge reference colors, but may not split one
    reference color into different new colors at different pixel positions.
    This checks rendered geometry, independently of unchanged tile IDs.
    """
    splash = [r for r in frames if r["d880"] == "18"]
    if not splash:
        return {"passed": False, "reason": "missing-stage-card"}
    first = frame_int(splash[0], "frame")
    early = [r for r in splash if frame_int(r, "frame") < first + 30]
    populated = max(sum(t != 0 for t in bytes.fromhex(r["tiles"])) for r in early)
    if populated == 0:
        return {"passed": False, "reason": "missing-stage-card-text"}

    def raster(row: dict) -> bytes:
        path = capture_dir / row["screenshot"]
        with Image.open(path) as source:
            if source.size != (160, 144):
                raise RuntimeError(f"unexpected stage-card raster size: {path}")
            return source.convert("RGB").tobytes()

    reference = None
    previous = None
    streak = []
    for row in early:
        if sum(t != 0 for t in bytes.fromhex(row["tiles"])) != populated:
            streak, previous = [], None
            continue
        pixels = raster(row)
        if len(set(zip(pixels[::3], pixels[1::3], pixels[2::3]))) <= 1:
            streak, previous = [], None
            continue
        key = (row["tiles"], pixels)
        contiguous = streak and frame_int(row, "frame") == frame_int(streak[-1], "frame") + 1
        streak = [*streak, row] if key == previous and contiguous else [row]
        previous = key
        if len(streak) == 3:
            reference, reference_pixels = streak[0], pixels
            break
    if reference is None:
        return {"passed": False, "reason": "missing-stable-early-card-raster"}
    start = frame_int(reference, "frame")
    replacement = next((r for r in frames if frame_int(r, "frame") > start
                        and r["d880"] == "02" and r["tiles"] != reference["tiles"]), None)
    if replacement is None:
        return {"passed": False, "reason": "missing-dungeon-replacement"}
    end = frame_int(replacement, "frame")
    interval = [r for r in frames if start <= frame_int(r, "frame") < end]
    consecutive = [frame_int(r, "frame") for r in interval] == list(range(start, end))
    reference_colors = list(zip(reference_pixels[::3], reference_pixels[1::3], reference_pixels[2::3]))
    bad, blank = [], []
    for row in interval:
        pixels = raster(row)
        colors = list(zip(pixels[::3], pixels[1::3], pixels[2::3]))
        if len(set(colors)) == 1:
            blank.append(frame_int(row, "frame"))
            continue
        mapping = {}
        conflicts = 0
        for before, after in zip(reference_colors, colors, strict=True):
            if mapping.setdefault(before, after) != after:
                conflicts += 1
        if conflicts:
            bad.append({"frame": frame_int(row, "frame"),
                        "conflicting_pixels": conflicts,
                        "tilemap_unchanged": row["tiles"] == reference["tiles"],
                        "screenshot": row["screenshot"]})
    return {"passed": consecutive and not bad,
            "reason": "missing-transition-frame" if not consecutive else
                      ("stage-card-raster-geometry-changed" if bad else "ok"),
            "reference_frame": start,
            "reference_screenshot_sha256": sha256(capture_dir / reference["screenshot"]),
            "reference_tile_hash": reference.get("tile_hash"),
            "first_dungeon_frame": end,
            "checked_frames": len(interval), "consecutive": consecutive,
            "uniform_blank_frames": blank, "unexpected_frames": bad}


def stage_card_palette_retirement(frames: list[dict], capture_dir: Path,
                                  expected_bg0: str) -> dict:
    """Require the reviewed colored card, optionally followed by terminal black.

    A palette change is not by itself proof of a safe fade. Every retired
    frame must be an actual all-black 160x144 raster, and the colored card
    must never reappear before the dungeon replaces its tilemap. The separate
    glyph oracle still checks all the preceding visible card frames.
    """
    splash = [r for r in frames if r["d880"] == "18"]
    if not splash:
        return {"passed": False, "reason": "missing-stage-card"}
    start = frame_int(splash[0], "frame")
    replacement = next((r for r in frames if frame_int(r, "frame") > start
                        and r["d880"] == "02" and r["tiles"] != splash[-1]["tiles"]), None)
    if replacement is None:
        return {"passed": False, "reason": "missing-dungeon-replacement"}
    end = frame_int(replacement, "frame")
    interval = [r for r in frames if start <= frame_int(r, "frame") < end]
    consecutive = [frame_int(r, "frame") for r in interval] == list(range(start, end))
    retired = False
    visible, blank, bad = [], [], []
    for row in interval:
        frame = frame_int(row, "frame")
        if row["bg0"] == expected_bg0 and not retired:
            visible.append(frame)
            if row["visual"]["chromatic_pixels"] == 0:
                bad.append({"frame": frame, "reason": "uncolored-visible-card"})
        elif row["bg0"] == "0000000000000000":
            retired = True
            with Image.open(capture_dir / row["screenshot"]) as source:
                black = source.size == (160, 144) and source.convert("RGB").getbbox() is None
            blank.append(frame)
            if not black:
                bad.append({"frame": frame, "reason": "blank-palette-has-visible-pixels"})
        else:
            bad.append({"frame": frame, "reason": "unexpected-palette-or-card-reappeared"})
    return {"passed": consecutive and len(visible) >= 3 and not bad,
            "consecutive": consecutive, "visible_card_frames": len(visible),
            "terminal_black_frames": blank, "unexpected_frames": bad}


PRESENTATION_KEYS = (
    "tile_hash", "attr_hash", "bg0", "bg_cram", "tiles", "attrs",
)


def presentation_signature(row: dict) -> tuple[str, ...]:
    """Bind rendered pixels to the underlying visible map and CGB palette."""
    return (
        *(str(row[key]) for key in PRESENTATION_KEYS),
        str(row.get("visual", {}).get("sha256", "")),
    )


def background_presentation_signature(row: dict) -> tuple[str, ...]:
    """Bind the visible BG while tolerating sprite and map-page cadence."""
    return tuple(str(row[key]) for key in PRESENTATION_KEYS)


def segment_uses_exact_bg0(segment: dict, expected_bg0: str) -> bool:
    """Reject a stable but wrong-color selector/STAGE-card presentation."""
    return (
        segment.get("frames", 0) > 0
        and segment.get("bg0_runs") == [{
            "first_frame": segment.get("first_frame"),
            "last_frame": segment.get("last_frame"),
            "value": expected_bg0,
        }]
    )


def pregame_frames_are_consecutive(
    frames: list[dict], first_gameplay: int,
) -> bool:
    """Prove the blank-SRAM receipt did not sample around a one-frame flash."""
    if not frames or first_gameplay < 0:
        return False
    captured = [frame_int(row, "frame") for row in frames]
    return (
        bool(captured)
        and captured[0] == 170
        and first_gameplay in captured
        and captured[-1] >= first_gameplay + 15
        and captured == list(range(captured[0], captured[-1] + 1))
    )


def stage1_entry_transition_integrity(
    frames: list[dict], first_gameplay: int,
) -> dict[str, object]:
    """Allow only a complete final STAGE card or complete Stage-1 map.

    The scene byte changes before the publisher flips the completed dungeon
    map. Start with the terminal stable STAGE-card run, include every frame
    regardless of D880/FFC1 through the first dungeon presentation, and bind
    rendered pixels, tiles, attributes, and all BG CRAM. Then require that
    same complete dungeon BG through the remaining settle tail while allowing
    sprite animation and equivalent physical-map page cadence. A one-frame
    cyan, partial-map, or stale-attribute presentation is therefore a third
    state and fails.
    """
    splash = [row for row in frames if row["d880"] == "18"]
    if not splash or first_gameplay < 0:
        return {
            "passed": False,
            "reason": "missing-splash-or-gameplay",
            "terminal_splash_run_frames": 0,
            "transition_frames": 0,
            "unexpected_frames": [],
        }
    reference = splash[-1]
    reference_signature = presentation_signature(reference)
    terminal_run = []
    expected_frame = frame_int(reference, "frame")
    for row in reversed(splash):
        if (
            frame_int(row, "frame") != expected_frame
            or presentation_signature(row) != reference_signature
        ):
            break
        terminal_run.append(row)
        expected_frame -= 1
    terminal_run.reverse()
    final = frames[-1]
    final_frame = frame_int(final, "frame")
    final_background_signature = background_presentation_signature(final)
    dungeon = next((
        row for row in frames
        if frame_int(row, "frame") > frame_int(reference, "frame")
        and row["tile_hash"] != reference["tile_hash"]
        and background_presentation_signature(row)
        == final_background_signature
        and (frame_int(row, "lcdc", 16) & 0x80) != 0
    ), None)
    if (
        dungeon is None
        or final_frame < first_gameplay
        or final["tile_hash"] == reference["tile_hash"]
        or (frame_int(final, "lcdc", 16) & 0x80) == 0
    ):
        return {
            "passed": False,
            "reason": "missing-complete-dungeon-presentation",
            "terminal_splash_run_frames": len(terminal_run),
            "transition_frames": 0,
            "unexpected_frames": [],
        }
    dungeon_signature = presentation_signature(dungeon)
    transition = [
        row for row in frames
        if frame_int(row, "frame") > frame_int(reference, "frame")
        and frame_int(row, "frame") <= frame_int(dungeon, "frame")
    ]
    unexpected = [
        row for row in transition
        if presentation_signature(row)
        not in {reference_signature, dungeon_signature}
    ]
    settled_tail = [
        row for row in frames
        if frame_int(row, "frame") > frame_int(dungeon, "frame")
    ]
    unstable_tail = [
        row for row in settled_tail
        if background_presentation_signature(row)
        != final_background_signature
        or (frame_int(row, "lcdc", 16) & 0x80) == 0
    ]
    transition_numbers = [frame_int(row, "frame") for row in transition]
    transition_consecutive = (
        bool(transition_numbers)
        and transition_numbers == list(range(
            frame_int(reference, "frame") + 1,
            frame_int(dungeon, "frame") + 1,
        ))
    )
    if len(terminal_run) < 4:
        reason = "unstable-final-splash"
    elif not transition_consecutive:
        reason = "missing-transition-frame"
    elif unexpected:
        reason = "third-presentation-state"
    elif len(settled_tail) < 4:
        reason = "short-dungeon-settle-tail"
    elif unstable_tail:
        reason = "unstable-dungeon-tail"
    else:
        reason = "ok"
    return {
        "passed": (
            len(terminal_run) >= 4
            and transition_consecutive
            and not unexpected
            and presentation_signature(transition[-1]) == dungeon_signature
            and len(settled_tail) >= 4
            and not unstable_tail
        ),
        "reason": reason,
        "terminal_splash_first_frame": frame_int(terminal_run[0], "frame"),
        "terminal_splash_last_frame": frame_int(reference, "frame"),
        "terminal_splash_run_frames": len(terminal_run),
        "first_dungeon_frame": frame_int(dungeon, "frame"),
        "transition_frames": len(transition),
        "transition_consecutive": transition_consecutive,
        "settled_tail_frames": len(settled_tail),
        "unexpected_frames": [
            {
                "frame": frame_int(row, "frame"),
                "d880": row["d880"],
                "ffc1": row["ffc1"],
                "tile_hash": row["tile_hash"],
                "attr_hash": row["attr_hash"],
                "bg0": row["bg0"],
                "visual_sha256": row.get("visual", {}).get("sha256"),
            }
            for row in unexpected[:12]
        ],
        "unstable_tail_frames": [
            {
                "frame": frame_int(row, "frame"),
                "d880": row["d880"],
                "ffc1": row["ffc1"],
                "lcdc": row["lcdc"],
                "tile_hash": row["tile_hash"],
                "attr_hash": row["attr_hash"],
                "bg0": row["bg0"],
                "visual_sha256": row.get("visual", {}).get("sha256"),
            }
            for row in unstable_tail[:12]
        ],
    }


def handoff_is_coherent(splash: list[dict], handoff: list[dict]) -> bool:
    """Accept only complete repeats of the final rendered STAGE card.

    D880 changes one callback before the alternate map becomes visible.  That
    boundary may therefore retain one *complete* final card, as stock does;
    it must never expose a card whose tile attributes are being repurposed for
    the dungeon.  Bind both the rendered pixels and their underlying visible
    map/CRAM state so a partial recolor cannot masquerade as a clean handoff.
    """
    if not splash or not handoff:
        return False
    reference = splash[-1]
    keys = ("tile_hash", "attr_hash", "bg0", "bg_cram", "tiles", "attrs")
    return all(
        row["visual"]["sha256"] == reference["visual"]["sha256"]
        and all(row[key] == reference[key] for key in keys)
        for row in handoff
    )


def first_gameplay_map_is_atomic(
    frames: list[dict], first_gameplay: int, splash_hash: str | None,
) -> bool:
    """Reject partial dungeon maps between the final card and stable play."""
    if first_gameplay < 0 or splash_hash is None:
        return False
    gameplay = [
        row for row in frames
        if frame_int(row, "frame") >= first_gameplay and row["d880"] == "02"
    ]
    dungeon = [row for row in gameplay if row["tile_hash"] != splash_hash]
    if not dungeon:
        return False
    first_tile = dungeon[0]["tile_hash"]
    first_attr = dungeon[0]["attr_hash"]
    # The probe stops shortly after gameplay appears. Every presented dungeon
    # frame in that bounded handoff must therefore be the same complete map;
    # r49's cyan flash produced three distinct tile hashes here.
    return all(
        row["tile_hash"] == first_tile and row["attr_hash"] == first_attr
        for row in dungeon
    )


def first_gameplay_map_uses_stage1_bg0(
    frames: list[dict], first_gameplay: int, splash_hash: str | None,
    expected_bg0: str,
) -> bool:
    """Reject a complete dungeon map rendered through the STAGE-card cyan."""
    if first_gameplay < 0 or splash_hash is None:
        return False
    dungeon = [
        row for row in frames
        if frame_int(row, "frame") >= first_gameplay
        and row["d880"] == "02"
        and row["tile_hash"] != splash_hash
    ]
    return bool(dungeon) and all(row["bg0"] == expected_bg0 for row in dungeon)


def summarize_frames(
    frames: list[dict], first_gameplay: int = -1,
) -> dict:
    selector_candidates = [
        row for row in frames
        if row["d880"] == "00" and row["ffc1"] == "00"
        and frame_int(row, "frame") > 220 and frame_int(row, "populated") >= 10
    ]
    # The selector is assembled over several intentionally blank/partial
    # frames. Gate the longest fully rendered tilemap identity, not those
    # construction frames; otherwise the valid black build frame looks like a
    # monochrome regression.
    selector_tile_hash = (
        Counter(row["tile_hash"] for row in selector_candidates)
        .most_common(1)[0][0]
        if selector_candidates else None
    )
    selector = [
        row for row in selector_candidates
        if row["tile_hash"] == selector_tile_hash
    ]
    splash = [row for row in frames if row["d880"] == "18"]

    def segment(rows: list[dict]) -> dict:
        bg0_runs: list[dict[str, object]] = []
        for row in rows:
            if not bg0_runs or bg0_runs[-1]["value"] != row["bg0"]:
                bg0_runs.append({
                    "first_frame": frame_int(row, "frame"),
                    "last_frame": frame_int(row, "frame"),
                    "value": row["bg0"],
                })
            else:
                bg0_runs[-1]["last_frame"] = frame_int(row, "frame")
        chromatic = [int(row["visual"]["chromatic_pixels"]) for row in rows]
        return {
            "frames": len(rows),
            "first_frame": frame_int(rows[0], "frame") if rows else -1,
            "last_frame": frame_int(rows[-1], "frame") if rows else -1,
            "nonzero_attr_frames": sum(
                frame_int(row, "nonzero_attrs") != 0 for row in rows
            ),
            "bg0_runs": bg0_runs,
            "minimum_chromatic_pixels": min(chromatic, default=-1),
            "maximum_chromatic_pixels": max(chromatic, default=-1),
            "zero_chromatic_frames": sum(value == 0 for value in chromatic),
            "tile_hash": rows[0]["tile_hash"] if rows else None,
        }

    splash_summary = segment(splash)
    handoff: list[dict] = []
    splash_hash = splash_summary["tile_hash"]
    if first_gameplay >= 0 and splash_hash is not None:
        for row in frames:
            if frame_int(row, "frame") < first_gameplay:
                continue
            if row["tile_hash"] != splash_hash:
                break
            handoff.append(row)
    return {
        "selector": segment(selector),
        "splash": splash_summary,
        "gameplay_handoff": segment(handoff),
        "gameplay_handoff_is_coherent": handoff_is_coherent(
            splash, handoff
        ),
        "first_gameplay_map_is_atomic": first_gameplay_map_is_atomic(
            frames, first_gameplay, splash_hash
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument(
        "--baseline-rom", type=Path, default=STOCK_ROM,
        help="stock ROM used for saved-game transition timing comparison",
    )
    parser.add_argument(
        "--max-stock-lag", type=int, default=10,
        help="maximum allowed first-gameplay lag versus stock, in frames",
    )
    parser.add_argument(
        "--observe",
        action="store_true",
        help="write the temporal receipt without enforcing color stability",
    )
    args = parser.parse_args()
    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.baseline_rom.is_file():
        parser.error(f"baseline ROM not found: {args.baseline_rom}")
    output = args.output.resolve()
    if ROOT not in output.parents:
        parser.error("--output must be inside the repository (normally tmp/)")

    first_result, first_frames = run_route(
        args.rom, output / "run-1", args.timeout
    )
    second_result, second_frames = run_route(
        args.rom, output / "run-2", args.timeout
    )
    baseline_result, baseline_frames = run_route(
        args.baseline_rom, output / "baseline-stock", args.timeout
    )
    blank_first_result, blank_first_frames = run_route(
        args.rom, output / "blank-sram-run-1", args.timeout,
        force_save=False,
    )
    blank_second_result, blank_second_frames = run_route(
        args.rom, output / "blank-sram-run-2", args.timeout,
        force_save=False,
    )
    first_gameplay = int(first_result.get("first_gameplay", "-1"))
    second_gameplay = int(second_result.get("first_gameplay", "-1"))
    baseline_first_gameplay = int(
        baseline_result.get("first_gameplay", "-1")
    )
    first_summary = summarize_frames(first_frames, first_gameplay)
    second_summary = summarize_frames(second_frames, second_gameplay)
    blank_first_gameplay = int(
        blank_first_result.get("first_gameplay", "-1")
    )
    blank_second_gameplay = int(
        blank_second_result.get("first_gameplay", "-1")
    )
    blank_first_summary = summarize_frames(
        blank_first_frames, blank_first_gameplay
    )
    blank_second_summary = summarize_frames(
        blank_second_frames, blank_second_gameplay
    )
    blank_first_transition = stage1_entry_transition_integrity(
        blank_first_frames, blank_first_gameplay
    )
    blank_second_transition = stage1_entry_transition_integrity(
        blank_second_frames, blank_second_gameplay
    )
    first_core = [
        {key: value for key, value in row.items() if key != "visual"}
        for row in first_frames
    ]
    second_core = [
        {key: value for key, value in row.items() if key != "visual"}
        for row in second_frames
    ]
    replay_exact = first_core == second_core
    rendered_replay_exact = [
        row["visual"]["sha256"] for row in first_frames
    ] == [
        row["visual"]["sha256"] for row in second_frames
    ]
    blank_first_core = [
        {key: value for key, value in row.items() if key != "visual"}
        for row in blank_first_frames
    ]
    blank_second_core = [
        {key: value for key, value in row.items() if key != "visual"}
        for row in blank_second_frames
    ]
    blank_replay_exact = blank_first_core == blank_second_core
    blank_rendered_replay_exact = [
        row["visual"]["sha256"] for row in blank_first_frames
    ] == [
        row["visual"]["sha256"] for row in blank_second_frames
    ]
    stock_lag = first_gameplay - baseline_first_gameplay
    rom_bytes = args.rom.read_bytes()
    expected_stage1_bg0 = rom_bytes[
        STAGE1_BG0_OFFSET:STAGE1_BG0_OFFSET + 8
    ].hex().upper()
    expected_title_bg0 = rom_bytes[
        TITLE_BG0_OFFSET:TITLE_BG0_OFFSET + 8
    ].hex().upper()
    static_handoff = inspect_stage_card_palette_handoff(rom_bytes)
    title_exits = {
        name: title_exit_color_integrity(rows)
        for name, rows in (("run_1", first_frames), ("run_2", second_frames),
                           ("blank_run_1", blank_first_frames),
                           ("blank_run_2", blank_second_frames))
    }
    stage_card_rasters = {
        name: stage_card_raster_integrity(rows, output / directory)
        for name, rows, directory in (
            ("run_1", first_frames, "run-1"),
            ("run_2", second_frames, "run-2"),
            ("blank_run_1", blank_first_frames, "blank-sram-run-1"),
            ("blank_run_2", blank_second_frames, "blank-sram-run-2"))
    }
    card_retirements = {
        name: stage_card_palette_retirement(rows, output / directory, expected_title_bg0)
        for name, rows, directory in (
            ("run_1", first_frames, "run-1"),
            ("run_2", second_frames, "run-2"),
            ("blank_run_1", blank_first_frames, "blank-sram-run-1"),
            ("blank_run_2", blank_second_frames, "blank-sram-run-2"))
    }
    checks = {
        "rendered STAGE card retires without exposing overwritten glyph graphics": all(
            result["passed"] for result in stage_card_rasters.values()
        ),
        "outgoing title never becomes a nonuniform monochrome image": all(
            result["passed"] for result in title_exits.values()
        ),
        "exact map-flip palette handoff is installed": (
            static_handoff["installed"]
        ),
        "first route completed": first_result.get("status") == "ok",
        "replay route completed": second_result.get("status") == "ok",
        "selector observed": first_result.get("saw_selector") == "1",
        "splash observed": first_result.get("saw_splash") == "1",
        "frame-state replay exact": replay_exact,
        "rendered-frame replay exact": rendered_replay_exact,
        "stock saved-game route completed": (
            baseline_result.get("status") == "ok"
        ),
        "saved-game route stays within stock timing bound": (
            first_gameplay >= 0
            and baseline_first_gameplay >= 0
            and stock_lag <= args.max_stock_lag
        ),
        "selector attributes remain palette 0": (
            first_summary["selector"]["frames"] > 0
            and first_summary["selector"]["nonzero_attr_frames"] == 0
        ),
        "splash attributes remain palette 0": (
            first_summary["splash"]["frames"] > 0
            and first_summary["splash"]["nonzero_attr_frames"] == 0
        ),
        "selector BG0 is temporally stable": (
            len(first_summary["selector"]["bg0_runs"]) == 1
        ),
        "splash keeps the reviewed colored card or a raster-verified terminal black fade": (
            card_retirements["run_1"]["passed"] and card_retirements["run_2"]["passed"]
        ),
        "selector never becomes monochrome": (
            first_summary["selector"]["zero_chromatic_frames"] == 0
        ),
        "gameplay handoff preserves only the complete final STAGE card": (
            first_summary["gameplay_handoff_is_coherent"]
        ),
        "first dungeon handoff has no partial map frames": (
            first_summary["first_gameplay_map_is_atomic"]
            and second_summary["first_gameplay_map_is_atomic"]
        ),
        "Stage-1 BG0 is resident before the first dungeon tile appears": (
            first_gameplay_map_uses_stage1_bg0(
                first_frames, first_gameplay,
                first_summary["splash"]["tile_hash"],
                expected_stage1_bg0,
            )
            and first_gameplay_map_uses_stage1_bg0(
                second_frames, int(second_result.get("first_gameplay", "-1")),
                second_summary["splash"]["tile_hash"],
                expected_stage1_bg0,
            )
        ),
        "blank-SRAM routes start without save artifacts or fixture writes": (
            blank_first_result.get("blank_sram_at_launch") == "1"
            and blank_second_result.get("blank_sram_at_launch") == "1"
            and blank_first_result.get("force_save") == "0"
            and blank_second_result.get("force_save") == "0"
            and blank_first_result.get("capture_start") == "170"
            and blank_second_result.get("capture_start") == "170"
        ),
        "blank-SRAM natural routes reach the Stage splash and gameplay": (
            blank_first_result.get("status") == "ok"
            and blank_second_result.get("status") == "ok"
            and blank_first_result.get("saw_splash") == "1"
            and blank_second_result.get("saw_splash") == "1"
        ),
        "blank-SRAM pregame captures every consecutive rendered frame": (
            pregame_frames_are_consecutive(
                blank_first_frames, blank_first_gameplay
            )
            and pregame_frames_are_consecutive(
                blank_second_frames, blank_second_gameplay
            )
        ),
        "blank-SRAM pregame frame-state and raster replay are exact": (
            blank_replay_exact and blank_rendered_replay_exact
        ),
        "blank-SRAM STAGE splash attrs remain stable through retirement": (
            blank_first_summary["splash"]["frames"] > 0
            and blank_second_summary["splash"]["frames"] > 0
            and blank_first_summary["splash"]["nonzero_attr_frames"] == 0
            and blank_second_summary["splash"]["nonzero_attr_frames"] == 0
        ),
        "blank-SRAM splash keeps the reviewed card or raster-verified terminal black": (
            card_retirements["blank_run_1"]["passed"]
            and card_retirements["blank_run_2"]["passed"]
        ),
        "blank-SRAM Stage-1 entry exposes no third purple/cyan/partial state": (
            bool(blank_first_transition["passed"])
            and bool(blank_second_transition["passed"])
        ),
        "blank-SRAM first dungeon map and attributes are atomic": (
            blank_first_summary["first_gameplay_map_is_atomic"]
            and blank_second_summary["first_gameplay_map_is_atomic"]
        ),
        "blank-SRAM Stage-1 BG0 precedes the first dungeon tile": (
            first_gameplay_map_uses_stage1_bg0(
                blank_first_frames, blank_first_gameplay,
                blank_first_summary["splash"]["tile_hash"],
                expected_stage1_bg0,
            )
            and first_gameplay_map_uses_stage1_bg0(
                blank_second_frames, blank_second_gameplay,
                blank_second_summary["splash"]["tile_hash"],
                expected_stage1_bg0,
            )
        ),
    }
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if all(checks.values()) else "fail",
        "observe_only": args.observe,
        "rom": str(args.rom.resolve()),
        "rom_sha256": sha256(args.rom),
        "checks": checks,
        "title_exit": title_exits,
        "stage_card_raster": stage_card_rasters,
        "stage_card_palette_retirement": card_retirements,
        "expected_title_bg0": expected_title_bg0,
        "expected_stage1_bg0": expected_stage1_bg0,
        "static_handoff": {
            "installed": static_handoff["installed"],
            "hook_address": f"{static_handoff['hook_address']:04X}",
            "bridge_address": f"{static_handoff['bridge_address']:04X}",
            "private_bank": 21,
            "private_entry": "4000",
            "helper_size": len(static_handoff["helper"]),
            "discriminator_index": static_handoff["discriminator_index"],
            "title_discriminator": (
                f"{static_handoff['title_discriminator']:02X}"
            ),
        },
        "run_1": first_result,
        "run_2": second_result,
        "stock_baseline": {
            "rom": str(args.baseline_rom.resolve()),
            "rom_sha256": sha256(args.baseline_rom),
            "result": baseline_result,
            "first_gameplay_lag_frames": stock_lag,
            "maximum_allowed_lag_frames": args.max_stock_lag,
            "summary": summarize_frames(
                baseline_frames, baseline_first_gameplay
            ),
        },
        "summary": first_summary,
        "replay_summary": second_summary,
        "blank_sram": {
            "route": (
                "fresh runtime; no .sav/.ram; DOWN@180, A@193, "
                "Stage-card A@300; no WRAM/SRAM fixture writes"
            ),
            "run_1": blank_first_result,
            "run_2": blank_second_result,
            "frame_state_replay_exact": blank_replay_exact,
            "rendered_replay_exact": blank_rendered_replay_exact,
            "pregame_frames_consecutive": (
                pregame_frames_are_consecutive(
                    blank_first_frames, blank_first_gameplay
                )
                and pregame_frames_are_consecutive(
                    blank_second_frames, blank_second_gameplay
                )
            ),
            "entry_transition": blank_first_transition,
            "replay_entry_transition": blank_second_transition,
            "summary": blank_first_summary,
            "replay_summary": blank_second_summary,
        },
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if args.observe:
        print("OBSERVE: temporal receipt written without enforcing failures.")
        return 0
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
