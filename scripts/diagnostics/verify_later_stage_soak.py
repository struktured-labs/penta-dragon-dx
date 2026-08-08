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
BANK13 = 13 * 0x4000
NATIVE_BG0_ALIAS_ADDR = 0x6838
TITLE_PALETTE_SOURCE_ADDR = 0x6800
LATER_STAGE_BG0_SOURCE_TABLE_ADDR = 0x4CE4


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
              attr_trace: bool, stream_trace: bool, wram_audit: bool,
              capture_stable: int, trace_addrs: str) -> Path:
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
    if stream_trace:
        env["SOAK_STREAM_TRACE"] = str(prefix.with_suffix(".stream-writers.tsv"))
    if trace_addrs:
        env["SOAK_TRACE_ADDRS"] = trace_addrs
    command = [mgba]
    # The Qt frontend accepts --fastforward; mgba-headless already runs as
    # fast as possible and rejects that option.
    if (screenshots or attr_trace or stream_trace or wram_audit) and "mgba-qt" in Path(mgba).name:
        command.append("--fastforward")
    command.extend(["--script", str(PROBE), str(rom)])
    error_log = prefix.with_suffix(".emulator.log").open("wb")
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=error_log,
        stderr=subprocess.STDOUT,
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
        error_log.close()


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
        "--stream-trace", action="store_true",
        help="trace direct Stage 5/7 packed-map writers after initial load",
    )
    parser.add_argument(
        "--trace-addrs", default="",
        help="comma-separated optional mGBA breakpoint addresses for diagnosis",
    )
    parser.add_argument(
        "--wram-audit", action="store_true",
        help="prove candidate fixed-WRAM ranges remain unchanged during play",
    )
    parser.add_argument(
        "--require-native-bg0", action="store_true",
        help=(
            "require every captured later-stage room to retain the candidate "
            "ROM's title-safe native BG0 alias"
        ),
    )
    parser.add_argument(
        "--require-stage-bg0", action="store_true",
        help=(
            "require every captured room to retain its Stage 2-7 palette "
            "selected by the candidate ROM's stage-source table"
        ),
    )
    parser.add_argument(
        "--require-stage-base-palette", action="store_true",
        help=(
            "require every captured Stage 2-7 scene LUT to retain its "
            "candidate-ROM YAML palette slot (plus BG5 lava overrides)"
        ),
    )
    parser.add_argument(
        "--require-semantic-pickups", action="store_true",
        help=(
            "require the route to encounter collision-audited pickup tiles; "
            "their exact palettes are always validated"
        ),
    )
    args = parser.parse_args()
    if args.capture_stable < 0:
        parser.error("--capture-stable must be non-negative")
    semantic_pickup_samples = 0
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
    native_bg0_offset = BANK13 + NATIVE_BG0_ALIAS_ADDR - 0x4000
    native_bg0 = args.rom.resolve().read_bytes()[
        native_bg0_offset:native_bg0_offset + 8
    ]
    if args.require_native_bg0 and len(native_bg0) != 8:
        parser.error("candidate ROM does not contain a complete native BG0 alias")
    rom_bytes = args.rom.resolve().read_bytes()
    source_table_offset = (
        BANK13 + LATER_STAGE_BG0_SOURCE_TABLE_ADDR - 0x4000
    )
    stage_source_lows = rom_bytes[source_table_offset:source_table_offset + 6]
    if args.require_stage_bg0 and len(stage_source_lows) != 6:
        parser.error("candidate ROM does not contain the Stage 2-7 BG0 table")
    if args.require_stage_base_palette and len(stage_source_lows) != 6:
        parser.error("candidate ROM does not contain the Stage 2-7 palette table")
    try:
        for stage in stages:
            target = stage - 1
            try:
                report = run_stage(
                    args.mgba, args.rom.resolve(), target, args.frames,
                    output, args.timeout, args.screenshots, args.attr_trace,
                    args.stream_trace, args.wram_audit, args.capture_stable,
                    args.trace_addrs,
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
                f"lava_mismatch={fields['lava_mismatch']} "
                f"pickup_expected={fields['pickup_expected']} "
                f"pickup_mismatch={fields['pickup_mismatch']} "
                f"material_expected={fields['material_expected']} "
                f"material_mismatch={fields['material_mismatch']}"
            )
            semantic_pickup_samples += fields["pickup_expected"]
            if fields["frames"] < args.frames:
                failures.append(f"Stage {target + 1}: stopped at {fields['frames']} frames")
            if fields["samples"] < 20:
                failures.append(f"Stage {target + 1}: too few stable samples")
            if (
                fields["unexpected"]
                or fields["unsafe"]
                or fields["lava_mismatch"]
                or fields["pickup_mismatch"]
                or fields["material_mismatch"]
            ):
                failures.append(f"Stage {target + 1}: invalid BG attributes observed")
            if stage == 4 and fields["material_expected"] == 0:
                failures.append("Stage 4: no floor/wall material cells observed")
            if args.wram_audit and fields["wram_changed"]:
                failures.append(
                    f"Stage {target + 1}: audited WRAM changed "
                    f"{fields['wram_changed']} times"
                )
            if fields["expected_scene"] not in scenes:
                failures.append(f"Stage {target + 1}: expected scene was never sampled")
            if len(rooms) < 2:
                failures.append(f"Stage {target + 1}: exercised only {len(rooms)} room")
            if args.require_native_bg0:
                bg0_mismatches: list[str] = []
                for room in rooms:
                    bgp = output / f"stage{target + 1}.room{room:02X}.bgp.bin"
                    if not bgp.is_file() or len(bgp.read_bytes()) != 64:
                        bg0_mismatches.append(f"{room:02X}:missing")
                        continue
                    observed_bg0 = bgp.read_bytes()[:8]
                    if observed_bg0 != native_bg0:
                        bg0_mismatches.append(
                            f"{room:02X}:{observed_bg0.hex().upper()}"
                        )
                print(
                    f"Stage {target + 1}: native_bg0="
                    f"{'PASS' if not bg0_mismatches else 'FAIL'} "
                    f"expected={native_bg0.hex().upper()}"
                )
                if bg0_mismatches:
                    failures.append(
                        f"Stage {target + 1}: non-native BG0 in "
                        + ",".join(bg0_mismatches)
                    )
            if args.require_stage_bg0:
                source_low = stage_source_lows[target - 1]
                source_offset = (
                    BANK13 + TITLE_PALETTE_SOURCE_ADDR - 0x4000
                    + source_low
                )
                expected_bg0 = rom_bytes[source_offset:source_offset + 8]
                bg0_mismatches: list[str] = []
                for room in rooms:
                    bgp = output / f"stage{target + 1}.room{room:02X}.bgp.bin"
                    if not bgp.is_file() or len(bgp.read_bytes()) != 64:
                        bg0_mismatches.append(f"{room:02X}:missing")
                        continue
                    observed_bg0 = bgp.read_bytes()[:8]
                    if observed_bg0 != expected_bg0:
                        bg0_mismatches.append(
                            f"{room:02X}:{observed_bg0.hex().upper()}"
                        )
                print(
                    f"Stage {target + 1}: stage_bg0="
                    f"{'PASS' if not bg0_mismatches else 'FAIL'} "
                    f"source=$68{source_low:02X} "
                    f"expected={expected_bg0.hex().upper()}"
                )
                if bg0_mismatches:
                    failures.append(
                        f"Stage {target + 1}: wrong stage BG0 in "
                        + ",".join(bg0_mismatches)
                    )
            if args.require_stage_base_palette:
                expected_slot = stage_source_lows[target - 1] // 8
                allowed_slots = {expected_slot}
                if target + 1 in (5, 7):
                    allowed_slots.add(5)
                lut_mismatches: list[str] = []
                for room in rooms:
                    lut = output / f"stage{target + 1}.room{room:02X}.bg-lut.bin"
                    if not lut.is_file() or len(lut.read_bytes()) != 256:
                        lut_mismatches.append(f"{room:02X}:missing")
                        continue
                    observed_slots = set(lut.read_bytes())
                    if not observed_slots <= allowed_slots or expected_slot not in observed_slots:
                        lut_mismatches.append(
                            f"{room:02X}:"
                            + ",".join(str(value) for value in sorted(observed_slots))
                        )
                print(
                    f"Stage {target + 1}: stage_base_palette="
                    f"{'PASS' if not lut_mismatches else 'FAIL'} "
                    f"expected=BG{expected_slot} "
                    f"allowed={sorted(allowed_slots)}"
                )
                if lut_mismatches:
                    failures.append(
                        f"Stage {target + 1}: wrong scene LUT in "
                        + ",".join(lut_mismatches)
                    )
        if args.require_semantic_pickups and semantic_pickup_samples == 0:
            failures.append(
                "no collision-audited later-stage pickup tile was observed"
            )
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
