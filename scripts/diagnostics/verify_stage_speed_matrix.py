#!/usr/bin/env python3
"""Compare vanilla/DX main-loop throughput across selected dungeon stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage_speed.lua"
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_DX = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_owned_process_group(process: subprocess.Popen) -> None:
    """Stop only the xvfb/mGBA session created by this probe."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    # xvfb-run can exit before its emulator child. Finish any survivors in
    # this exact session without using a process-name pattern.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if process.poll() is None:
        process.wait(timeout=2)


def run_one(
    mgba: str,
    rom: Path,
    label: str,
    target: int,
    mode: str,
    frames: int,
    atomic_addr: int,
    output: Path,
    timeout: float,
) -> dict:
    run_dir = output / f"stage{target + 1}-{label}-{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    receipt = run_dir / "result.json"
    marker = run_dir / "DONE"
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE_SPEED_TARGET": str(target),
            "STAGE_SPEED_OUT": str(receipt),
            "STAGE_SPEED_DONE": str(marker),
            "STAGE_SPEED_TRACE": str(run_dir / "attr-events.tsv"),
            "STAGE_SPEED_LIFECYCLE": str(run_dir / "lifecycle.tsv"),
            "STAGE_SPEED_MODE": mode,
            "STAGE_SPEED_FRAMES": str(frames),
            "STAGE_SPEED_ATOMIC_ADDR": str(atomic_addr),
        }
    )
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    log = run_dir / "mgba.log"
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                "xvfb-run",
                "-a",
                mgba,
                "--fastforward",
                "-C",
                f"savegamePath={run_dir}",
                "-C",
                f"savestatePath={run_dir}",
                str(rom),
                "--script",
                str(PROBE),
                "-l",
                "0",
            ],
            cwd=run_dir,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if receipt.is_file() and marker.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        stop_owned_process_group(process)
    if not receipt.is_file():
        raise RuntimeError(
            f"Stage {target + 1} {label}/{mode}: no receipt; see {log}"
        )
    result = json.loads(receipt.read_text())
    result["rom"] = str(rom)
    result["rom_md5"] = md5(rom)
    result["log"] = str(log)
    return result


def targets(raw: str) -> list[int]:
    values = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not values or any(value < 0 or value > 6 for value in values):
        raise argparse.ArgumentTypeError("targets must be comma-separated FFBA 0..6")
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dx-rom", type=Path, default=DEFAULT_DX)
    parser.add_argument("--original-rom", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--targets", type=targets, default=[0, 4, 6])
    parser.add_argument(
        "--input-mode",
        choices=("right", "stationary", "patrol"),
        default="right",
    )
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--atomic-addr", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.mgba:
        parser.error("mgba-qt was not found")
    if args.frames <= 0 or args.timeout <= 0:
        parser.error("frames and timeout must be positive")

    dx = args.dx_rom.resolve()
    original = args.original_rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    rows: list[dict] = []

    for target in args.targets:
        baseline = run_one(
            args.mgba, original, "original", target, args.input_mode,
            args.frames, 0, output, args.timeout,
        )
        candidate = run_one(
            args.mgba, dx, "dx", target, args.input_mode,
            args.frames, args.atomic_addr, output, args.timeout,
        )
        baseline_hits = baseline["main_loop_hits"]
        candidate_hits = candidate["main_loop_hits"]
        ratio = candidate_hits / baseline_hits if baseline_hits else 0.0
        candidate_scene_mismatch_frames = (
            args.frames - candidate["expected_scene_frames"]
        )
        # A frame callback can land inside the stock HRAM OAM-DMA routine.
        # During that bounded interval CPU-bus reads of WRAM correctly return
        # $FF. The probe classifies every such sample from its PC and DMA
        # source, so tolerate all proven DMA-unreadable samples while keeping
        # every real scene mismatch fatal. This is cadence-independent and
        # therefore deterministic across otherwise equivalent builds.
        dma_unreadable_scene_samples = candidate.get(
            "dma_unreadable_scene_samples", 0
        )
        compiler_unreadable_scene_samples = candidate.get(
            "compiler_unreadable_scene_samples", 0
        )
        non_dma_scene_mismatch_frames = candidate.get(
            "non_dma_scene_mismatch_frames",
            candidate_scene_mismatch_frames,
        )
        candidate_scene_ok = (
            non_dma_scene_mismatch_frames == 0
            and candidate_scene_mismatch_frames
            == dma_unreadable_scene_samples
        )
        # FFC1 is a stage sub-mode flag and legitimately clears in some
        # layouts. Continuity is instead proven from the stock main-loop
        # breakpoint: reject a long internal stall or a run that stops making
        # progress before the final 30 rendered frames.
        max_continuity_gap = 30
        baseline_continuity_ok = (
            baseline.get("max_main_loop_gap", max_continuity_gap + 1)
            <= max_continuity_gap
            and baseline.get("last_main_loop_frame", -1)
            >= args.frames - max_continuity_gap
        )
        candidate_continuity_ok = (
            candidate.get("max_main_loop_gap", max_continuity_gap + 1)
            <= max_continuity_gap
            and candidate.get("last_main_loop_frame", -1)
            >= args.frames - max_continuity_gap
        )
        passed = (
            baseline["breakpoints_available"]
            and candidate["breakpoints_available"]
            and baseline["frames"] == args.frames
            and candidate["frames"] == args.frames
            and baseline["final_scene"] == target + 2
            and candidate["final_scene"] == target + 2
            and baseline["expected_scene_frames"] == args.frames
            and candidate_scene_ok
            and baseline_continuity_ok
            and candidate_continuity_ok
            and abs(1.0 - ratio) <= args.tolerance + 1e-9
        )
        row = {
            "target": target,
            "stage": target + 1,
            "ratio": round(ratio, 4),
            "candidate_scene_ok": candidate_scene_ok,
            "candidate_scene_mismatch_frames": candidate_scene_mismatch_frames,
            "candidate_dma_unreadable_scene_samples": (
                dma_unreadable_scene_samples
            ),
            "candidate_compiler_unreadable_scene_samples": (
                compiler_unreadable_scene_samples
            ),
            "candidate_non_dma_scene_mismatch_frames": (
                non_dma_scene_mismatch_frames
            ),
            "max_continuity_gap": max_continuity_gap,
            "baseline_continuity_ok": baseline_continuity_ok,
            "candidate_continuity_ok": candidate_continuity_ok,
            "passed": passed,
            "original": baseline,
            "dx": candidate,
        }
        rows.append(row)
        print(
            f"Stage {target + 1}: original={baseline_hits} dx={candidate_hits} "
            f"ratio={ratio:.3f} scroll={baseline['scroll_changes']}/"
            f"{candidate['scroll_changes']} {'PASS' if passed else 'FAIL'}"
        )
        if not passed:
            reasons = []
            if abs(1.0 - ratio) > args.tolerance + 1e-9:
                reasons.append(f"throughput ratio {ratio:.3f}")
            if not candidate_scene_ok:
                reasons.append("scene mismatch")
            if not baseline_continuity_ok:
                reasons.append("baseline main-loop continuity missing")
            if not candidate_continuity_ok:
                reasons.append("candidate main-loop continuity missing")
            failures.append(
                f"Stage {target + 1}: " + (", ".join(reasons) or "gate failed")
            )

    manifest = {
        "status": "pass" if not failures else "fail",
        "mode": args.input_mode,
        "frames": args.frames,
        "tolerance": args.tolerance,
        "original_rom_md5": md5(original),
        "dx_rom_md5": md5(dx),
        "rows": rows,
        "failures": failures,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"Receipt: {manifest_path}")
        return 1
    print(f"PASS: selected stage-speed matrix is within tolerance.")
    print(f"Receipt: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
