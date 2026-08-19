#!/usr/bin/env python3
"""Compare stock and DX Troop source planes at actual map publications."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


PLANE_SIZE = 24 * 24
RECORD_SIZE = 2 + PLANE_SIZE


def load(path: Path) -> list[tuple[int, bytes]]:
    raw = path.read_bytes()
    if len(raw) % RECORD_SIZE:
        raise ValueError(f"{path}: {len(raw)} is not a multiple of {RECORD_SIZE}")
    return [
        (raw[offset] | raw[offset + 1] << 8,
         raw[offset + 2:offset + RECORD_SIZE])
        for offset in range(0, len(raw), RECORD_SIZE)
    ]


def digest(plane: bytes) -> str:
    return hashlib.sha256(plane).hexdigest()


def summary(records: list[tuple[int, bytes]]) -> dict[str, object]:
    hashes = [digest(plane) for _, plane in records]
    counts = Counter(hashes)
    return {
        "records": len(records),
        "first_frame": records[0][0] if records else None,
        "last_frame": records[-1][0] if records else None,
        "unique_planes": len(counts),
        "duplicate_publications": len(records) - len(counts),
        "most_common": counts.most_common(12),
    }


def greedy_discriminator(good: list[bytes], bad: list[bytes]) -> list[int]:
    remaining = {(g, b) for g in range(len(good)) for b in range(len(bad))}
    selected: list[int] = []
    while remaining:
        best_offset = -1
        best_cover: set[tuple[int, int]] = set()
        for offset in range(PLANE_SIZE):
            cover = {(g, b) for g, b in remaining
                     if good[g][offset] != bad[b][offset]}
            if len(cover) > len(best_cover):
                best_offset, best_cover = offset, cover
        if best_offset < 0:
            break
        selected.append(best_offset)
        remaining -= best_cover
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--og", type=Path, required=True)
    parser.add_argument("--dx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    og_records, dx_records = load(args.og), load(args.dx)
    og_by_hash = {digest(plane): plane for _, plane in og_records}
    dx_by_hash = {digest(plane): plane for _, plane in dx_records}
    og_only = sorted(set(og_by_hash) - set(dx_by_hash))
    dx_only = sorted(set(dx_by_hash) - set(og_by_hash))
    shared = sorted(set(og_by_hash) & set(dx_by_hash))
    discriminator = greedy_discriminator(
        list(og_by_hash.values()), [dx_by_hash[key] for key in dx_only]
    ) if dx_only else []
    nearest = []
    for key in dx_only:
        plane = dx_by_hash[key]
        choices = [
            (sum(left != right for left, right in zip(plane, stock)), stock_key)
            for stock_key, stock in og_by_hash.items()
        ]
        distance, stock_key = min(choices)
        stock = og_by_hash[stock_key]
        mismatches = [index for index, (left, right) in enumerate(zip(plane, stock))
                      if left != right]
        nearest.append({
            "dx_hash": key,
            "og_hash": stock_key,
            "hamming_distance": distance,
            "mismatch_cells": [
                {"offset": index, "row": index // 24, "column": index % 24,
                 "dx": plane[index], "og": stock[index]}
                for index in mismatches[:32]
            ],
        })
    result = {
        "schema": "penta-troop-publication-corpus-v1",
        "og": summary(og_records),
        "dx": summary(dx_records),
        "shared_unique_planes": len(shared),
        "og_only_unique_planes": len(og_only),
        "dx_only_unique_planes": len(dx_only),
        "og_only_hashes": og_only,
        "dx_only_hashes": dx_only,
        "greedy_discriminator_offsets": discriminator,
        "greedy_discriminator_cells": [
            {
                "offset": offset, "row": offset // 24, "column": offset % 24,
                "og_values": dict(sorted(Counter(
                    plane[offset] for plane in og_by_hash.values()
                ).items())),
                "dx_only_values": dict(sorted(Counter(
                    dx_by_hash[key][offset] for key in dx_only
                ).items())),
            }
            for offset in discriminator
        ],
        "nearest_stock_planes": nearest,
        "all_dx_planes_stock_observed": not dx_only,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
