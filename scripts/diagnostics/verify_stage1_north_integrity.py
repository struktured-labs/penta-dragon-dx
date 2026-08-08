#!/usr/bin/env python3
"""Compare the natural Stage-1 north room with the untouched Japanese ROM."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_north_integrity.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_BASELINE = ROOT / "rom/Penta Dragon (J).gb"


def stop_owned_process_group(process: subprocess.Popen[str]) -> None:
    """Stop only the guarded mGBA session created by this route."""

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


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def run_route(
    rom: Path,
    output: Path,
    frames: int,
    play_frames: int,
    timeout: float,
    target_camera: int | None,
    target_room: int,
    target_settle: int,
    snap_interval: int,
    fire: bool,
    trace: Path | None,
    trace_writes: bool,
    via_opening: bool = False,
) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    runtime_rom = runtime / "route.gb"
    (runtime / "route.sav").unlink(missing_ok=True)
    (runtime / "route.gb.ram").unlink(missing_ok=True)
    shutil.copy2(rom.resolve(), runtime_rom)
    env = os.environ.copy()
    env.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        STAGE1_NORTH_OUT=str(output),
        STAGE1_NORTH_FRAMES=str(frames),
        STAGE1_NORTH_PLAY_FRAMES=str(play_frames),
        STAGE1_NORTH_TARGET_ROOM=str(target_room),
        STAGE1_NORTH_TARGET_SETTLE=str(target_settle),
        STAGE1_NORTH_SNAP_INTERVAL=str(snap_interval),
        STAGE1_NORTH_VIA_OPENING="1" if via_opening else "0",
    )
    if target_camera is not None:
        env["STAGE1_NORTH_TARGET_CAMERA"] = str(target_camera)
    if fire:
        env["STAGE1_NORTH_FIRE"] = "1"
    if trace is not None:
        env["STAGE1_NORTH_TRACE_FILE"] = str(trace.resolve())
    if trace_writes:
        env["STAGE1_NORTH_TRACE_WRITES"] = "1"
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
    report_path = output / "probe.txt"
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
            if report_path.is_file() and report_path.stat().st_size > 0:
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        stop_owned_process_group(process)
    stdout = process.stdout.read() if process.stdout is not None else ""
    if not report_path.is_file():
        raise RuntimeError(
            f"route produced no report (exit {process.returncode}): "
            f"{stdout.rstrip()}"
        )
    report = parse_report(report_path)
    if report.get("status") != "ok":
        raise RuntimeError(
            f"route did not reach the first north room: {report}"
        )
    return report


def byte_diff(left: bytes, right: bytes) -> tuple[int, int]:
    offsets = [
        offset
        for offset, (a, b) in enumerate(zip(left, right, strict=True))
        if a != b
    ]
    return len(offsets), offsets[0] if offsets else -1


def compare_visible_terrain(
    candidate: bytes,
    baseline: bytes,
    *,
    width: int = 24,
    rows: int = 16,
    seam_columns: int = 2,
    max_phase: int = 4,
) -> dict[str, object]:
    """Compare the gameplay rows after accounting for the native X ring.

    C1A0 is a 24x24 circular packed map, not a fixed room image. Enemy
    contact can deflect Sara horizontally even under identical UP input, so
    the same world terrain can be published at a different two-column ring
    phase. Compare every mutually visible cell at the best bounded phase,
    while independently requiring the newly exposed wall seam to be stable
    and nonblank. The bottom eight rows are outside the 16-tile gameplay
    viewport (HUD/off-screen scratch) and are retained in the raw receipt but
    are not terrain.
    """
    usable_end = width - seam_columns
    options: list[dict[str, object]] = []
    for phase in range(-max_phase, max_phase + 1):
        if phase >= 0:
            baseline_start = phase
            candidate_start = 0
            length = usable_end - phase
        else:
            baseline_start = 0
            candidate_start = -phase
            length = usable_end + phase
        differences = 0
        first_difference = -1
        for row in range(rows):
            baseline_offset = row * width + baseline_start
            candidate_offset = row * width + candidate_start
            for column in range(length):
                if (
                    baseline[baseline_offset + column]
                    == candidate[candidate_offset + column]
                ):
                    continue
                differences += 1
                if first_difference < 0:
                    first_difference = row * width + candidate_start + column
        options.append(
            {
                "phase_columns": phase,
                "compared_bytes": rows * length,
                "differences": differences,
                "first_candidate_difference": first_difference,
            }
        )
    best = min(
        options,
        key=lambda row: (int(row["differences"]), -int(row["compared_bytes"])),
    )
    phase = int(best["phase_columns"])
    if phase > 0:
        baseline_edges = {
            baseline[row * width:row * width + phase].hex()
            for row in range(rows)
        }
        candidate_edges = {
            candidate[
                row * width + usable_end - phase:row * width + usable_end
            ].hex()
            for row in range(rows)
        }
    elif phase < 0:
        edge_width = -phase
        baseline_edges = {
            baseline[
                row * width + usable_end - edge_width:row * width + usable_end
            ].hex()
            for row in range(rows)
        }
        candidate_edges = {
            candidate[row * width:row * width + edge_width].hex()
            for row in range(rows)
        }
    else:
        baseline_edges = set()
        candidate_edges = set()
    padding_rows = {
        (
            baseline[row * width + usable_end:(row + 1) * width].hex(),
            candidate[row * width + usable_end:(row + 1) * width].hex(),
        )
        for row in range(rows)
    }
    edge_values = bytes.fromhex("".join(sorted(baseline_edges | candidate_edges)))
    best.update(
        {
            "width": width,
            "rows": rows,
            "seam_columns": seam_columns,
            "max_phase_columns": max_phase,
            "baseline_edge_signatures": sorted(baseline_edges),
            "candidate_edge_signatures": sorted(candidate_edges),
            "edge_signatures_stable": (
                len(baseline_edges) <= 1 and len(candidate_edges) <= 1
            ),
            "edge_signatures_nonblank": (
                phase == 0 or bool(edge_values) and all(edge_values)
            ),
            "padding_signatures": sorted(
                f"{left}/{right}" for left, right in padding_rows
            ),
            "padding_stable_and_equal": (
                len(padding_rows) == 1
                and next(iter(padding_rows))[0] == next(iter(padding_rows))[1]
            ),
        }
    )
    return best


def optional_camera(value: str) -> int | None:
    if value.lower() == "none":
        return None
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--play-frames", type=int, default=240)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--target-camera",
        type=optional_camera,
        default=0x03A4,
        help="stop when DC03:DC02 reaches this value in the target room",
    )
    parser.add_argument("--target-room", type=lambda value: int(value, 0), default=1)
    parser.add_argument("--target-settle", type=int, default=8)
    parser.add_argument("--snap-interval", type=int, default=0)
    parser.add_argument(
        "--fire",
        action="store_true",
        help="hold A while walking north, matching ordinary armed play",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="replay recorded JSONL controller keys instead of generated input",
    )
    parser.add_argument(
        "--trace-writes",
        action="store_true",
        help="record C1A0-C1CF writes near the first failing north boundary",
    )
    parser.add_argument(
        "--dynamic-prefix",
        type=int,
        default=0,
        help="allow differences only in this off-screen C1A0 prefix",
    )
    parser.add_argument(
        "--max-frame-lag",
        type=int,
        help="maximum candidate gameplay-frame lag at the target coordinate",
    )
    parser.add_argument(
        "--max-frame-lag-ratio",
        type=float,
        help=(
            "maximum lag as a fraction of the untouched ROM's gameplay "
            "frames at the target coordinate"
        ),
    )
    args = parser.parse_args()
    if not 0 <= args.dynamic_prefix <= 0x240:
        parser.error("--dynamic-prefix must be between 0 and 576")
    if args.max_frame_lag is not None and args.max_frame_lag < 0:
        parser.error("--max-frame-lag cannot be negative")
    if (
        args.max_frame_lag_ratio is not None
        and not 0 <= args.max_frame_lag_ratio < 1
    ):
        parser.error("--max-frame-lag-ratio must be in [0, 1)")
    if (
        args.max_frame_lag is not None
        and args.max_frame_lag_ratio is not None
    ):
        parser.error(
            "--max-frame-lag and --max-frame-lag-ratio are mutually exclusive"
        )

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    baseline_report = run_route(
        args.baseline,
        output / "baseline",
        args.frames,
        args.play_frames,
        args.timeout,
        args.target_camera,
        args.target_room,
        args.target_settle,
        args.snap_interval,
        args.fire,
        args.trace,
        args.trace_writes,
        False,
    )
    candidate_report = run_route(
        args.rom,
        output / "candidate",
        args.frames,
        args.play_frames,
        args.timeout,
        args.target_camera,
        args.target_room,
        args.target_settle,
        args.snap_interval,
        args.fire,
        args.trace,
        args.trace_writes,
        False,
    )

    baseline_room = (output / "baseline/c1a0.bin").read_bytes()
    candidate_room = (output / "candidate/c1a0.bin").read_bytes()
    differences, first_difference = byte_diff(candidate_room, baseline_room)
    terrain = compare_visible_terrain(candidate_room, baseline_room)
    terrain_differences = int(terrain["differences"])
    first_terrain_difference = int(terrain["first_candidate_difference"])
    gameplay_frame_lag = (
        int(candidate_report["gameplay_frames"])
        - int(baseline_report["gameplay_frames"])
    )
    max_frame_lag = args.max_frame_lag
    if args.max_frame_lag_ratio is not None:
        max_frame_lag = math.floor(
            int(baseline_report["gameplay_frames"])
            * args.max_frame_lag_ratio
        )
    lag_ok = (
        max_frame_lag is None
        or abs(gameplay_frame_lag) <= max_frame_lag
    )
    terrain_ok = (
        terrain_differences == 0
        and bool(terrain["edge_signatures_stable"])
        and bool(terrain["edge_signatures_nonblank"])
        and bool(terrain["padding_stable_and_equal"])
    )
    receipt = {
        "status": "pass" if terrain_ok and lag_ok else "fail",
        "candidate_rom": str(args.rom.resolve()),
        "candidate_sha256": digest(args.rom),
        "baseline_rom": str(args.baseline.resolve()),
        "baseline_sha256": digest(args.baseline),
        "input_route": (
            f"cold GAME START; recorded controller trace {args.trace}; "
            "no gameplay memory writes"
            if args.trace is not None
            else (
                "cold GAME START; hold UP+A; no gameplay memory writes"
                if args.fire
                else "cold GAME START; hold UP; no gameplay memory writes"
            )
        ),
        "gameplay_frames": args.play_frames,
        "target_camera": args.target_camera,
        "target_room": args.target_room,
        "target_settle_frames": args.target_settle,
        "candidate": candidate_report,
        "baseline": baseline_report,
        "packed_room_bytes": len(candidate_room),
        "packed_room_differences": differences,
        "first_difference": first_difference,
        "dynamic_prefix_bytes": args.dynamic_prefix,
        "terrain_differences": terrain_differences,
        "first_terrain_difference": first_terrain_difference,
        "visible_terrain_overlap": terrain,
        "gameplay_frame_lag": gameplay_frame_lag,
        "max_frame_lag": max_frame_lag,
        "max_frame_lag_ratio": args.max_frame_lag_ratio,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if not terrain_ok:
        print(
            "FAIL: natural north room differs from the untouched ROM at "
            f"{terrain_differences}/{terrain['compared_bytes']} "
            "mutually visible terrain bytes; first candidate offset "
            f"0x{first_terrain_difference:03X}"
        )
        return 1
    if not lag_ok:
        print(
            "FAIL: candidate reached the target "
            f"{gameplay_frame_lag:+d} gameplay frames from stock; allowed "
            f"±{max_frame_lag}"
        )
        return 1
    print(
        "PASS: recorded north route reached stock-matching terrain "
        f"({terrain['compared_bytes']} exact bytes at ring phase "
        f"{terrain['phase_columns']:+d}) with "
        f"{gameplay_frame_lag:+d}-frame timing delta."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
