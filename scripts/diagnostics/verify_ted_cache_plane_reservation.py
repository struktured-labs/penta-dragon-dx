#!/usr/bin/env python3
"""Reserve Ted's WRAM2/3 D000-D305 cache records with a write canary.

Each record contains the $300-byte attribute plane plus four bytes of cache
metadata (four-byte signature plus scene/validity bytes).
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
MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_ted_cache_planes.lua")
SCHEMA = "penta-ted-cache-plane-reservation-v4"
HEADER = re.compile(
    r"status=(\S+) frames=(\d+) bank2=(\d+) bank3=(\d+) read2=(\d+) read3=(\d+)"
)
OWNER = re.compile(r"owner=([23]):([0-9A-F]{4}) count=(\d+)")
READER = re.compile(r"reader=([23]):([0-9A-F]{4}) count=(\d+)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyze(
    text: str, frames: int, allowed_pcs: frozenset[int],
    allowed_read_pcs: frozenset[int] = frozenset(),
) -> dict[str, object]:
    lines = text.splitlines()
    match = HEADER.fullmatch(lines[0]) if lines else None
    if match is None:
        return {"status": "fail", "reason": "missing-header"}
    status, observed, bank2, bank3, read2, read3 = match.groups()
    owners, readers = {}, {}
    examples = []
    for line in lines[1:]:
        owner = OWNER.fullmatch(line)
        if owner:
            bank, pc, count = owner.groups()
            owners[f"{bank}:{pc}"] = int(count)
        elif reader := READER.fullmatch(line):
            bank, pc, count = reader.groups()
            readers[f"{bank}:{pc}"] = int(count)
        else:
            examples.append(line)
    unknown = {
        key: count for key, count in owners.items()
        if int(key.split(":")[1], 16) not in allowed_pcs
    }
    foreign_readers = {
        key: count for key, count in readers.items()
        if int(key.split(":")[1], 16) not in allowed_read_pcs
    }
    passed = (
        status == "ok" and int(observed) == frames and not unknown
        and sum(owners.values()) == int(bank2) + int(bank3)
        and not foreign_readers
        and sum(readers.values()) == int(read2) + int(read3)
    )
    return {
        "status": "pass" if passed else "fail",
        "probe_status": status, "frames": int(observed),
        "bank2_writes": int(bank2), "bank3_writes": int(bank3),
        "bank2_reads": int(read2), "bank3_reads": int(read3),
        "owners": owners, "unknown_owners": unknown, "examples": examples,
        "readers": readers, "foreign_readers": foreign_readers,
    }


def capture(rom: Path, state: Path, prefix: Path, frames: int, timeout: float) -> str:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    marker = Path(str(prefix) + ".done")
    prefix.unlink(missing_ok=True); marker.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(TED_CACHE_PLANES_OUT=str(prefix), TED_CACHE_PLANES_FRAMES=str(frames),
               QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy")
    process = subprocess.Popen(
        [str(MGBA), "--fastforward", "-t", str(state), str(rom),
         "--script", str(PROBE)], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if marker.is_file() and prefix.is_file():
                return prefix.read_text()
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        raise TimeoutError(f"Ted cache-plane probe exceeded {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=2800)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-pc", action="append", type=lambda value: int(value, 0), default=[],
        help="declared cache-writer PC; repeat when the implementation is split",
    )
    parser.add_argument(
        "--allow-read-pc", action="append",
        type=lambda value: int(value, 0), default=[],
        help="declared cache-reader PC; repeat for split lookup helpers",
    )
    args = parser.parse_args()
    traces = args.output.parent / "traces"
    first = capture(args.rom.resolve(), args.state.resolve(), traces / "run-a.txt",
                    args.frames, args.timeout)
    second = capture(args.rom.resolve(), args.state.resolve(), traces / "run-b.txt",
                     args.frames, args.timeout)
    allowed = frozenset(args.allow_pc)
    allowed_read = frozenset(args.allow_read_pc)
    metrics = analyze(first, args.frames, allowed, allowed_read)
    deterministic = first == second
    negative = analyze(
        f"status=ok frames={args.frames} bank2=0 bank3=1 read2=0 read3=0\n"
        "owner=3:FFFF count=1\n", args.frames, allowed
    )["status"] == "fail"
    read_negative = analyze(
        f"status=ok frames={args.frames} bank2=0 bank3=0 read2=1 read3=0\n"
        "reader=2:FFFF count=1\n", args.frames, allowed
    )["status"] == "fail"
    passed = (metrics["status"] == "pass" and deterministic and negative
              and read_negative)
    receipt = {
        "schema": SCHEMA, "status": "pass" if passed else "fail",
        "rom_sha256": sha256(args.rom), "state_sha256": sha256(args.state),
        "deterministic_replay": deterministic,
        "trace_sha256": [
            hashlib.sha256(first.encode()).hexdigest(),
            hashlib.sha256(second.encode()).hexdigest(),
        ],
        "metrics": metrics,
        "allowed_writer_pcs": [f"{pc:04X}" for pc in sorted(allowed)],
        "allowed_reader_pcs": [f"{pc:04X}" for pc in sorted(allowed_read)],
        "negative_control": {
            "occupied_plane_rejected": negative,
            "foreign_reader_rejected": read_negative,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
