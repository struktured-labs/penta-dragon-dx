#!/usr/bin/env python3
"""Measure repeated boss palette planes at the native map-copy entry."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from boss_geometry_contract import BOSSES


ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_semantic_cadence.lua")
LINE = re.compile(
    r"copy=(?P<copy>\d+) frame=(?P<frame>\d+) "
    r"destination=(?P<destination>[0-9A-F]{4}) "
    r"changed_cells=(?P<changed>\d+) repeat=(?P<repeat>[01]) "
    r"tile_changed_cells=(?P<tile_changed>\d+) "
    r"tile_repeat=(?P<tile_repeat>[01]) "
    r"sig_a=(?P<sig_a>[0-9A-F]{2}) sig_b=(?P<sig_b>[0-9A-F]{2}) "
    r"cache_a=(?P<cache_a>[0-9A-F]{2}) cache_b=(?P<cache_b>[0-9A-F]{2}) "
    r"hit=(?P<hit>[01]) tile_sig=(?P<tile_sig>[0-9A-F]{2}) "
    r"tile_cache=(?P<tile_cache>[0-9A-F]{2}) tile_hit=(?P<tile_hit>[01]) "
    r"guarded=(?P<guarded>[01])"
)


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
    for raw in Path(str(prefix) + ".trace").read_text().splitlines():
        match = LINE.fullmatch(raw)
        if match:
            rows.append({
                key: int(
                    value,
                    16 if key in {
                        "destination", "sig_a", "sig_b", "cache_a", "cache_b",
                        "tile_sig", "tile_cache",
                    }
                    else 10,
                )
                for key, value in match.groupdict().items()
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
    # Crystal Dragon deliberately keeps its specialized raw-layout cache for
    # the stock ghost/translucency effect. Every other boss must prove that
    # exact raw-layout repeats hit while every real change misses. Changed
    # layouts then take the atomic tile+attribute path unconditionally.
    cache_contract = target == 2 or all(
        row["tile_hit"] == (row["tile_repeat"] and not row["guarded"])
        for row in steady
    )
    if not cache_contract:
        bad = [
            row for row in steady
            if row["tile_hit"] != (row["tile_repeat"] and not row["guarded"])
        ]
        raise RuntimeError(
            f"semantic cache contract failed for {BOSSES[target].name}: {bad[:3]}"
        )
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
        "steady_tile_cache_hits": sum(row["tile_hit"] for row in steady),
        "cache_contract": "specialized-crystal-cache" if target == 2 else "pass",
        "trace": str(Path(str(prefix) + ".trace").resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--target", action="append", type=int, choices=range(9))
    parser.add_argument("--frames", type=int, default=150)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    targets = args.target or list(range(9))
    rows = []
    for target in targets:
        matches = sorted(args.states.glob(f"boss{target}_*.ss0"))
        if len(matches) != 1:
            parser.error(f"expected one state for boss {target}, found {len(matches)}")
        rows.append(capture(
            args.rom.resolve(), matches[0].resolve(),
            args.output.parent / "semantic" / BOSSES[target].name,
            target, args.frames, args.timeout,
        ))
    receipt = {"status": "pass", "frames": args.frames, "bosses": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
