#!/usr/bin/env python3
"""Diagnostic characterization of Ted's packed staging workspace.

This is intentionally not a release gate. Ted's C1A0 plane contains future
poses in the original rendering design, so visible-map publication—not raw
workspace cleanliness—is the authoritative correctness boundary. Use
``verify_ted_determinism.py`` for the official 2,800-frame release contract.

The unmodified game uses only tile IDs $01-$86 in Ted's packed C1A0 plane.
Across the authoritative 2,800-frame stock trace, at most 164 cells belong to
Ted's numbered/sparse art at once.  Stage terrain, enemy art, sanitizer marker
bytes, and accumulated future poses violate those bounds before a screenshot
comparison has to guess whether they are visible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts/mgba-headless-singleflight"
PROBE = Path(__file__).with_name("probe_ted_source_map_pairs.lua")
FRAME_SIZE = 4 + 24 * 24 + 2 * 0x400
BODY_TILES = frozenset(range(0x02, 0x77)) | {
    0x7B, 0x7D, 0x80, 0x82, 0x83, 0x84, 0x85, 0x86,
}
MAX_NATIVE_SOURCE_BODY_CELLS = 164
MAX_NATIVE_SOURCE_TILE = 0x86
SCHEMA = "penta-ted-source-publication-v1"


def run(rom: Path, state: Path, prefix: Path, frames: int, timeout: float) -> bytes:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    stock_rom = not (rom.read_bytes()[0x143] & 0x80)
    env.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        TED_SOURCE_MAP_OUT=str(prefix),
        TED_SOURCE_MAP_FRAMES=str(frames),
        TED_SOURCE_MAP_STOCK="1" if stock_rom else "0",
    )
    process = subprocess.Popen(
        [str(MGBA), "-t", str(state), "--script", str(PROBE), str(rom)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )
    marker = Path(str(prefix) + ".done")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if marker.is_file():
                status = marker.read_text().strip()
                if not status.startswith("status=ok"):
                    raise RuntimeError(status)
                data = Path(str(prefix) + ".bin").read_bytes()
                if len(data) != frames * FRAME_SIZE:
                    raise RuntimeError(
                        f"trace size {len(data)} != {frames} * {FRAME_SIZE}"
                    )
                return data
            if process.poll() is not None:
                raise RuntimeError(
                    (process.stderr.read() if process.stderr else "").strip()
                )
            time.sleep(0.02)
        raise TimeoutError(f"Ted source trace timed out after {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def analyze(data: bytes, frames: int) -> dict[str, object]:
    body_counts: list[int] = []
    foreign_frames = oversized_frames = 0
    examples: list[dict[str, object]] = []
    for frame in range(frames):
        record = data[frame * FRAME_SIZE:(frame + 1) * FRAME_SIZE]
        source = record[4:4 + 24 * 24]
        body = sum(tile in BODY_TILES for tile in source)
        foreign = sum(tile > MAX_NATIVE_SOURCE_TILE for tile in source)
        body_counts.append(body)
        if foreign:
            foreign_frames += 1
            if len(examples) < 16:
                examples.append({
                    "frame": frame, "kind": "foreign-source-tiles",
                    "count": foreign, "maximum_tile": max(source),
                })
        if body > MAX_NATIVE_SOURCE_BODY_CELLS:
            oversized_frames += 1
            if len(examples) < 16:
                examples.append({
                    "frame": frame, "kind": "oversized-source-pose",
                    "body_cells": body,
                })
    failures = {
        name: count for name, count in (
            ("foreign-source-tiles", foreign_frames),
            ("oversized-source-pose", oversized_frames),
        ) if count
    }
    return {
        "status": "pass" if not failures else "fail",
        "frames": frames,
        "native_maximum_tile": MAX_NATIVE_SOURCE_TILE,
        "native_maximum_body_cells": MAX_NATIVE_SOURCE_BODY_CELLS,
        "observed_minimum_body_cells": min(body_counts),
        "observed_maximum_body_cells": max(body_counts),
        "foreign_source_frames": foreign_frames,
        "oversized_source_frames": oversized_frames,
        "failures": failures,
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--states", type=Path)
    parser.add_argument("--frames", type=int, default=2800)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument(
        "--receipt-only", action="store_true",
        help=(
            "write deterministic traces/report but leave pass/fail ownership "
            "to the aggregate readiness gate"
        ),
    )
    args = parser.parse_args()
    state = args.state or (args.states / "boss4_ted.ss0" if args.states else None)
    if state is None:
        parser.error("--state or --states is required")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    traces = args.output.parent / "traces"
    first = run(args.rom.resolve(), state.resolve(), traces / "run-a",
                args.frames, args.timeout)
    second = run(args.rom.resolve(), state.resolve(), traces / "run-b",
                 args.frames, args.timeout)
    deterministic = first == second
    report = {
        "schema": SCHEMA,
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "state_sha256": hashlib.sha256(state.read_bytes()).hexdigest(),
        "trace_sha256": hashlib.sha256(first).hexdigest(),
        "deterministic_replay": deterministic,
        "metrics": analyze(first, args.frames),
    }
    if not deterministic:
        report["metrics"]["status"] = "fail"
        report["metrics"]["failures"]["nondeterministic-replay"] = 1
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if args.receipt_only or report["metrics"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
