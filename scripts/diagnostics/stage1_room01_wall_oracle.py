#!/usr/bin/env python3
"""Pure, reviewed Stage-1 room-01 wall-attribute oracle.

This module deliberately has no dependency on the palette YAML, the ROM
builder's tile lookup table, or bytes read from the candidate ROM.  Its only
expectations come from the separately reviewed fixture passed by the caller.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


VIEW_WIDTH = 21
VIEW_HEIGHT = 19
VIEW_CELLS = VIEW_WIDTH * VIEW_HEIGHT


def load_reviewed_wall_contract(path: Path) -> dict[str, object]:
    """Load the human-reviewed position fixture without consulting build data."""
    contract = json.loads(path.read_text())
    if contract.get("schema") != "penta-stage1-room01-wall-oracle-v1":
        raise ValueError(f"unsupported room-01 wall fixture schema: {path}")
    return contract


def _selector_matches(
    row: Mapping[str, object], selector: Mapping[str, object]
) -> bool:
    return all(int(row[name]) == int(value) for name, value in selector.items())


def _wall_cells(
    contract: Mapping[str, object],
) -> list[tuple[int, int, int, int]]:
    """Return reviewed cells as (view index, map offset, tile, attr)."""
    room01 = contract["room01_checkpoint"]
    assert isinstance(room01, Mapping)
    selector = room01["selector"]
    assert isinstance(selector, Mapping)
    scx = int(selector["scx"])
    scy = int(selector["scy"])
    expected_attr = int(room01["expected_attr"])
    rows = room01["wall_rows"]
    assert isinstance(rows, Sequence)
    cells: list[tuple[int, int, int, int]] = []
    seen: set[int] = set()
    for row_spec in rows:
        assert isinstance(row_spec, Mapping)
        y = int(row_spec["y"])
        row_cells = row_spec["cells"]
        assert isinstance(row_cells, Sequence)
        for cell in row_cells:
            assert isinstance(cell, Sequence) and len(cell) == 2
            x, tile = map(int, cell)
            if not (0 <= x < VIEW_WIDTH and 0 <= y < VIEW_HEIGHT):
                raise ValueError(f"reviewed wall cell is outside the viewport: {x},{y}")
            index = y * VIEW_WIDTH + x
            if index in seen:
                raise ValueError(f"duplicate reviewed wall view index: {index}")
            seen.add(index)
            map_y = ((scy + y * 8) >> 3) & 0x1F
            map_x = ((scx + x * 8) >> 3) & 0x1F
            cells.append((index, map_y * 32 + map_x, tile, expected_attr))
    return cells


def reviewed_room01_context_map(
    contract: Mapping[str, object],
) -> dict[tuple[int, int, int], int]:
    """Map reviewed (room, map offset, tile) cells to their exact attr byte."""
    room01 = contract["room01_checkpoint"]
    assert isinstance(room01, Mapping)
    selector = room01["selector"]
    assert isinstance(selector, Mapping)
    room = int(selector["room"])
    return {
        (room, map_offset, tile): expected_attr
        for _, map_offset, tile, expected_attr in _wall_cells(contract)
    }


def reviewed_room01_tile_attr_map(
    contract: Mapping[str, object],
) -> dict[tuple[int, int], int]:
    """Return the reviewed room-local wall tile class and exact attr byte.

    The runtime room-$01 fix updates four mutable C600 entries while leaving
    the immutable ROM LUT untouched.  The broad trajectory oracle therefore
    needs a room-local expectation for every occurrence of the reviewed wall
    tile class, not merely the 64 checkpoint coordinates.  This class is
    derived only from the reviewed fixture; it never consults the ROM LUT,
    palette YAML, or a candidate-produced table.
    """
    room01 = contract["room01_checkpoint"]
    assert isinstance(room01, Mapping)
    selector = room01["selector"]
    assert isinstance(selector, Mapping)
    room = int(selector["room"])
    result: dict[tuple[int, int], int] = {}
    for _, _, tile, expected_attr in _wall_cells(contract):
        key = (room, tile)
        previous = result.setdefault(key, expected_attr)
        if previous != expected_attr:
            raise ValueError(
                f"reviewed room-{room:02X} tile ${tile:02X} has "
                "conflicting attribute expectations"
            )
    return result


def reviewed_stage1_wall_oracle(
    records: Sequence[Mapping[str, object]],
    contract: Mapping[str, object],
) -> dict[str, object]:
    """Validate the reviewed room-01 walls and independent room-05 control.

    Selection is semantic: gameplay frame numbers are evidence only and are
    never used to locate either checkpoint.  Attribute bytes are compared in
    full, so values such as ``86`` do not pass merely because their palette
    number is six.
    """
    room01 = contract["room01_checkpoint"]
    room05 = contract["room05_patterned_floor_control"]
    assert isinstance(room01, Mapping) and isinstance(room05, Mapping)
    room01_selector = room01["selector"]
    room05_selector = room05["selector"]
    assert isinstance(room01_selector, Mapping)
    assert isinstance(room05_selector, Mapping)
    wall_cells = _wall_cells(contract)

    room01_records = [
        row for row in records if _selector_matches(row, room01_selector)
    ]
    room05_records = [
        row for row in records if _selector_matches(row, room05_selector)
    ]
    fingerprint = hashlib.sha256()
    room01_tile_mismatches = 0
    room01_attr_mismatches = 0
    first_room01_mismatch = None
    for record_index, row in enumerate(room01_records):
        tiles = bytes(row["tiles"])
        attrs = bytes(row["attrs"])
        if len(tiles) != VIEW_CELLS or len(attrs) != VIEW_CELLS:
            raise ValueError("trajectory tile/attribute view must contain 399 bytes")
        for view_index, map_offset, expected_tile, expected_attr in wall_cells:
            actual_tile = tiles[view_index]
            actual_attr = attrs[view_index]
            fingerprint.update(bytes((actual_tile, actual_attr)))
            tile_bad = actual_tile != expected_tile
            attr_bad = actual_attr != expected_attr
            room01_tile_mismatches += tile_bad
            room01_attr_mismatches += attr_bad
            if (tile_bad or attr_bad) and first_room01_mismatch is None:
                y, x = divmod(view_index, VIEW_WIDTH)
                first_room01_mismatch = {
                    "record_index": record_index,
                    "gameplay_frame": row.get("gameplay_frame"),
                    "view_index": view_index,
                    "x": x,
                    "y": y,
                    "map_offset": map_offset,
                    "actual_tile": actual_tile,
                    "expected_tile": expected_tile,
                    "actual_attr": actual_attr,
                    "expected_attr": expected_attr,
                }

    patterned_ids = {
        int(tile) for tile in room05["patterned_floor_tile_ids"]
    }
    expected_floor_attr = int(room05["expected_attr"])
    control_cells = room05["control_cells"]
    assert isinstance(control_cells, Sequence)
    room05_tile_mismatches = 0
    room05_attr_mismatches = 0
    patterned_attr_mismatches = 0
    observed_patterned_cells = 0
    observed_patterned_ids: set[int] = set()
    first_room05_mismatch = None
    visible_rows = int(room05["visible_rows"])
    visible_columns = int(room05["visible_columns"])
    for record_index, row in enumerate(room05_records):
        tiles = bytes(row["tiles"])
        attrs = bytes(row["attrs"])
        if len(tiles) != VIEW_CELLS or len(attrs) != VIEW_CELLS:
            raise ValueError("trajectory tile/attribute view must contain 399 bytes")
        for cell in control_cells:
            assert isinstance(cell, Mapping)
            view_index = int(cell["view_index"])
            expected_tile = int(cell["tile"])
            actual_tile = tiles[view_index]
            actual_attr = attrs[view_index]
            fingerprint.update(bytes((actual_tile, actual_attr)))
            tile_bad = actual_tile != expected_tile
            attr_bad = actual_attr != expected_floor_attr
            room05_tile_mismatches += tile_bad
            room05_attr_mismatches += attr_bad
            if (tile_bad or attr_bad) and first_room05_mismatch is None:
                y, x = divmod(view_index, VIEW_WIDTH)
                first_room05_mismatch = {
                    "record_index": record_index,
                    "gameplay_frame": row.get("gameplay_frame"),
                    "view_index": view_index,
                    "x": x,
                    "y": y,
                    "actual_tile": actual_tile,
                    "expected_tile": expected_tile,
                    "actual_attr": actual_attr,
                    "expected_attr": expected_floor_attr,
                }
        for y in range(visible_rows):
            for x in range(visible_columns):
                view_index = y * VIEW_WIDTH + x
                tile = tiles[view_index]
                if tile not in patterned_ids:
                    continue
                actual_attr = attrs[view_index]
                observed_patterned_cells += 1
                observed_patterned_ids.add(tile)
                fingerprint.update(bytes((view_index & 0xFF, tile, actual_attr)))
                if actual_attr == expected_floor_attr:
                    continue
                patterned_attr_mismatches += 1
                if first_room05_mismatch is None:
                    first_room05_mismatch = {
                        "record_index": record_index,
                        "gameplay_frame": row.get("gameplay_frame"),
                        "view_index": view_index,
                        "x": x,
                        "y": y,
                        "actual_tile": tile,
                        "expected_tile": tile,
                        "actual_attr": actual_attr,
                        "expected_attr": expected_floor_attr,
                    }

    room01_minimum = int(room01["minimum_records"])
    room05_minimum = int(room05["minimum_records"])
    room01_exact = (
        len(room01_records) >= room01_minimum
        and room01_tile_mismatches == 0
        and room01_attr_mismatches == 0
    )
    room05_exact = (
        len(room05_records) >= room05_minimum
        and room05_tile_mismatches == 0
        and room05_attr_mismatches == 0
        and patterned_attr_mismatches == 0
        and observed_patterned_cells > 0
    )
    return {
        "schema": contract["schema"],
        "room01": {
            "selector": dict(room01_selector),
            "minimum_records": room01_minimum,
            "records": len(room01_records),
            "gameplay_frames": [row.get("gameplay_frame") for row in room01_records],
            "reviewed_cells_per_record": len(wall_cells),
            "checked_cell_instances": len(room01_records) * len(wall_cells),
            "expected_attr": int(room01["expected_attr"]),
            "tile_mismatches": room01_tile_mismatches,
            "attr_mismatches": room01_attr_mismatches,
            "first_mismatch": first_room01_mismatch,
            "exact": room01_exact,
        },
        "room05_patterned_floor_control": {
            "selector": dict(room05_selector),
            "minimum_records": room05_minimum,
            "records": len(room05_records),
            "gameplay_frames": [row.get("gameplay_frame") for row in room05_records],
            "patterned_floor_tile_ids": sorted(patterned_ids),
            "observed_patterned_tile_ids": sorted(observed_patterned_ids),
            "observed_patterned_cells": observed_patterned_cells,
            "expected_attr": expected_floor_attr,
            "tile_mismatches": room05_tile_mismatches,
            "control_attr_mismatches": room05_attr_mismatches,
            "patterned_attr_mismatches": patterned_attr_mismatches,
            "first_mismatch": first_room05_mismatch,
            "exact": room05_exact,
        },
        "fingerprint_sha256": fingerprint.hexdigest(),
        "exact": room01_exact and room05_exact,
    }
