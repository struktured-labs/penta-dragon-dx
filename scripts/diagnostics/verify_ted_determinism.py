#!/usr/bin/env python3
"""Require deterministic, contained, non-banded Ted color animation."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from verify_boss_geometry import TED_NUMBERED_BODY_OFFSETS
from arena_tables_data import TED_BODY_TILE_PAL
from ted_native_pose_contract_v2 import (
    BODY_TILES,
    MAX_BODY_CELLS,
    MIN_BODY_CELLS,
    NATIVE_POSE_SHA256,
    NUMBERED_TILE_POSITION as TED_NUMBERED_TILE_POSITION,
    SPARSE_TILE_POSITIONS as TED_SPARSE_TILE_POSITIONS,
    SPARSE_TILES as TED_TENTACLE_TILES,
    cells_digest,
)


ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts/mgba-headless-singleflight"
PROBE = Path(__file__).with_name("probe_ted_determinism.lua")
TRACE_HEADER_SIZE = 7
FRAME_SIZE = TRACE_HEADER_SIZE + 2 * 2 * 0x400
SCHEMA = "penta-ted-full-plane-v3"
TED_FLOOR_TILES = frozenset((0x77, 0x78, 0x79, 0x7A))
# Ted's checker owns two editable stone materials instead of inheriting one
# uniform BG0 ramp. Diagonal cells use BG6 blue-gray; off-diagonals use BG7
# steel/navy. This makes background variation explicit and YAML-tuneable.
TED_FLOOR_PALETTE = {0x77: 6, 0x78: 7, 0x79: 7, 0x7A: 6}
TED_SPARSE_LIMB_OFFSETS = frozenset(
    (row, col)
    for row in range(-1, 6)
    for col in range(-6, 10)
)
TED_WRAP_FRINGE_OFFSETS = frozenset(((-1, 7), (-1, 8)))
# Ted's numbered $02-$76 body is a row-major encoding of the native
# silhouette: every ID has exactly one crown-relative coordinate across all
# 2,800 stock frames.  This identity contract explains failures more usefully
# than a pose hash alone while storing no ROM graphics.
# The widest native sparse-limb pose legitimately occupies seven more cells
# than the numbered-body-only fixture. 393 is the measured intact floor.
MIN_FLOOR_CELLS_PER_VISIBLE_FRAME = 393


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(rom: Path, state: Path, prefix: Path, frames: int, timeout: float,
        reinstall_runtime: bool, debug_trace: bool = False) -> None:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        TED_DETERMINISM_OUT=str(prefix),
        TED_DETERMINISM_FRAMES=str(frames),
        TED_DETERMINISM_REINSTALL="1" if reinstall_runtime else "0",
        TED_DETERMINISM_DEBUG="1" if debug_trace else "0",
    )
    process = subprocess.Popen(
        [str(MGBA), "-t", str(state), "--script", str(PROBE), str(rom)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            marker = Path(str(prefix) + ".done")
            if marker.is_file():
                if not marker.read_text().startswith("status=ok"):
                    raise RuntimeError(marker.read_text().strip())
                return
            if process.poll() is not None:
                raise RuntimeError((process.stderr.read() if process.stderr else "").strip())
            time.sleep(0.02)
        raise TimeoutError(f"Ted trace timed out after {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)


def signed(value: int) -> int:
    value &= 0x1F
    return value - 32 if value >= 16 else value


def crown(tiles: bytes) -> list[tuple[int, int]]:
    return [
        (row, col)
        for row in range(32)
        for col in range(32)
        if all(tiles[row * 32 + ((col + step) & 31)] == 2 + step for step in range(5))
    ]


def anchor_score(tiles: bytes, attrs: bytes, anchor: tuple[int, int]) -> tuple[int, int, int]:
    """Score one physical anchor against the exact Ted silhouette.

    Ted's native animation legitimately replaces the entire numbered crown in
    several poses, so carrying the previous crown position measures a moving
    boss against stale coordinates.  Prefer the anchor containing the most
    boss art, then the fewest colored cells outside the same exact envelope.
    The remaining off-body counts are still reported by the strict gate.
    """
    anchor_row, anchor_col = anchor
    inside_body = off_body = off_color = 0
    for offset, (tile, attr) in enumerate(zip(tiles, attrs)):
        row, col = divmod(offset, 32)
        relative = (signed(row-anchor_row), signed(col-anchor_col))
        inside = (
            relative in TED_SPARSE_LIMB_OFFSETS
            if tile in TED_TENTACLE_TILES
            else relative in TED_NUMBERED_BODY_OFFSETS
                 or relative in TED_WRAP_FRINGE_OFFSETS
        )
        if tile in BODY_TILES:
            inside_body += inside
            off_body += not inside
        if attr:
            off_color += not inside
    return (-inside_body, off_body, off_color)


def resolve_anchor(tiles: bytes, attrs: bytes) -> tuple[int, int] | None:
    """Resolve crownless native poses without relying on temporal carryover."""
    if not any(tile in BODY_TILES for tile in tiles):
        return None
    # The production materializer encodes the physical origin in four-cell
    # units; limiting candidates to that native lattice also keeps this
    # 2,800-frame release gate inexpensive.
    return min(
        ((row, col) for row in range(0, 32, 4) for col in range(0, 32, 4)),
        key=lambda anchor: (*anchor_score(tiles, attrs, anchor), *anchor),
    )


def native_pose_digest(tiles: bytes, anchor: tuple[int, int]) -> tuple[str, int]:
    """Hash translation-normalized Ted art without embedding stock graphics."""
    anchor_row, anchor_col = anchor
    cells = []
    for offset, tile in enumerate(tiles):
        if tile not in BODY_TILES:
            continue
        row, col = divmod(offset, 32)
        cells.append((signed(row-anchor_row), signed(col-anchor_col), tile))
    normalized = tuple(sorted(cells))
    return cells_digest(normalized), len(normalized)


def position_violations(
    tiles: bytes, anchor: tuple[int, int]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return exact numbered and sparse identity violations for one pose."""
    anchor_row, anchor_col = anchor
    numbered: list[dict[str, object]] = []
    sparse: list[dict[str, object]] = []
    for offset, tile in enumerate(tiles):
        row, col = divmod(offset, 32)
        relative = (signed(row-anchor_row), signed(col-anchor_col))
        expected = TED_NUMBERED_TILE_POSITION.get(tile)
        if expected is not None and relative != expected:
            numbered.append({
                "tile": tile, "relative": relative, "expected": expected,
            })
        allowed = TED_SPARSE_TILE_POSITIONS.get(tile)
        if allowed is not None and relative not in allowed:
            sparse.append({"tile": tile, "relative": relative})
    return numbered, sparse


def floor_palette_violations(tiles: bytes, attrs: bytes) -> list[dict[str, int]]:
    """Return checker cells that do not use their BG6/BG7 material."""
    violations = []
    for offset, (tile, attr) in enumerate(zip(tiles, attrs)):
        if tile not in TED_FLOOR_TILES:
            continue
        expected = TED_FLOOR_PALETTE[tile]
        if attr != expected:
            row, col = divmod(offset, 32)
            violations.append({
                "row": row, "col": col, "tile": tile,
                "actual": attr, "expected": expected,
            })
    return violations


def body_palette_violations(tiles: bytes, attrs: bytes) -> list[dict[str, int]]:
    """Return Ted art cells that disagree with the YAML-derived arena LUT.

    Merely requiring a nonzero attribute misses stale-but-colored fragments
    and material swaps.  The writer mirror is only correct when every native
    body/tentacle tile carries the exact palette selected by the editable Ted
    table, on every rendered frame.
    """
    violations = []
    for offset, (tile, attr) in enumerate(zip(tiles, attrs)):
        expected = TED_BODY_TILE_PAL.get(tile)
        if expected is None or attr == expected:
            continue
        row, col = divmod(offset, 32)
        violations.append({
            "row": row, "col": col, "tile": tile,
            "actual": attr, "expected": expected,
        })
    return violations


def analyze(data: bytes, frames: int) -> dict[str, object]:
    if len(data) != frames * FRAME_SIZE:
        raise ValueError(f"trace size {len(data)} != {frames} * {FRAME_SIZE}")
    failures: Counter[str] = Counter()
    examples: list[dict[str, object]] = []
    previous_relative: dict[tuple[int, int, int], tuple[bool, int, int]] = {}
    palette_rows: defaultdict[int, set[int]] = defaultdict(set)
    row_palettes: defaultdict[int, Counter[int]] = defaultdict(Counter)
    colored_body = off_body = off_body_tiles = flicker = crown_errors = 0
    numbered_identity_mismatches = sparse_position_mismatches = 0
    numbered_mismatch_deltas: Counter[str] = Counter()
    numbered_mismatch_tiles: Counter[str] = Counter()
    numbered_mismatch_tile_deltas: Counter[str] = Counter()
    numbered_mismatch_group_slots: Counter[str] = Counter()
    numbered_mismatch_frames = 0
    runtime_anchor_samples = runtime_anchor_matches = 0
    runtime_anchor_deltas: Counter[str] = Counter()
    floor_samples = floor_lattice_mismatches = floor_palette_mismatches = 0
    body_palette_samples = body_palette_mismatches = 0
    sparse_floor_frames = 0
    tentacle_samples = 0
    native_pose_matches = native_pose_mismatches = 0
    crownless_pose_frames = 0
    for frame in range(frames):
        record = data[frame * FRAME_SIZE:(frame + 1) * FRAME_SIZE]
        # LCDC bit 3 selects the physical BG map currently reaching the LCD.
        # The native renderer deliberately stages the next segmented pose in
        # the other map; judging that hidden work plane as visible geometry
        # produced false crown, containment, and flicker failures.  Both maps
        # remain in the raw deterministic replay hash, while visual contracts
        # apply to the map the player can actually see this frame.
        active_map_index = 1 if record[0] & 0x08 else 0
        runtime_anchor = (record[4] & 0x1F, record[5] & 0x1F)
        publication_map_index = record[6] & 0x01
        cursor = TRACE_HEADER_SIZE
        for map_index, base in enumerate((0x9800, 0x9C00)):
            tiles = record[cursor:cursor + 0x400]; cursor += 0x400
            attrs = record[cursor:cursor + 0x400]; cursor += 0x400
            crowns = crown(tiles)
            if map_index == publication_map_index and len(crowns) == 1:
                runtime_anchor_samples += 1
                anchor_delta = (
                    signed(runtime_anchor[0] - crowns[0][0]),
                    signed(runtime_anchor[1] - crowns[0][1]),
                )
                runtime_anchor_deltas[
                    f"{anchor_delta[0]},{anchor_delta[1]}"
                ] += 1
                runtime_anchor_matches += anchor_delta == (0, 0)
            if map_index != active_map_index:
                continue
            if len(crowns) != 1:
                crown_errors += 1
                if len(examples) < 24:
                    examples.append({"kind": "crown-count", "frame": frame,
                                     "base": f"{base:04X}", "count": len(crowns)})
                continue
            anchor_row, anchor_col = crowns[0]
            pose_sha, pose_cells = native_pose_digest(
                tiles, (anchor_row, anchor_col)
            )
            numbered_bad, sparse_bad = position_violations(
                tiles, (anchor_row, anchor_col)
            )
            floor_palette_bad = floor_palette_violations(tiles, attrs)
            body_palette_bad = body_palette_violations(tiles, attrs)
            numbered_identity_mismatches += len(numbered_bad)
            sparse_position_mismatches += len(sparse_bad)
            if numbered_bad:
                numbered_mismatch_frames += 1
            for violation in numbered_bad:
                relative = violation["relative"]
                expected = violation["expected"]
                delta = (
                    signed(relative[0] - expected[0]),
                    signed(relative[1] - expected[1]),
                )
                numbered_mismatch_deltas[f"{delta[0]},{delta[1]}"] += 1
                numbered_mismatch_tiles[f"{violation['tile']:02X}"] += 1
                numbered_mismatch_tile_deltas[
                    f"{violation['tile']:02X}@{delta[0]},{delta[1]}"
                ] += 1
                physical_col = (anchor_col + relative[1]) & 0x1F
                numbered_mismatch_group_slots[str(physical_col % 3)] += 1
            floor_palette_mismatches += len(floor_palette_bad)
            body_palette_mismatches += len(body_palette_bad)
            body_palette_samples += sum(tile in TED_BODY_TILE_PAL for tile in tiles)
            for violation in numbered_bad:
                if len(examples) < 24:
                    examples.append({
                        "kind": "numbered-tile-position",
                        "frame": frame, "base": f"{base:04X}",
                        **violation,
                    })
            for violation in sparse_bad:
                if len(examples) < 24:
                    examples.append({
                        "kind": "sparse-tile-position",
                        "frame": frame, "base": f"{base:04X}",
                        **violation,
                    })
            for violation in floor_palette_bad:
                if len(examples) < 24:
                    examples.append({
                        "kind": "floor-palette-mismatch",
                        "frame": frame, "base": f"{base:04X}",
                        **violation,
                    })
            for violation in body_palette_bad:
                if len(examples) < 24:
                    examples.append({
                        "kind": "body-palette-mismatch",
                        "frame": frame, "base": f"{base:04X}",
                        **violation,
                    })
            if (pose_sha in NATIVE_POSE_SHA256
                    and MIN_BODY_CELLS <= pose_cells <= MAX_BODY_CELLS):
                native_pose_matches += 1
            else:
                native_pose_mismatches += 1
                failures["non-native-pose-geometry"] += 1
                if len(examples) < 24:
                    examples.append({
                        "kind": "non-native-pose-geometry", "frame": frame,
                        "base": f"{base:04X}", "body_cells": pose_cells,
                        "pose_sha256": pose_sha,
                    })
            frame_floor_cells = 0
            for offset, (tile, attr) in enumerate(zip(tiles, attrs)):
                row, col = divmod(offset, 32)
                relative = (signed(row-anchor_row), signed(col-anchor_col))
                inside = tile in BODY_TILES
                if tile in TED_FLOOR_TILES:
                    frame_floor_cells += 1
                    floor_samples += 1
                    expected_floor = 0x77 + 2 * (row & 1) + (col & 1)
                    if tile != expected_floor:
                        floor_lattice_mismatches += 1
                        if len(examples) < 24:
                            examples.append({
                                "kind": "floor-lattice-mismatch",
                                "frame": frame, "base": f"{base:04X}",
                                "row": row, "col": col, "tile": tile,
                                "expected": expected_floor,
                            })
                if inside and tile in BODY_TILES:
                    if tile in TED_TENTACLE_TILES:
                        tentacle_samples += 1
                    if not attr:
                        failures["uncolored-body"] += 1
                    else:
                        colored_body += 1
                        palette_rows[attr].add(relative[0])
                        row_palettes[relative[0]][attr] += 1
                    key = (map_index, relative[0], relative[1])
                    old = previous_relative.get(key)
                    occupied = tile in BODY_TILES
                    # A different art tile moving into the same screen cell is
                    # native animation, not palette flicker.  Reject only the
                    # same stable tile changing palette at that body-relative
                    # position on consecutive frames.
                    if (old is not None and old[0] and occupied
                            and old[1] == tile and old[2] != attr):
                        flicker += 1
                        if len(examples) < 24:
                            examples.append({"kind": "stable-tile-palette-flicker",
                                             "frame": frame, "base": f"{base:04X}",
                                             "relative": relative, "tile": tile,
                                             "previous": old[2], "actual": attr})
                    previous_relative[key] = (occupied, tile, attr)
            if frame_floor_cells < MIN_FLOOR_CELLS_PER_VISIBLE_FRAME:
                sparse_floor_frames += 1

    # Reject palettes that are merely non-overlapping horizontal tile bands.
    active_rows = {palette: rows for palette, rows in palette_rows.items() if rows}
    row_pairs = list(active_rows.items())
    disjoint_pairs = sum(
        not left_rows.intersection(right_rows)
        for index, (_left, left_rows) in enumerate(row_pairs)
        for _right, right_rows in row_pairs[index + 1:]
    )
    if len(active_rows) >= 3 and disjoint_pairs == len(active_rows) * (len(active_rows)-1)//2:
        failures["horizontal-palette-bands"] += 1
    dominant_rows = {
        row: counts.most_common(1)[0]
        for row, counts in sorted(row_palettes.items()) if counts
    }
    sharp_row_boundaries = []
    for row in range(min(dominant_rows, default=0), max(dominant_rows, default=-1)):
        if row not in dominant_rows or row + 1 not in dominant_rows:
            continue
        left, right = dominant_rows[row], dominant_rows[row + 1]
        left_share = left[1] / sum(row_palettes[row].values())
        right_share = right[1] / sum(row_palettes[row + 1].values())
        if left[0] != right[0] and left_share >= 0.75 and right_share >= 0.75:
            sharp_row_boundaries.append({
                "after_relative_row": row,
                "from_palette": left[0], "to_palette": right[0],
                "from_share": left_share, "to_share": right_share,
            })
    if len(sharp_row_boundaries) >= 2:
        failures["sharp-horizontal-material-seams"] += len(sharp_row_boundaries)
    for name, count in (
        ("boss-tile-off-body", off_body_tiles),
        ("colored-off-body", off_body),
        ("stable-tile-palette-flicker", flicker),
        ("crown-count", crown_errors),
        ("floor-lattice-mismatch", floor_lattice_mismatches),
        ("floor-palette-mismatch", floor_palette_mismatches),
        ("body-palette-mismatch", body_palette_mismatches),
        ("sparse-native-floor", sparse_floor_frames),
        ("numbered-tile-position", numbered_identity_mismatches),
        ("sparse-tile-position", sparse_position_mismatches),
    ):
        if count:
            failures[name] += count
    if not tentacle_samples:
        failures["missing-tentacle-tiles"] += 1
    return {
        "status": "pass" if not failures else "fail",
        "frames": frames,
        "full_physical_cells_hashed": frames * 2 * 0x400,
        "visible_cells_analyzed": frames * 0x400,
        "colored_body_samples": colored_body,
        "floor_samples": floor_samples,
        "floor_lattice_mismatches": floor_lattice_mismatches,
        "floor_palette_mismatches": floor_palette_mismatches,
        "body_palette_samples": body_palette_samples,
        "body_palette_mismatches": body_palette_mismatches,
        "minimum_floor_cells_per_visible_frame": MIN_FLOOR_CELLS_PER_VISIBLE_FRAME,
        "sparse_floor_frames": sparse_floor_frames,
        "tentacle_samples": tentacle_samples,
        "numbered_identity_mismatches": numbered_identity_mismatches,
        "numbered_identity_mismatch_frames": numbered_mismatch_frames,
        "numbered_identity_delta_histogram": dict(
            numbered_mismatch_deltas.most_common()
        ),
        "numbered_identity_tile_histogram": dict(
            numbered_mismatch_tiles.most_common()
        ),
        "numbered_identity_tile_delta_histogram": dict(
            numbered_mismatch_tile_deltas.most_common()
        ),
        "numbered_identity_group_slot_histogram": dict(
            numbered_mismatch_group_slots.most_common()
        ),
        "runtime_anchor_samples": runtime_anchor_samples,
        "runtime_anchor_matches": runtime_anchor_matches,
        "runtime_anchor_delta_histogram": dict(
            runtime_anchor_deltas.most_common()
        ),
        "sparse_position_mismatches": sparse_position_mismatches,
        "crownless_pose_frames": crownless_pose_frames,
        "native_pose_matches": native_pose_matches,
        "native_pose_mismatches": native_pose_mismatches,
        "native_pose_contract_size": len(NATIVE_POSE_SHA256),
        "palette_relative_rows": {str(k): sorted(v) for k, v in sorted(active_rows.items())},
        "dominant_palette_by_relative_row": {
            str(row): {"palette": item[0], "samples": item[1]}
            for row, item in dominant_rows.items()
        },
        "sharp_horizontal_boundaries": sharp_row_boundaries,
        "failures": dict(sorted(failures.items())),
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    states = parser.add_mutually_exclusive_group(required=True)
    states.add_argument("--state", type=Path)
    states.add_argument("--states", type=Path)
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument(
        "--reinstall-runtime", action="store_true",
        help="discard a serialized older Ted C500 helper before replay",
    )
    parser.add_argument(
        "--debug-trace", action="store_true",
        help="retain per-frame Ted pose/token diagnostics beside each trace",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--receipt-only", action="store_true",
        help="write deterministic evidence and defer pass/fail to the aggregate",
    )
    args = parser.parse_args()
    state = args.state
    if state is None:
        matches = sorted(args.states.glob("boss4_ted.ss0"))
        if len(matches) != 1:
            parser.error(f"expected one boss4_ted.ss0 in {args.states}, got {matches}")
        state = matches[0]
    work = (
        args.output.resolve().parent
        / "ted-determinism"
        / uuid.uuid4().hex
    )
    prefixes = [work / "run-a", work / "run-b"]
    for prefix in prefixes:
        run(
            args.rom.resolve(), state.resolve(), prefix, args.frames,
            args.timeout, args.reinstall_runtime, args.debug_trace,
        )
    traces = [Path(str(prefix) + ".bin") for prefix in prefixes]
    hashes = [digest(path) for path in traces]
    metrics = analyze(traces[0].read_bytes(), args.frames)
    deterministic = hashes[0] == hashes[1]
    receipt = {
        "schema": SCHEMA,
        "status": "pass" if deterministic and metrics["status"] == "pass" else "fail",
        "deterministic_replay": deterministic,
        "trace_sha256": hashes,
        "rom_sha256": digest(args.rom.resolve()),
        "state_sha256": digest(state.resolve()),
        "metrics": metrics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if args.receipt_only or receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
