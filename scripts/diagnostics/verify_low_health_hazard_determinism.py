#!/usr/bin/env python3
"""Run the low-health hazard gate twice and require byte-exact evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
VERIFIER = Path(__file__).with_name("verify_low_health_flicker.py")
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
# The child verifier owns the checked-in mGBA singleflight launcher; this
# wrapper only sequences two children and never accepts an emulator override.


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def corpus_digest(directory: Path) -> str:
    value = hashlib.sha256()
    paths = [directory / "low-health.frames.tsv"]
    paths.extend(sorted(directory.glob("low-health.frame*.png")))
    for path in paths:
        value.update(path.name.encode())
        value.update(b"\0")
        value.update(path.read_bytes())
    return value.hexdigest()


def stable_summary(receipt: dict, directory: Path) -> dict:
    return {
        "rom_sha256": receipt["rom_sha256"],
        "music_transition_sample": receipt["music_transition_sample"],
        "healthy_samples": receipt["healthy_samples"],
        "low_health_frames": receipt["low_health_frames"],
        "scene0b_frames": receipt.get("scene0b_frames", 0),
        "candidate_runtime": receipt.get("candidate_runtime"),
        "hazard_publication_counters": receipt.get(
            "hazard_publication_counters"
        ),
        "dma_unreadable_samples": receipt["dma_unreadable_samples"],
        "compiler_unreadable_samples": receipt["compiler_unreadable_samples"],
        "bg_cram_variants": receipt["bg_cram_variants"],
        "maximum_unexpected_lut_mismatches": receipt[
            "maximum_unexpected_lut_mismatches"
        ],
        "hazard_mismatch_frames": receipt["hazard_mismatch_frames"],
        "render_metrics": receipt["render_metrics"],
        "checks": receipt["checks"],
        "passed": receipt["passed"],
        "native_capture": receipt.get("native_capture"),
        "frames_tsv_sha256": digest(directory / "low-health.frames.tsv"),
        "render_corpus_sha256": corpus_digest(directory),
    }


def rows(path: Path) -> list[dict[str, str]]:
    with path.open() as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def aligned_corpus_comparison(
    first: Path, second: Path, samples: int,
) -> dict[str, int | bool]:
    """Diagnostic only: inspect overlap after startup alignment (#67).

    mGBA can resume the same savestate on either side of one emulated frame.
    Comparing equal sample numbers therefore reports a false nondeterminism
    even when every rendered frame and machine state are identical with a
    one- or two-frame shift. Search only {-2,-1,0,+1,+2}, require the entire
    overlap to be exact, and record the selected shift. The two-frame bound
    is receipt-derived from the guarded post-copy path and still compares at
    least 412/414 rendered frames byte-for-byte; any state or image drift in
    that aligned corpus remains a hard failure. The deliberately injected health
    threshold is sample-indexed, so its two bookkeeping fields are verified
    independently by each child gate rather than compared across the shifted
    boundary.
    """
    first_rows = rows(first / "low-health.frames.tsv")
    second_rows = rows(second / "low-health.frames.tsv")
    ignored = {"sample", "frame", "health_phase", "hp_main"}
    best = {
        "passed": False,
        "shift": 99,
        "compared_frames": 0,
        "row_mismatches": samples,
        "image_mismatches": samples,
    }
    maximum_phase_shift = 2
    for shift in (0, -1, 1, -2, 2):
        first_start = max(0, -shift)
        second_start = max(0, shift)
        count = min(
            len(first_rows) - first_start,
            len(second_rows) - second_start,
        )
        row_mismatches = 0
        image_mismatches = 0
        for offset in range(count):
            left_index = first_start + offset
            right_index = second_start + offset
            left = first_rows[left_index]
            right = second_rows[right_index]
            if any(
                left[key] != right[key]
                for key in left
                if key not in ignored
            ):
                row_mismatches += 1
            left_png = first / f"low-health.frame{left_index + 1:04d}.png"
            right_png = second / f"low-health.frame{right_index + 1:04d}.png"
            if left_png.read_bytes() != right_png.read_bytes():
                image_mismatches += 1
        candidate = {
            "passed": (
                count >= samples - maximum_phase_shift
                and row_mismatches == 0
                and image_mismatches == 0
            ),
            "shift": shift,
            "compared_frames": count,
            "row_mismatches": row_mismatches,
            "image_mismatches": image_mismatches,
        }
        if candidate["passed"]:
            return candidate
        if (
            row_mismatches + image_mismatches
            < int(best["row_mismatches"]) + int(best["image_mismatches"])
        ):
            best = candidate
    return best


def exact_corpus_comparison(first: Path, second: Path, samples: int) -> dict:
    """#67: compare every delivered row/image without shifts or field masks.

    The child may deliver up to eight extra frames to finish an in-flight
    publication. Compare those too; neither missing nor extra frames disappear
    into an overlapping prefix.
    """
    traces = [rows(path / "low-health.frames.tsv") for path in (first, second)]
    row_differences = []
    image_differences = []
    count = max(map(len, traces))
    for index in range(count):
        pair = [trace[index] if index < len(trace) else None for trace in traces]
        if pair[0] != pair[1]:
            row_differences.append(index + 1)
        images = [path / f"low-health.frame{index + 1:04d}.png"
                  for path in (first, second)]
        if (not all(path.is_file() for path in images)
                or images[0].read_bytes() != images[1].read_bytes()):
            image_differences.append(index + 1)
    expected = {f"low-health.frame{index + 1:04d}.png" for index in range(count)}
    extra_images = [sorted(path.name for path in directory.glob("low-health.frame*.png")
                           if path.name not in expected)
                    for directory in (first, second)]
    return {
        "passed": (samples <= len(traces[0]) <= samples + 8
                   and len(traces[0]) == len(traces[1])
                   and not row_differences and not image_differences
                   and not any(extra_images)),
        "row_counts": list(map(len, traces)),
        "compared_frames": count,
        "row_mismatch_samples": row_differences,
        "image_mismatch_samples": image_differences,
        "extra_images": extra_images,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--state", type=Path,
                        help="exact fixture state forwarded to the child verifier")
    parser.add_argument("--boot-derived-state", action="store_true",
                        help="forward exact-state mode without normalization")
    parser.add_argument("--hazard-state-receipt", type=Path,
                        help="current hazard-state receipt for boot-derived mode")
    parser.add_argument("--trace-scanner", action="store_true",
                        help="forward read-only bank-qualified scanner tracing")
    # Receipt-qualified moving route: Up+A advances every packed hazard row,
    # reaches the native low-health music handoff at sample 400, and stops one
    # frame before the fixture's unavoidable death transition begins.
    parser.add_argument("--samples", type=int, default=417)
    parser.add_argument(
        "--post-trigger-keys", type=lambda value: int(value, 0), default=0x41
    )
    parser.add_argument("--require-music-transition", action="store_true")
    parser.add_argument("--require-scene0b-low-health", action="store_true")
    parser.add_argument("--scene0b-frames", type=int, default=120)
    parser.add_argument("--require-pulse-countdown", action="store_true")
    parser.add_argument("--require-hazard-attributes", action="store_true")
    parser.add_argument(
        "--require-hazard-publication-owner", action="store_true",
        help=(
            "require every completed hazard publication to reach the "
            "geometry scanner and semantic row writer in both replays"
        ),
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    replays = []
    statuses = []
    for index in (1, 2):
        replay = output / f"replay-{index}"
        replay.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(VERIFIER),
            str(args.rom.resolve()),
            "--samples", str(args.samples),
            "--post-trigger-keys", hex(args.post_trigger_keys),
            "--output", str(replay),
            "--timeout", str(args.timeout),
        ]
        if args.state is not None:
            command.extend(["--state", str(args.state.resolve())])
        if args.boot_derived_state:
            command.append("--boot-derived-state")
        if args.hazard_state_receipt is not None:
            command.extend(["--hazard-state-receipt",
                            str(args.hazard_state_receipt.resolve())])
        if args.trace_scanner:
            command.append("--trace-scanner")
        if args.require_music_transition:
            command.append("--require-music-transition")
        if args.require_scene0b_low_health:
            command.extend([
                "--require-scene0b-low-health",
                "--scene0b-frames", str(args.scene0b_frames),
            ])
        if args.require_pulse_countdown:
            command.append("--require-pulse-countdown")
        if args.require_hazard_attributes:
            command.append("--require-hazard-attributes")
        if args.require_hazard_publication_owner:
            command.append("--require-hazard-publication-owner")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout + 15,
            check=False,
        )
        (replay / "verifier.log").write_text(completed.stdout)
        statuses.append(completed.returncode)
        receipt_path = replay / "receipt.json"
        if not receipt_path.is_file():
            print(
                f"FAIL: replay {index} produced no receipt; "
                f"see {replay / 'verifier.log'}"
            )
            return 1
        receipt = json.loads(receipt_path.read_text())
        replays.append(stable_summary(receipt, replay))

    aligned = aligned_corpus_comparison(
        output / "replay-1", output / "replay-2", args.samples
    )
    exact = exact_corpus_comparison(
        output / "replay-1", output / "replay-2", args.samples
    )
    inner_passed = statuses == [0, 0] and all(
        replay["passed"] for replay in replays
    )
    checks = {
        "both low-health hazard replays pass": inner_passed,
        "full unshifted state trace and rendered corpus are byte-exact": (
            bool(exact["passed"])
        ),
        "complete native audio video state and input timeline are byte-exact": (
            all(replay.get("native_capture", {}).get("restored_replay_epoch", {}).get("status")
                == "PASS" for replay in replays)
            and all(replays[0]["native_capture"]["hashes"]["native." + suffix]
                    == replays[1]["native_capture"]["hashes"]["native." + suffix]
                    for suffix in ("s16le", "video", "states", "timeline.tsv"))
        ),
    }
    receipt = {
        "schema": "penta-low-health-hazard-determinism-v2",
        "rom": str(args.rom.resolve()),
        "rom_sha256": digest(args.rom),
        "samples": args.samples,
        "scene0b_profile_required": args.require_scene0b_low_health,
        "scene0b_stimulus_frames": args.scene0b_frames,
        "statuses": statuses,
        "replays": replays,
        "diagnostic_alignment_only": aligned,
        "exact_comparison": exact,
        "checks": checks,
        "passed": all(checks.values()),
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    if not receipt["passed"]:
        failed = [name for name, passed in checks.items() if not passed]
        print("FAIL: " + "; ".join(failed))
        print(f"Receipt: {receipt_path}")
        return 1
    print("PASS: two byte-exact low-health hazard replays remained clean")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
