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
from pathlib import Path


BASELINE_CACHE = Path(__file__).parent / ".phantom_d887_baseline.json"


def run_d887(rom_path: str, frames: int) -> dict:
    out = tempfile.NamedTemporaryFile(suffix=".txt", delete=False).name
    env = os.environ.copy()
    env["STATE_PATH"] = out
    env["MEASURE_FRAMES"] = str(frames)
    env["DISPLAY"] = ":0"
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    env["SDL_AUDIODRIVER"] = "dummy"
    cmd = ["/home/struktured/projects/penta-dragon-dx-claude/mgba-qt.sh", rom_path,
           "--script", "scripts/probes/phantom_d887.lua", "-l", "0"]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, timeout=180)
    except subprocess.TimeoutExpired as e:
        try: os.unlink(out)
        except OSError: pass
        raise RuntimeError(f"phantom_d887 timed out after 180s for {rom_path}") from e

    if not os.path.exists(out) or os.path.getsize(out) < 10:
        try: os.unlink(out)
        except OSError: pass
        raise RuntimeError(
            f"phantom_d887 produced no output for {rom_path}\n"
            f"  exit code: {proc.returncode}\n"
            f"  cmd: {' '.join(cmd)}\n"
            f"  stdout: {proc.stdout.decode(errors='replace')[:500]}\n"
            f"  stderr: {proc.stderr.decode(errors='replace')[:500]}"
        )
    with open(out) as fh:
        text = fh.read()
    try: os.unlink(out)
    except OSError: pass

    transitions = None
    for line in text.splitlines():
        if line.startswith("transitions="):
            transitions = int(line.split("=")[1])
            break
    if transitions is None:
        raise RuntimeError(
            f"could not parse transitions from phantom_d887 output:\n{text[:500]}"
        )
    return {"transitions": transitions, "raw": text}


def _baseline_key(rom_path: str, frames: int) -> str:
    st = os.stat(rom_path)
    return f"{os.path.abspath(rom_path)}|{st.st_size}|{int(st.st_mtime)}|{frames}"


def get_baseline(rom_path: str, frames: int, force: bool = False) -> int:
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
    ap.add_argument("--rebaseline", action="store_true",
                    help="Force fresh baseline measurement (ignore cache)")
    args = ap.parse_args()

    print(f"Baseline ({args.baseline_rom}):")
    baseline_transitions = get_baseline(
        args.baseline_rom, args.frames, force=args.rebaseline
    )

    print(f"Measuring {args.rom}...")
    candidate = run_d887(args.rom, args.frames)
    print(f"  candidate: {candidate['transitions']} D887 transitions")

    threshold = max(int(baseline_transitions * args.tolerance), 5)
    print(f"\nThreshold: {threshold} (= {args.tolerance} × baseline, min 5)")

    if candidate['transitions'] > threshold:
        print(f"\nFAIL: candidate {candidate['transitions']} > threshold {threshold}\n"
              f"      Extra D887 churn suggests phantom-sound regression "
              f"(+{candidate['transitions']-baseline_transitions} vs baseline).")
        sys.exit(1)
    else:
        print(f"\nPASS: candidate {candidate['transitions']} ≤ threshold {threshold} "
              f"(baseline-equivalent D887 behavior).")
        sys.exit(0)


if __name__ == "__main__":
    main()
