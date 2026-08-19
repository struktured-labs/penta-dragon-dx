#!/usr/bin/env python3
"""Measure repeated boss palette planes at the native map-copy entry."""

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

SHARED_CACHE_TARGETS = (0, 1, 3, 5, 6, 7, 8)

MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_semantic_cadence.lua")
LINE = re.compile(
    r"copy=(?P<copy>\d+) frame=(?P<frame>\d+) "
    r"destination=(?P<destination>[0-9A-F]{4}) "
    r"changed_cells=(?P<changed>\d+) repeat=(?P<repeat>[01]) "
    r"tile_changed_cells=(?P<tile_changed>\d+) "
    r"tile_repeat=(?P<tile_repeat>[01]) "
    r"sum_a=(?P<sum_a>[0-9A-F]{2}) sum_b=(?P<sum_b>[0-9A-F]{2}) "
    r"raw_sig=(?P<raw_sig>[0-9A-F]{2}) "
    r"cache_raw=(?P<cache_raw>[0-9A-F]{2}) "
    r"cache_sum_b=(?P<cache_sum_b>[0-9A-F]{2}) "
    r"cache_scene=(?P<cache_scene>[0-9A-F]{2}) "
    r"cache_sum_a=(?P<cache_sum_a>[0-9A-F]{2}) "
    r"hit=(?P<hit>[01]) raw_hit=(?P<raw_hit>[01]) "
    r"guarded=(?P<guarded>[01])"
)
CACHE_WRITER_LINE = re.compile(
    r"cache_writer frame=(?P<frame>\d+) "
    r"address=(?P<address>[0-9A-F]{4}) bank=(?P<bank>[0-9A-F]{2}) "
    r"pc=(?P<pc>[0-9A-F]{4}) old=(?P<old>[0-9A-F]{2}) "
    r"new=(?P<new>[0-9A-F]{2})"
)
CACHE_RECORD = tuple(range(CACHE_9C00_BASE, CACHE_9C00_BASE + 4))
HELPER_END = HELPER_ENTRY + len(build_helper(shalamar_native_exact_class=4))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_sha256(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    rom: Path, state: Path, prefix: Path, target: int, frames: int, timeout: float
) -> dict[str, object]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    marker.unlink(missing_ok=True)
    Path(str(prefix) + ".trace").unlink(missing_ok=True)
    runtime_dir = prefix.parent / f"{prefix.name}-runtime-{uuid.uuid4().hex}"
    runtime_dir.mkdir(parents=True)
    env = os.environ.copy()
    env.update(
        BOSS_SEMANTIC_OUT=str(prefix),
        BOSS_SEMANTIC_SCENE=str(BOSSES[target].scene),
        BOSS_SEMANTIC_FRAMES=str(frames),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            str(MGBA), "--fastforward", "-t", str(state),
            "-C", f"savegamePath={runtime_dir}",
            "-C", f"savestatePath={runtime_dir}",
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
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"semantic cadence timed out: {BOSSES[target].name}")
    finally:
        terminate(process)

    status = marker.read_text().strip()
    if not status.startswith("ok "):
        raise RuntimeError(f"semantic cadence rejected: {status}")
    rows = []
    cache_writers = []
    for raw in Path(str(prefix) + ".trace").read_text().splitlines():
        match = LINE.fullmatch(raw)
        if match:
            rows.append({
                key: int(
                    value,
                    16 if key in {
                        "destination", "sum_a", "sum_b", "raw_sig",
                        "cache_raw", "cache_sum_b", "cache_scene",
                        "cache_sum_a",
                    }
                    else 10,
                )
                for key, value in match.groupdict().items()
            })
            continue
        writer_match = CACHE_WRITER_LINE.fullmatch(raw)
        if writer_match:
            cache_writers.append({
                key: int(value, 10 if key == "frame" else 16)
                for key, value in writer_match.groupdict().items()
            })
    if len(rows) < 4:
        raise RuntimeError(f"too few boss publications: {len(rows)}")
    initialized: set[int] = set()
    steady = []
    for row in rows:
        destination = row["destination"]
        if destination in (0x9800, 0x9C00) and destination in initialized:
            steady.append(row)
        elif destination in (0x9800, 0x9C00):
            initialized.add(destination)
    # The source can advance between the decision and the $42A7 observation
    # boundary, so a cache byte cannot be paired with the later live plane.
    # Prove collision freedom directly from the source/plane corpus emitted at
    # that same boundary; this is the exact relation the helper must preserve.
    plane_size = 24 * 24
    raw_planes = Path(str(prefix) + ".planes.bin").read_bytes()
    raw_tiles = Path(str(prefix) + ".tiles.bin").read_bytes()
    expected_size = len(rows) * plane_size
    if len(raw_planes) != expected_size or len(raw_tiles) != expected_size:
        raise RuntimeError(
            f"semantic corpus size mismatch: rows={len(rows)} "
            f"planes={len(raw_planes)} tiles={len(raw_tiles)}"
        )
    key_owner: dict[tuple[int, int, int, int], bytes] = {}
    exact_owner: dict[tuple[int, int, int, int, int], bytes] = {}
    false_semantic_hits = []
    false_raw_hits = []
    guard_mismatches = []
    for index, row in enumerate(rows):
        start = index * plane_size
        plane = raw_planes[start:start + plane_size]
        source = raw_tiles[start:start + plane_size]
        destination = row["destination"]
        expected_guard = destination == 0x4400 or BOSSES[target].scene == 0x10
        if bool(row["guarded"]) != expected_guard:
            guard_mismatches.append(row)
        if expected_guard:
            continue
        key = (
            destination, row["sum_a"], row["sum_b"], BOSSES[target].scene
        )
        exact_key = (*key, row["raw_sig"])
        if key_owner.setdefault(key, plane) != plane:
            false_semantic_hits.append(row)
        if exact_owner.setdefault(exact_key, source) != source:
            false_raw_hits.append(row)
    # Crystal Dragon deliberately keeps its specialized ghost cache. Every
    # shared-cache boss must expose the exact scene in both physical cache
    # records and have no corpus-level semantic or exact-layout aliases.
    cache_contract = not guard_mismatches and (
        target in (2, 4) or (
            all(row["cache_scene"] == BOSSES[target].scene for row in steady)
            and not false_semantic_hits
            and not false_raw_hits
        )
    )
    if not cache_contract:
        bad = [
            row for row in steady
            if row["cache_scene"] != BOSSES[target].scene
        ]
        raise RuntimeError(
            f"semantic cache contract failed for {BOSSES[target].name}: "
            f"cache={bad[:3]} semantic_aliases={false_semantic_hits[:3]} "
            f"raw_aliases={false_raw_hits[:3]} guards={guard_mismatches[:3]}"
        )
    foreign_cache_writers = [
        writer for writer in cache_writers
        if writer["address"] not in CACHE_RECORD
        or writer["bank"] != HELPER_BANK
        or not (HELPER_ENTRY <= writer["pc"] < HELPER_END)
    ]
    if foreign_cache_writers:
        raise RuntimeError(
            f"foreign $9C00 cache writers for {BOSSES[target].name}: "
            f"{foreign_cache_writers[:8]}"
        )
    cache_writer_counts = {
        f"{address:04X}": sum(
            writer["address"] == address for writer in cache_writers
        )
        for address in CACHE_RECORD
    }
    # A restored-PC breakpoint can be dispatched just before or just after
    # mGBA's first frame callback.  That changes every absolute frame label by
    # a constant (observed: two frames) without changing one emulated event.
    # Hash the complete cadence relative to its first publication and include
    # the full tile/plane corpora separately.  This is stricter than hashing
    # the presentation trace alone: exact content and writer attribution must
    # match, while host-side callback phase cannot create a false failure.
    frame_origin = rows[0]["frame"]
    normalized_rows = [
        {**row, "frame": row["frame"] - frame_origin} for row in rows
    ]
    normalized_writers = [
        {**writer, "frame": writer["frame"] - frame_origin}
        for writer in cache_writers
    ]
    trajectory_sha256 = object_sha256({
        "rows": normalized_rows,
        "cache_writers": normalized_writers,
    })
    return {
        "boss": BOSSES[target].name,
        "scene": f"{BOSSES[target].scene:02X}",
        "copies": len(rows),
        "steady_copies": len(steady),
        "steady_repeats": sum(row["repeat"] for row in steady),
        "steady_changes": sum(not row["repeat"] for row in steady),
        "maximum_changed_cells": max((row["changed"] for row in steady), default=0),
        "steady_cache_hits": sum(row["hit"] for row in steady),
        "steady_tile_repeats": sum(row["tile_repeat"] for row in steady),
        "steady_tile_changes": sum(not row["tile_repeat"] for row in steady),
        "steady_tile_cache_hits": sum(row["raw_hit"] for row in steady),
        "false_semantic_hits": len(false_semantic_hits),
        "false_raw_hits": len(false_raw_hits),
        "guard_mismatches": len(guard_mismatches),
        "cache_contract": (
            "specialized-crystal-cache" if target == 2 else
            "specialized-ted-cache" if target == 4 else "pass"
        ),
        "cache_writer_contract": "pass",
        "cache_writer_counts": cache_writer_counts,
        "cache_writer_bank": f"{HELPER_BANK:02X}",
        "cache_writer_pc_range": f"{HELPER_ENTRY:04X}-{HELPER_END - 1:04X}",
        "foreign_cache_writers": 0,
        "trace": str(Path(str(prefix) + ".trace").resolve()),
        "trace_sha256": sha256(Path(str(prefix) + ".trace")),
        "trajectory_sha256": trajectory_sha256,
        "frame_origin": frame_origin,
        "tiles_sha256": sha256(Path(str(prefix) + ".tiles.bin")),
        "planes_sha256": sha256(Path(str(prefix) + ".planes.bin")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--target", action="append", type=int, choices=range(9))
    parser.add_argument(
        "--audit-cache-ownership", action="store_true",
        help=(
            "also replay Crystal and Ted so the relocated DF5C-DF5F record "
            "is watched across all nine boss implementations"
        ),
    )
    parser.add_argument("--frames", type=int, default=150)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument(
        "--replays", type=int, default=2,
        help="independent restored-state captures required to match (default: 2)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.replays < 2:
        parser.error("--replays must be at least 2")
    rom = args.rom.resolve()
    states = args.states.resolve()
    # Crystal Dragon and Ted own specialized publication caches. Their
    # dedicated ghost and native-pose determinism suites remain authoritative;
    # this receipt defaults to the seven bosses routed through the shared key.
    if args.target and args.audit_cache_ownership:
        parser.error("--audit-cache-ownership cannot be combined with --target")
    targets = (
        list(range(9)) if args.audit_cache_ownership
        else args.target or list(SHARED_CACHE_TARGETS)
    )
    rows = []
    for target in targets:
        matches = sorted(
            path for path in states.glob(f"boss{target}_*.ss0")
            if ".failed." not in path.name and ".candidate." not in path.name
        )
        if len(matches) != 1:
            parser.error(f"expected one state for boss {target}, found {len(matches)}")
        state = matches[0].resolve()
        replays = [
            capture(
                rom, state,
                args.output.parent / "semantic" / BOSSES[target].name
                / f"run-{run + 1}",
                target, args.frames, args.timeout,
            )
            for run in range(args.replays)
        ]
        replay_fingerprints = [
            (
                run["trajectory_sha256"], run["tiles_sha256"],
                run["planes_sha256"],
            )
            for run in replays
        ]
        if len(set(replay_fingerprints)) != 1:
            raise RuntimeError(
                f"semantic replay differs for {BOSSES[target].name}: "
                f"{replay_fingerprints}"
            )
        row = dict(replays[0])
        row.update({
            "state_sha256": sha256(state),
            "deterministic_replays": args.replays,
            "replay_trace_sha256": [
                run["trace_sha256"] for run in replays
            ],
            "replay_trajectory_sha256": [
                run["trajectory_sha256"] for run in replays
            ],
            "replay_tiles_sha256": [
                run["tiles_sha256"] for run in replays
            ],
            "replay_planes_sha256": [
                run["planes_sha256"] for run in replays
            ],
            "replay_frame_origins": [run["frame_origin"] for run in replays],
            "replay_match": True,
        })
        rows.append(row)
    receipt = {
        "status": "pass",
        "rom_sha256": sha256(rom),
        "frames": args.frames,
        "deterministic_replays": args.replays,
        "bosses": rows,
    }
    if not args.target:
        aggregate_counts = {
            f"{address:04X}": sum(
                row["cache_writer_counts"][f"{address:04X}"] for row in rows
            )
            for address in CACHE_RECORD
        }
        if any(count == 0 for count in aggregate_counts.values()):
            raise RuntimeError(
                "$9C00 cache ownership corpus did not exercise every byte: "
                f"{aggregate_counts}"
            )
        receipt["cache_9c00_ownership"] = {
            "status": "pass",
            "record": f"{CACHE_RECORD[0]:04X}-{CACHE_RECORD[-1]:04X}",
            "per_byte_writer_counts": aggregate_counts,
            "only_writer_bank": f"{HELPER_BANK:02X}",
            "only_writer_pc_range": f"{HELPER_ENTRY:04X}-{HELPER_END - 1:04X}",
            "boss_scope": (
                "all-nine" if args.audit_cache_ownership else "shared-cache-seven"
            ),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
