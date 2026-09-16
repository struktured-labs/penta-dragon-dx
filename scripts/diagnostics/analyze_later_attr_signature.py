#!/usr/bin/env python3
"""Search/audit the two-byte Stage 2-7 packed-layout cache signature.

The runtime stores two XORs of three C1A0 cells plus FFBD. A cache collision
can expose a newly shifted tile plane with the previous pickup/material
attributes, so this tool evaluates raw layouts against their complete desired
semantic attribute planes. Inputs are receipt artifacts, never ROM assets.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
from pathlib import Path
import random
import re


RAW_SIZE = 24 * 24
STATE_FEATURES = ("scx", "scy", "dc00", "dc01", "dc02", "dc03", "dc0b", "ffcf")
FEATURE_SIZE = RAW_SIZE + len(STATE_FEATURES)
LAYOUT_STAGE = re.compile(r"stage(?P<stage>[2-7])\.layout-events\.tsv$")


def semantic_lut(stage: int) -> bytes:
    table = bytearray(256)
    health = (0x88, 0x89, 0x96, 0x98, 0x99)
    rare = (0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7)
    if stage in (3, 5, 6):
        for tile in health:
            table[tile] = 1
    if stage in (2, 5, 7):
        for tile in rare:
            table[tile] = 2
    if stage == 4:
        for tile in range(0x01, 0x09):
            table[tile] = 4
        table[0x2D] = table[0x2E] = 2
    if stage == 5:
        for tile in (*range(0x02, 0x08), *range(0x12, 0x18)):
            table[tile] = 5
    if stage == 7:
        for tile in (0xA0, 0xA1, 0xB0, 0xB1):
            table[tile] = 4
        table[0x19] = table[0x1A] = 5
    return bytes(table)


def desired_plane(stage: int, raw: bytes) -> bytes:
    lut = semantic_lut(stage)
    return bytes(lut[tile] for tile in raw)


def parse_layout_trace(path: Path) -> list[tuple[int, int, bytes]]:
    match = LAYOUT_STAGE.search(path.name)
    if not match:
        raise ValueError(f"cannot infer stage from {path}")
    stage = int(match.group("stage"))
    rows = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        raw = bytes.fromhex(fields[-1])
        if len(raw) != RAW_SIZE:
            raise ValueError(f"{path}:{number}: raw size {len(raw)}")
        if len(fields) < 14:
            raise ValueError(
                f"{path}:{number}: layout trace lacks current state fields"
            )
        dc = bytes.fromhex(fields[9])
        if len(dc) != 4:
            raise ValueError(f"{path}:{number}: malformed DC00-DC03 field")
        state = bytes((int(fields[7], 16), int(fields[8], 16))) + dc + bytes(
            (int(fields[10], 16), int(fields[11], 16))
        )
        rows.append((stage, int(fields[1], 16), raw + state))
    return rows


def parse_publication_trace(stage: int, path: Path) -> list[tuple[int, int, bytes]]:
    rows = []
    lines = path.read_text().splitlines()
    if not lines:
        return rows
    header = lines[0].split("\t")
    columns = {name: index for index, name in enumerate(header)}
    for number, line in enumerate(lines[1:], 2):
        fields = line.split("\t")
        if fields[columns["event"]] != "copy-entry":
            continue
        raw_text = fields[columns["raw"]]
        if raw_text == "-":
            continue
        raw = bytes.fromhex(raw_text)
        if len(raw) != RAW_SIZE:
            raise ValueError(f"{path}:{number}: raw size {len(raw)}")
        state = bytes(int(fields[columns[name]], 16) for name in STATE_FEATURES)
        rows.append((stage, int(fields[columns["room"]], 16), raw + state))
    return rows


def xor_key(raw: bytes, samples: tuple[int, ...]) -> int:
    value = 0
    for offset in samples:
        value ^= raw[offset]
    return value


def metrics(records, a: tuple[int, ...], b: tuple[int, ...],
            context: tuple[int, ...] = ()) -> tuple[int, int]:
    key_semantics = defaultdict(set)
    semantic_keys = defaultdict(set)
    for stage, room, raw, semantic in records:
        context_value = room ^ xor_key(raw, context)
        key = (stage, context_value, xor_key(raw, a), xor_key(raw, b))
        key_semantics[key].add(semantic)
        semantic_keys[(stage, room, semantic)].add(key[1:])
    collisions = sum(len(values) - 1 for values in key_semantics.values())
    false_variants = sum(len(values) - 1 for values in semantic_keys.values())
    return collisions, false_variants


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout_trace", nargs="*", type=Path)
    parser.add_argument(
        "--publication", action="append", default=[], metavar="STAGE:PATH",
        help="add a stage-side publication trace containing full raw sources",
    )
    parser.add_argument("--trials", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=0x503301)
    parser.add_argument("--size-a", type=int, default=3)
    parser.add_argument("--size-b", type=int, default=3)
    parser.add_argument(
        "--allow-variant-offsets", action="store_true",
        help="allow animation/state features that can cause extra rebuilds",
    )
    parser.add_argument(
        "--search-addition", action="store_true",
        help="exhaustively append one feature to either current XOR",
    )
    parser.add_argument(
        "--search-paired-additions", action="store_true",
        help="append one feature to each current XOR and search the pair",
    )
    parser.add_argument("--current-a", default="15,83,230")
    parser.add_argument("--current-b", default="250,337,433")
    parser.add_argument(
        "--context", default="",
        help="feature offsets XORed with FFBD in the third cache byte",
    )
    args = parser.parse_args()

    observed = []
    corpus_hash = hashlib.sha256()
    for path in args.layout_trace:
        corpus_hash.update(path.read_bytes())
        observed.extend(parse_layout_trace(path))
    for spec in args.publication:
        stage_text, path_text = spec.split(":", 1)
        path = Path(path_text)
        corpus_hash.update(path.read_bytes())
        observed.extend(parse_publication_trace(int(stage_text), path))
    unique = {(stage, room, features) for stage, room, features in observed}
    records = [
        (stage, room, features, desired_plane(stage, features[:RAW_SIZE]))
        for stage, room, features in sorted(unique)
    ]
    if not records:
        raise SystemExit("no corpus records")

    current_a = tuple(int(value) for value in args.current_a.split(","))
    current_b = tuple(int(value) for value in args.current_b.split(","))
    context = tuple(
        int(value) for value in args.context.split(",") if value
    )
    current = metrics(records, current_a, current_b, context)
    print(
        f"records={len(records)} corpus_sha256={corpus_hash.hexdigest()} "
        f"current={current_a}/{current_b} collisions={current[0]} "
        f"false_variants={current[1]}"
    )

    rng = random.Random(args.seed)
    # Dynamic animation cells create expensive false variants. Prefer source
    # offsets whose values are stable within an identical semantic plane.
    values_by_semantic = defaultdict(lambda: defaultdict(set))
    for stage, room, raw, semantic in records:
        owner = values_by_semantic[(stage, room, semantic)]
        for offset, value in enumerate(raw):
            owner[offset].add(value)
    stable_offsets = [
        offset for offset in range(FEATURE_SIZE)
        if all(len(owner[offset]) == 1 for owner in values_by_semantic.values())
    ]
    raw_values_by_room = defaultdict(lambda: defaultdict(set))
    for stage, room, raw, _semantic in records:
        owner = raw_values_by_room[(stage, room)]
        for offset, value in enumerate(raw):
            owner[offset].add(value)
    informative_offsets = {
        offset for offset in range(FEATURE_SIZE)
        if any(len(owner[offset]) > 1 for owner in raw_values_by_room.values())
    }
    stable_offsets = [
        offset for offset in stable_offsets if offset in informative_offsets
    ]
    if args.allow_variant_offsets:
        stable_offsets = sorted(informative_offsets)
    sample_count = args.size_a + args.size_b
    if len(stable_offsets) < sample_count:
        stable_offsets = list(range(FEATURE_SIZE))
    names = {
        RAW_SIZE + index: name for index, name in enumerate(STATE_FEATURES)
    }
    print(
        f"stable_offsets={len(stable_offsets)} trials={args.trials} "
        f"state_features={names}"
    )
    best = (current[0], current[1], current_a, current_b)
    if args.search_addition:
        for offset in range(FEATURE_SIZE):
            if offset not in current_a:
                a = current_a + (offset,)
                result = metrics(records, a, current_b, context)
                best = min(best, (result[0], result[1], a, current_b))
            if offset not in current_b:
                b = current_b + (offset,)
                result = metrics(records, current_a, b, context)
                best = min(best, (result[0], result[1], current_a, b))
        print(
            f"addition_best collisions={best[0]} false_variants={best[1]} "
            f"a={best[2]} b={best[3]}"
        )
    if args.search_paired_additions:
        for offset_a in stable_offsets:
            if offset_a in current_a:
                continue
            a = current_a + (offset_a,)
            for offset_b in stable_offsets:
                if offset_b in current_b or offset_b == offset_a:
                    continue
                b = current_b + (offset_b,)
                result = metrics(records, a, b, context)
                candidate = (result[0], result[1], a, b)
                if candidate < best:
                    best = candidate
                    print(
                        f"paired_best collisions={best[0]} "
                        f"false_variants={best[1]} a={best[2]} b={best[3]}"
                    )
                    if best[:2] == (0, 0):
                        break
            if best[:2] == (0, 0):
                break
    for _ in range(args.trials):
        selected = rng.sample(stable_offsets, sample_count)
        a = tuple(sorted(selected[:args.size_a]))
        b = tuple(sorted(selected[args.size_a:]))
        result = metrics(records, a, b, context)
        candidate = (result[0], result[1], a, b)
        if candidate < best:
            best = candidate
            print(
                f"best collisions={best[0]} false_variants={best[1]} "
                f"a={best[2]} b={best[3]}"
            )
            if best[:2] == (0, 0):
                break
    if best[0]:
        raise SystemExit("no collision-free key found")
    print(f"PASS a={best[2]} b={best[3]} false_variants={best[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
