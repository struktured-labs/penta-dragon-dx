"""Authoritative, translation-normalized contract for settled Ted poses.

The native classifier has 49 keys, but keys 13 and 14 identify incomplete
source-plane states rather than self-contained rendered poses. Production
intentionally holds the last complete pose through those states. This
contract therefore describes the 47 publishable poses, including connector
halves omitted by the historical 45-pose contract.
"""

from __future__ import annotations

import hashlib

from ted_native_sparse_pose_data import (
    POSE_CONNECTOR_DATA,
    POSE_COUNT,
    POSE_DATA,
    SOURCE_RECORDS,
    SOURCE_SHA256,
)


CONTRACT_VERSION = 2
TRANSIENT_POSE_INDICES = frozenset((13, 14))
# Measured consecutive publication records in the pinned 626-record stock
# corpus. "Non-publishable" does not mean a one-frame event: stock can retain
# key 14 for 34 copies while its two physical maps alternate complete and
# sparse-absent art. The GBC renderer deliberately stabilizes that interval.
NON_PUBLISHABLE_MAX_PUBLICATION_RUN = {13: 7, 14: 34}
SETTLED_POSE_INDICES = tuple(
    index for index in range(POSE_COUNT) if index not in TRANSIENT_POSE_INDICES
)
BODY_TILES = frozenset(range(0x02, 0x77)) | frozenset(range(0x7B, 0x87))
SPARSE_TILES = frozenset(range(0x7B, 0x87))
NUMBERED_ROW_SPANS = (
    (0, 5), (-2, 6), (-2, 6), (-2, 6), (-2, 6), (-2, 7),
    (-3, 7), (-4, 7), (-4, 7), (-4, 7), (-3, 7), (-2, 6),
    (0, 6), (1, 5),
)


def signed5(value: int) -> int:
    value &= 0x1F
    return value - 32 if value >= 16 else value


def _decode_records(data: bytes) -> list[tuple[tuple[int, int, int], ...]]:
    records = []
    cursor = 0
    for _ in range(POSE_COUNT):
        count = data[cursor]
        cursor += 1
        pose = []
        for _ in range(count):
            tile, row, column = data[cursor:cursor + 3]
            cursor += 3
            pose.append((tile, signed5(row), signed5(column)))
        records.append(tuple(pose))
    assert cursor == len(data)
    return records


def decode_complete_poses() -> tuple[tuple[tuple[int, int, int], ...], ...]:
    sparse = _decode_records(POSE_DATA)
    connectors = _decode_records(POSE_CONNECTOR_DATA)
    return tuple(
        tuple(sorted((*pose, *connector)))
        for pose, connector in zip(sparse, connectors, strict=True)
    )


NUMBERED_TILE_POSITION: dict[int, tuple[int, int]] = {}
_tile = 0x02
for _row, (_left, _right) in enumerate(NUMBERED_ROW_SPANS):
    for _column in range(_left, _right):
        NUMBERED_TILE_POSITION[_tile] = (_row, _column)
        _tile += 1
assert _tile == 0x77 and len(NUMBERED_TILE_POSITION) == 117


def pose_cells(pose: tuple[tuple[int, int, int], ...]) -> tuple[tuple[int, int, int], ...]:
    """Overlay one measured sparse pose on the canonical numbered body."""
    cells = {position: tile for tile, position in NUMBERED_TILE_POSITION.items()}
    for tile, row, column in pose:
        cells[(row, column)] = tile
    return tuple(sorted((row, column, tile) for (row, column), tile in cells.items()))


def cells_digest(cells: tuple[tuple[int, int, int], ...]) -> str:
    """Hash stable, translation-normalized ``(row, column, tile)`` triples."""
    packed = bytearray()
    for row, column, tile in sorted(cells):
        packed.extend(((row + 32) & 0xFF, (column + 32) & 0xFF, tile))
    return hashlib.sha256(packed).hexdigest()


COMPLETE_POSES = decode_complete_poses()
SETTLED_POSE_CELLS = tuple(pose_cells(COMPLETE_POSES[index]) for index in SETTLED_POSE_INDICES)
NATIVE_POSE_SHA256 = frozenset(cells_digest(cells) for cells in SETTLED_POSE_CELLS)
MIN_BODY_CELLS = min(map(len, SETTLED_POSE_CELLS))
MAX_BODY_CELLS = max(map(len, SETTLED_POSE_CELLS))
SPARSE_TILE_POSITIONS = {
    tile: frozenset(
        (row, column)
        for index in SETTLED_POSE_INDICES
        for sparse_tile, row, column in COMPLETE_POSES[index]
        if sparse_tile == tile
    )
    for tile in SPARSE_TILES
}

assert SOURCE_SHA256 == "1e61ad967b7b9714ae285f911bb483634dfdfde4bc65bcc44476840ab57df7cd"
assert SOURCE_RECORDS == 626
assert len(SETTLED_POSE_INDICES) == len(NATIVE_POSE_SHA256) == 47
assert (MIN_BODY_CELLS, MAX_BODY_CELLS) == (117, 147)
