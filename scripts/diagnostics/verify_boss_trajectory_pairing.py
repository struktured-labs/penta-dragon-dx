#!/usr/bin/env python3
"""Measure OG/DX boss-arena speed over trajectory-matched spans only.

WHY THIS EXISTS
---------------
Every cross-ROM boss speed receipt rides OG/DX state fixtures that land at
different arena phases, and pairing validity has been an assumption rather
than a precondition. The receipts show the consequence: physically
implausible signs (ted -17.1%, cameo -17.0% at 7200 frames) and magnitudes
that grow with the observation window -- trajectory divergence amplifying,
not a fixed CPU delta. ``verify_boss_speed_parity.py`` fixed the *metric*
(loop iterations, not event rates) but still compares unmatched spans.

This tool makes pairing checkable and then measures inside it:

1. ``probe_boss_trajectory_pairing.lua`` samples the boss-phase WRAM vector
   (DD85-88, DCB8, DD08, FFBF) at every arena-loop iteration (the
   bank2:$406F anchor, FF99==$02 filtered) -- iteration-indexed, never
   frame-indexed, because the builds legitimately shift frame phase
   (~5.3 frames/iteration).
2. The driver compresses each side's vector sequence into TRANSITIONS
   (vector value changes) and aligns OG and DX at the first common
   transition. Alignment on transitions is phase-shift-proof: two runs that
   entered the arena at different points in the boss cycle still share the
   cycle's transition sequence once aligned.
3. Speed is reported as frames-per-iteration over the MATCHED SPAN only,
   plus the first divergent transition. An unpairable run (no common
   transitions) is itself the receipt: it upgrades "direction-only" from
   doctrine to a measured property of that fixture pair.

This is a measurement instrument, not a gate: it exits non-zero only on
harness failure. Classification (paired / unpairable / static-vector) and
the matched-span ratio live in the receipt for the release ledger.
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

from boss_geometry_contract import BOSSES

SCHEMA = "penta-boss-trajectory-pairing-v1"
ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_trajectory_pairing.lua")
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
MIN_MATCHED_TRANSITIONS = 3

ITER_LINE = re.compile(
    r"iter=(?P<iter>\d+) frame=(?P<frame>\d+) scene_frame=(?P<scene_frame>\d+) "
    r"svbk=(?P<svbk>\d+) vec=(?P<vec>[0-9A-F]+) ffcd=(?P<ffcd>[0-9A-F]{2})"
)
COMPLETE = re.compile(
    r"complete status=(?P<status>\S+) frames=(?P<frames>\d+) "
    r"scene_frames=(?P<scene_frames>\d+) iters=(?P<iters>\d+) "
    r"raw_anchor_hits=(?P<raw_hits>\d+) scene=(?P<scene>[0-9A-F]{2})"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_for(directory: Path, target: int) -> Path:
    matches = sorted(
        path for path in directory.glob(f"boss{target}_*.ss0")
        if ".failed." not in path.name and ".candidate." not in path.name
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one state for boss {target} in {directory}, "
            f"found {len(matches)}"
        )
    return matches[0]


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
    rom_bytes = rom.read_bytes()
    env = os.environ.copy()
    env.update(
        TRAJ_OUT=str(prefix),
        TRAJ_SCENE=str(BOSSES[target].scene),
        TRAJ_WARMUP=str(warmup),
        TRAJ_FRAMES=str(frames),
        # Same banked-writer sniff as verify_boss_speed_parity.py: only those
        # candidates park SVBK on 2/3 across frame boundaries. The stock DMG
        # ROM reads FF70=$FF, so the guard must stay off there.
        TRAJ_BANKED_WRITER=(
            "1" if (
                rom_bytes[0x3136:0x3139] == bytes.fromhex("C3 38 08")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD 80 DB")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD E4 6F")
                or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD 87 DB")
            )
            else "0"
        ),
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
            raise TimeoutError(f"trajectory probe timed out: {prefix.name}")
    finally:
        terminate(process)

    samples: list[dict[str, object]] = []
    match = None
    for line in trace.read_text().splitlines():
        row = ITER_LINE.fullmatch(line.strip())
        if row:
            samples.append({
                "iter": int(row.group("iter")),
                "frame": int(row.group("frame")),
                "vec": row.group("vec"),
                "svbk": int(row.group("svbk")),
            })
            continue
        found = COMPLETE.fullmatch(line.strip())
        if found:
            match = found
    if match is None:
        raise RuntimeError(f"no completion record for {prefix.name}")
    status = match.group("status")
    if status not in {"ok", "scene-exit"}:
        raise RuntimeError(f"trajectory probe rejected {prefix.name}: {status}")
    if len(samples) != int(match.group("iters")):
        raise RuntimeError(
            f"iteration line count {len(samples)} disagrees with completion "
            f"record {match.group('iters')} for {prefix.name}"
        )
    if len(samples) < 2:
        raise RuntimeError(f"too few iterations observed for {prefix.name}")
    scene_frames = int(match.group("scene_frames"))
    parked = sum(1 for sample in samples if sample["svbk"] not in (0, 1))
    return {
        "status": status,
        "scene_frames": scene_frames,
        "iters": len(samples),
        "raw_anchor_hits": int(match.group("raw_hits")),
        "svbk_parked_samples": parked,
        "samples": samples,
        "state_sha256": sha256(state),
        "trace_sha256": sha256(trace),
        "trace": str(trace.resolve()),
    }


def transitions(samples: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compress the per-iteration vector sequence into change events."""
    events: list[dict[str, object]] = []
    for previous, current in zip(samples, samples[1:]):
        if current["vec"] != previous["vec"]:
            events.append({
                "from": previous["vec"],
                "to": current["vec"],
                "iter": current["iter"],
                "frame": current["frame"],
            })
    return events


def align(og: list[dict[str, object]], dx: list[dict[str, object]]) -> dict[str, object]:
    """Align two transition streams at the first common (from, to) event and
    walk forward while the streams agree."""
    dx_index: dict[tuple[str, str], int] = {}
    for position, event in enumerate(dx):
        dx_index.setdefault((event["from"], event["to"]), position)
    start_og = start_dx = None
    for position, event in enumerate(og):
        found = dx_index.get((event["from"], event["to"]))
        if found is not None:
            start_og, start_dx = position, found
            break
    if start_og is None or start_dx is None:
        return {"classification": "unpairable", "matched_transitions": 0}
    matched = 0
    while (
        start_og + matched < len(og)
        and start_dx + matched < len(dx)
        and og[start_og + matched]["from"] == dx[start_dx + matched]["from"]
        and og[start_og + matched]["to"] == dx[start_dx + matched]["to"]
    ):
        matched += 1
    result: dict[str, object] = {
        "start_og": start_og,
        "start_dx": start_dx,
        "matched_transitions": matched,
        "og_transitions": len(og),
        "dx_transitions": len(dx),
    }
    if matched < MIN_MATCHED_TRANSITIONS:
        result["classification"] = "unpairable"
        return result
    result["classification"] = "paired"
    divergent_og = start_og + matched
    result["first_divergence"] = {
        "matched_span_end": matched,
        "og": og[divergent_og] if divergent_og < len(og) else None,
        "dx": (
            dx[start_dx + matched]
            if start_dx + matched < len(dx) else None
        ),
    }
    span: dict[str, object] = {}
    for side, events, start in (("og", og, start_og), ("dx", dx, start_dx)):
        first, last = events[start], events[start + matched - 1]
        iters = last["iter"] - first["iter"]
        frames = last["frame"] - first["frame"]
        span[side] = {
            "iters": iters,
            "frames": frames,
            "frames_per_iter": (frames / iters) if iters > 0 else None,
        }
    result["matched_span"] = span
    og_rate = span["og"]["frames_per_iter"]
    dx_rate = span["dx"]["frames_per_iter"]
    if og_rate and dx_rate:
        # >1.0 means DX spends more frames per identical unit of boss-cycle
        # work than OG: a real slowdown over an identical workload.
        result["dx_over_og_frames_per_iter"] = dx_rate / og_rate
        result["slowdown_percent"] = (dx_rate / og_rate - 1.0) * 100.0
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--dx-states", type=Path, required=True)
    parser.add_argument("--og-states", type=Path, required=True)
    parser.add_argument("--target", action="append", type=int, choices=range(9))
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--frames", type=int, default=1800)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dx_rom = args.dx_rom.resolve()
    original = args.original.resolve()
    targets = args.target or list(range(9))
    rows: list[dict[str, object]] = []
    harness_failures: list[str] = []

    for target in targets:
        name = BOSSES[target].name
        row: dict[str, object] = {
            "boss": name,
            "scene": f"{BOSSES[target].scene:02X}",
        }
        try:
            sides: dict[str, dict[str, object]] = {}
            for side, rom, states in (
                ("og", original, args.og_states.resolve()),
                ("dx", dx_rom, args.dx_states.resolve()),
            ):
                state = state_for(states, target)
                replays = [
                    capture(
                        rom,
                        state,
                        args.output.parent / "boss-trajectory" / name
                            / f"{side}-{replay}",
                        target,
                        args.warmup,
                        args.frames,
                        args.timeout,
                    )
                    for replay in ("a", "b")
                ]
                if replays[0]["trace_sha256"] != replays[1]["trace_sha256"]:
                    raise RuntimeError(
                        f"non-deterministic {side} replay for {name}"
                    )
                sides[side] = replays[0]
                sides[side]["deterministic_replay"] = True
        except Exception as error:  # noqa: BLE001 - reported per boss
            row["status"] = "error"
            row["error"] = str(error)
            harness_failures.append(f"{name}: {error}")
            rows.append(row)
            continue

        og_events = transitions(sides["og"]["samples"])
        dx_events = transitions(sides["dx"]["samples"])
        if not og_events or not dx_events:
            row["status"] = "static-vector"
            row["og_transitions"] = len(og_events)
            row["dx_transitions"] = len(dx_events)
        else:
            alignment = align(og_events, dx_events)
            row["alignment"] = alignment
            row["status"] = alignment["classification"]
        for side in ("og", "dx"):
            summary = {
                key: sides[side][key]
                for key in (
                    "scene_frames", "iters", "raw_anchor_hits",
                    "svbk_parked_samples", "state_sha256", "trace_sha256",
                    "trace",
                )
            }
            summary["iters_per_scene_frame"] = (
                sides[side]["iters"] / sides[side]["scene_frames"]
            )
            row[side] = summary
        rows.append(row)
        matched = row.get("alignment", {}).get("matched_transitions", 0)
        slowdown = row.get("alignment", {}).get("slowdown_percent")
        print(
            f"{name:16s} {row['status']:13s} "
            f"og_iters={row['og']['iters']:5d} dx_iters={row['dx']['iters']:5d} "
            f"matched={matched:4d} "
            + (f"matched-span slowdown={slowdown:+6.2f}%"
               if slowdown is not None else "matched-span slowdown=n/a")
        )

    receipt = {
        "schema": SCHEMA,
        "status": "pass" if not harness_failures else "fail",
        "instrument": (
            "phase-vector (DD85-88, DCB8, DD08, FFBF) sampled per arena-loop "
            "iteration at bank2:$406F (FF99==$02 filtered); OG/DX aligned on "
            "vector transitions; frames-per-iteration over the matched span"
        ),
        "warmup_frames": args.warmup,
        "observation_frames": args.frames,
        "min_matched_transitions": MIN_MATCHED_TRANSITIONS,
        "original_rom_sha256": sha256(original),
        "dx_rom_sha256": sha256(dx_rom),
        "bosses": rows,
        "harness_failures": harness_failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    if harness_failures:
        print("HARNESS FAIL:")
        for failure in harness_failures:
            print(f"  - {failure}")
    print(f"Receipt: {args.output}")
    return 1 if harness_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
