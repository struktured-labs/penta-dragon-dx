#!/usr/bin/env python3
"""Prove the shared arena key never hides a changed semantic attr plane."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from arena_semantic_key import (
    PLANE_SIZE,
    PENTA_SEMANTIC_SAMPLE,
    RAW_SUM_SAMPLES,
    SUM_A_SAMPLES,
    SUM_B_SAMPLES,
    penta_semantic_key,
    raw_key,
    semantic_key,
)


SPECIALIZED = {"crystal_dragon", "ted"}
EXPECTED = {"shalamar", "riff", "cameo", "troop", "faze", "angela", "penta_dragon"}
TRACE_DESTINATION = re.compile(
    r"copy=\d+ frame=\d+ destination=([0-9A-F]{4}) "
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    failures: list[str] = []
    rows = []
    observed: set[str] = set()
    for corpus in args.corpus:
        semantic_root = corpus / "semantic" if (corpus / "semantic").is_dir() else corpus
        for boss_dir in sorted(path for path in semantic_root.iterdir() if path.is_dir()):
            boss = boss_dir.name
            if boss in SPECIALIZED:
                continue
            for tile_path in sorted(boss_dir.glob("run-*.tiles.bin")):
                plane_path = tile_path.with_name(
                    tile_path.name.replace(".tiles.bin", ".planes.bin")
                )
                if not plane_path.is_file():
                    failures.append(f"missing paired plane file: {plane_path}")
                    continue
                tiles = tile_path.read_bytes()
                planes = plane_path.read_bytes()
                if len(tiles) != len(planes) or len(tiles) % PLANE_SIZE:
                    failures.append(
                        f"invalid corpus lengths for {tile_path}: "
                        f"tiles={len(tiles)} planes={len(planes)}"
                    )
                    continue
                observed.add(boss)
                count = len(tiles) // PLANE_SIZE
                trace_path = tile_path.with_name(
                    tile_path.name.replace(".tiles.bin", ".trace")
                )
                if not trace_path.is_file():
                    failures.append(f"missing paired trace file: {trace_path}")
                    continue
                destinations = [
                    int(match.group(1), 16)
                    for line in trace_path.read_text().splitlines()
                    if (match := TRACE_DESTINATION.match(line))
                ]
                if len(destinations) != count:
                    failures.append(
                        f"trace/corpus count differs for {tile_path}: "
                        f"trace={len(destinations)} corpus={count}"
                    )
                    continue
                unexpected = sorted(set(destinations) - {0x4400, 0x9800, 0x9C00})
                if unexpected:
                    failures.append(
                        f"unexpected destinations for {tile_path}: {unexpected}"
                    )
                    continue
                eligible = [
                    index for index, destination in enumerate(destinations)
                    if destination in (0x9800, 0x9C00)
                ]
                key_to_plane: dict[tuple[int, tuple[int, int]], bytes] = {}
                exact_key_to_source: dict[
                    tuple[int, tuple[int, int], int], bytes
                ] = {}
                false_hits = 0
                raw_false_hits = 0
                false_misses = 0
                plane_changes = 0
                key_changes = 0
                previous: dict[int, tuple[tuple[int, int], bytes]] = {}
                for index in eligible:
                    start = index * PLANE_SIZE
                    source = tiles[start:start + PLANE_SIZE]
                    plane = planes[start:start + PLANE_SIZE]
                    destination = destinations[index]
                    key = (
                        penta_semantic_key(source)
                        if boss == "penta_dragon" else semantic_key(source)
                    )
                    prior_plane = key_to_plane.setdefault((destination, key), plane)
                    if prior_plane != plane:
                        false_hits += 1
                    exact_key = (destination, key, raw_key(source))
                    prior_source = exact_key_to_source.setdefault(exact_key, source)
                    if prior_source != source:
                        raw_false_hits += 1
                    prior = previous.get(destination)
                    if prior is not None:
                        plane_changed = plane != prior[1]
                        key_changed = key != prior[0]
                        plane_changes += plane_changed
                        key_changes += key_changed
                        false_misses += key_changed and not plane_changed
                    previous[destination] = key, plane
                if false_hits:
                    failures.append(
                        f"{boss}/{tile_path.name}: {false_hits} false semantic hits"
                    )
                if raw_false_hits:
                    failures.append(
                        f"{boss}/{tile_path.name}: {raw_false_hits} false raw hits"
                    )
                rows.append({
                    "corpus": str(corpus),
                    "boss": boss,
                    "run": tile_path.name,
                    "records": count,
                    "cache_eligible_records": len(eligible),
                    "distinct_keys": len(key_to_plane),
                    "distinct_planes": len({
                        planes[i:i + PLANE_SIZE]
                        for i in range(0, len(planes), PLANE_SIZE)
                    }),
                    "false_hits": false_hits,
                    "raw_false_hits": raw_false_hits,
                    "false_misses": false_misses,
                    "plane_changes": plane_changes,
                    "key_changes": key_changes,
                    "fast_repeats": max(0, count - 1 - key_changes),
                    "tiles_sha256": sha256(tile_path),
                    "planes_sha256": sha256(plane_path),
                })

    missing = sorted(EXPECTED - observed)
    if missing:
        failures.append(f"missing shared-cache bosses: {', '.join(missing)}")
    report = {
        "status": "pass" if not failures else "fail",
        "samples": {
            "sum_a": SUM_A_SAMPLES,
            "sum_b": SUM_B_SAMPLES,
            "penta": (PENTA_SEMANTIC_SAMPLE,),
            "raw_sum": RAW_SUM_SAMPLES,
        },
        "specialized_bosses": sorted(SPECIALIZED),
        "runs": rows,
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
