#!/usr/bin/env python3
"""
GB Game Verifier — Compare two ROM runs frame-by-frame.

Runs an original ROM and a remake ROM with identical inputs,
captures memory state + screenshots at regular intervals,
then diffs everything and reports divergences.

Usage:
    uv run python scripts/verifier/compare.py \\
        --og "rom/original.gb" \\
        --remake "rom/working/remake.gbc" \\
        --input scripts/verifier/inputs/game_start.csv \\
        --frames 3600 --interval 30
"""
import argparse
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from dataclasses import dataclass, field

try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


@dataclass
class FrameState:
    frame: int
    keys: int
    memory: dict = field(default_factory=dict)
    screenshot_path: str = ""


@dataclass
class Divergence:
    frame: int
    field: str
    og_value: str
    remake_value: str
    severity: str = "info"  # info, warning, error


def run_rom(rom_path: str, dump_dir: str, input_file: str,
            max_frames: int, interval: int) -> list[FrameState]:
    """Run a ROM in mGBA headlessly, dump state every N frames."""
    env = os.environ.copy()
    env["VERIFY_DUMP_DIR"] = dump_dir
    env["VERIFY_INTERVAL"] = str(interval)
    env["VERIFY_MAX_FRAMES"] = str(max_frames)
    env["VERIFY_INPUT_FILE"] = input_file or ""
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    lua_script = str(Path(__file__).parent / "dual_run.lua")
    timeout_sec = max_frames // 30 + 30  # generous timeout

    # Start Xvfb
    xvfb = subprocess.Popen(
        ["Xvfb", ":98", "-screen", "0", "640x480x24"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    env["DISPLAY"] = ":98"

    try:
        subprocess.run(
            ["mgba-qt", rom_path, "--script", lua_script, "-l", "0"],
            env=env, timeout=timeout_sec,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        pass
    finally:
        xvfb.terminate()
        xvfb.wait()

    # Parse state CSV
    states = []
    csv_path = os.path.join(dump_dir, "state.csv")
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                st = FrameState(
                    frame=int(row["frame"]),
                    keys=int(row["keys"]),
                    memory={k: int(v) for k, v in row.items()
                            if k not in ("frame", "keys")},
                    screenshot_path=os.path.join(
                        dump_dir,
                        f"frame_{int(row['frame']):06d}.png"
                    )
                )
                states.append(st)
    return states


def compare_frames(og_states: list[FrameState],
                   rm_states: list[FrameState]) -> list[Divergence]:
    """Compare two state sequences and return divergences."""
    divergences = []

    # Match by frame number
    og_by_frame = {s.frame: s for s in og_states}
    rm_by_frame = {s.frame: s for s in rm_states}

    all_frames = sorted(set(og_by_frame.keys()) | set(rm_by_frame.keys()))

    for fr in all_frames:
        og = og_by_frame.get(fr)
        rm = rm_by_frame.get(fr)

        if og is None:
            divergences.append(Divergence(fr, "MISSING", "no data", "has data", "warning"))
            continue
        if rm is None:
            divergences.append(Divergence(fr, "MISSING", "has data", "no data", "warning"))
            continue

        # Compare memory values
        all_keys = set(og.memory.keys()) | set(rm.memory.keys())
        for key in sorted(all_keys):
            og_val = og.memory.get(key, -1)
            rm_val = rm.memory.get(key, -1)
            if og_val != rm_val:
                severity = "error" if key in ("SCX", "SCY", "boss_flag", "gameplay") else "warning"
                divergences.append(Divergence(
                    fr, key, str(og_val), str(rm_val), severity
                ))

        # Compare screenshots if PIL available
        if HAS_PIL and os.path.exists(og.screenshot_path) and os.path.exists(rm.screenshot_path):
            try:
                og_img = np.array(Image.open(og.screenshot_path).convert("L"))
                rm_img = np.array(Image.open(rm.screenshot_path).convert("L"))
                if og_img.shape == rm_img.shape:
                    diff = np.abs(og_img.astype(int) - rm_img.astype(int))
                    pct_diff = (diff > 10).sum() / diff.size * 100
                    if pct_diff > 5.0:
                        divergences.append(Divergence(
                            fr, "screenshot",
                            f"OG frame", f"{pct_diff:.1f}% pixels differ",
                            "warning" if pct_diff < 30 else "error"
                        ))
            except Exception:
                pass

    return divergences


def generate_report(divergences: list[Divergence], output_path: str = None):
    """Generate a human-readable divergence report."""
    lines = []
    lines.append("=" * 60)
    lines.append("GB GAME VERIFIER — DIVERGENCE REPORT")
    lines.append("=" * 60)

    errors = [d for d in divergences if d.severity == "error"]
    warnings = [d for d in divergences if d.severity == "warning"]
    infos = [d for d in divergences if d.severity == "info"]

    lines.append(f"Total: {len(divergences)} divergences "
                 f"({len(errors)} errors, {len(warnings)} warnings, {len(infos)} info)")
    lines.append("")

    if errors:
        lines.append("--- ERRORS (behavioral differences) ---")
        for d in errors[:50]:
            lines.append(f"  Frame {d.frame:6d} | {d.field:15s} | OG={d.og_value:>6s} RM={d.remake_value}")
        if len(errors) > 50:
            lines.append(f"  ... and {len(errors) - 50} more errors")
        lines.append("")

    if warnings:
        lines.append("--- WARNINGS ---")
        for d in warnings[:30]:
            lines.append(f"  Frame {d.frame:6d} | {d.field:15s} | OG={d.og_value:>6s} RM={d.remake_value}")
        if len(warnings) > 30:
            lines.append(f"  ... and {len(warnings) - 30} more warnings")
        lines.append("")

    # Summary by field
    fields = {}
    for d in divergences:
        fields.setdefault(d.field, []).append(d)
    lines.append("--- SUMMARY BY FIELD ---")
    for field_name, divs in sorted(fields.items(), key=lambda x: -len(x[1])):
        lines.append(f"  {field_name:15s}: {len(divs)} divergences")

    report = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)

    print(report)
    return report


def record_inputs(rom_path: str, output_file: str, max_frames: int = 3600):
    """Record inputs from a scripted playthrough for replay."""
    # This generates a standard input sequence: start game, play
    lines = []
    # Title: DOWN then A to select GAME START
    lines.append("130,128")   # DOWN
    lines.append("133,0")
    lines.append("150,1")     # A
    lines.append("153,0")
    # Skip stage intro
    lines.append("250,1")     # A
    lines.append("253,0")
    # Gameplay: alternate dodge + shoot
    for f in range(500, max_frames, 60):
        lines.append(f"{f},65")      # UP+A for 30 frames
        lines.append(f"{f+30},129")  # DOWN+A for 30 frames
    with open(output_file, "w") as f:
        f.write("\n".join(lines))
    print(f"Recorded {len(lines)} input events to {output_file}")


def main():
    parser = argparse.ArgumentParser(description="GB Game Verifier")
    parser.add_argument("--og", required=True, help="Original ROM path")
    parser.add_argument("--remake", required=True, help="Remake ROM path")
    parser.add_argument("--input", default="", help="Input recording CSV")
    parser.add_argument("--frames", type=int, default=3600, help="Max frames to compare")
    parser.add_argument("--interval", type=int, default=30, help="Dump interval (frames)")
    parser.add_argument("--report", default="tmp/verify_report.txt", help="Report output path")
    parser.add_argument("--record-inputs", action="store_true", help="Generate default input sequence")
    args = parser.parse_args()

    os.makedirs("tmp", exist_ok=True)

    if args.record_inputs:
        record_inputs(args.og, args.input or "tmp/verify_inputs.csv", args.frames)
        return

    input_file = args.input
    if not input_file:
        input_file = "tmp/verify_inputs.csv"
        record_inputs(args.og, input_file, args.frames)

    print(f"=== Running OG: {args.og} ===")
    og_dir = "tmp/verify_og"
    os.makedirs(og_dir, exist_ok=True)
    og_states = run_rom(args.og, og_dir, input_file, args.frames, args.interval)
    print(f"  Captured {len(og_states)} states")

    print(f"=== Running Remake: {args.remake} ===")
    rm_dir = "tmp/verify_rm"
    os.makedirs(rm_dir, exist_ok=True)
    rm_states = run_rom(args.remake, rm_dir, input_file, args.frames, args.interval)
    print(f"  Captured {len(rm_states)} states")

    print(f"=== Comparing ===")
    divergences = compare_frames(og_states, rm_states)

    generate_report(divergences, args.report)


if __name__ == "__main__":
    main()
