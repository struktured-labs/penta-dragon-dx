#!/usr/bin/env python3
"""Static footprint, timing, and retained-corpus checks for experimental r534."""

from __future__ import annotations

from collections import defaultdict
import hashlib
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import compose_ending_bgp_handoff_r518 as r518  # noqa: E402
import compose_stage4_cache_key_r534 as r534  # noqa: E402
import compose_story_neutral_guard_r533 as r533  # noqa: E402


EXPECTED_SHA256 = (
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
)
CORPORA = (
    (
        ROOT / "tmp/stage2-isolated-entry-r263/stage346-semantic-soak-8000/"
        "stage4.layout-events.tsv",
        "54becf276a33dc9f51cce123d39c8ce80f58be04f4b186a534c34ae2a672c90a",
        328,
    ),
    (
        ROOT / "tmp/stage4-lazy-departure-r286/"
        "stage4-semantic-soak-8000-r1/stage4.layout-events.tsv",
        "b7aef5fa5200045ddfad99b9224481409127f9720ffcc84bdff4485533caf0fd",
        87,
    ),
    (
        ROOT / "tmp/r533-stage4-dma-current302/stage4.layout-events.tsv",
        "ede54fe6b4bc5d98ebdf1a2c173ebbd9c9b06d5a54b785cfa3abf42142bbdc0f",
        238,
    ),
)
OLD_KEY_A = (81,)
OLD_KEY_B = (337,)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def plane(raw: bytes) -> bytes:
    return bytes(
        4 if 0x01 <= tile <= 0x08 else 2 if tile in (0x2D, 0x2E) else 0
        for tile in raw
    )


def xor_key(raw: bytes, samples: tuple[int, ...]) -> int:
    value = 0
    for sample in samples:
        value ^= raw[sample]
    return value


def parse(path: Path, expected_sha: str, expected_rows: int):
    payload = path.read_bytes()
    if digest(payload) != expected_sha:
        raise AssertionError(f"retained corpus identity changed: {path}")
    rows = []
    for number, line in enumerate(payload.decode().splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 14:
            raise AssertionError(f"{path}:{number}: expected 14 fields")
        raw = bytes.fromhex(fields[13])
        if len(raw) != 576:
            raise AssertionError(f"{path}:{number}: truncated raw layout")
        rows.append((int(fields[2], 16), int(fields[1], 16), raw, plane(raw)))
    if len(rows) != expected_rows:
        raise AssertionError(f"{path}: expected {expected_rows} rows")
    return rows


def metrics(corpora, samples_a: tuple[int, ...], samples_b: tuple[int, ...]):
    by_key = defaultdict(set)
    by_plane = defaultdict(set)
    false_hits = hits = misses = 0
    misses_by_corpus = []
    false_hits_by_corpus = []
    unique = {}
    for rows in corpora:
        caches = {}
        local_misses = local_false_hits = 0
        for physical, room, raw, semantic in rows:
            key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
            unique[(room, raw)] = semantic
            previous = caches.get(physical)
            if previous is not None and previous[0] == key:
                hits += 1
                if previous[1] != semantic:
                    false_hits += 1
                    local_false_hits += 1
            else:
                misses += 1
                local_misses += 1
                caches[physical] = (key, semantic)
        misses_by_corpus.append(local_misses)
        false_hits_by_corpus.append(local_false_hits)
    for (room, raw), semantic in unique.items():
        key = (room, xor_key(raw, samples_a), xor_key(raw, samples_b))
        by_key[key].add(semantic)
        by_plane[(room, semantic)].add(key)
    return {
        "rows": sum(len(rows) for rows in corpora),
        "unique_records": len(unique),
        "collisions": sum(len(values) - 1 for values in by_key.values()),
        "false_variants": sum(len(values) - 1 for values in by_plane.values()),
        "hits": hits,
        "misses": misses,
        "false_hits": false_hits,
        "misses_by_corpus": misses_by_corpus,
        "false_hits_by_corpus": false_hits_by_corpus,
    }


source = r518.BASE.read_bytes()
parent, _ = r533.build(source)
candidate, receipt = r534.build(source)
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


check(digest(parent) == r534.PARENT_SHA256, "r533 parent digest differs")
check(digest(candidate) == EXPECTED_SHA256, "r534 candidate digest differs")
check(receipt["candidate_sha256"] == EXPECTED_SHA256,
      "r534 receipt digest differs")

changed = {
    index for index, (before, after) in enumerate(zip(parent, candidate))
    if before != after
}
receipt_changed = {int(value, 16) for value in receipt["changed_from_parent"]}
check(changed == receipt_changed, "r534 changed-offset receipt differs")
check(changed - r534.CHECKSUM_OFFSETS == {
    int(value, 16) for value in receipt["functional_changed_offsets"]
}, "r534 functional delta differs")

delay = r534.offset(r534.DELAY_SOURCE_ADDR)
helper = r534.offset(r534.HELPER_KEY_SOURCE_ADDR)
check(candidate[delay:delay + len(r534.NEW_DELAY_REGION)]
      == r534.NEW_DELAY_REGION, "r534 second-key fragment differs")
check(candidate[helper:helper + len(r534.NEW_HELPER_REGION)]
      == r534.NEW_HELPER_REGION, "r534 first-key fragment differs")
runtime_jr_site = 0xDB3A
runtime_jr_target = runtime_jr_site + 2 + int.from_bytes(
    r534.NEW_HELPER_REGION[9:10], "little", signed=True
)
check(runtime_jr_target == 0xDB0D, "r534 cross-fragment JR target differs")
check(r534.NEW_DELAY_REGION[8:11] == bytes.fromhex("C3 92 DA"),
      "r534 shared compare join differs")
check(receipt["runtime"]["delta_t_per_stage4_decision"] == 4,
      "r534 hot-path timing delta differs")

corpora = [parse(*spec) for spec in CORPORA]
old = metrics(corpora, OLD_KEY_A, OLD_KEY_B)
new = metrics(corpora, r534.KEY_A, r534.KEY_B)
check(old == {
    "rows": 653,
    "unique_records": 32,
    "collisions": 7,
    "false_variants": 0,
    "hits": 510,
    "misses": 143,
    "false_hits": 31,
    "misses_by_corpus": [50, 52, 41],
    "false_hits_by_corpus": [0, 0, 31],
}, f"old-key negative control differs: {old}")
check(new == {
    "rows": 653,
    "unique_records": 32,
    "collisions": 0,
    "false_variants": 0,
    "hits": 500,
    "misses": 153,
    "false_hits": 0,
    "misses_by_corpus": [50, 52, 51],
    "false_hits_by_corpus": [0, 0, 0],
}, f"r534 key/replay metrics differ: {new}")

if failures:
    print("FAIL")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("PASS")
print(f"parent delta bytes {len(changed)} ({len(changed - r534.CHECKSUM_OFFSETS)} functional)")
print(f"old key: {old}")
print(f"new key: {new}")
print("Stage 4 key path +4T/decision, still 36T faster than native")
print(f"candidate sha256 {EXPECTED_SHA256}")
