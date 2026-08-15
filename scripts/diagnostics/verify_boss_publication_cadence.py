#!/usr/bin/env python3
"""Enforce near-stock boss cadence, with one explicit ghost exception."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

from boss_geometry_contract import BOSSES

SCHEMA = "penta-boss-publication-cadence-v3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_publication_cadence.lua")
COPY = re.compile(
    r"copy=(\d+) frame=(\d+) destination=([0-9A-F]{4})"
    r"(?: ly=([0-9A-F]{2}) stat=([0-9A-F]{2}) pc=([0-9A-F]{4})"
    r"(?: caller=([0-9A-F]{4}))?)?"
)
CRYSTAL_DRAGON_TARGET = 2
DEFAULT_MAX_SLOWDOWN = 0.01
DEFAULT_CRYSTAL_MAX_SLOWDOWN = 0.05
# Ted's roughly six-frame publication interval makes a 600-frame ±1% result
# quantized by individual events: 102 vs 104 copies reported 1.29% fast, while
# the authoritative 2,800-frame window measured 484 vs 485 and 0.21% fast.
# Match its full-plane geometry horizon so one boundary event cannot decide the
# release gate. Other bosses retain the faster general-purpose window.
MIN_OBSERVATION_FRAMES_BY_TARGET = {4: 2800}


def allowed_slowdown(
    target: int,
    ordinary: float = DEFAULT_MAX_SLOWDOWN,
    crystal: float = DEFAULT_CRYSTAL_MAX_SLOWDOWN,
) -> float:
    """Return the policy limit for one boss; Crystal is the sole exception."""
    return crystal if target == CRYSTAL_DRAGON_TARGET else ordinary


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def state_for(directory: Path, target: int) -> Path:
    matches = sorted(
        path for path in directory.glob(f"boss{target}_*.ss0")
        if ".failed." not in path.name
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one state for boss {target} in {directory}, found {len(matches)}"
        )
    return matches[0]


def capture(
    rom: Path,
    state: Path,
    prefix: Path,
    target: int,
    warmup: int,
    frames: int,
    timeout: float,
) -> dict[str, object]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    source_trace = Path(str(prefix) + ".sources.bin")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    source_trace.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        BOSS_CADENCE_OUT=str(prefix),
        BOSS_CADENCE_SCENE=str(BOSSES[target].scene),
        BOSS_CADENCE_WARMUP=str(warmup),
        BOSS_CADENCE_FRAMES=str(frames),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            str(MGBA), "--fastforward", "-t", str(state),
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
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"cadence probe timed out: {prefix.name}")
    finally:
        terminate(process)

    status = marker.read_text().split()[0]
    if status not in {"ok", "scene-exit"}:
        raise RuntimeError(f"cadence probe rejected {prefix.name}: {status}")
    matches = [match for line in trace.read_text().splitlines()
               if (match := COPY.fullmatch(line))]
    copy_frames = [int(match.group(2)) for match in matches]
    if len(copy_frames) < 8:
        raise RuntimeError(f"too few publications for {prefix.name}: {len(copy_frames)}")
    source_record_size = 4 + 24 * 24
    expected_source_size = len(matches) * source_record_size
    if not source_trace.is_file() or source_trace.stat().st_size != expected_source_size:
        raise RuntimeError(
            f"source trace size for {prefix.name} is "
            f"{source_trace.stat().st_size if source_trace.is_file() else 'missing'}; "
            f"expected {expected_source_size}"
        )
    gaps = [b - a for a, b in zip(copy_frames, copy_frames[1:])]
    return {
        "status": status,
        "copies": len(copy_frames),
        "first_frame": copy_frames[0],
        "last_frame": copy_frames[-1],
        "mean_gap": statistics.fmean(gaps),
        "median_gap": statistics.median(gaps),
        "copy_start_ly_histogram": {
            f"{value:02X}": sum(
                match.group(4) is not None and int(match.group(4), 16) == value
                for match in matches
            )
            for value in sorted({
                int(match.group(4), 16) for match in matches
                if match.group(4) is not None
            })
        },
        "caller_histogram": {
            f"{value:04X}": sum(
                match.group(7) is not None and int(match.group(7), 16) == value
                for match in matches
            )
            for value in sorted({
                int(match.group(7), 16) for match in matches
                if match.group(7) is not None
            })
        },
        "state_sha256": sha256(state),
        "trace_sha256": sha256(trace),
        "source_trace_sha256": sha256(source_trace),
        "source_trace": str(source_trace.resolve()),
        "source_records": len(matches),
        "trace": str(trace.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=ROOT / "rom/Penta Dragon (J).gb")
    parser.add_argument("--dx-states", type=Path, required=True)
    parser.add_argument("--og-states", type=Path, required=True)
    parser.add_argument("--target", action="append", type=int, choices=range(9))
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument(
        "--max-slowdown",
        type=float,
        default=DEFAULT_MAX_SLOWDOWN,
        help="maximum slowdown for every ordinary boss (default: 0.01)",
    )
    parser.add_argument(
        "--crystal-max-slowdown",
        type=float,
        default=DEFAULT_CRYSTAL_MAX_SLOWDOWN,
        help=(
            "sole exception for Crystal Dragon's ghost/portal effect "
            "(default: 0.05)"
        ),
    )
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--receipt-only", action="store_true",
        help="write measured evidence and defer pass/fail to an aggregate gate",
    )
    args = parser.parse_args()

    targets = args.target or list(range(9))
    rows = []
    passed = True
    for target in targets:
        boss = BOSSES[target]
        observation_frames = max(
            args.frames, MIN_OBSERVATION_FRAMES_BY_TARGET.get(target, 0)
        )
        pair = {}
        for side, rom, states in (
            ("og", args.original.resolve(), args.og_states.resolve()),
            ("dx", args.dx_rom.resolve(), args.dx_states.resolve()),
        ):
            state: Path | None = None
            try:
                state = state_for(states, target)
                pair[side] = capture(
                    rom, state,
                    args.output.parent / "cadence" / side / boss.name,
                    target, args.warmup, observation_frames, args.timeout,
                )
            except (OSError, RuntimeError, TimeoutError) as error:
                # Receipt-only mode exists specifically so a broken candidate
                # still leaves authoritative evidence.  A dead publisher must
                # become a failed row, not abort before writing the receipt.
                if not args.receipt_only:
                    raise
                pair[side] = {
                    "status": "capture-error",
                    "error": str(error),
                    "copies": 0,
                    "state_sha256": (
                        sha256(state) if state is not None and state.is_file()
                        else None
                    ),
                    "caller_histogram": {},
                }
        maximum_slowdown = allowed_slowdown(
            target,
            ordinary=args.max_slowdown,
            crystal=args.crystal_max_slowdown,
        )
        # A large speedup is also broken cadence: it changes boss animation,
        # attack timing, and side-by-side phase just as surely as a slowdown.
        publications_live = all(
            isinstance(pair[side].get("mean_gap"), (int, float))
            and int(pair[side].get("copies", 0)) >= 8
            for side in ("og", "dx")
        )
        speed_ratio = (
            pair["og"]["mean_gap"] / pair["dx"]["mean_gap"]
            if publications_live else None
        )
        boss_pass = publications_live and (
            abs(1.0 - speed_ratio) <= maximum_slowdown + 1e-9
        )
        passed &= boss_pass
        rows.append({
            "boss": boss.name,
            "scene": f"{boss.scene:02X}",
            "status": "pass" if boss_pass else "fail",
            "maximum_slowdown_percent": maximum_slowdown * 100.0,
            "maximum_speed_deviation_percent": maximum_slowdown * 100.0,
            "observation_frames": observation_frames,
            "publication_liveness": publications_live,
            "speed_ratio": speed_ratio,
            "slowdown_percent": (
                (1.0 - speed_ratio) * 100.0 if speed_ratio is not None else None
            ),
            "og": pair["og"],
            "dx": pair["dx"],
        })
        if speed_ratio is None:
            print(f"FAIL {boss.name}: publication liveness failed")
        else:
            print(
                f"{'PASS' if boss_pass else 'FAIL'} {boss.name}: "
                f"DX/OG speed={speed_ratio:.4f}, "
                f"slowdown={(1-speed_ratio)*100:.2f}% "
                f"(absolute limit {maximum_slowdown*100:.2f}%)"
            )

    receipt = {
        "schema": SCHEMA,
        "dx_rom_sha256": sha256(args.dx_rom.resolve()),
        "original_rom_sha256": sha256(args.original.resolve()),
        "status": "pass" if passed else "fail",
        "ordinary_maximum_slowdown_percent": args.max_slowdown * 100.0,
        "crystal_dragon_maximum_slowdown_percent": (
            args.crystal_max_slowdown * 100.0
        ),
        "exception_boss": BOSSES[CRYSTAL_DRAGON_TARGET].name,
        "warmup_frames": args.warmup,
        "observation_frames": args.frames,
        "minimum_observation_frames_by_target": MIN_OBSERVATION_FRAMES_BY_TARGET,
        "bosses": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(args.output.resolve())
    return 0 if args.receipt_only or passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
