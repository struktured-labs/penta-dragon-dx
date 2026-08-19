#!/usr/bin/env python3
"""Verify Ted's even-row block-major resident-mask architecture offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROWS = COLS = 24
RECORD_SIZE = 4 + ROWS * COLS
CROWN = bytes(range(2, 7))
SPANS = (
    (0, 5), (-2, 6), (-2, 6), (-2, 6), (-2, 6), (-2, 7),
    (-3, 7), (-4, 7), (-4, 7), (-4, 7), (-3, 7), (-2, 6),
    (0, 6), (1, 5),
)
DRAW_RUNS = bytes.fromhex("02 CD A2 FF A3 F4 94 E5 94 F5 94 21 A1 B7")
CLEAR_RUNS = bytes.fromhex("02 00 A2 00 A3 00 94 00 94 00 94 00 A1 00")
POINTER_BASE = 0xD600
RENDER_BASE = 0xD61A


def resident_address(record: int) -> int:
    pair_row, pair_col = divmod(record, 12)
    return POINTER_BASE + pair_row * 48 + 24 + pair_col * 2


def render_runs(memory: dict[int, int], token: int, table: bytes) -> int:
    if token == 0:
        return 0
    cursor = RENDER_BASE + token
    changed_bits = 0
    for offset in range(0, len(table), 2):
        header, edges = table[offset:offset + 2]
        cursor += (header >> 4) * 4
        middle = 0 if table == CLEAR_RUNS else 0x0F
        values = [edges >> 4] + [middle] * (header & 0x0F) + [edges & 0x0F]
        for desired in values:
            previous = memory.get(cursor, 0)
            changed_bits += (previous ^ desired).bit_count()
            memory[cursor] = desired
            cursor += 2
    return changed_bits


def read_sources(path: Path) -> list[bytes]:
    raw = path.read_bytes()
    if not raw or len(raw) % RECORD_SIZE:
        raise ValueError(f"{path}: invalid {len(raw)}-byte source trace")
    return [
        raw[offset + 4:offset + RECORD_SIZE]
        for offset in range(0, len(raw), RECORD_SIZE)
    ]


def crowns(source: bytes) -> list[int]:
    return [
        offset
        for offset in range(ROWS * COLS - 4)
        if offset // COLS == (offset + 4) // COLS
        and source[offset:offset + 5] == CROWN
    ]


def completed_crown_ends(source: bytes) -> list[int]:
    return [
        offset
        for offset, tile in enumerate(source)
        if tile == 6
        and not (offset // COLS & 1)
        and not (offset % COLS & 1)
    ]


def block_mask(anchor: int) -> list[int]:
    anchor_row, anchor_col = divmod(anchor, COLS)
    out: list[int] = []
    for row in range(0, ROWS, 2):
        for col in range(0, COLS, 2):
            nibble = 0
            for bit, (dr, dc) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
                relative_row = row + dr - anchor_row
                relative_col = col + dc - anchor_col
                inside = (
                    0 <= relative_row < len(SPANS)
                    and SPANS[relative_row][0]
                    <= relative_col < SPANS[relative_row][1]
                )
                nibble |= int(inside) << bit
            out.append(nibble)
    assert len(out) == 144
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    sources = read_sources(args.trace)
    old = [0] * 144
    membership_mismatches = 0
    changed_cells = 0
    mask_transitions = 0
    two_pass_repair_cells = 0
    two_pass_final_mismatches = 0
    exact_renderer_address_mismatches = 0
    resident_memory = {resident_address(index): 0 for index in range(144)}
    crown_end_failures: list[dict[str, object]] = []
    for index, source in enumerate(sources):
        found = crowns(source)
        ends = completed_crown_ends(source)
        exact_end = (
            len(found) == 1
            and len(ends) == 1
            and ends[0] - 4 == found[0]
        )
        if not exact_end:
            crown_end_failures.append({
                "record": index,
                "crowns": found,
                "even_even_tile_06": ends,
            })
            continue
        current = block_mask(found[0])
        for row in range(ROWS):
            for col in range(COLS):
                record = (row // 2) * 12 + col // 2
                bit = (row & 1) * 2 + (col & 1)
                actual = (current[record] >> bit) & 1
                relative_row = row - found[0] // COLS
                relative_col = col - found[0] % COLS
                expected = int(
                    0 <= relative_row < len(SPANS)
                    and SPANS[relative_row][0]
                    <= relative_col < SPANS[relative_row][1]
                )
                membership_mismatches += actual != expected
        delta = [left ^ right for left, right in zip(old, current)]
        changed = any(delta)
        mask_transitions += changed
        changed_cells += sum(value.bit_count() for value in delta)
        if changed:
            # The compact renderer clears every set bit in the old 34-nibble
            # run, then draws every set bit in the new run.  It may touch an
            # overlap twice, but must finish at the same resident mask.
            two_pass_repair_cells += sum(value.bit_count() for value in old)
            two_pass_repair_cells += sum(
                value.bit_count() for value in current
            )
            old_token = (crowns(sources[index - 1])[0] - 4) if index else 0
            new_token = found[0] - 4
            render_runs(resident_memory, old_token, CLEAR_RUNS)
            render_runs(resident_memory, new_token, DRAW_RUNS)
            rendered = [resident_memory[resident_address(record)] for record in range(144)]
            mismatch = sum(left != right for left, right in zip(rendered, current))
            two_pass_final_mismatches += mismatch
            exact_renderer_address_mismatches += mismatch
        old = current

    # A later aligned tile-$06 which is not preceded by $02-$05 must be
    # rejected by the cold five-byte sequence validator.
    extra = bytearray(sources[0])
    extra_offset = 20 * COLS + 4
    extra[extra_offset] = 6
    extra_ends = completed_crown_ends(extra)
    extra_last_rejected = not (
        extra[extra_ends[-1] - 4:extra_ends[-1] + 1] == CROWN
    )
    missing = bytearray(sources[0])
    missing[crowns(missing)[0] + 4] = 0x77
    missing_rejected = not completed_crown_ends(missing)
    correct_order = block_mask(crowns(sources[0])[0])
    bit_order_negative = [
        ((value & 0x3) << 2) | ((value >> 2) & 0x3)
        for value in correct_order
    ]
    bit_order_control_detected = bit_order_negative != correct_order

    passed = (
        not crown_end_failures
        and membership_mismatches == 0
        and mask_transitions == 17
        and changed_cells == 1803
        and two_pass_final_mismatches == 0
        and exact_renderer_address_mismatches == 0
        and extra_last_rejected
        and missing_rejected
        and bit_order_control_detected
    )
    receipt = {
        "schema": "penta-ted-block-major-mask-model-v1",
        "status": "pass" if passed else "fail",
        "records": len(sources),
        "block_records": 144,
        "membership_mismatches": membership_mismatches,
        "mask_transitions": mask_transitions,
        "changed_membership_cells": changed_cells,
        "two_pass_renderer": {
            "repair_cells": two_pass_repair_cells,
            "average_repair_cells_per_publication": (
                two_pass_repair_cells / len(sources)
            ),
            "final_mask_mismatches": two_pass_final_mismatches,
            "exact_run_address_mismatches": exact_renderer_address_mismatches,
        },
        "completed_crown_end_failures": crown_end_failures[:32],
        "negative_controls": {
            "later_false_tile_06_rejected": extra_last_rejected,
            "missing_tile_06_rejected": missing_rejected,
            "wrong_nibble_bit_order_detected": bit_order_control_detected,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
