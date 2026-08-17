#!/usr/bin/env python3
"""Measure HBlank-window consumption of the bank1 tile copier per stage.

Step 0 of docs/speed_optimization_plan_v3.md: split the dungeon slowdown
into per-window overhead vs window count before touching the builder. For
each ROM this tool statically scans the copier region for STAT-poll sites
(`F0 41 E6 xx [FE xx] <cond-branch>`) and their fall-through window bodies,
passes both lists to probe_window_count.lua, and reports:

  windows  = wait exits (window-body executions) per play window
  polls    = busy-wait iterations (~ time spent waiting)
  path share on the candidate (atomic $42DF vs stock $433B bodies)

The probe replicates probe_stage_speed.lua's boot route and input, so the
numbers sit beside the gameplay_speed_parity receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_window_count.lua")
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"

COMPLETE = re.compile(
    r"complete status=(?P<status>\S+) frames=(?P<frames>\d+) "
    r"play_frames=(?P<play>\d+) main_loop_hits=(?P<hits>\d+) "
    r"copy_entries=(?P<copies>\d+) scene=(?P<scene>[0-9A-F]{2})"
)
COUNTER = re.compile(r"(?P<kind>poll|body) (?P<addr>[0-9A-F]{4}) (?P<count>\d+)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scan_sites(rom: Path, lo: int = 0x42A0, hi: int = 0x4380):
    """Return ([poll addresses], [window-body addresses]) for one ROM."""
    buf = rom.read_bytes()
    polls, bodies = [], []
    i = lo
    while i < hi - 6:
        if buf[i] == 0xF0 and buf[i + 1] == 0x41 and buf[i + 2] == 0xE6:
            j = i + 4
            if buf[j] == 0xFE:
                j += 2
            op = buf[j]
            if op in (0xC2, 0xCA):
                j += 3
            elif op in (0x20, 0x28):
                j += 2
            else:
                i += 1
                continue
            polls.append(i)
            bodies.append(j)
            i = j
        else:
            i += 1
    if not polls:
        raise RuntimeError(f"no STAT-poll sites found in {rom}")
    return polls, bodies


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def capture(rom: Path, target: int, frames: int, prefix: Path, timeout: float):
    polls, bodies = scan_sites(rom)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        WC_OUT=str(prefix),
        WC_TARGET=str(target),
        WC_FRAMES=str(frames),
        WC_POLLS=",".join(f"{a:04X}" for a in polls),
        WC_BODIES=",".join(f"{a:04X}" for a in bodies),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            str(MGBA), "--fastforward",
            "-C", f"savegamePath={prefix.parent}",
            "-C", f"savestatePath={prefix.parent}",
            str(rom), "--script", str(PROBE),
        ],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
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
            raise TimeoutError(f"window count probe timed out: {prefix.name}")
    finally:
        terminate(process)

    status = marker.read_text().strip()
    if status != "ok":
        raise RuntimeError(f"window count probe rejected {prefix.name}: {status}")
    header = None
    counters: dict[str, dict[int, int]] = {"poll": {}, "body": {}}
    for line in trace.read_text().splitlines():
        found = COMPLETE.fullmatch(line.strip())
        if found:
            header = found
            continue
        counter = COUNTER.fullmatch(line.strip())
        if counter:
            counters[counter.group("kind")][int(counter.group("addr"), 16)] = int(
                counter.group("count")
            )
    if header is None:
        raise RuntimeError(f"no completion record for {prefix.name}")
    play = int(header.group("play"))
    windows = sum(counters["body"].values())
    polls_total = sum(counters["poll"].values())
    return {
        "status": status,
        "play_frames": play,
        "main_loop_hits": int(header.group("hits")),
        "copy_entries": int(header.group("copies")),
        "windows": windows,
        "poll_iterations": polls_total,
        "windows_per_frame": windows / play if play else 0.0,
        "polls_per_frame": polls_total / play if play else 0.0,
        "poll_sites": {f"{a:04X}": c for a, c in sorted(counters["poll"].items())},
        "body_sites": {f"{a:04X}": c for a, c in sorted(counters["body"].items())},
        "trace": str(trace.resolve()),
        "trace_sha256": sha256(trace),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument(
        "--stage", action="append", type=int, choices=range(7),
        help="FFBA stage target(s); default 0, 4, 6 (stages 1, 5, 7)",
    )
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    stages = args.stage or [0, 4, 6]
    rows = []
    for target in stages:
        row: dict[str, object] = {"stage": target + 1, "ffba": target}
        for side, rom in (("og", args.original.resolve()), ("dx", args.dx_rom.resolve())):
            row[side] = capture(
                rom, target, args.frames,
                args.output.parent / "window-count" / f"stage{target + 1}" / side,
                args.timeout,
            )
        og, dx = row["og"], row["dx"]
        row["window_ratio"] = (
            dx["windows_per_frame"] / og["windows_per_frame"]
            if og["windows_per_frame"] else None
        )
        row["poll_ratio"] = (
            dx["polls_per_frame"] / og["polls_per_frame"]
            if og["polls_per_frame"] else None
        )
        rows.append(row)
        print(
            f"stage {target + 1}: og windows/frame={og['windows_per_frame']:.2f} "
            f"dx={dx['windows_per_frame']:.2f} ratio={row['window_ratio']:.3f} | "
            f"og polls/frame={og['polls_per_frame']:.1f} "
            f"dx={dx['polls_per_frame']:.1f} ratio={row['poll_ratio']:.3f} | "
            f"main-loop og={og['main_loop_hits']} dx={dx['main_loop_hits']}"
        )

    receipt = {
        "schema": "penta-window-count-v1",
        "frames": args.frames,
        "original_rom_sha256": sha256(args.original.resolve()),
        "dx_rom_sha256": sha256(args.dx_rom.resolve()),
        "stages": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Receipt: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
