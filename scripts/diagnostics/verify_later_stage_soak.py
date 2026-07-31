#!/usr/bin/env python3
"""Run multi-room Stage 2–7 palette-integrity soaks under mGBA."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_later_stage_soak.lua"


def read_fields(report: Path) -> tuple[dict[str, int], list[int], list[int]]:
    lines = report.read_text().splitlines()
    fields = {
        key: int(raw, 16 if key == "expected_scene" else 10)
        for key, raw in re.findall(r"([a-z_]+)=([0-9A-Fa-f]+)", lines[0])
    }
    rooms = [int(value, 16) for value in lines[1].split("=", 1)[1].split(",") if value]
    scenes = [int(value, 16) for value in lines[2].split("=", 1)[1].split(",") if value]
    return fields, rooms, scenes


def run_stage(mgba: str, rom: Path, target: int, frames: int,
              output: Path, timeout: float, screenshots: bool,
              attr_trace: bool, wram_audit: bool,
              capture_stable: int) -> Path:
    prefix = output / f"stage{target + 1}"
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "SOAK_TARGET": str(target),
        "SOAK_OUT": str(prefix),
        "SOAK_FRAMES": str(frames),
        "SOAK_SCREENSHOTS": "1" if screenshots else "0",
        "SOAK_CAPTURE_STABLE": str(capture_stable),
        "SOAK_WRAM_AUDIT": "1" if wram_audit else "0",
    })
    if attr_trace:
        env["SOAK_ATTR_TRACE"] = str(prefix.with_suffix(".attr-events.tsv"))
    command = [mgba]
    # The Qt frontend accepts --fastforward; mgba-headless already runs as
    # fast as possible and rejects that option.
    if (screenshots or attr_trace or wram_audit) and "mgba-qt" in Path(mgba).name:
        command.append("--fastforward")
    command.extend(["--script", str(PROBE), str(rom)])
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    report = prefix.with_suffix(".report")
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if report.exists() and report.stat().st_size:
                return report
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"Stage {target + 1} soak timed out")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-headless-singleflight")
    )
    parser.add_argument("--frames", type=int, default=8000)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument(
        "--stages",
        default="2,3,4,5,6,7",
        help="comma-separated stage numbers to exercise (default: 2..7)",
    )
    parser.add_argument("--keep-dir", type=Path)
    parser.add_argument(
        "--screenshots", action="store_true",
        help="capture each visited room and first mismatch (use with mgba-qt)",
    )
    parser.add_argument(
        "--capture-stable",
        type=int,
        default=4,
        help="stable frames before each room screenshot (default: 4; use 0 "
             "to capture very brief routes)",
    )
    parser.add_argument(
        "--attr-trace", action="store_true",
        help="trace each Stage 5/7 desired lava map for cache-key analysis",
    )
    parser.add_argument(
        "--wram-audit", action="store_true",
        help="prove candidate fixed-WRAM ranges remain unchanged during play",
    )
    args = parser.parse_args()
    if args.capture_stable < 0:
        parser.error("--capture-stable must be non-negative")
    try:
        stages = [int(value) for value in args.stages.split(",") if value]
    except ValueError:
        parser.error("--stages must be a comma-separated list of integers")
    if not stages or any(stage < 2 or stage > 7 for stage in stages):
        parser.error("--stages entries must be between 2 and 7")

    temporary = None
    if args.keep_dir:
        output = args.keep_dir.resolve()
        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="penta-later-soak-")
        output = Path(temporary.name)

    failures: list[str] = []
    try:
        for stage in stages:
            target = stage - 1
            try:
                report = run_stage(
                    args.mgba, args.rom.resolve(), target, args.frames,
                    output, args.timeout, args.screenshots, args.attr_trace,
                    args.wram_audit, args.capture_stable,
                )
                fields, rooms, scenes = read_fields(report)
            except Exception as exc:
                failures.append(str(exc))
                continue

            print(
                f"Stage {target + 1}: frames={fields['frames']} "
                f"rooms={[f'{room:02X}' for room in rooms]} "
                f"scenes={[f'{scene:02X}' for scene in scenes]} "
                f"unexpected={fields['unexpected']} unsafe={fields['unsafe']} "
                f"lava_mismatch={fields['lava_mismatch']}"
            )
            if fields["frames"] < args.frames:
                failures.append(f"Stage {target + 1}: stopped at {fields['frames']} frames")
            if fields["samples"] < 20:
                failures.append(f"Stage {target + 1}: too few stable samples")
            if fields["unexpected"] or fields["unsafe"] or fields["lava_mismatch"]:
                failures.append(f"Stage {target + 1}: invalid BG attributes observed")
            if args.wram_audit and fields["wram_changed"]:
                failures.append(
                    f"Stage {target + 1}: audited WRAM changed "
                    f"{fields['wram_changed']} times"
                )
            if fields["expected_scene"] not in scenes:
                failures.append(f"Stage {target + 1}: expected scene was never sampled")
            if len(rooms) < 2:
                failures.append(f"Stage {target + 1}: exercised only {len(rooms)} room")
    finally:
        if temporary is not None:
            temporary.cleanup()

    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPASS: all later stages completed multi-room BG-integrity soaks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
