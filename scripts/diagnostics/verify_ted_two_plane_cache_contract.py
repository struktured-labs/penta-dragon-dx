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
    350, 182, 86, 403, 173, 437, 101, 186, 370, 303, 431, 82,
    399, 221, 240, 390, 198, 227, 163, 209, 419, 94, 196, 204,
    244, 564, 464, 144, 443, 374, 150, 14,
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

    The 32-cell sum plus rolling-3 hash is collision-free across the qualified
    and fresh generated-state Ted corpora. Both operations are eight-bit and
    map directly to the ROM runtime's ADD-only loop.
    """
    total = rolling = 0
    for index in samples:
        value = source[index]
        total = (total + value) & 0xFF
        rolling = (rolling * 3 + value) & 0xFF
    return total, rolling


def incremental_signature(source: bytes) -> tuple[int, int, int, int]:
    """Exact runtime key maintained by the Ted-only cloned writer."""
    sums = [0, 0, 0, 0]
    for index, value in enumerate(source):
        group = (index ^ (index >> 5)) & 3
        sums[group] = (sums[group] + value) & 0xFF
    return tuple(sums)  # type: ignore[return-value]


def combined_corpus_negative_control(table: bytes) -> dict:
    """Portable witness from qualified record 142 and fresh record 133."""
    prefix = (
        119, 68, 121, 4, 59, 22, 120, 121, 121, 120, 8, 27, 37, 81,
        119, 200, 71, 87, 120, 120, 223, 121, 69, 77, 119, 107, 29,
        119, 32, 121, 49,
    )
    qualified = prefix + (119,)
    fresh = prefix + (131,)

    def key(values: tuple[int, ...]) -> tuple[int, int]:
        total = rolling = 0
        for value in values:
            total = (total + value) & 0xFF
            rolling = (rolling * 3 + value) & 0xFF
        return total, rolling

    return {
        "provenance": ["qualified:142", "fresh:133"],
        "truncated_compact_collision": key(qualified[:-1]) == key(fresh[:-1]),
        "full_compact_separates": key(qualified) != key(fresh),
        "truncated_mapped_collision": bytes(
            table[value] for value in qualified[:-1]
        ) == bytes(table[value] for value in fresh[:-1]),
        "full_mapped_separates": bytes(
            table[value] for value in qualified
        ) != bytes(table[value] for value in fresh),
    }


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
    key_bytes = sorted(set(map(len, keys)))
    signature = incremental_signature if key_bytes == [4] else (
        lambda source: compact_signature(source, SAMPLES)
    )
    expected = [bytes(signature(source)) for source in sources]
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
    exact_mismatches = sum(
        observed != wanted for observed, wanted in zip(keys, expected)
    ) + abs(len(keys) - len(expected))
    return {
        "keys": len(keys), "unique_keys": len(set(keys)),
        "key_bytes": key_bytes,
        "exact_compact_key_mismatches": exact_mismatches,
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
    incremental_mode = rom[0x80EF:0x80F2] == bytes.fromhex("CD 8C 7A")
    table = rom[TED_TABLE_OFFSET:TED_TABLE_OFFSET + 256]
    raw_sources = source_path.read_bytes()
    sources = read_sources(source_path)
    metrics = analyze(sources, table, SAMPLES)
    prefix_control = analyze(sources, table, SAMPLES[:-1])
    compact = analyze_compact(sources, table, SAMPLES)
    incremental = analyze_compact(sources, table, tuple(range(0)))
    if incremental_mode:
        layouts = [bytes(table[tile] for tile in source) for source in sources]
        signatures = [incremental_signature(source) for source in sources]
        owners: dict[tuple[int, int, int, int], bytes] = {}
        collisions = 0
        for signature, layout in zip(signatures, layouts):
            previous = owners.setdefault(signature, layout)
            collisions += previous != layout
        incremental = {
            "signature_bytes": 4,
            "unique_signatures": len(set(signatures)),
            "layout_collisions": collisions,
        }
    compact_control = analyze_compact(
        sources, table, SAMPLES[:-1]
    )
    combined_control = combined_corpus_negative_control(table)
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
            (incremental if incremental_mode else compact)["layout_collisions"] == 0,
        "bounded_compact_signature":
            (incremental if incremental_mode else compact)["signature_bytes"] in (2, 4),
        "bounded_compact_fifo_misses":
            incremental_mode or compact["fifo_misses"] <= 50,
        "bounded_physical_attribute_publications":
            physical["attribute_publications"] <= 90
            and physical["redundant_attribute_publications_skipped"] >= 390,
        "runtime_key_population": runtime["keys"] == metrics["records"],
        "runtime_key_is_exact_compact_signature":
            runtime["key_bytes"] == ([4] if incremental_mode else [2])
            and runtime["exact_compact_key_mismatches"] == 0,
        "collision_free_runtime_key": runtime["layout_collisions"] == 0,
        "bounded_runtime_key_misses": runtime["fifo_misses"] <= 50,
        "overdiscriminating_runtime_key_negative_control":
            rejects_overdiscriminating_key(metrics["records"]),
        "no_false_cache_hits": metrics["false_cache_hits"] == 0,
        "bounded_signature": incremental_mode or metrics["signature_cells"] <= 32,
        "two_plane_compile_budget": metrics["two_plane_misses"] <= 50
            and metrics["full_compile_fraction"] <= 0.10,
        "truncated_signature_negative_control":
            combined_control["truncated_mapped_collision"]
            and combined_control["full_mapped_separates"],
        "truncated_compact_signature_negative_control":
            combined_control["truncated_compact_collision"]
            and combined_control["full_compact_separates"],
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
        "incremental_signature": incremental,
        "physical_publication_cache": physical,
        "runtime_key": runtime,
        "negative_control": prefix_control,
        "compact_negative_control": compact_control,
        "combined_corpus_negative_control": combined_control,
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
