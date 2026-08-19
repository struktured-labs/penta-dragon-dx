"""Phantom-sound verification.

Runs phantom_d887.lua against ROM, then compares D887 transition count to the
vanilla baseline. Vanilla coalesces D887 writes via the original game's sound
engine; modded builds with bank-switch bugs (FF99 / trampoline / VBlank
overrun) lose coalescence, producing many more transitions.

The vanilla baseline is cached on disk (keyed by ROM mtime+size) so we don't
re-measure it on every invocation. Use --rebaseline to force a fresh measure.

Usage:
    python verify_phantom_d887.py <rom> [--baseline-rom <vanilla>]
                                        [--frames N] [--tolerance 1.5]
                                        [--rebaseline]

Exit 0 = PASS (transitions <= tolerance × baseline)
Exit 1 = FAIL (more transitions than allowed)
Exit 2 = harness error
"""
from __future__ import annotations
import json
import os
import sys
import subprocess
import tempfile
import argparse
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MGBA_QT = PROJECT_ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("phantom_d887.lua")
# These are the two intentional commands reachable on this deterministic
# Stage-1 route. Both are direct vanilla call sites:
#   $57AF: LD A,$26; RST $38
#   $799F: LD A,$0C; RST $38
ROUTE_COMMAND_VALUES = {0x0C, 0x26}
BASELINE_CACHE = Path(
    os.environ.get(
        "PENTA_PHANTOM_BASELINE_CACHE",
        str(PROJECT_ROOT / "tmp" / "penta_phantom_d887_baseline.json"),
    )
)


def parse_probe_metrics(text: str) -> dict:
    metrics = {}
    for line in text.splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key == "command_values":
            parsed = {}
            for item in filter(None, value.split(",")):
                command, count = item.split(":", 1)
                parsed[int(command, 16)] = int(count)
            metrics[key] = parsed
        elif key == "transitions_per_second":
            metrics[key] = float(value)
        else:
            try:
                metrics[key] = int(value)
            except ValueError:
                continue
    return metrics


def run_d887(rom_path: str, frames: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="penta-phantom-") as temp:
        out = Path(temp) / "result.txt"
        env = os.environ.copy()
        env["STATE_PATH"] = str(out)
        env["MEASURE_FRAMES"] = str(frames)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["SDL_AUDIODRIVER"] = "dummy"
        cmd = [
            str(MGBA_QT),
            "-C",
            f"savegamePath={temp}",
            "-C",
            f"savestatePath={temp}",
            str(Path(rom_path).resolve()),
            "--script",
            str(PROBE),
            "-l",
            "0",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=temp,
                env=env,
                capture_output=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(
                f"phantom_d887 timed out after 180s for {rom_path}"
            ) from error

        # mGBA-Qt can briefly retain its application lock after a scripted
        # instance exits. This matters when --raw-output-dir measures vanilla
        # and the candidate back-to-back in one Python process.
        if not out.is_file() or out.stat().st_size < 10:
            time.sleep(0.5)
            proc = subprocess.run(
                cmd,
                cwd=temp,
                env=env,
                capture_output=True,
                timeout=180,
            )

        if not out.is_file() or out.stat().st_size < 10:
            raise RuntimeError(
                f"phantom_d887 produced no output for {rom_path}\n"
                f"  exit code: {proc.returncode}\n"
                f"  cmd: {' '.join(cmd)}\n"
                f"  stdout: {proc.stdout.decode(errors='replace')[:500]}\n"
                f"  stderr: {proc.stderr.decode(errors='replace')[:500]}"
            )
        text = out.read_text()

    metrics = parse_probe_metrics(text)
    transitions = metrics.get("transitions")
    if transitions is None:
        raise RuntimeError(
            f"could not parse transitions from phantom_d887 output:\n{text[:500]}"
        )
    return {"transitions": transitions, "metrics": metrics, "raw": text}


def _baseline_key(rom_path: str, frames: int) -> str:
    st = os.stat(rom_path)
    return f"{os.path.abspath(rom_path)}|{st.st_size}|{int(st.st_mtime)}|{frames}"


def get_baseline(rom_path: str, frames: int, force: bool = False) -> int:
    BASELINE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    key = _baseline_key(rom_path, frames)
    if not force and BASELINE_CACHE.exists():
        try:
            cache = json.loads(BASELINE_CACHE.read_text())
        except (OSError, ValueError):
            cache = {}
        if key in cache:
            print(f"  baseline (cached): {cache[key]} D887 transitions")
            return cache[key]
    else:
        cache = {}
        if BASELINE_CACHE.exists():
            try:
                cache = json.loads(BASELINE_CACHE.read_text())
            except (OSError, ValueError):
                cache = {}

    print(f"  measuring baseline ({rom_path}, {frames} frames)...")
    baseline = run_d887(rom_path, frames)
    cache[key] = baseline['transitions']
    try:
        BASELINE_CACHE.write_text(json.dumps(cache, indent=2))
    except OSError as e:
        sys.stderr.write(f"  warning: could not write baseline cache: {e}\n")
    print(f"  baseline: {baseline['transitions']} D887 transitions")
    return baseline['transitions']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rom")
    ap.add_argument("--baseline-rom",
                    default="rom/Penta Dragon (J).gb",
                    help="Vanilla ROM for D887 baseline (default: vanilla)")
    ap.add_argument("--frames", type=int, default=600,
                    help="Total frames to monitor (default 600 ≈ 10s)")
    ap.add_argument("--tolerance", type=float, default=1.5,
                    help="PASS if rom transitions <= tolerance × baseline (default 1.5)")
    ap.add_argument("--clean-pulse-tolerance", type=float, default=2.0,
                    help="Hard ceiling for structurally clean, route-valid command pulses")
    ap.add_argument("--rebaseline", action="store_true",
                    help="Force fresh baseline measurement (ignore cache)")
    ap.add_argument("--raw-output-dir", type=Path,
                    help="Write the candidate transition trace here")
    args = ap.parse_args()

    print(f"Baseline ({args.baseline_rom}):")
    baseline_transitions = get_baseline(
        args.baseline_rom, args.frames, force=args.rebaseline
    )

    print(f"Measuring {args.rom}...")
    candidate = run_d887(args.rom, args.frames)
    print(f"  candidate: {candidate['transitions']} D887 transitions")
    metrics = candidate["metrics"]
    print(
        "  pulse shape: "
        f"commands={metrics.get('command_pulses', '?')}, "
        f"clears={metrics.get('clear_pulses', '?')}, "
        f"chained={metrics.get('chained_commands', '?')}, "
        f"unpaired={metrics.get('unpaired_commands', '?')}, "
        f"max_nonzero_run={metrics.get('max_nonzero_run', '?')}"
    )
    values = metrics.get("command_values", {})
    if values:
        print(
            "  command values: "
            + ", ".join(f"{value:02X}×{count}" for value, count in sorted(values.items()))
        )
    if args.raw_output_dir:
        args.raw_output_dir.mkdir(parents=True, exist_ok=True)
        (args.raw_output_dir / "candidate.txt").write_text(candidate["raw"])

    threshold = max(int(baseline_transitions * args.tolerance), 5)
    print(f"\nThreshold: {threshold} (= {args.tolerance} × baseline, min 5)")

    semantic_metrics_present = all(
        key in metrics
        for key in (
            "command_pulses",
            "clear_pulses",
            "chained_commands",
            "unpaired_commands",
            "max_nonzero_run",
            "command_values",
        )
    )
    structurally_clean = (
        semantic_metrics_present
        and metrics["chained_commands"] == 0
        and metrics["unpaired_commands"] == 0
        and metrics["max_nonzero_run"] <= 1
        and set(metrics["command_values"]).issubset(ROUTE_COMMAND_VALUES)
    )
    clean_ceiling = max(
        int(baseline_transitions * args.clean_pulse_tolerance),
        8,
    )

    if candidate["transitions"] <= threshold:
        print(f"\nPASS: candidate {candidate['transitions']} ≤ threshold {threshold} "
              f"(baseline-equivalent D887 behavior).")
        sys.exit(0)
    elif structurally_clean and candidate["transitions"] <= clean_ceiling:
        print(
            f"\nPASS: candidate exceeds the raw progress-sensitive threshold "
            f"({candidate['transitions']} > {threshold}) but all commands are "
            f"one-frame, paired, route-valid pulses and remain below the clean "
            f"hard ceiling {clean_ceiling}."
        )
        sys.exit(0)
    else:
        print(f"\nFAIL: candidate {candidate['transitions']} > threshold {threshold}\n"
              f"      Extra D887 churn suggests phantom-sound regression "
              f"(+{candidate['transitions']-baseline_transitions} vs baseline).")
        sys.exit(1)


if __name__ == "__main__":
    main()
