#!/usr/bin/env python3
"""
Speed Verification for Penta Dragon DX.

Runs both original and DX ROMs to the real dungeon, applies identical input
for 10 seconds, and compares game-state advancement rates.

PASS criteria: DX scroll/advancement within +/-5% of original.

Usage:
    uv run python scripts/verify_speed.py
    uv run python scripts/verify_speed.py --dx-rom rom/working/custom.gb

Exit codes:
    0 = PASS
    1 = FAIL
    2 = ERROR
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MGBA = os.getenv("MGBA_PATH", "/home/struktured/bin/mgba-qt")
ORIG_ROM = PROJECT_ROOT / "rom" / "Penta Dragon (J).gb"
DEFAULT_DX_ROM = PROJECT_ROOT / "rom" / "working" / "penta_dragon_dx_v288.gb"
LUA_SCRIPT = PROJECT_ROOT / "scripts" / "verify_speed.lua"

TOLERANCE = 0.05  # 5% deviation allowed
FLOAT_EPSILON = 1e-9


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stop_process(process: subprocess.Popen) -> None:
    """Stop only the xvfb-run process owned by this probe."""
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def run_speed_test(
    rom_path: Path,
    label: str,
    output_dir: Path,
    timeout: float,
    input_mode: str,
) -> dict:
    """Run speed test on a single ROM."""
    run_dir = output_dir / f"run-{label}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "result.json"
    marker = run_dir / f"DONE_VERIFY_SPEED_{label}"
    report_path.unlink(missing_ok=True)
    marker.unlink(missing_ok=True)

    env = os.environ.copy()
    env["VERIFY_OUTPUT"] = str(report_path)
    env["VERIFY_ROM_LABEL"] = label
    env["VERIFY_INPUT_MODE"] = input_mode
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    cmd = [
        "xvfb-run",
        "-a",
        MGBA,
        "-C",
        f"savegamePath={run_dir}",
        "-C",
        f"savestatePath={run_dir}",
        "--fastforward",
        str(rom_path),
        "--script",
        str(LUA_SCRIPT),
        "-l",
        "0",
    ]

    log_path = run_dir / "mgba.log"
    log_handle = log_path.open("w")
    try:
        process = subprocess.Popen(
            cmd,
            env=env,
            cwd=run_dir,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        log_handle.close()
        return {"error": f"mgba-qt not found at {MGBA}"}

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if report_path.is_file() and marker.is_file():
            break
        if process.poll() is not None:
            break
        time.sleep(0.05)
    stop_process(process)
    log_handle.close()

    if not report_path.exists():
        return {
            "error": f"No report generated for {label}",
            "returncode": process.returncode,
            "log": str(log_path),
        }

    result = json.loads(report_path.read_text())
    result.update(
        rom=str(rom_path),
        rom_md5=md5(rom_path),
        log=str(log_path),
    )
    return result


def compare_results(orig: dict, dx: dict) -> dict:
    """Compare original and DX speed metrics."""
    if "error" in orig or "error" in dx:
        return {
            "passed": False,
            "error": orig.get("error", "") or dx.get("error", ""),
            "original": orig,
            "dx": dx,
        }

    metrics = {}
    all_pass = True

    # A single breakpoint at the stock bank-0 main-loop entry is the direct
    # throughput receipt. Missing breakpoint support is a gate failure; falling
    # back to the old indirect counters would recreate the false PASS this
    # probe was corrected to prevent.
    orig_breakpoint = orig.get("main_loop_breakpoint_available") is True
    dx_breakpoint = dx.get("main_loop_breakpoint_available") is True
    breakpoint_available = orig_breakpoint and dx_breakpoint
    metrics["main_loop_breakpoint_available"] = {
        "original": orig_breakpoint,
        "dx": dx_breakpoint,
        "ratio": 1.0 if breakpoint_available else 0.0,
        "within_tolerance": breakpoint_available,
    }
    if not breakpoint_available:
        all_pass = False

    original_scene = orig.get("final_scene", -1)
    dx_scene = dx.get("final_scene", -1)
    scene_matches = original_scene == 0x02 and dx_scene == 0x02
    metrics["final_scene"] = {
        "original": original_scene,
        "dx": dx_scene,
        "ratio": 1.0 if scene_matches else 0.0,
        "within_tolerance": scene_matches,
    }
    if not scene_matches:
        all_pass = False

    orig_loop_hits = orig.get("main_loop_hits", 0)
    dx_loop_hits = dx.get("main_loop_hits", 0)
    loop_ratio = dx_loop_hits / orig_loop_hits if orig_loop_hits else 0.0
    loop_within_tolerance = (
        breakpoint_available
        and orig_loop_hits > 0
        and abs(1.0 - loop_ratio) <= TOLERANCE + FLOAT_EPSILON
    )
    metrics["main_loop_hits"] = {
        "original": orig_loop_hits,
        "dx": dx_loop_hits,
        "ratio": round(loop_ratio, 3),
        "within_tolerance": loop_within_tolerance,
    }
    if not loop_within_tolerance:
        all_pass = False

    # These counters are deterministic for the scripted route and measure
    # whether the stock gameplay cadence still advances at the same rate.
    for key in [
        "scroll_ticks",
        "dc81_changes",
    ]:
        orig_val = orig.get(key, 0)
        dx_val = dx.get(key, 0)

        if orig_val == 0:
            # Can't compare if original has no movement
            ratio = 1.0
            within_tolerance = True
        else:
            ratio = dx_val / orig_val
            within_tolerance = (
                abs(1.0 - ratio) <= TOLERANCE + FLOAT_EPSILON
            )

        metrics[key] = {
            "original": orig_val,
            "dx": dx_val,
            "ratio": round(ratio, 3),
            "within_tolerance": within_tolerance,
        }
        if not within_tolerance:
            all_pass = False

    # OAM and Sara-state activity are retained as diagnostic evidence. Enemy
    # spawn/RNG differences and Sara's room-transition coordinate resets make
    # them unsuitable as hard parity gates.
    for key in [
        "emitter_breakpoints_available",
        "central_emitter_hits",
        "free_emitter_hits",
        "oam_changes",
        "enemy_oam_changes",
        "sara_oam_changes",
        "sara_oam_full_changes",
        "sara_x_changes",
        "sara_x_distance",
        "sara_x_first",
        "sara_x_last",
        "sara_state_changes",
    ]:
        orig_val = orig.get(key, 0)
        dx_val = dx.get(key, 0)
        metrics[key] = {
            "original": orig_val,
            "dx": dx_val,
            "ratio": round(dx_val / orig_val, 3) if orig_val else 1.0,
            "within_tolerance": True,
            "info_only": True,
        }

    original_start = orig.get("game_start_frame", 0)
    dx_start = dx.get("game_start_frame", 0)
    start_ratio = dx_start / original_start if original_start else 1.0
    start_within_tolerance = (
        original_start > 0
        and dx_start <= original_start * (1.0 + TOLERANCE)
    )
    metrics["game_start_frame"] = {
        "original": original_start,
        "dx": dx_start,
        "extra_frames": dx_start - original_start,
        "ratio": round(start_ratio, 3),
        "within_tolerance": start_within_tolerance,
    }
    if not start_within_tolerance:
        all_pass = False

    original_dungeon = orig.get("dungeon_start_frame", 0)
    dx_dungeon = dx.get("dungeon_start_frame", 0)
    dungeon_ratio = (
        dx_dungeon / original_dungeon if original_dungeon else 1.0
    )
    metrics["dungeon_start_frame"] = {
        "original": original_dungeon,
        "dx": dx_dungeon,
        "extra_frames": dx_dungeon - original_dungeon,
        "ratio": round(dungeon_ratio, 3),
        "within_tolerance": True,
        "info_only": True,
    }

    return {
        "status": "pass" if all_pass else "fail",
        "passed": all_pass,
        "tolerance": TOLERANCE,
        "metrics": metrics,
        "original": orig,
        "dx": dx,
    }


def main():
    parser = argparse.ArgumentParser(description="Speed Verification")
    parser.add_argument("--dx-rom", default=str(DEFAULT_DX_ROM),
                        help="DX ROM path")
    parser.add_argument("--orig-rom", default=str(ORIG_ROM),
                        help="Original ROM path")
    parser.add_argument(
        "--output",
        type=Path,
        help="receipt directory (default: a persistent directory under /tmp)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="timeout per ROM in seconds (default: 30)",
    )
    parser.add_argument(
        "--input-mode",
        choices=("right", "stationary"),
        default="right",
        help="gameplay input during the 600-frame measurement",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    dx_rom = Path(args.dx_rom).resolve()
    if not dx_rom.exists():
        fixed = PROJECT_ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
        if fixed.exists():
            dx_rom = fixed.resolve()
        else:
            print(f"ERROR: DX ROM not found: {args.dx_rom}")
            sys.exit(2)

    orig_rom = Path(args.orig_rom).resolve()
    if not orig_rom.exists():
        print(f"ERROR: Original ROM not found: {args.orig_rom}")
        sys.exit(2)

    output_dir = (
        args.output.resolve()
        if args.output
        else Path(tempfile.mkdtemp(prefix="penta-speed-parity-"))
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()

    print("[SPEED] Running original ROM...")
    orig_result = run_speed_test(
        orig_rom, "original", output_dir, args.timeout, args.input_mode
    )

    print("[SPEED] Running DX ROM...")
    dx_result = run_speed_test(
        dx_rom, "dx", output_dir, args.timeout, args.input_mode
    )

    comparison = compare_results(orig_result, dx_result)
    comparison.update(
        started_at=started_at,
        finished_at=utc_now(),
        original_rom=str(orig_rom),
        original_rom_md5=md5(orig_rom),
        dx_rom=str(dx_rom),
        dx_rom_md5=md5(dx_rom),
    )

    if args.json:
        print(json.dumps(comparison, indent=2))
    else:
        passed = comparison.get("passed", False)
        print(f"\n[SPEED] {'PASS' if passed else 'FAIL'}")

        if "metrics" in comparison:
            for key, m in comparison["metrics"].items():
                status = "OK" if m["within_tolerance"] else "DEVIATION"
                print(f"  {key}: orig={m['original']} dx={m['dx']} "
                      f"ratio={m['ratio']:.3f} [{status}]")

        if comparison.get("error"):
            print(f"  Error: {comparison['error']}")

    # Save full report
    report_path = output_dir / "manifest.json"
    report_path.write_text(json.dumps(comparison, indent=2) + "\n")
    print(f"Receipt: {report_path}")

    sys.exit(0 if comparison.get("passed", False) else 1)


if __name__ == "__main__":
    main()
