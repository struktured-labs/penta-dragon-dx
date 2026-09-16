#!/usr/bin/env python3
"""Prove the complete two-map Stage-7 block-cache model.

This is intentionally a static/corpus gate, not a ROM builder.  It qualifies
the completed-C1A0 signature used by a prospective Stage-7 publisher and
models exact dirty-block publication for both physical BG maps.  Any unseen
pair must take the runtime slow path; corpus membership is never treated as a
proof that future pairs cannot exist.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from analyze_later_attr_signature import semantic_lut  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def desired_plane(raw: bytes, lut: bytes) -> bytes:
    plane = bytearray(24 * 32)
    for row in range(24):
        for column in range(24):
            plane[row * 32 + column] = lut[raw[row * 24 + column]]
    return bytes(plane)


def blocks(raw: bytes, lut: bytes):
    for block_row in range(12):
        for block_column in range(12):
            source = block_row * 48 + block_column * 2
            pair = (raw[source + 1], raw[source + 24])
            quartet = (
                lut[raw[source]],
                lut[raw[source + 1]],
                lut[raw[source + 24]],
                lut[raw[source + 25]],
            )
            yield block_row, block_column, pair, quartet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path("tmp"),
        help="scratch tree containing archived stage7.layout-events.tsv files",
    )
    parser.add_argument(
        "--receipt", type=Path,
        default=Path("tmp/stage7-block-pair-cache/static-receipt.json"),
    )
    args = parser.parse_args()

    paths = sorted(args.root.glob("**/stage7.layout-events.tsv"))
    if len(paths) != 24:
        raise AssertionError(f"expected exact 24-file corpus, found {len(paths)}")
    lut = bytes(semantic_lut(7))
    corpus: list[tuple[Path, list[tuple[int, bytes]]]] = []
    pair_outputs: dict[tuple[int, int], set[tuple[int, ...]]] = defaultdict(set)
    top_outputs: dict[int, set[tuple[int, ...]]] = defaultdict(set)
    bottom_outputs: dict[int, set[tuple[int, ...]]] = defaultdict(set)
    valid_layouts = malformed = 0
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
        events: list[tuple[int, bytes]] = []
        for line in path.read_text().splitlines():
            fields = line.split("\t")
            if len(fields[-1]) != 1152:
                malformed += 1
                continue
            raw = bytes.fromhex(fields[-1])
            destination = int(fields[2], 16)
            if destination not in (0x9800, 0x9C00) or len(raw) != 576:
                raise AssertionError(f"invalid layout record in {path}")
            events.append((destination, raw))
            valid_layouts += 1
            for _, _, pair, quartet in blocks(raw, lut):
                pair_outputs[pair].add(quartet)
                top_outputs[pair[0]].add(quartet)
                bottom_outputs[pair[1]].add(quartet)
        corpus.append((path, events))

    block_samples = valid_layouts * 144
    if valid_layouts != 1645 or block_samples != 236880:
        raise AssertionError(
            f"corpus width changed: layouts={valid_layouts} blocks={block_samples}"
        )
    if len(pair_outputs) != 52:
        raise AssertionError(f"expected 52 observed pairs, got {len(pair_outputs)}")
    pair_collisions = sum(len(outputs) - 1 for outputs in pair_outputs.values())
    if pair_collisions:
        raise AssertionError(f"two-tile signature has {pair_collisions} collisions")

    # Required negative control: neither individual source tile is sufficient.
    top_collisions = sum(len(outputs) - 1 for outputs in top_outputs.values())
    bottom_collisions = sum(len(outputs) - 1 for outputs in bottom_outputs.values())
    if not top_collisions or not bottom_collisions:
        raise AssertionError("single-tile collision negative control disappeared")

    # h = top_right + 38 * bottom_left (mod 256).  Runtime can implement the
    # multiply through one immutable 256-byte page.  The record selected by
    # h still stores and compares both bytes, so an unseen/colliding pair
    # fails closed to the exact LUT slow path rather than trusting the hash.
    hashes = {
        pair: (pair[0] + 38 * pair[1]) & 0xFF for pair in pair_outputs
    }
    if len(set(hashes.values())) != len(hashes):
        raise AssertionError("pair hash is no longer injective on the corpus")
    record_ids = {
        pair: index for index, pair in enumerate(sorted(pair_outputs))
    }

    dirty_histogram: Counter[int] = Counter()
    initialized_maps = dirty_events = total_blocks = 0
    for path, events in corpus:
        caches = {0x9800: bytearray([0xFF] * 144),
                  0x9C00: bytearray([0xFF] * 144)}
        planes = {0x9800: bytearray(768), 0x9C00: bytearray(768)}
        published = {0x9800: bytearray(768), 0x9C00: bytearray(768)}
        valid: set[int] = set()
        for destination, raw in events:
            cache, plane = caches[destination], planes[destination]
            dirty: set[int] = set()
            if destination not in valid:
                # A physical map's first publication initializes all padding
                # and all semantic cells, independent of their zero value.
                dirty.update(range(48))
                valid.add(destination)
                initialized_maps += 1
            for row, column, pair, quartet in blocks(raw, lut):
                position = row * 12 + column
                record_id = record_ids[pair]
                if cache[position] == record_id:
                    continue
                cache[position] = record_id
                output = row * 64 + column * 2
                old = (plane[output], plane[output + 1],
                       plane[output + 32], plane[output + 33])
                if old == quartet:
                    continue
                plane[output], plane[output + 1] = quartet[:2]
                plane[output + 32], plane[output + 33] = quartet[2:]
                half = 0 if column < 8 else 1
                dirty.update((row * 4 + half, row * 4 + 2 + half))

            expected = desired_plane(raw, lut)
            if bytes(plane) != expected:
                raise AssertionError(f"shadow mismatch in {path}")
            for block in dirty:
                start = block * 16
                published[destination][start:start + 16] = plane[start:start + 16]
            if bytes(published[destination]) != expected:
                raise AssertionError(f"sparse publication leaves a trail in {path}")
            dirty_histogram[len(dirty)] += 1
            total_blocks += len(dirty)
            dirty_events += bool(dirty)

    receipt = {
        "schema": "penta-stage7-block-pair-cache-static-v1",
        "status": "STATIC_PASS_EMULATOR_REQUIRED",
        "corpus": {
            "files": len(paths),
            "valid_layouts": valid_layouts,
            "malformed_rows_skipped": malformed,
            "two_by_two_blocks": block_samples,
            "sha256": digest.hexdigest(),
            "file_sha256": {str(path): sha256(path) for path in paths},
        },
        "signature": {
            "fields": ["top_right_raw_tile", "bottom_left_raw_tile"],
            "observed_pairs": len(pair_outputs),
            "semantic_quartet_collisions": pair_collisions,
            "hash": "(top_right + 38 * bottom_left) & 0xFF",
            "hash_collisions": 0,
            "exact_pair_recheck_required": True,
            "unseen_pair_policy": "fail closed to exact four-cell LUT slow path",
        },
        "negative_controls": {
            "top_right_only_semantic_collisions": top_collisions,
            "bottom_left_only_semantic_collisions": bottom_collisions,
            "single_tile_key_rejected": True,
        },
        "two_map_model": {
            "plane_bytes_per_map": 768,
            "cache_bytes_per_map": 144,
            "dirty_mask_bytes_per_map": 6,
            "first_map_initializations": initialized_maps,
            "events_with_publication": dirty_events,
            "published_blocks": total_blocks,
            "average_blocks_per_all_layouts": total_blocks / valid_layouts,
            "average_blocks_per_dirty_layout": total_blocks / dirty_events,
            "maximum_blocks": max(dirty_histogram),
            "dirty_block_histogram": {
                str(key): value for key, value in sorted(dirty_histogram.items())
            },
            "exact_shadow_equality_every_layout": True,
            "exact_sparse_publication_every_layout": True,
            "neutral_transitions_clear_old_attrs": True,
        },
        "wram_layout": {
            "plane": "$D000-$D2FF in destination-owned SVBK2/SVBK3",
            "record_cache": "$D300-$D38F (144 bytes)",
            "dirty_mask": "$D390-$D395 (6 bytes)",
            "validity_and_owner": "$D3F8-$D3FF",
            "below_stage2_runtime_D400": True,
            "scene7_gate_required": True,
        },
        "transport_contract": {
            "initial_physical_map": "all 48 blocks before display",
            "later_map": "all and only changed 16-byte blocks before display",
            "atomic_map_flip_after_completion": True,
            "active_lcd_gdma_forbidden": True,
            "r158_static_definition_table_reuse_forbidden": True,
        },
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
