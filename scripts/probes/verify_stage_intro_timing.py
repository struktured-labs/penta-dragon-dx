#!/usr/bin/env python3
"""Compare STAGE XX splash timing with the vanilla ROM."""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LUA_PROBE = Path(__file__).with_name("stage_intro_timing.lua")
DEFAULT_BASELINE = PROJECT_ROOT / "rom" / "Penta Dragon (J).gb"


def parse_result(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def run_rom(rom: Path) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="penta_stage_timing_") as temp_dir:
        output = Path(temp_dir) / "result.txt"
        env = os.environ.copy()
        env.update({
            "STAGE_TIMING_OUT": str(output),
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
        })
        command = [
            "xvfb-run", "-a", "/home/struktured/bin/mgba-qt", str(rom),
            "--script", str(LUA_PROBE), "--fastforward", "-l", "0",
        ]
        try:
            subprocess.run(
                command, cwd=PROJECT_ROOT, env=env, capture_output=True,
                timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            pass
        if not output.exists():
            raise RuntimeError(f"stage timing probe produced no result for {rom}")
        return parse_result(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--baseline-rom", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--tolerance-frames", type=int, default=12,
        help="maximum stage-splash frames over vanilla (default: 12)",
    )
    args = parser.parse_args()

    baseline = run_rom(args.baseline_rom.resolve())
    candidate = run_rom(args.rom.resolve())
    baseline_frames = int(baseline.get("stage_frames", "-1"))
    candidate_frames = int(candidate.get("stage_frames", "-1"))
    limit = baseline_frames + args.tolerance_frames

    print(f"Baseline: {baseline}")
    print(f"Candidate: {candidate}")
    print(f"Limit: {limit} frames ({baseline_frames} vanilla + "
          f"{args.tolerance_frames} tolerance)")
    if baseline.get("status") != "ok" or candidate.get("status") != "ok":
        raise SystemExit("FAIL: stage splash did not reach dungeon gameplay")
    if abs(candidate_frames - baseline_frames) > args.tolerance_frames:
        raise SystemExit(
            f"FAIL: stage splash lasted {candidate_frames} frames; vanilla is "
            f"{baseline_frames} (tolerance {args.tolerance_frames})"
        )
    if candidate.get("stage_contaminated_cells") != "0":
        raise SystemExit(
            "FAIL: STAGE XX has nonzero CGB palette attributes: "
            f"{candidate.get('stage_contaminated_cells')} cells"
        )
    print("PASS: STAGE XX ditty/splash timing is baseline-equivalent.")


if __name__ == "__main__":
    main()
