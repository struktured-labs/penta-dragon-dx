#!/usr/bin/env python3
"""Prove the fixed Ted edge region never contains low crown art in stock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from verify_ted_determinism import TED_NUMBERED_TILE_POSITION

FRAME_SIZE = 4 + 24 * 24 + 2 * 0x400
ROWS = frozenset((12, 16, 17, 18, 19))
SCHEMA = "penta-ted-edge-invariant-v1"
TARGETS = frozenset((0x13, 0x14, 0x1C, 0x1F, 0x20, 0x27, 0x28))


def forbidden(tile: int, row: int, column: int) -> bool:
    return (
        row in ROWS and 14 <= column < 24
        and (0x02 <= tile <= 0x20 or tile in (0x27, 0x28))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.trace.read_bytes()
    if len(data) % FRAME_SIZE:
        raise ValueError(f"trace size {len(data)} is not a frame multiple")
    frames, violations, examples = len(data) // FRAME_SIZE, 0, []
    duplicate_occurrences = canonical_first = ordering_violations = 0
    for frame in range(frames):
        record = data[frame * FRAME_SIZE:(frame + 1) * FRAME_SIZE]
        source = record[4:4 + 24 * 24]
        crowns = []
        for row in range(24):
            for column in range(20):
                offset = row * 24 + column
                if source[offset:offset + 5] == bytes(range(2, 7)):
                    crowns.append((row, column))
        if len(crowns) == 1:
            crown_row, crown_column = crowns[0]
            for tile in TARGETS:
                expected_row, expected_column = TED_NUMBERED_TILE_POSITION[tile]
                canonical_offset = (
                    (crown_row + expected_row) * 24
                    + crown_column + expected_column
                )
                offsets = [
                    offset for offset, value in enumerate(source)
                    if value == tile
                ]
                for offset in offsets:
                    if offset == canonical_offset:
                        continue
                    duplicate_occurrences += 1
                    if (0 <= canonical_offset < len(source)
                            and source[canonical_offset] == tile
                            and canonical_offset < offset):
                        canonical_first += 1
                    else:
                        ordering_violations += 1
                        if len(examples) < 16:
                            examples.append({
                                "frame": frame,
                                "kind": "source-publication-order",
                                "tile": tile, "canonical": canonical_offset,
                                "duplicate": offset,
                            })
        cursor = 4 + 24 * 24
        for map_index in range(2):
            tiles = record[cursor:cursor + 0x400]
            cursor += 0x400
            for row in ROWS:
                for column in range(14, 24):
                    tile = tiles[row * 32 + column]
                    if forbidden(tile, row, column):
                        violations += 1
                        if len(examples) < 16:
                            examples.append({
                                "frame": frame, "map": map_index,
                                "row": row, "column": column, "tile": tile,
                            })
    # Source ordering is characterization, not an acceptance condition. Four
    # stock frame-1021 counterexamples prove that "first identity wins" is an
    # invalid sanitizer policy even though early poses happen to satisfy it.
    status = "pass" if frames == 2800 and violations == 0 else "fail"
    receipt = {
        "schema": SCHEMA, "status": status, "frames": frames,
        "maps_checked": frames * 2, "cells_checked": frames * 2 * 50,
        "forbidden_occurrences": violations, "examples": examples,
        "source_duplicate_occurrences": duplicate_occurrences,
        "source_canonical_precedes_duplicate": canonical_first,
        "source_ordering_violations": ordering_violations,
        "source_canonical_always_precedes_duplicate": (
            duplicate_occurrences > 0
            and canonical_first == duplicate_occurrences
        ),
        "trace": str(args.trace.resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
