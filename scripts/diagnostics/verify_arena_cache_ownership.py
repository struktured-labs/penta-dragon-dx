#!/usr/bin/env python3
"""Fail closed on foreign writers to the relocated DF5C-DF5F arena cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from boss_geometry_contract import BOSSES  # noqa: E402
from scripts.arena_semantic_key import (  # noqa: E402
    CACHE_9C00_BASE,
    HELPER_BANK,
    HELPER_ENTRY,
    build_helper,
)

MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_arena_cache_ownership.lua")
WRITER = re.compile(
    r"writer index=(?P<index>\d+) frame=(?P<frame>\d+) "
    r"scene=(?P<scene>[0-9A-F]{2}) address=(?P<address>[0-9A-F]{4}) "
    r"bank=(?P<bank>[0-9A-F]{2}) pc=(?P<pc>[0-9A-F]{4}) "
    r"old=(?P<old>[0-9A-F]{2}) new=(?P<new>[0-9A-F]{2})"
)
COMPLETE = re.compile(
    r"complete frames=(?P<frames>\d+) scene_frames=(?P<scene_frames>\d+) "
    r"final_scene=(?P<final_scene>[0-9A-F]{2}) writes=(?P<writes>\d+)"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def capture(
    rom: Path, state: Path, prefix: Path, target: int, frames: int,
    timeout: float, helper_end: int, record: tuple[int, ...],
    expect_foreign: bool,
) -> dict[str, object]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    runtime = prefix.parent / f"{prefix.name}-runtime-{uuid.uuid4().hex}"
    runtime.mkdir(parents=True)
    env = os.environ.copy()
    env.update(
        ARENA_CACHE_OWNERSHIP_OUT=str(prefix),
        ARENA_CACHE_OWNERSHIP_FRAMES=str(frames),
        ARENA_CACHE_OWNERSHIP_SCENE=str(BOSSES[target].scene),
        ARENA_CACHE_OWNERSHIP_BASE=str(record[0]),
        ARENA_CACHE_OWNERSHIP_SIZE=str(len(record)),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen([
        str(MGBA), "--fastforward", "-t", str(state),
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        str(rom), "--script", str(PROBE),
    ], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"cache ownership timed out: {BOSSES[target].name}")
    finally:
        terminate(process)
    if marker.read_text().strip() != "ok":
        raise RuntimeError(f"cache ownership marker failed: {marker}")

    writers: list[dict[str, int]] = []
    summary = None
    for line in trace.read_text().splitlines():
        match = WRITER.fullmatch(line)
        if match:
            writers.append({
                key: int(value, 10 if key in {"index", "frame"} else 16)
                for key, value in match.groupdict().items()
            })
            continue
        match = COMPLETE.fullmatch(line)
        if match:
            summary = {
                key: int(value, 16 if key == "final_scene" else 10)
                for key, value in match.groupdict().items()
            }
    if summary is None or summary["frames"] != frames:
        raise RuntimeError(f"missing ownership completion summary: {trace}")
    foreign = [
        row for row in writers
        if row["address"] not in record
        or row["bank"] != HELPER_BANK
        or not (HELPER_ENTRY <= row["pc"] < helper_end)
    ]
    if foreign and not expect_foreign:
        raise RuntimeError(
            f"foreign cache writer for {BOSSES[target].name}: {foreign[:8]}"
        )
    origin = writers[0]["frame"] if writers else 0
    normalized = [
        {**row, "frame": row["frame"] - origin} for row in writers
    ]
    return {
        "boss": BOSSES[target].name,
        "scene": f"{BOSSES[target].scene:02X}",
        "state_sha256": sha256(state),
        "trace": str(trace.resolve()),
        "trace_sha256": sha256(trace),
        "writer_trajectory_sha256": object_sha256(normalized),
        "writer_frame_origin": origin,
        "writers": len(writers),
        "per_byte_writer_counts": {
            f"{address:04X}": sum(row["address"] == address for row in writers)
            for address in record
        },
        "foreign_writers": len(foreign),
        "foreign_writer_examples": foreign[:16],
        "observed_scene_frames": summary["scene_frames"],
        "final_scene": f"{summary['final_scene']:02X}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=650)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--replays", type=int, default=2)
    parser.add_argument("--shalamar-native-exact-class", type=int, default=4)
    parser.add_argument(
        "--record-base", type=lambda value: int(value, 0),
        default=CACHE_9C00_BASE,
    )
    parser.add_argument("--record-size", type=int, default=4)
    parser.add_argument(
        "--expect-foreign-writer", action="store_true",
        help="positive-control mode: require at least one writer outside the helper",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.replays < 2:
        parser.error("--replays must be at least 2")
    if not 0 <= args.shalamar_native_exact_class <= 15:
        parser.error("--shalamar-native-exact-class must be 0..15")
    if args.record_size < 1 or args.record_base + args.record_size > 0xE000:
        parser.error("record range must be within WRAM C000-DFFF")
    record = tuple(range(args.record_base, args.record_base + args.record_size))
    helper_end = HELPER_ENTRY + len(build_helper(
        shalamar_native_exact_class=args.shalamar_native_exact_class
    ))
    rom = args.rom.resolve()
    states = args.states.resolve()
    bosses = []
    for target in range(9):
        matches = sorted(
            path for path in states.glob(f"boss{target}_*.ss0")
            if ".failed." not in path.name and ".candidate." not in path.name
        )
        if len(matches) != 1:
            parser.error(f"expected one state for boss {target}, found {len(matches)}")
        runs = [capture(
            rom, matches[0].resolve(),
            args.output.parent / "ownership" / BOSSES[target].name / f"run-{run + 1}",
            target, args.frames, args.timeout, helper_end, record,
            args.expect_foreign_writer,
        ) for run in range(args.replays)]
        fingerprints = [run["writer_trajectory_sha256"] for run in runs]
        if len(set(fingerprints)) != 1:
            raise RuntimeError(
                f"writer replay differs for {BOSSES[target].name}: {fingerprints}"
            )
        row = dict(runs[0])
        row.update({
            "deterministic_replays": args.replays,
            "replay_writer_trajectory_sha256": fingerprints,
            "replay_trace_sha256": [run["trace_sha256"] for run in runs],
            "replay_frame_origins": [run["writer_frame_origin"] for run in runs],
        })
        bosses.append(row)
    totals = {
        f"{address:04X}": sum(
            boss["per_byte_writer_counts"][f"{address:04X}"] for boss in bosses
        )
        for address in record
    }
    if any(count == 0 for count in totals.values()):
        raise RuntimeError(f"ownership corpus missed cache bytes: {totals}")
    foreign_total = sum(boss["foreign_writers"] for boss in bosses)
    if args.expect_foreign_writer and foreign_total == 0:
        raise RuntimeError("positive control observed no foreign writer")
    receipt = {
        "schema": "penta-arena-cache-ownership-v1",
        "status": "pass",
        "rom_sha256": sha256(rom),
        "frames_per_boss": args.frames,
        "deterministic_replays": args.replays,
        "record": f"{record[0]:04X}-{record[-1]:04X}",
        "allowed_writer_bank": f"{HELPER_BANK:02X}",
        "allowed_writer_pc_range": f"{HELPER_ENTRY:04X}-{helper_end - 1:04X}",
        "per_byte_writer_counts": totals,
        "foreign_writers": foreign_total,
        "expected_foreign_writer": args.expect_foreign_writer,
        "bosses": bosses,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
