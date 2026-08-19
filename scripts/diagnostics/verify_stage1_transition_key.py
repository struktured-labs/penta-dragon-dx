#!/usr/bin/env python3
"""Prove a Stage-1 map-cache key against exact live semantic transitions."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_transition_key.lua")
DEFAULT_STATES = (
    "level1_sara_w_alone.ss0",
    "level1_sara_w_gargoyle_mini_boss.ss0",
    "level1_sara_w_spiral_power_active_health1.ss0",
)
FEATURE_FIELDS = {
    "scx", "scy", "dc02", "room", "dc00", "dc01", "dc03", "dc81",
    "ffcf", "ffe8", "ffe9", "ffeb",
}
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)


def parse_samples(text: str) -> tuple[int, ...]:
    samples = tuple(int(part, 0) for part in text.split(",") if part.strip())
    if not samples or any(not 0 <= sample < 576 for sample in samples):
        raise argparse.ArgumentTypeError("samples must be packed offsets 0..575")
    return samples


def parse_features(text: str) -> tuple[str, ...]:
    features = tuple(part.strip().lower() for part in text.split(",") if part.strip())
    if not features:
        raise argparse.ArgumentTypeError("at least one key feature is required")
    for feature in features:
        if feature in FEATURE_FIELDS:
            continue
        if feature.startswith("raw") and feature[3:].isdigit():
            if 0 <= int(feature[3:]) < 576:
                continue
        raise argparse.ArgumentTypeError(f"unknown key feature: {feature}")
    return features


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def run_profile(
    *, mgba: Path, rom: Path, output: Path, name: str, mode: str,
    state: Path | None, frames: int, max_frames: int, timeout: float,
) -> tuple[Path, dict[str, str]]:
    runtime = output / name
    runtime.mkdir(parents=True, exist_ok=True)
    trace = runtime / "events.tsv"
    report = runtime / "probe.txt"
    log_path = runtime / "mgba.log"
    for stale in (trace, report, log_path):
        stale.unlink(missing_ok=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE1_KEY_OUT": str(trace),
        "STAGE1_KEY_REPORT": str(report),
        "STAGE1_KEY_MODE": mode,
        "STAGE1_KEY_FRAMES": str(frames),
        "STAGE1_KEY_MAX_FRAMES": str(max_frames),
    })
    command = [str(mgba), "--fastforward"]
    if state is not None:
        command.extend(["-t", str(state)])
    command.extend([
        str(runtime_rom), "--script", str(PROBE),
        "-C", f"savegamePath={runtime}",
    ])
    with log_path.open("w") as log:
        process = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                if report.is_file() and report.stat().st_size:
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError(f"{name}: no report within {timeout:.1f}s")
            if not report.is_file() or not report.stat().st_size:
                raise RuntimeError(f"{name}: emulator exited without a report")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return trace, parse_report(report)


def assess(
    trace: Path, features: tuple[str, ...], canonical_lut: bytes | None,
) -> dict:
    last_key: dict[int, int] = {}
    last_plane: dict[int, bytes] = {}
    events = publications = transitions = false_negatives = false_positives = 0
    first_false_negative = None
    destinations: set[int] = set()
    with trace.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            events += 1
            destination = int(row["destination"], 16)
            destinations.add(destination)
            raw = bytes.fromhex(row["raw"])
            plane = (
                bytes(canonical_lut[tile] & 0x07 for tile in raw)
                if canonical_lut is not None else bytes.fromhex(row["plane"])
            )
            key = 0
            for feature in features:
                if feature.startswith("raw"):
                    key ^= raw[int(feature[3:])]
                else:
                    key ^= int(row[feature], 16)
            key &= 0x7F
            published = last_key.get(destination) != key
            transitioned = last_plane.get(destination) != plane
            publications += int(published)
            transitions += int(transitioned)
            false_negatives += int(transitioned and not published)
            false_positives += int(published and not transitioned)
            if transitioned and not published and first_false_negative is None:
                first_false_negative = {
                    "event": events,
                    "copy": int(row["copy"]),
                    "frame": int(row["frame"]),
                    "destination": f"{destination:04X}",
                    "room": row["room"],
                    "scx": row["scx"],
                    "scy": row["scy"],
                    "dc02": row["dc02"],
                    "key": key,
                }
            last_key[destination] = key
            last_plane[destination] = plane
    return {
        "events": events,
        "destinations": [f"{value:04X}" for value in sorted(destinations)],
        "publications": publications,
        "semantic_transitions": transitions,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
        "first_false_negative": first_false_negative,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    key_group = parser.add_mutually_exclusive_group(required=True)
    key_group.add_argument("--features", type=parse_features)
    key_group.add_argument("--samples", type=parse_samples)
    parser.add_argument("--states", type=Path, default=ROOT / "save_states_for_claude")
    parser.add_argument("--state", action="append", dest="state_names", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--attract-frames", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument(
        "--mgba", type=Path, default=ROOT / "scripts/mgba-qt-singleflight"
    )
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument("--skip-attract", action="store_true")
    args = parser.parse_args()

    rom = args.rom.resolve()
    features = args.features or tuple(f"raw{sample}" for sample in args.samples)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    profiles: list[tuple[str, str, Path | None, int, int]] = []
    if not args.skip_live:
        profiles.append(("cold-live", "live", None, args.frames, 6000))
    if not args.skip_attract:
        profiles.append((
            "cold-attract", "attract", None, args.attract_frames, 40000
        ))
    for state_name in tuple(args.state_names) or DEFAULT_STATES:
        state = (args.states / state_name).resolve()
        if not state.is_file():
            raise SystemExit(f"missing state: {state}")
        profiles.append((state.stem, "state", state, args.frames, 6000))

    rom_bytes = rom.read_bytes()
    canonical_lut = rom_bytes[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 256]
    if len(canonical_lut) != 256:
        raise SystemExit("candidate does not contain the Stage-1 semantic LUT")
    receipt = {
        "schema": "penta-dragon-dx-stage1-transition-key-v2",
        "rom": str(rom),
        "rom_sha256": hashlib.sha256(rom_bytes).hexdigest(),
        "features": list(features),
        "canonical_lut_sha256": hashlib.sha256(canonical_lut).hexdigest(),
        "profiles": {},
    }
    failed = False
    for name, mode, state, frames, max_frames in profiles:
        trace, probe_report = run_profile(
            mgba=args.mgba.resolve(), rom=rom, output=output, name=name,
            mode=mode, state=state, frames=frames, max_frames=max_frames,
            timeout=args.timeout,
        )
        proposed = assess(trace, features, canonical_lut)
        current = assess(trace, ("scx", "dc02", "raw49"), canonical_lut)
        live_plane = assess(trace, features, None)
        profile = {
            "probe": probe_report,
            "proposed_canonical_plane": proposed,
            "current_camera_raw49": current,
            "live_lut_plane_telemetry": live_plane,
        }
        receipt["profiles"][name] = profile
        failed |= proposed["events"] == 0 or proposed["false_negatives"] != 0
        print(
            f"{name}: events={proposed['events']} "
            f"transitions={proposed['semantic_transitions']} "
            f"proposed pubs={proposed['publications']} "
            f"fn={proposed['false_negatives']} fp={proposed['false_positives']} "
            f"current pubs={current['publications']} "
            f"fn={current['false_negatives']} fp={current['false_positives']}"
        )
    receipt["passed"] = not failed
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if failed:
        print(f"FAIL: unsafe or empty profile; receipt: {receipt_path}")
        return 1
    print(
        f"PASS: key features {features} covered every observed Stage-1 "
        f"semantic transition; receipt: {receipt_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
