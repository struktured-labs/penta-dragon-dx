#!/usr/bin/env python3
"""Require every DX boss map-publication cadence to stay within 5% of OG."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time

from boss_geometry_contract import BOSSES


ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_publication_cadence.lua")
COPY = re.compile(r"copy=(\d+) frame=(\d+) destination=([0-9A-F]{4})")


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
    matches = sorted(directory.glob(f"boss{target}_*.ss0"))
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
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
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
    copy_frames = [
        int(match.group(2))
        for line in trace.read_text().splitlines()
        if (match := COPY.fullmatch(line))
    ]
    if len(copy_frames) < 8:
        raise RuntimeError(f"too few publications for {prefix.name}: {len(copy_frames)}")
    gaps = [b - a for a, b in zip(copy_frames, copy_frames[1:])]
    return {
        "status": status,
        "copies": len(copy_frames),
        "first_frame": copy_frames[0],
        "last_frame": copy_frames[-1],
        "mean_gap": statistics.fmean(gaps),
        "median_gap": statistics.median(gaps),
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
    parser.add_argument("--max-slowdown", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    targets = args.target or list(range(9))
    rows = []
    passed = True
    for target in targets:
        boss = BOSSES[target]
        pair = {}
        for side, rom, states in (
            ("og", args.original.resolve(), args.og_states.resolve()),
            ("dx", args.dx_rom.resolve(), args.dx_states.resolve()),
        ):
            pair[side] = capture(
                rom,
                state_for(states, target),
                args.output.parent / "cadence" / side / boss.name,
                target,
                args.warmup,
                args.frames,
                args.timeout,
            )
        speed_ratio = pair["og"]["mean_gap"] / pair["dx"]["mean_gap"]
        boss_pass = speed_ratio + 1e-9 >= 1.0 - args.max_slowdown
        passed &= boss_pass
        rows.append({
            "boss": boss.name,
            "scene": f"{boss.scene:02X}",
            "status": "pass" if boss_pass else "fail",
            "speed_ratio": speed_ratio,
            "slowdown_percent": (1.0 - speed_ratio) * 100.0,
            "og": pair["og"],
            "dx": pair["dx"],
        })
        print(
            f"{'PASS' if boss_pass else 'FAIL'} {boss.name}: "
            f"DX/OG speed={speed_ratio:.4f}, slowdown={(1-speed_ratio)*100:.2f}%"
        )

    receipt = {
        "status": "pass" if passed else "fail",
        "maximum_slowdown_percent": args.max_slowdown * 100.0,
        "warmup_frames": args.warmup,
        "observation_frames": args.frames,
        "bosses": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(args.output.resolve())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
