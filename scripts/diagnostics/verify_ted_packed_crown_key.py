#!/usr/bin/env python3
"""Prove the compact Ted crown-key writer against a captured source corpus."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROWS = COLS = 24
RECORD_SIZE = 4 + ROWS * COLS
CROWN = bytes(range(2, 7))
ELIGIBLE = ((0, 8), (4, 4), (4, 8), (4, 12), (4, 16), (8, 8), (8, 12))


def sources(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if not raw or len(raw) % RECORD_SIZE:
        raise ValueError(f"{path}: invalid {len(raw)}-byte source corpus")
    return [raw[pos + 4:pos + RECORD_SIZE] for pos in range(0, len(raw), RECORD_SIZE)]


def is_crown(source: bytes, position: tuple[int, int]) -> bool:
    row, col = position
    start = row * COLS + col
    return source[start:start + len(CROWN)] == CROWN


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    failures: list[dict[str, object]] = []
    hit_histogram: dict[int, int] = {}
    valid_is_last = 0
    records = sources(args.trace)
    for index, source in enumerate(records):
        hits = [pos for pos in ELIGIBLE if source[pos[0] * COLS + pos[1]] == 2]
        crowns = [pos for pos in hits if is_crown(source, pos)]
        hit_histogram[len(hits)] = hit_histogram.get(len(hits), 0) + 1
        if len(crowns) == 1 and hits and crowns[0] == hits[-1]:
            valid_is_last += 1
        else:
            failures.append({
                "record": index,
                "eligible_02": [list(pos) for pos in hits],
                "valid_crowns": [list(pos) for pos in crowns],
            })

    # A later eligible false $02 must overwrite the hot key, then fail the
    # cold five-byte sequence check. This proves the architecture fails closed
    # instead of trusting the corpus-only overwrite-last invariant blindly.
    control = bytearray(records[0])
    true = next(pos for pos in ELIGIBLE if is_crown(control, pos))
    later = next((pos for pos in ELIGIBLE if pos > true), None)
    if later is None:
        # Move the true crown to the first eligible position, preserving one
        # complete sequence, so a later false candidate always exists.
        start = true[0] * COLS + true[1]
        control[start:start + 5] = bytes((0x77,)) * 5
        true = ELIGIBLE[0]
        start = true[0] * COLS + true[1]
        control[start:start + 5] = CROWN
        later = ELIGIBLE[-1]
    false_start = later[0] * COLS + later[1]
    control[false_start] = 2
    control[false_start + 1:false_start + 5] = bytes((0x77,)) * 4
    control_hits = [pos for pos in ELIGIBLE if control[pos[0] * COLS + pos[1]] == 2]
    selected = control_hits[-1]
    negative_rejected = not is_crown(control, selected)

    passed = not failures and valid_is_last == len(records) and negative_rejected
    receipt = {
        "schema": "penta-ted-packed-crown-key-v1",
        "status": "pass" if passed else "fail",
        "records": len(records),
        "eligible_positions": [list(pos) for pos in ELIGIBLE],
        "eligible_02_histogram": {str(k): v for k, v in sorted(hit_histogram.items())},
        "valid_crown_is_last": valid_is_last,
        "failures": failures[:32],
        "negative_control": {
            "later_false_eligible_02_selected": list(selected),
            "cold_sequence_validator_rejected": negative_rejected,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
