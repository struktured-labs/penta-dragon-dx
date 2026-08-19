#!/usr/bin/env python3
"""Qualify crown uniqueness/alignment for the 576-bit Ted mask builder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROWS = COLS = 24
SOURCE_SIZE = ROWS * COLS
SOURCE_RECORD_SIZE = 4 + SOURCE_SIZE
SOURCE_MAP_RECORD_SIZE = SOURCE_RECORD_SIZE + 2 * 0x400
CROWN = bytes(range(2, 7))
SPANS = (
    (0, 5), (-2, 6), (-2, 6), (-2, 6), (-2, 6), (-2, 7),
    (-3, 7), (-4, 7), (-4, 7), (-4, 7), (-3, 7), (-2, 6),
    (0, 6), (1, 5),
)
SPARSE = frozenset((0x7B, 0x7D, 0x80, 0x82, 0x83, 0x84, 0x85, 0x86))


def crowns(source: bytes) -> list[tuple[int, int]]:
    return [
        (row, col)
        for row in range(ROWS)
        for col in range(COLS - len(CROWN) + 1)
        if source[row * COLS + col:row * COLS + col + len(CROWN)] == CROWN
    ]


def read_sources(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"{path}: invalid {len(raw)}-byte source trace")
    if len(raw) % SOURCE_MAP_RECORD_SIZE == 0:
        record_size = SOURCE_MAP_RECORD_SIZE
    elif len(raw) % SOURCE_RECORD_SIZE == 0:
        record_size = SOURCE_RECORD_SIZE
    else:
        raise ValueError(
            f"{path}: invalid {len(raw)}-byte source trace; expected "
            f"{SOURCE_RECORD_SIZE}- or {SOURCE_MAP_RECORD_SIZE}-byte records"
        )
    return [
        raw[offset + 4:offset + 4 + SOURCE_SIZE]
        for offset in range(0, len(raw), record_size)
    ]


def body_mask(anchor: tuple[int, int] | None) -> bytearray:
    mask = bytearray(72)
    if anchor is None:
        return mask
    for rel_row, (left, right) in enumerate(SPANS):
        row = anchor[0] + rel_row
        for col in range(anchor[1] + left, anchor[1] + right):
            packed = row * COLS + col
            mask[packed >> 3] |= 1 << (packed & 7)
    return mask


def classify(tile: int, allowed: bool) -> tuple[int, int]:
    keep = tile < 2 or tile in SPARSE or (2 <= tile < 0x77 and allowed)
    colored = tile in SPARSE or (2 <= tile < 0x77 and allowed)
    return (tile if keep else 0, ((tile % 7) + 1) if colored else 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sources = read_sources(args.trace)
    histogram: dict[str, int] = {}
    invalid: list[dict[str, object]] = []
    retained_anchor: tuple[int, int] | None = None
    crownless_records = 0
    for index, source in enumerate(sources):
        found = crowns(source)
        if len(found) == 1:
            retained_anchor = found[0]
        elif not found:
            crownless_records += 1
        anchor = retained_anchor if len(found) <= 1 else None
        aligned = anchor is not None and anchor[1] % 4 == 0
        bounded = anchor is not None and (
            anchor[0] + 14 <= ROWS
            and anchor[1] >= 4
            and anchor[1] + 7 <= COLS
        )
        if not aligned or not bounded:
            invalid.append({
                "record": index,
                "crowns": [list(item) for item in found],
                "aligned": aligned,
                "bounded": bounded,
            })
        if anchor is not None:
            key = f"{anchor[0]}:{anchor[1]}"
            histogram[key] = histogram.get(key, 0) + 1

    # Prove the gate rejects the two layouts the runtime must fail closed on.
    ambiguous = bytearray(sources[0])
    for step, tile in enumerate(CROWN):
        ambiguous[20 * COLS + 1 + step] = tile
    shifted = bytearray(sources[0])
    original = crowns(shifted)
    shifted_rejected = False
    if len(original) == 1:
        row, col = original[0]
        shifted[row * COLS + col:row * COLS + col + 5] = bytes([0x77]) * 5
        shifted[row * COLS + col + 1:row * COLS + col + 6] = CROWN
        shifted_found = crowns(shifted)
        shifted_rejected = (
            len(shifted_found) == 1 and shifted_found[0][1] % 4 != 0
        )
    ambiguous_rejected = len(crowns(ambiguous)) != 1

    old_mask = bytearray(72)
    delta_mismatches = no_delta_mismatches = mask_transitions = 0
    changed_membership_cells = max_changed_membership_cells = 0
    edge_publications = 0
    retained_anchor = None
    for source in sources:
        found = crowns(source)
        if len(found) == 1:
            retained_anchor = found[0]
        elif len(found) > 1:
            retained_anchor = None
        anchor = retained_anchor
        new_mask = body_mask(anchor)
        direct = [
            classify(tile, bool(old_mask[index >> 3] & (1 << (index & 7))))
            for index, tile in enumerate(source)
        ]
        no_delta = list(direct)
        changed = bytes(left ^ right for left, right in zip(old_mask, new_mask))
        changed_cells = sum(byte.bit_count() for byte in changed)
        changed_membership_cells += changed_cells
        max_changed_membership_cells = max(
            max_changed_membership_cells, changed_cells
        )
        if any(changed):
            mask_transitions += 1
        if anchor is not None and (anchor[0] == 0 or anchor[1] == 16):
            edge_publications += 1
        for index, tile in enumerate(source):
            if changed[index >> 3] & (1 << (index & 7)):
                direct[index] = classify(
                    tile, bool(new_mask[index >> 3] & (1 << (index & 7)))
                )
        expected = [
            classify(tile, bool(new_mask[index >> 3] & (1 << (index & 7))))
            for index, tile in enumerate(source)
        ]
        delta_mismatches += sum(a != b for a, b in zip(direct, expected))
        no_delta_mismatches += sum(
            a != b for a, b in zip(no_delta, expected)
        )
        old_mask = new_mask

    passed = (
        not invalid and ambiguous_rejected and shifted_rejected
        and delta_mismatches == 0
        and no_delta_mismatches > 0
        and edge_publications > 0
    )
    receipt = {
        "schema": "penta-ted-incremental-mask-corpus-v1",
        "status": "pass" if passed else "fail",
        "records": len(sources),
        "crownless_records_using_retained_anchor": crownless_records,
        "unique_anchor_positions": len(histogram),
        "anchor_histogram": dict(sorted(histogram.items())),
        "invalid_records": invalid[:32],
        "negative_controls": {
            "ambiguous_crown_rejected": ambiguous_rejected,
            "unaligned_crown_rejected": shifted_rejected,
            "missing_delta_repair_mismatches": no_delta_mismatches,
        },
        "fused_mask_delta": {
            "mask_transitions": mask_transitions,
            "classification_mismatches": delta_mismatches,
            "row0_or_col16_publications": edge_publications,
            "changed_membership_cells": changed_membership_cells,
            "max_changed_membership_cells": max_changed_membership_cells,
            "average_repair_cells_per_publication": (
                changed_membership_cells / len(sources)
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
