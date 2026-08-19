#!/usr/bin/env python3
"""Offline exact-oracle controls for the incremental Ted sanitizer design."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROWS, COLS = 24, 32
SPANS = (
    (0, 5), (-2, 6), (-2, 6), (-2, 6), (-2, 6), (-2, 7),
    (-3, 7), (-4, 7), (-4, 7), (-4, 7), (-3, 7), (-2, 6),
    (0, 6), (1, 5),
)
SPARSE = frozenset((0x7B, 0x7D, 0x80, 0x82, 0x83, 0x84, 0x85, 0x86))


class Model:
    def __init__(self, *, repair: bool = True, allow_high: bool = False,
                 widen_left: bool = False, byte_mask: bool = False) -> None:
        self.raw = [0] * (ROWS * COLS)
        self.tiles = [0] * (ROWS * COLS)
        self.attrs = [0] * (ROWS * COLS)
        self.mask = bytearray(72)
        self.lut = [(tile % 7) + 1 for tile in range(256)]
        self.current: tuple[int, int] | None = None
        self.candidate_count = 0
        self.candidate_offset = 0
        self.old = (0, 0)
        self.repair_enabled = repair
        self.allow_high = allow_high
        self.widen_left = widen_left
        self.byte_mask = byte_mask

    def inside_exact(self, offset: int) -> bool:
        if self.current is None:
            return False
        row, col = divmod(offset, COLS)
        rel_row = (row - self.current[0]) & 31
        rel_col = (col - self.current[1]) & 31
        if rel_col >= 16:
            rel_col -= 32
        if rel_row >= len(SPANS):
            return False
        left, right = SPANS[rel_row]
        return left <= rel_col < right

    def inside(self, offset: int) -> bool:
        if self.current is None:
            return False
        row, col = divmod(offset, COLS)
        rel_row = (row - self.current[0]) & 31
        rel_col = (col - self.current[1]) & 31
        if rel_col >= 16:
            rel_col -= 32
        if rel_row >= len(SPANS):
            return False
        left, right = SPANS[rel_row]
        if self.widen_left:
            left -= 1
        return left <= rel_col < right

    def classify(self, offset: int) -> None:
        tile = self.raw[offset]
        keep = tile < 2 or tile in SPARSE
        colored = tile in SPARSE
        row, col = divmod(offset, COLS)
        packed = row * 24 + col
        masked = (
            row < 24 and col < 24
            and bool(self.mask[packed >> 3] & (1 << (packed & 7)))
        )
        if 2 <= tile < 0x77 and masked:
            keep = colored = True
        if self.allow_high and tile >= 0x87:
            keep = colored = True
        self.tiles[offset] = tile if keep else 0
        self.attrs[offset] = self.lut[tile] if colored else 0

    def write(self, offset: int, tile: int) -> None:
        self.raw[offset] = tile
        if tile == 2:
            self.candidate_count += 1
            self.candidate_offset = offset
        self.classify(offset)

    def valid_crown(self, anchor: tuple[int, int] | None) -> bool:
        if anchor is None:
            return False
        row, col = anchor
        start = row * COLS + col
        return col <= 27 and self.raw[start:start + 5] == list(range(2, 7))

    def rebuild_mask(self) -> None:
        self.mask[:] = bytes(len(self.mask))
        if self.current is None:
            return
        for row in range(24):
            for col in range(24):
                offset = row * COLS + col
                if not self.inside(offset):
                    continue
                packed = row * 24 + col
                if self.byte_mask:
                    self.mask[packed >> 3] = 0xFF
                else:
                    self.mask[packed >> 3] |= 1 << (packed & 7)

    def publication(self) -> None:
        candidate = (
            divmod(self.candidate_offset, COLS)
            if self.candidate_count == 1
            and self.valid_crown(divmod(self.candidate_offset, COLS))
            else None
        )
        self.candidate_count = 0
        if candidate is not None and candidate == self.current:
            return
        old = self.current
        self.old = old if old is not None else (0, 0)
        # No crown or multiple crowns fail closed: clear the body mask and
        # neutralize the last valid envelope rather than choosing debris.
        self.current = candidate
        old_mask = bytes(self.mask)
        self.rebuild_mask()
        if self.repair_enabled:
            # The full native writer already classified content changes with
            # the resident mask. Repair exactly the cells whose membership
            # bit changed, which is equivalent to old/new envelope repair.
            for packed in range(ROWS * 24):
                bit = 1 << (packed & 7)
                if (old_mask[packed >> 3] ^ self.mask[packed >> 3]) & bit:
                    row, col = divmod(packed, 24)
                    self.classify(row * COLS + col)
    def mismatches(self) -> int:
        expected_tiles, expected_attrs = [], []
        for offset, tile in enumerate(self.raw):
            keep = tile < 2 or tile in SPARSE
            colored = tile in SPARSE
            if 2 <= tile < 0x77 and self.inside_exact(offset):
                keep = colored = True
            expected_tiles.append(tile if keep else 0)
            expected_attrs.append(self.lut[tile] if colored else 0)
        return sum(a != b for a, b in zip(self.tiles, expected_tiles)) + sum(
            a != b for a, b in zip(self.attrs, expected_attrs)
        )


def stamp(model: Model, anchor: tuple[int, int]) -> None:
    source = [
        0x77 + 2 * (row & 1) + (col & 1)
        for row in range(ROWS)
        for col in range(COLS)
    ]
    source[23 * COLS + 31] = 0x90
    tile = 2
    for rel_row, (left, right) in enumerate(SPANS):
        for rel_col in range(left, right):
            source[(anchor[0] + rel_row) * COLS + anchor[1] + rel_col] = tile
            tile += 1
    assert tile == 0x77
    source[(anchor[0] + 2) * COLS + anchor[1] + 8] = 0x82
    source[(anchor[0] + 4) * COLS + anchor[1] - 4] = 0x86
    for offset, value in enumerate(source):
        model.write(offset, value)


def exercise(model: Model) -> list[int]:
    # Explicit rejected controls stay raw but must never publish color/art.
    model.write(23 * COLS + 31, 0x90)
    mismatches = []
    for anchor in ((4, 12), (4, 12), (4, 8), (4, 8),
                   (4, 12), (4, 12), (8, 12), (8, 12)):
        stamp(model, anchor)
        scratch_col = anchor[1] - 1
        model.write(anchor[0] * COLS + scratch_col, 0x40)
        model.publication()
        mismatches.append(model.mismatches())
    return mismatches


def build_receipt() -> dict[str, object]:
    """Exercise the exact candidate and all required negative controls."""
    candidate = Model()
    candidate_result = exercise(candidate)
    no_repair = exercise(Model(repair=False))
    high_leak = exercise(Model(allow_high=True))
    wide_geometry = exercise(Model(widen_left=True))
    byte_mask = exercise(Model(byte_mask=True))

    no_crown = Model()
    stamp(no_crown, (4, 12))
    no_crown.publication()
    for offset in range(ROWS * COLS):
        no_crown.write(offset, 0x77 + 2 * ((offset // COLS) & 1) + (offset & 1))
    no_crown.publication()
    no_crown_safe = (
        no_crown.current is None
        and not any(no_crown.mask)
        and no_crown.mismatches() == 0
    )

    ambiguous = Model()
    stamp(ambiguous, (4, 12))
    ambiguous.publication()
    ambiguous_source = list(ambiguous.raw)
    for step in range(5):
        ambiguous_source[18 * COLS + 2 + step] = 2 + step
    for offset, value in enumerate(ambiguous_source):
        ambiguous.write(offset, value)
    ambiguous.publication()
    ambiguous_safe = (
        ambiguous.current is None
        and not any(ambiguous.mask)
        and ambiguous.mismatches() == 0
    )

    # Palette-edit control: the next source write must consume the new LUT.
    offset = (candidate.current[0] + 3) * COLS + candidate.current[1]
    tile = candidate.raw[offset]
    before = candidate.attrs[offset]
    candidate.lut[tile] = (before + 3) & 7
    candidate.write(offset, tile)
    palette_roundtrip = candidate.attrs[offset] == candidate.lut[tile]

    receipt: dict[str, object] = {
        "schema": "penta-ted-incremental-mask-model-v2",
        "publications": 8,
        "candidate_mismatches": candidate_result,
        "candidate_total": sum(candidate_result),
        "negative_no_repair_total": sum(no_repair),
        "negative_high_leak_total": sum(high_leak),
        "negative_wide_geometry_total": sum(wide_geometry),
        "negative_byte_mask_total": sum(byte_mask),
        "body_mask_bytes": 72,
        "no_crown_fail_closed": no_crown_safe,
        "ambiguous_crown_fail_closed": ambiguous_safe,
        "palette_roundtrip": palette_roundtrip,
    }
    passed = (
        receipt["candidate_total"] == 0
        and receipt["negative_no_repair_total"] > 0
        and receipt["negative_high_leak_total"] > 0
        and receipt["negative_wide_geometry_total"] > 0
        and receipt["negative_byte_mask_total"] > 0
        and no_crown_safe
        and ambiguous_safe
        and palette_roundtrip
    )
    receipt["status"] = "pass" if passed else "fail"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    receipt = build_receipt()
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
    print(payload, end="")
    return 0 if receipt["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
