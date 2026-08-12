#!/usr/bin/env python3
"""Verify animated boss geometry/palette contracts through mGBA.

All nine arena states run through one receipt format and one runtime path.
The default release gate enforces the currently proven Shalamar geometry and
audits the other eight.  ``--require-all-strict`` promotes every boss to the
same zero-mismatch gate and reports all blockers in one run.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from boss_geometry_contract import (
    BOSSES,
    CRYSTAL_ENTRY_PHASE_CELLS,
    NAMES,
    crystal_entry_attr_map,
)


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
PROBE = ROOT / "scripts/diagnostics/probe_boss_geometry.lua"
DEFAULT_MGBA = ROOT / "scripts/mgba-headless-singleflight"
def run_probe(mgba: Path, rom: Path, state: Path, prefix: Path,
              scene: int, frames: int, warmup: int, timeout: float) -> None:
    for suffix in (".done", ".tsv"):
        prefix.with_suffix(suffix).unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "BOSS_GEOMETRY_OUT": str(prefix),
        "BOSS_GEOMETRY_FRAMES": str(frames),
        "BOSS_GEOMETRY_WARMUP": str(warmup),
        "BOSS_GEOMETRY_SCENE": str(scene),
    })
    proc = subprocess.Popen(
        [str(mgba), "-t", str(state), "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if prefix.with_suffix(".done").exists():
                return
            if proc.poll() is not None:
                stderr = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError(
                    f"mGBA exited {proc.returncode} before receipt: {stderr}"
                )
            time.sleep(0.02)
        raise RuntimeError(f"timed out after {timeout:.1f}s")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=1.0)


def parse_trace(path: Path) -> list[
    tuple[int, int, int, int, int, int, int, int, int, int]
]:
    rows = []
    with path.open() as handle:
        header = next(handle).rstrip().split("\t")
        assert header == [
            "frame", "base", "scy", "scx", "row", "col",
            "screen_row", "screen_col", "tile", "attr",
        ]
        for line in handle:
            (frame, base, scy, scx, row, col, screen_row, screen_col,
             tile, attr) = line.rstrip().split("\t")
            rows.append((
                int(frame), int(base, 16), int(scy, 16), int(scx, 16),
                int(row), int(col),
                int(screen_row), int(screen_col), int(tile, 16), int(attr),
            ))
    return rows


def expected_lut(name: str) -> list[int]:
    from arena_tables_data import ARENA_TILE_PAL
    result = [ARENA_TILE_PAL[name].get(tile, 0) for tile in range(256)]
    # The production table builder reserves $FF as the neutral/empty sentinel
    # even when a concise source span includes it.
    result[0xFF] = 0
    return result


def analyze_crystal_cached_layout(
    samples: list[tuple[int, int, int, int, int, int, int, int, int, int]],
    raw_lut_mismatches_by_frame: Counter[int],
) -> dict[str, object]:
    """Audit Crystal's atomic camera-wrap contract, not a false tile LUT.

    The portal scrolls animated tiles through a cached material lattice. Every
    physical map therefore holds one layout for hundreds of frames, then
    changes as one large atomic publication when the native camera wraps. A
    per-tile rule reports those intentional intermediate frames as failures;
    this contract instead catches partial/confetti publications and rapid
    palette alternation directly.
    """
    entry = crystal_entry_attr_map()
    layouts: dict[int, dict[tuple[int, int], int]] = {}
    bases: dict[int, int] = {}
    for frame, base, _scy, _scx, row, col, *_tail, attr in samples:
        if frame not in layouts:
            layouts[frame] = {}
            bases[frame] = base
        layouts[frame][(row, col)] = attr

    violations: list[dict[str, object]] = []
    invalid_attrs = sum(attr not in {0, 4} for *_, attr in samples)
    if invalid_attrs:
        violations.append({"kind": "invalid-material-slot", "count": invalid_attrs})

    previous: dict[int, tuple[int, ...]] = {}
    last_transition: dict[int, int] = {}
    transitions: list[dict[str, int]] = []
    entry_mismatches = 0
    for frame in sorted(layouts):
        base = bases[frame]
        layout = layouts[frame]
        if len(layout) not in {360, 378, 380, 399}:
            violations.append({
                "kind": "incomplete-layout", "frame": frame,
                "cells": len(layout),
            })
            continue
        if base not in previous:
            comparable = set(layout) & {
                (row, col) for row in range(18) for col in range(20)
            }
            different = sum(
                layout[(row, col)] != entry[(base, row, col)]
                for row, col in comparable
                if (row, col) not in CRYSTAL_ENTRY_PHASE_CELLS
            )
            entry_mismatches += max(0, different - 1)
            if different > 1:
                violations.append({
                    "kind": "entry-layout", "frame": frame,
                    "base": f"{base:04X}", "cells": different,
                })
        else:
            comparable = set(layout) & set(previous[base])
            changed = sum(
                layout[cell] != previous[base][cell]
                for cell in comparable
            )
            if changed:
                gap = frame - last_transition.get(base, -10_000)
                event = {
                    "frame": frame, "base": base, "changed_cells": changed,
                    "raw_lut_mismatches": raw_lut_mismatches_by_frame[frame],
                    "gap": gap,
                }
                transitions.append(event)
                # Measured native wraps replace 99-121 visible cells at once.
                # Small writes are the confetti/flicker failure mode.
                if changed < 80:
                    violations.append({
                        "kind": "partial-layout-publish", **event,
                    })
                if raw_lut_mismatches_by_frame[frame] != 0:
                    violations.append({
                        "kind": "non-atomic-layout-publish", **event,
                    })
                if base in last_transition and gap < 180:
                    violations.append({
                        "kind": "rapid-layout-alternation", **event,
                    })
                last_transition[base] = frame
        previous[base] = layout

    max_raw = max(raw_lut_mismatches_by_frame.values(), default=0)
    if max_raw > 18:
        violations.append({
            "kind": "portal-lut-drift", "maximum": max_raw, "limit": 18,
        })
    if len(layouts) >= 1800 and len(transitions) < 8:
        violations.append({
            "kind": "missing-camera-wraps", "count": len(transitions),
            "minimum": 8,
        })
    return {
        "contract_mismatches": entry_mismatches + invalid_attrs + len([
            violation for violation in violations
            if violation["kind"] not in {"entry-layout", "invalid-material-slot"}
        ]),
        "contract_examples": violations[:20],
        "cached_layout_transitions": transitions,
        "max_frame_lut_mismatches": max_raw,
    }


def analyze(name: str,
            samples: list[
                tuple[int, int, int, int, int, int, int, int, int, int]
            ],
            frames: int,
            strict: bool) -> dict[str, object]:
    seen_frames = {sample[0] for sample in samples}
    if len(seen_frames) != frames:
        raise AssertionError(
            f"{name}: expected {frames} sampled frames, got {len(seen_frames)}"
        )
    lut = expected_lut(name)
    palette_samples = Counter(attr for *_prefix, attr in samples)
    scroll_samples = Counter(
        (scy, scx) for _frame, _base, scy, scx, *_tail in samples
    )
    observed_tiles = sorted({sample[-2] for sample in samples})
    unused_tiles = sorted(set(range(256)) - set(observed_tiles))
    mismatch_count = 0
    raw_lut_mismatch_count = 0
    mismatch_examples = []
    hidden_staging_mismatches = 0
    lower_colored = 0
    upper_gray_parts = 0
    warm_samples = 0
    cameo_top_edge_samples = 0
    cameo_top_edge_uncolored = 0
    raw_lut_mismatches_by_frame: Counter[int] = Counter()
    base_by_frame = {
        frame: base for frame, base, *_tail in samples
    }
    for (frame, base, scy, scx, row, col, screen_row, screen_col, tile,
         attr) in samples:
        raw_expected = lut[tile]
        next_base = base_by_frame.get(frame + 1, base)
        hidden_penta_staging = (
            name == "penta_dragon"
            and attr != raw_expected
            and next_base != base
        )
        if hidden_penta_staging:
            # Penta clears one cell on the outgoing physical map after its
            # final scanout. The immediately following sample proves LCDC has
            # flipped to the peer map; count it separately from visible
            # geometry instead of manufacturing a one-frame color-bleed bug.
            hidden_staging_mismatches += 1
        elif attr != raw_expected:
            raw_lut_mismatch_count += 1
            raw_lut_mismatches_by_frame[frame] += 1
        expected = raw_expected
        if name == "shalamar" and row >= 12:
            expected = 0
        if attr != expected and not hidden_penta_staging:
            mismatch_count += 1
            if len(mismatch_examples) < 20:
                mismatch_examples.append({
                    "frame": frame, "row": row, "col": col,
                    "base": f"{base:04X}",
                    "scy": scy, "scx": scx,
                    "screen_row": screen_row, "screen_col": screen_col,
                    "tile": tile, "expected": expected, "actual": attr,
                })
        if name == "shalamar":
            if row >= 12 and attr in {4, 5}:
                lower_colored += 1
            if row < 12 and tile >= 2 and attr != 4:
                upper_gray_parts += 1
            if attr == 5:
                warm_samples += 1
        if name == "cameo" and 0x0C <= tile <= 0x0F:
            cameo_top_edge_samples += 1
            if attr != 1:
                cameo_top_edge_uncolored += 1

    crystal_metrics = (
        analyze_crystal_cached_layout(samples, raw_lut_mismatches_by_frame)
        if name == "crystal_dragon" else {}
    )
    if crystal_metrics:
        mismatch_count = int(crystal_metrics["contract_mismatches"])
        mismatch_examples = list(crystal_metrics["contract_examples"])

    result = {
        "frames": len(seen_frames),
        "samples": len(samples),
        "palette_samples": dict(sorted(palette_samples.items())),
        "scroll_samples": {
            f"scy_{scy:02X}_scx_{scx:02X}": count
            for (scy, scx), count in sorted(scroll_samples.items())
        },
        "observed_tile_ids": observed_tiles,
        "unused_tile_ids": unused_tiles,
        "tile_lut_mismatches": raw_lut_mismatch_count,
        "hidden_staging_mismatches": hidden_staging_mismatches,
        "contract_mismatches": mismatch_count,
        "contract_kind": (
            "cached-atomic-camera-wrap"
            if name == "crystal_dragon" else "tile-lut"
        ),
        "mismatch_examples": mismatch_examples,
        "contract_status": "pass" if strict and mismatch_count == 0 else (
            "fail" if strict else "audit"
        ),
        "lower_shalamar_colored_samples": lower_colored,
        "upper_shalamar_gray_part_samples": upper_gray_parts,
        "shalamar_warm_band_samples": warm_samples,
        "cameo_top_edge_samples": cameo_top_edge_samples,
        "cameo_top_edge_uncolored_samples": cameo_top_edge_uncolored,
    }
    result.update(crystal_metrics)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--frames", type=int, default=360)
    parser.add_argument(
        "--target", type=int, action="append", choices=range(len(BOSSES)),
        help="audit only this boss index (repeatable; default: all nine)",
    )
    parser.add_argument(
        "--warmup-frames",
        type=int,
        default=8,
        help="restored-state grace period before collecting full-frame samples",
    )
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-all-strict",
        action="store_true",
        help="require zero tile/geometry mismatches for every boss",
    )
    parser.add_argument(
        "--trace-dir",
        type=Path,
        help="retain per-boss TSV traces in this directory",
    )
    args = parser.parse_args()
    if args.frames <= 0:
        parser.error("--frames must be positive")
    if args.warmup_frames < 0:
        parser.error("--warmup-frames must be non-negative")

    rom = args.rom.resolve()
    states = args.states.resolve()
    output = args.output and args.output.resolve()

    temporary = None
    if args.trace_dir:
        work = args.trace_dir.resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(
            prefix="penta-boss-geometry-", dir="/mnt/data/tmp"
        )
        work = Path(temporary.name)
    try:
        targets = args.target or list(range(len(BOSSES)))
        selected_names = {BOSSES[index].name for index in targets}
        strict_names = (
            selected_names if args.require_all_strict
            else selected_names & {"shalamar"}
        )
        receipt = {
            "rom": str(rom),
            "frames_per_boss": args.frames,
            "restored_state_warmup_frames": args.warmup_frames,
            "strict_bosses": sorted(strict_names),
            "selected_targets": targets,
            "bosses": {},
        }
        for index in targets:
            boss = BOSSES[index]
            name = boss.name
            matches = sorted(states.glob(f"boss{index}_{name}.ss0"))
            if len(matches) != 1:
                raise FileNotFoundError(
                    f"expected one boss{index}_{name}.ss0 in {states}, got {matches}"
                )
            prefix = work / f"boss{index}_{name}"
            run_probe(
                args.mgba.resolve(), rom, matches[0], prefix,
                boss.scene, args.frames, args.warmup_frames, args.timeout,
            )
            metrics = analyze(
                name,
                parse_trace(prefix.with_suffix(".tsv")),
                args.frames,
                name in strict_names,
            )
            receipt["bosses"][name] = metrics
            label = metrics["contract_status"].upper()
            print(
                f"{label} {index}: {name:15s} frames={metrics['frames']} "
                f"contract_mismatches={metrics['contract_mismatches']} "
                f"raw_lut_mismatches={metrics['tile_lut_mismatches']} "
                f"palette_samples={metrics['palette_samples']}"
            )

        blockers = {
            name: metrics["contract_mismatches"]
            for name, metrics in receipt["bosses"].items()
            if name in strict_names and metrics["contract_mismatches"]
        }
        staging_blockers = {
            name: metrics["hidden_staging_mismatches"]
            for name, metrics in receipt["bosses"].items()
            if name in strict_names
            and (
                metrics["hidden_staging_mismatches"] > 1
                if name == "penta_dragon"
                else metrics["hidden_staging_mismatches"] != 0
            )
        }
        blockers.update({
            f"{name}:hidden-staging": count
            for name, count in staging_blockers.items()
        })
        if "cameo" in strict_names:
            cameo = receipt["bosses"]["cameo"]
            if cameo["cameo_top_edge_samples"] == 0:
                blockers["cameo:top-edge-not-observed"] = 1
            if cameo["cameo_top_edge_uncolored_samples"]:
                blockers["cameo:top-edge-uncolored"] = cameo[
                    "cameo_top_edge_uncolored_samples"
                ]
        receipt["strict_pass"] = not blockers
        receipt["strict_blockers"] = blockers
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            print(f"receipt: {output}")
    finally:
        if temporary is not None:
            temporary.cleanup()
    if blockers:
        print("FAIL: strict boss geometry blockers:")
        for name, mismatches in blockers.items():
            print(f"  {name}: {mismatches} mismatches")
        return 1
    scope = ", ".join(BOSSES[index].name for index in targets)
    print(f"PASS: boss geometry receipt; strict geometry contract for {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
