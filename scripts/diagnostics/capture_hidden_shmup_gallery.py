#!/usr/bin/env python3
"""Capture native current-ROM phases of the hidden secret-jet route."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATE = ROOT / "save_states_for_claude/level1_sara_w_in_jet_form_secret_stage.ss0"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_hidden_shmup_gallery.lua")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=24000)
    parser.add_argument("--capture-every", type=int, default=1200)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    args = parser.parse_args()

    rom, state, output = args.rom.resolve(), args.state.resolve(), args.output.resolve()
    if not rom.is_file() or not state.is_file():
        parser.error("ROM and secret-stage state must exist")
    output.mkdir(parents=True, exist_ok=True)
    report = output / "trace.tsv"
    done = Path(f"{report}.done")
    for path in [report, done, output / "manifest.json"]:
        path.unlink(missing_ok=True)
    for path in output.glob("hidden-shmup-*.png"):
        path.unlink()

    env = os.environ.copy()
    env.update(
        HIDDEN_SHMUP_OUT=str(report),
        HIDDEN_SHMUP_SHOT_PREFIX=str(output / "hidden-shmup"),
        HIDDEN_SHMUP_FRAMES=str(args.frames),
        HIDDEN_SHMUP_CAPTURE_EVERY=str(args.capture_every),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [str(args.mgba), "--fastforward", "-t", str(state), "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            if done.is_file() or process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        terminate(process)

    screenshots = []
    for path in sorted(output.glob("hidden-shmup-*.png")):
        with Image.open(path) as source:
            image = source.convert("RGB")
        colors = image.getcolors(maxcolors=1_000_000) or []
        screenshots.append({
            "file": path.name,
            "sha256": digest(path),
            "distinct_colors": len(colors),
            "chromatic_pixels": sum(
                count for count, pixel in colors if max(pixel) - min(pixel) >= 24
            ),
        })
    trace = report.read_text().splitlines() if report.is_file() else []
    transition_rows = [line for line in trace[1:] if line and not line.startswith(("final", "screenshots"))]
    failures = []
    if not done.is_file() or done.read_text().strip() != "ok":
        failures.append("probe did not complete")
    if not screenshots:
        failures.append("no screenshots captured")
    if any(item["distinct_colors"] < 4 or item["chromatic_pixels"] < 100 for item in screenshots):
        failures.append("one or more frames are blank or nonchromatic")
    manifest = {
        "status": "pass" if not failures else "fail",
        "rom_sha256": digest(rom),
        "state_sha256": digest(state),
        "frames": args.frames,
        "transition_count": len(transition_rows),
        "transitions": transition_rows,
        "screenshots": screenshots,
        "failures": failures,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(f"PASS: {len(screenshots)} hidden-SHMUP frames, {len(transition_rows)} state transitions.")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
