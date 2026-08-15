#!/usr/bin/env python3
"""Prove Ted's two-plane attribute cache against exact copy-boundary sources."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "penta-ted-two-plane-cache-contract-v4"
CADENCE_SCHEMA = "penta-boss-publication-cadence-v3"
RECORD_SIZE = 4 + 24 * 24
TED_TABLE_OFFSET = 13 * 0x4000 + (0x7600 - 0x4000)
SAMPLES = (
    350, 230, 419, 221, 186, 151, 204, 390, 399, 196, 227,
    303, 403, 431, 443, 163, 164, 185, 374, 437, 464, 564,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_sources(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if len(raw) % RECORD_SIZE:
        raise ValueError(f"{path}: size is not divisible by {RECORD_SIZE}")
    return [raw[offset + 4:offset + RECORD_SIZE]
            for offset in range(0, len(raw), RECORD_SIZE)]


def analyze(sources: list[bytes], table: bytes, samples: tuple[int, ...]) -> dict:
    layouts = [bytes(table[tile] for tile in source) for source in sources]
    signatures = [bytes(layout[index] for index in samples) for layout in layouts]
    signature_layouts: dict[bytes, bytes] = {}
    collisions = 0
    for signature, layout in zip(signatures, layouts):
        previous = signature_layouts.setdefault(signature, layout)
        collisions += previous != layout

    cache: list[bytes] = []
    misses = false_hits = 0
    for signature, layout in zip(signatures, layouts):
        hit = next((item for item in cache if item == signature), None)
        if hit is None:
            misses += 1
            cache.insert(0, signature)
            cache[:] = cache[:2]
        else:
            cache.remove(hit)
            cache.insert(0, hit)
        false_hits += signature_layouts[signature] != layout
    unique_layouts = len(set(layouts))
    return {
        "records": len(layouts),
        "unique_layouts": unique_layouts,
        "signature_cells": len(samples),
        "signature_collisions": collisions,
        "false_cache_hits": false_hits,
        "two_plane_misses": misses,
        "two_plane_hits": len(layouts) - misses,
        "full_compile_fraction": misses / len(layouts),
    }


def compact_signature(source: bytes, samples: tuple[int, ...]) -> tuple[int, int]:
    """Return the production O(1)-sized raw-source signature.

    The 22-cell raw sum has one observed attribute-layout collision.  Raw cell
    221 separates exactly that pair, so the runtime needs only direct absolute
    reads, ADDs, and one retained byte—no table walk or multiplication.
    """
    return sum(source[index] for index in samples) & 0xFF, source[221]


def analyze_compact(sources: list[bytes], table: bytes,
                    samples: tuple[int, ...]) -> dict:
    layouts = [bytes(table[tile] for tile in source) for source in sources]
    signatures = [compact_signature(source, samples) for source in sources]
    owners: dict[tuple[int, int], bytes] = {}
    collisions = 0
    for signature, layout in zip(signatures, layouts):
        previous = owners.setdefault(signature, layout)
        collisions += previous != layout
    cache: list[tuple[int, int] | None] = [None, None]
    cursor = misses = 0
    for signature in signatures:
        if signature not in cache:
            cache[cursor] = signature
            cursor ^= 1
            misses += 1
    return {
        "signature_bytes": 2,
        "unique_signatures": len(set(signatures)),
        "layout_collisions": collisions,
        "fifo_misses": misses,
        "fifo_hits": len(signatures) - misses,
    }


def analyze_physical_publications(sources: list[bytes], table: bytes,
                                  raw: bytes) -> dict:
    last: dict[int, bytes] = {}
    publications = skips = 0
    for offset, source in zip(range(0, len(raw), RECORD_SIZE), sources):
        destination = raw[offset + 2] | raw[offset + 3] << 8
        layout = bytes(table[tile] for tile in source)
        if last.get(destination) == layout:
            skips += 1
        else:
            publications += 1
            last[destination] = layout
    return {
        "attribute_publications": publications,
        "redundant_attribute_publications_skipped": skips,
        "publication_fraction": publications / (publications + skips),
    }


def analyze_runtime_keys(trace_path: Path, sources: list[bytes],
                         table: bytes) -> dict:
    keys = [bytes.fromhex(line[4:]) for line in trace_path.read_text().splitlines()
            if line.startswith("key=")]
    layouts = [bytes(table[tile] for tile in source) for source in sources]
    owners: dict[bytes, bytes] = {}
    collisions = 0
    for key, layout in zip(keys, layouts):
        previous = owners.setdefault(key, layout)
        collisions += previous != layout
    cache: list[bytes | None] = [None, None]
    cursor = misses = 0
    for key in keys:
        if key not in cache:
            cache[cursor] = key
            cursor ^= 1
            misses += 1
    return {
        "keys": len(keys), "unique_keys": len(set(keys)),
        "layout_collisions": collisions,
        "fifo_misses": misses, "fifo_hits": len(keys) - misses,
    }


def rejects_overdiscriminating_key(record_count: int) -> bool:
    """A unique key per publication is collision-free but defeats caching."""
    cache: list[int | None] = [None, None]
    cursor = misses = 0
    for key in range(record_count):
        if key not in cache:
            cache[cursor] = key
            cursor ^= 1
            misses += 1
    return misses > 50


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--cadence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cadence = json.loads(args.cadence.read_text())
    bosses = cadence.get("bosses", [])
    ted = bosses[0] if len(bosses) == 1 else {}
    dx = ted.get("dx", {}) if isinstance(ted, dict) else {}
    source_path = Path(dx.get("source_trace", ""))
    rom = args.rom.read_bytes()
    table = rom[TED_TABLE_OFFSET:TED_TABLE_OFFSET + 256]
    raw_sources = source_path.read_bytes()
    sources = read_sources(source_path)
    metrics = analyze(sources, table, SAMPLES)
    prefix_control = analyze(sources, table, SAMPLES[:-1])
    compact = analyze_compact(sources, table, SAMPLES)
    compact_control = analyze_compact(
        sources, table, SAMPLES[:-1]
    )
    physical = analyze_physical_publications(sources, table, raw_sources)
    runtime = analyze_runtime_keys(Path(dx.get("trace", "")), sources, table)
    checks = {
        "cadence_schema": cadence.get("schema") == CADENCE_SCHEMA,
        "candidate_rom_identity": cadence.get("dx_rom_sha256") == sha256(args.rom),
        "source_trace_identity": dx.get("source_trace_sha256") == sha256(source_path),
        "authoritative_horizon": ted.get("observation_frames") == 2800,
        "publication_population": metrics["records"] >= 480,
        "bounded_layout_population": metrics["unique_layouts"] <= 64,
        "collision_free_signature": metrics["signature_collisions"] == 0,
        "collision_free_compact_signature":
            compact["layout_collisions"] == 0,
        "bounded_compact_signature": compact["signature_bytes"] == 2,
        "bounded_compact_fifo_misses": compact["fifo_misses"] <= 50,
        "bounded_physical_attribute_publications":
            physical["attribute_publications"] <= 90
            and physical["redundant_attribute_publications_skipped"] >= 390,
        "runtime_key_population": runtime["keys"] == metrics["records"],
        "collision_free_runtime_key": runtime["layout_collisions"] == 0,
        "bounded_runtime_key_misses": runtime["fifo_misses"] <= 50,
        "overdiscriminating_runtime_key_negative_control":
            rejects_overdiscriminating_key(metrics["records"]),
        "no_false_cache_hits": metrics["false_cache_hits"] == 0,
        "bounded_signature": metrics["signature_cells"] <= 24,
        "two_plane_compile_budget": metrics["two_plane_misses"] <= 50
            and metrics["full_compile_fraction"] <= 0.10,
        "truncated_signature_negative_control":
            prefix_control["signature_collisions"] > 0,
        "truncated_compact_signature_negative_control":
            compact_control["layout_collisions"] > 0,
    }
    receipt = {
        "schema": SCHEMA,
        "rom_sha256": sha256(args.rom),
        "source_trace_sha256": sha256(source_path),
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "samples": list(SAMPLES),
        "metrics": metrics,
        "compact_signature": compact,
        "physical_publication_cache": physical,
        "runtime_key": runtime,
        "negative_control": prefix_control,
        "compact_negative_control": compact_control,
        "sources": {
            "rom": str(args.rom.resolve()),
            "cadence": str(args.cadence.resolve()),
            "copy_sources": str(source_path.resolve()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
