#!/usr/bin/env python3
"""Pinned, offline tile-layout oracle for the Scene-$0B Stage-1 hazards.

The oracle deliberately does not learn from the ROM or tile map under test.
Its four legal phases per native 4x12 component family and its immutable
24x24 Scene-$0B source are checked against a hash-qualified fixture before any
observation is evaluated.  Each of the four components independently matches
one *whole* phase, so the legal state space is the 4^4 Cartesian product.  A
union of legal tile IDs is never used as an acceptance rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


PACKED_WIDTH = 24
PACKED_HEIGHT = 24
PACKED_CELLS = PACKED_WIDTH * PACKED_HEIGHT
PHYSICAL_WIDTH = 32
PHYSICAL_CELLS = PHYSICAL_WIDTH * PHYSICAL_WIDTH

SCHEMA = "penta-stage1-scene0b-hazard-tile-oracle-v1"
RESULT_SCHEMA = "penta-stage1-scene0b-hazard-tile-evaluation-v1"
FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures/stage1_scene0b_hazard_tile_oracle.json"
)
PINNED_FIXTURE_SHA256 = (
    "bb393a39141453ee754c0f8ee949fcfd5bb17d1c4534f278eb4ec14db3da0d7e"
)
PINNED_SOURCE_SHA256 = (
    "071a7e6fc168809e476a8996113956779d5d06bde774183bc4032b772359d42a"
)
PINNED_NATIVE_ROM_SHA256 = (
    "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"
)
PINNED_NATIVE_WINDOW_OFFSET = 0x1A200
PINNED_NATIVE_WINDOW_SIZE = 0x100
PINNED_NATIVE_WINDOW_SHA256 = (
    "34b53317e64934fbbbf4c2541fdf5805b6c4ab27c1046740b838cb9460dbab8e"
)
PINNED_OPERATOR_STATE_SHA256 = (
    "1ea1b02625268a64982bcf272177ce89527a5a99c0baa49e6a1e247a9d2c8b67"
)
PINNED_OPERATOR_SAVEDATA_SHA256 = (
    "569db09d694464705b123ae3ff2f566fbdf3f8d99d8c5e525e095a41c9498a2b"
)
PINNED_STAGE1_TABLES_SHA256 = (
    "3cc4b1116116537e5c12d9dc9feb02281c053a94fc59ad129f83745723a4f80a"
)
PINNED_TILE_TABLE_SHA256 = (
    "c277296aff34e23eb86fa820adb1ee3afab20254c0e6dce192c7c980d0c6c855"
)
PINNED_WORLD_WINDOW_SHA256 = (
    "93ef30180c9c0deb363e69ed805bab40f7f3f436f9185d7896b2f1a172ee4dfd"
)

_PINNED_OBJECTS = (
    (
        "north_standard", "standard_cylinder", 0, 0,
        ("99", "9A", "9B"), "P3",
    ),
    (
        "connector_thrust", "connector_thrust", 4, 0,
        ("8C", "8D", "8E"), "P2",
    ),
    (
        "upper_cylinder", "upper_cylinder", 8, 0,
        ("81", "82", "83"), "P2",
    ),
    (
        "south_standard", "standard_cylinder", 12, 0,
        ("89", "8A", "8B"), "P2",
    ),
)
_PINNED_FAMILIES = {
    "standard_cylinder": {
        "width": 12,
        "height": 4,
        "phases": (
            (
                "P0",
                "35722560336cdbe67126f0c6e0f80e1feb04153b590ed9ab7f24fdee8cc16ecb",
                (0x1A224, 0x1A228, 0x1A22C),
                ("5A5C0B0B", "5A5C0B0B", "65020C02"),
            ),
            (
                "P1",
                "b2da61097a99e4b24e90a4340b2182fc9e1769253f150c5d3b5f6878f5796eff",
                (0x1A264, 0x1A268, 0x1A26C),
                ("5B5D0B0B", "5B5D0B0B", "64020C02"),
            ),
            (
                "P2",
                "d8e87d19b921dd28fd070df1af7eb83cf35e08499d51369332cc4bb958e2e6c8",
                (0x1A2A4, 0x1A2A8, 0x1A2AC),
                ("5C5A0B0B", "5C5A0B0B", "63020C02"),
            ),
            (
                "P3",
                "003e0a6b8056b9a794b8493d77a35f4569a311e6fd0c96e9c5cc7daa14c93288",
                (0x1A2E4, 0x1A2E8, 0x1A2EC),
                ("5D5B0B0B", "5D5B0B0B", "62020C02"),
            ),
        ),
    },
    "connector_thrust": {
        "width": 12,
        "height": 4,
        "phases": (
            (
                "P0",
                "e3fa6a2b4d4fe4e2d007441a56e7643848d11fe388294abc78c66625e3515290",
                (0x1A230, 0x1A234, 0x1A238),
                ("01410161", "45435553", "45475557"),
            ),
            (
                "P1",
                "25ebd54ba92765d490bdcedbbb561f7f1b72f6a3bd0cea6c218f9d3724862a50",
                (0x1A210, 0x1A214, 0x1A218),
                ("0140015E", "44425452", "44465456"),
            ),
            (
                "P2",
                "2f0760749e34387cea577776901d80968b98c5b789a41f2c2871961e1908922d",
                (0x1A270, 0x1A274, 0x1A278),
                ("013F015F", "43455355", "43495359"),
            ),
            (
                "P3",
                "d933a18b4212b015ac170a2b1286058d9bce13a239d50d8fdf68e1bd901e4679",
                (0x1A250, 0x1A254, 0x1A258),
                ("013E0160", "42445254", "42485258"),
            ),
        ),
    },
    "upper_cylinder": {
        "width": 12,
        "height": 4,
        "phases": (
            (
                "P0",
                "2fa5c6f2dcfbb15f84f7e80e331faea27ee7e37aa50a647a87d4f11be132d05c",
                (0x1A204, 0x1A208, 0x1A20C),
                ("010A4A4C", "0B0B4A4C", "0B024F02"),
            ),
            (
                "P1",
                "e79a0334d1438b12ec3bd36653fa66481152494a1d8b12ddaa5d646719c2c475",
                (0x1A244, 0x1A248, 0x1A24C),
                ("010A4B4D", "0B0B4B4D", "0B025002"),
            ),
            (
                "P2",
                "b9934317759eb17c4299d0dff893e5b3794be154c4e307e68c7db240892f77a6",
                (0x1A284, 0x1A288, 0x1A28C),
                ("010A4C4A", "0B0B4C4A", "0B025102"),
            ),
            (
                "P3",
                "2bdb758a442349914a540d3b0616f3fdae5e16a7ff466a24d38e77fd44999fa6",
                (0x1A2C4, 0x1A2C8, 0x1A2CC),
                ("010A4D4B", "0B0B4D4B", "0B024E02"),
            ),
        ),
    },
}
_PINNED_COVERAGE = {
    "legacy_hazard_positions": 45,
    "legacy_broad_envelope_cells": 156,
    "exact_object_cells": 192,
    "exact_object_cells_outside_legacy_envelope": 48,
    "immutable_guard_cells": 12,
    "audited_union_cells": 204,
}
_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_UPPER_HEX = re.compile(r"[0-9A-F]*\Z")


class HazardTileContractError(ValueError):
    """The pinned oracle fixture or its caller-supplied source is invalid."""


class HazardTileAssertionError(AssertionError):
    """An observed Scene-$0B hazard map does not match a legal phase set."""

    def __init__(self, evaluation: "HazardTileEvaluation") -> None:
        self.evaluation = evaluation
        super().__init__(
            json.dumps(evaluation.to_receipt(max_mismatches=8), sort_keys=True)
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HazardTileContractError(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _sequence(value: Any, label: str) -> Sequence[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return value


def _exact_keys(
    value: Mapping[str, Any], expected: Iterable[str], label: str
) -> None:
    expected_set = set(expected)
    _require(
        set(value) == expected_set,
        f"{label} fields changed: expected {sorted(expected_set)}, "
        f"got {sorted(value)}",
    )


def _integer(value: Any, label: str) -> int:
    _require(type(value) is int, f"{label} must be an integer")
    return value


def _string(value: Any, label: str) -> str:
    _require(isinstance(value, str), f"{label} must be a string")
    return value


def _decode_rows(
    value: Any, width: int, height: int, label: str
) -> bytes:
    rows = _sequence(value, f"{label}.rows")
    _require(len(rows) == height, f"{label} must have {height} rows")
    decoded = bytearray()
    for index, raw_row in enumerate(rows):
        row = _string(raw_row, f"{label}.rows[{index}]")
        _require(
            len(row) == width * 2 and _UPPER_HEX.fullmatch(row) is not None,
            f"{label}.rows[{index}] is not canonical {width}-byte hex",
        )
        decoded.extend(bytes.fromhex(row))
    return bytes(decoded)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HazardTileContractError(
                f"oracle fixture repeats JSON key {key!r}"
            )
        result[key] = value
    return result


@dataclass(frozen=True)
class HazardPhase:
    id: str
    sha256: str
    width: int
    height: int
    tiles: bytes
    definition_offsets: tuple[int, int, int]
    metatile_definitions: tuple[bytes, bytes, bytes]

    def tile(self, row: int, column: int) -> int:
        if not (0 <= row < self.height and 0 <= column < self.width):
            raise IndexError((row, column))
        return self.tiles[row * self.width + column]


@dataclass(frozen=True)
class HazardFamily:
    name: str
    width: int
    height: int
    phases: tuple[HazardPhase, ...]

    def phase(self, phase_id: str) -> HazardPhase:
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise HazardTileContractError(
            f"unknown phase {phase_id!r} for family {self.name!r}"
        )


@dataclass(frozen=True)
class HazardObject:
    name: str
    family: str
    row: int
    column: int
    captured_world_ids: tuple[str, str, str]
    captured_phase: str


@dataclass(frozen=True)
class HazardCoverage:
    legacy_hazard_positions: tuple[int, ...]
    legacy_broad_envelope: tuple[int, ...]
    exact_object_cells: tuple[int, ...]
    exact_object_cells_outside_legacy_envelope: tuple[int, ...]
    immutable_guard_cells: tuple[int, ...]
    audited_union_cells: tuple[int, ...]

    def counts(self) -> dict[str, int]:
        return {
            "legacy_hazard_positions": len(self.legacy_hazard_positions),
            "legacy_broad_envelope_cells": len(
                self.legacy_broad_envelope
            ),
            "exact_object_cells": len(self.exact_object_cells),
            "exact_object_cells_outside_legacy_envelope": len(
                self.exact_object_cells_outside_legacy_envelope
            ),
            "immutable_guard_cells": len(self.immutable_guard_cells),
            "audited_union_cells": len(self.audited_union_cells),
        }


@dataclass(frozen=True)
class HazardTileContract:
    fixture_path: Path
    fixture_sha256: str
    immutable_source: bytes
    immutable_source_sha256: str
    objects: tuple[HazardObject, ...]
    families: tuple[HazardFamily, ...]
    coverage: HazardCoverage
    provenance: tuple[tuple[str, str, str], ...]

    def family(self, name: str) -> HazardFamily:
        for family in self.families:
            if family.name == name:
                return family
        raise HazardTileContractError(f"unknown hazard family {name!r}")

    def object(self, name: str) -> HazardObject:
        for hazard_object in self.objects:
            if hazard_object.name == name:
                return hazard_object
        raise HazardTileContractError(f"unknown hazard object {name!r}")


@dataclass(frozen=True)
class TileMismatch:
    kind: str
    row: int
    column: int
    expected: int
    actual: int
    object_name: str | None = None
    phase: str | None = None

    @property
    def packed_offset(self) -> int:
        return self.row * PACKED_WIDTH + self.column

    def to_receipt(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "row": self.row,
            "column": self.column,
            "packed_offset": self.packed_offset,
            "expected": self.expected,
            "actual": self.actual,
        }
        if self.object_name is not None:
            result["object"] = self.object_name
        if self.phase is not None:
            result["phase"] = self.phase
        return result


@dataclass(frozen=True)
class HazardObjectEvaluation:
    name: str
    family: str
    matched_phase: str | None
    best_phase: str
    phase_mismatch_counts: tuple[tuple[str, int], ...]
    mismatches: tuple[TileMismatch, ...]

    @property
    def exact(self) -> bool:
        return self.matched_phase is not None

    @property
    def mismatch_count(self) -> int:
        return len(self.mismatches)

    def to_receipt(self, max_mismatches: int) -> dict[str, Any]:
        return {
            "name": self.name,
            "family": self.family,
            "exact": self.exact,
            "matched_phase": self.matched_phase,
            "best_phase": self.best_phase,
            "phase_mismatch_counts": dict(self.phase_mismatch_counts),
            "mismatch_count": self.mismatch_count,
            "first_mismatches": [
                mismatch.to_receipt()
                for mismatch in self.mismatches[:max_mismatches]
            ],
        }


@dataclass(frozen=True)
class HazardTileEvaluation:
    fixture_sha256: str
    immutable_source_sha256: str
    objects: tuple[HazardObjectEvaluation, ...]
    immutable_guard_mismatches: tuple[TileMismatch, ...]
    unexpected_hazard_tiles: tuple[TileMismatch, ...]
    coverage: HazardCoverage

    @property
    def legal(self) -> bool:
        return (
            all(result.exact for result in self.objects)
            and not self.immutable_guard_mismatches
            and not self.unexpected_hazard_tiles
        )

    @property
    def matched_phases(self) -> dict[str, str | None]:
        return {
            result.name: result.matched_phase for result in self.objects
        }

    @property
    def mismatch_count(self) -> int:
        return (
            sum(result.mismatch_count for result in self.objects)
            + len(self.immutable_guard_mismatches)
            + len(self.unexpected_hazard_tiles)
        )

    def to_receipt(self, max_mismatches: int = 16) -> dict[str, Any]:
        _require(
            type(max_mismatches) is int and max_mismatches >= 0,
            "max_mismatches must be a non-negative integer",
        )
        return {
            "schema": RESULT_SCHEMA,
            "legal": self.legal,
            "fixture_sha256": self.fixture_sha256,
            "immutable_source_sha256": self.immutable_source_sha256,
            "matched_phases": self.matched_phases,
            "mismatch_count": self.mismatch_count,
            "objects": [
                result.to_receipt(max_mismatches) for result in self.objects
            ],
            "immutable_guard_cells": len(
                self.coverage.immutable_guard_cells
            ),
            "immutable_guard_mismatch_count": len(
                self.immutable_guard_mismatches
            ),
            "first_immutable_guard_mismatches": [
                mismatch.to_receipt()
                for mismatch in self.immutable_guard_mismatches[
                    :max_mismatches
                ]
            ],
            "owned_cells_scanned_for_unexpected_hazard_tiles": PACKED_CELLS,
            "unexpected_hazard_tile_count": len(
                self.unexpected_hazard_tiles
            ),
            "first_unexpected_hazard_tiles": [
                mismatch.to_receipt()
                for mismatch in self.unexpected_hazard_tiles[
                    :max_mismatches
                ]
            ],
            "coverage": self.coverage.counts(),
        }


def _stage1_tooth(tile: int) -> bool:
    return 0x64 <= (tile & 0xEF) < 0x6A


def _stage1_hazard_positions(tiles: bytes) -> set[int]:
    """Reproduce the pre-oracle geometry scanner for coverage accounting."""
    _require(
        len(tiles) == PHYSICAL_CELLS,
        "physical BG tile map has wrong size",
    )
    positions: set[int] = set()
    for row in range(PHYSICAL_WIDTH):
        start = row * PHYSICAL_WIDTH
        values = tiles[start:start + PHYSICAL_WIDTH]
        columns: Iterable[int] = ()
        if _stage1_tooth(values[0]) or _stage1_tooth(values[1]):
            width = 11 if _stage1_tooth(values[10]) else (
                10 if _stage1_tooth(values[9]) else 9
            )
            columns = range(width)
        elif values[4] == 0x6A:
            columns = range(5, 15)
        elif _stage1_tooth(values[4]) or _stage1_tooth(values[5]):
            columns = range(4, 13)
        elif _stage1_tooth(values[6]):
            columns = tuple(
                column for column in range(4, 14)
                if _stage1_tooth(values[column])
            )
        positions.update(start + column for column in columns)
    return positions


def _physical_from_packed(packed: bytes) -> bytes:
    _require(len(packed) == PACKED_CELLS, "packed tile map has wrong size")
    physical = bytearray(PHYSICAL_CELLS)
    for row in range(PACKED_HEIGHT):
        physical[row * PHYSICAL_WIDTH:row * PHYSICAL_WIDTH + PACKED_WIDTH] = (
            packed[row * PACKED_WIDTH:(row + 1) * PACKED_WIDTH]
        )
    return bytes(physical)


def _packed_from_observed(observed: bytes | bytearray | memoryview) -> bytes:
    payload = bytes(observed)
    if len(payload) == PACKED_CELLS:
        return payload
    if len(payload) == PHYSICAL_CELLS:
        packed = bytearray()
        for row in range(PACKED_HEIGHT):
            packed.extend(
                payload[
                    row * PHYSICAL_WIDTH:
                    row * PHYSICAL_WIDTH + PACKED_WIDTH
                ]
            )
        return bytes(packed)
    raise HazardTileContractError(
        "observed tile map must be packed 24x24 (576 bytes) or physical "
        "32x32 (1024 bytes)"
    )


def _visible_object_cells(
    hazard_object: HazardObject, family: HazardFamily
) -> tuple[tuple[int, int, int, int, int], ...]:
    """Return (local row/column, world row/column, packed offset)."""
    cells = []
    for local_row in range(family.height):
        row = hazard_object.row + local_row
        for local_column in range(family.width):
            column = hazard_object.column + local_column
            if 0 <= row < PACKED_HEIGHT and 0 <= column < PACKED_WIDTH:
                cells.append(
                    (
                        local_row,
                        local_column,
                        row,
                        column,
                        row * PACKED_WIDTH + column,
                    )
                )
    return tuple(cells)


def _is_hazard_family_tile(tile: int) -> bool:
    # All native cylinder shells, teeth, shafts, and tips are in this band.
    # Fixed wall-tail cells can also use this band.  Those cells remain exact
    # to the immutable source; only the four component rectangles may vary.
    return 0x60 <= tile <= 0x7F


@lru_cache(maxsize=4)
def load_contract(path: Path = FIXTURE_PATH) -> HazardTileContract:
    """Load and fully authenticate the exact hazard-layout fixture."""
    path = Path(path).resolve()
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise HazardTileContractError(
            f"hazard oracle fixture is unreadable: {error}"
        ) from error
    digest = _sha256(raw)
    _require(
        digest == PINNED_FIXTURE_SHA256,
        "hazard oracle fixture identity changed: "
        f"expected {PINNED_FIXTURE_SHA256}, got {digest}",
    )
    try:
        document = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_json_without_duplicate_keys
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise HazardTileContractError(
            f"hazard oracle fixture is malformed JSON: {error}"
        ) from error
    root = _mapping(document, "oracle fixture")
    _exact_keys(
        root,
        (
            "schema",
            "purpose",
            "derivation",
            "immutable_source",
            "coverage",
            "objects",
            "families",
            "provenance",
        ),
        "oracle fixture",
    )
    _require(root["schema"] == SCHEMA, "hazard oracle schema changed")
    _string(root["purpose"], "oracle fixture purpose")

    derivation = _mapping(root["derivation"], "derivation")
    _exact_keys(
        derivation,
        (
            "native_animation_definitions",
            "native_stage1_tables",
            "captured_world_window",
        ),
        "derivation",
    )
    native_rom = _mapping(
        derivation["native_animation_definitions"],
        "derivation.native_animation_definitions",
    )
    _exact_keys(
        native_rom,
        (
            "path",
            "file_sha256",
            "window_offset",
            "window_size",
            "window_sha256",
        ),
        "derivation.native_animation_definitions",
    )
    _require(
        native_rom["path"] == "rom/Penta Dragon (J).gb"
        and native_rom["file_sha256"] == PINNED_NATIVE_ROM_SHA256
        and _integer(
            native_rom["window_offset"],
            "native_animation_definitions.window_offset",
        )
        == PINNED_NATIVE_WINDOW_OFFSET
        and _integer(
            native_rom["window_size"],
            "native_animation_definitions.window_size",
        )
        == PINNED_NATIVE_WINDOW_SIZE
        and native_rom["window_sha256"] == PINNED_NATIVE_WINDOW_SHA256,
        "native animation definition authority changed",
    )
    native_tables = _mapping(
        derivation["native_stage1_tables"],
        "derivation.native_stage1_tables",
    )
    _exact_keys(
        native_tables,
        (
            "path",
            "state_sha256",
            "savedata_sha256",
            "stage1_tables_size",
            "stage1_tables_sha256",
            "tile_table_size",
            "tile_table_sha256",
        ),
        "derivation.native_stage1_tables",
    )
    _require(
        native_tables["path"]
        == "save_states_for_claude/rc11_low-health-degradation.ss0"
        and native_tables["state_sha256"] == PINNED_OPERATOR_STATE_SHA256
        and native_tables["savedata_sha256"]
        == PINNED_OPERATOR_SAVEDATA_SHA256
        and _integer(
            native_tables["stage1_tables_size"],
            "native_stage1_tables.stage1_tables_size",
        )
        == 0x800
        and native_tables["stage1_tables_sha256"]
        == PINNED_STAGE1_TABLES_SHA256
        and _integer(
            native_tables["tile_table_size"],
            "native_stage1_tables.tile_table_size",
        )
        == 0x400
        and native_tables["tile_table_sha256"]
        == PINNED_TILE_TABLE_SHA256,
        "native Stage-1 table authority changed",
    )
    world_spec = _mapping(
        derivation["captured_world_window"],
        "derivation.captured_world_window",
    )
    _exact_keys(
        world_spec,
        ("camera_x", "camera_y", "width", "height", "sha256", "rows"),
        "derivation.captured_world_window",
    )
    _require(
        _integer(world_spec["camera_x"], "captured_world_window.camera_x")
        == 3
        and _integer(
            world_spec["camera_y"], "captured_world_window.camera_y"
        )
        == 10
        and _integer(world_spec["width"], "captured_world_window.width")
        == 6
        and _integer(world_spec["height"], "captured_world_window.height")
        == 6,
        "captured world window geometry changed",
    )
    world_window = _decode_rows(
        world_spec["rows"], 6, 6, "captured_world_window"
    )
    _require(
        world_spec["sha256"] == PINNED_WORLD_WINDOW_SHA256
        and _sha256(world_window) == PINNED_WORLD_WINDOW_SHA256,
        "captured world window identity changed",
    )

    source_spec = _mapping(root["immutable_source"], "immutable_source")
    _exact_keys(
        source_spec,
        (
            "label",
            "width",
            "height",
            "world_width",
            "world_height",
            "sha256",
            "rows",
        ),
        "immutable_source",
    )
    _string(source_spec["label"], "immutable_source.label")
    _require(
        _integer(source_spec["width"], "immutable_source.width")
        == PACKED_WIDTH
        and _integer(source_spec["height"], "immutable_source.height")
        == PACKED_HEIGHT
        and _integer(source_spec["world_width"], "immutable_source.world_width")
        == 22
        and _integer(
            source_spec["world_height"], "immutable_source.world_height"
        )
        == 20,
        "immutable source dimensions changed",
    )
    source = _decode_rows(
        source_spec["rows"], PACKED_WIDTH, PACKED_HEIGHT, "immutable_source"
    )
    source_digest = _sha256(source)
    _require(
        source_spec["sha256"] == PINNED_SOURCE_SHA256
        and source_digest == PINNED_SOURCE_SHA256,
        "immutable source identity changed",
    )
    for row in range(20):
        _require(
            source[row * PACKED_WIDTH + 22:(row + 1) * PACKED_WIDTH]
            == b"\x00\x00",
            f"immutable source row {row} lost its two-cell zero padding",
        )
    _require(
        source[20 * PACKED_WIDTH:] == bytes(4 * PACKED_WIDTH),
        "immutable source lost its four zero-padding rows",
    )

    families_spec = _mapping(root["families"], "families")
    _require(
        set(families_spec) == set(_PINNED_FAMILIES),
        "hazard family names changed",
    )
    families: list[HazardFamily] = []
    for family_name, pinned in _PINNED_FAMILIES.items():
        family_spec = _mapping(
            families_spec[family_name], f"families.{family_name}"
        )
        _exact_keys(
            family_spec,
            ("width", "height", "authority", "phases"),
            f"families.{family_name}",
        )
        width = _integer(family_spec["width"], f"{family_name}.width")
        height = _integer(family_spec["height"], f"{family_name}.height")
        _require(
            width == pinned["width"] and height == pinned["height"],
            f"{family_name} dimensions changed",
        )
        _string(family_spec["authority"], f"{family_name}.authority")
        phases_spec = _sequence(
            family_spec["phases"], f"{family_name}.phases"
        )
        _require(
            len(phases_spec) == len(pinned["phases"]),
            f"{family_name} phase count changed",
        )
        phases: list[HazardPhase] = []
        for phase_index, (
            (
                phase_id,
                phase_digest,
                pinned_offsets,
                pinned_definitions,
            ),
            raw_phase,
        ) in enumerate(
            zip(pinned["phases"], phases_spec, strict=True)
        ):
            phase_spec = _mapping(
                raw_phase, f"{family_name}.phases[{phase_index}]"
            )
            _exact_keys(
                phase_spec,
                (
                    "id",
                    "sha256",
                    "definition_offsets",
                    "metatile_definitions",
                    "rows",
                ),
                f"{family_name}.phases[{phase_index}]",
            )
            _require(
                phase_spec["id"] == phase_id
                and phase_spec["sha256"] == phase_digest,
                f"{family_name} phase {phase_index} identity changed",
            )
            raw_offsets = _sequence(
                phase_spec["definition_offsets"],
                f"{family_name}.{phase_id}.definition_offsets",
            )
            _require(
                len(raw_offsets) == 3,
                f"{family_name}.{phase_id} must have three definition offsets",
            )
            offsets: list[int] = []
            for definition_index, raw_offset in enumerate(raw_offsets):
                offset_text = _string(
                    raw_offset,
                    f"{family_name}.{phase_id}.definition_offsets"
                    f"[{definition_index}]",
                )
                _require(
                    re.fullmatch(r"[0-9A-F]{5}", offset_text) is not None,
                    f"{family_name}.{phase_id} has a malformed ROM offset",
                )
                offsets.append(int(offset_text, 16))
            _require(
                tuple(offsets) == pinned_offsets,
                f"{family_name}.{phase_id} definition offsets changed",
            )
            raw_definitions = _sequence(
                phase_spec["metatile_definitions"],
                f"{family_name}.{phase_id}.metatile_definitions",
            )
            _require(
                len(raw_definitions) == 3,
                f"{family_name}.{phase_id} must have three definitions",
            )
            definitions: list[bytes] = []
            for definition_index, raw_definition in enumerate(raw_definitions):
                definition_text = _string(
                    raw_definition,
                    f"{family_name}.{phase_id}.metatile_definitions"
                    f"[{definition_index}]",
                )
                _require(
                    len(definition_text) == 8
                    and _UPPER_HEX.fullmatch(definition_text) is not None,
                    f"{family_name}.{phase_id} has a malformed definition",
                )
                definitions.append(bytes.fromhex(definition_text))
            _require(
                tuple(item.hex().upper() for item in definitions)
                == pinned_definitions,
                f"{family_name}.{phase_id} metatile definitions changed",
            )
            tiles = _decode_rows(
                phase_spec["rows"],
                width,
                height,
                f"{family_name}.{phase_id}",
            )
            _require(
                _sha256(tiles) == phase_digest,
                f"{family_name} phase {phase_id} bytes changed",
            )
            phases.append(
                HazardPhase(
                    phase_id,
                    phase_digest,
                    width,
                    height,
                    tiles,
                    tuple(offsets),  # type: ignore[arg-type]
                    tuple(definitions),  # type: ignore[arg-type]
                )
            )
        families.append(
            HazardFamily(family_name, width, height, tuple(phases))
        )

    objects_spec = _sequence(root["objects"], "objects")
    _require(
        len(objects_spec) == len(_PINNED_OBJECTS),
        "hazard object count changed",
    )
    objects: list[HazardObject] = []
    for index, (raw_object, pinned) in enumerate(
        zip(objects_spec, _PINNED_OBJECTS, strict=True)
    ):
        object_spec = _mapping(raw_object, f"objects[{index}]")
        _exact_keys(
            object_spec,
            (
                "name",
                "family",
                "row",
                "column",
                "captured_world_ids",
                "captured_phase",
            ),
            f"objects[{index}]",
        )
        raw_world_ids = _sequence(
            object_spec["captured_world_ids"],
            f"objects[{index}].captured_world_ids",
        )
        _require(
            len(raw_world_ids) == 3,
            f"objects[{index}] must own three world IDs",
        )
        world_ids = tuple(
            _string(value, f"objects[{index}].captured_world_ids")
            for value in raw_world_ids
        )
        actual = (
            object_spec["name"],
            object_spec["family"],
            _integer(object_spec["row"], f"objects[{index}].row"),
            _integer(object_spec["column"], f"objects[{index}].column"),
            world_ids,
            _string(
                object_spec["captured_phase"],
                f"objects[{index}].captured_phase",
            ),
        )
        _require(actual == pinned, f"hazard object {index} placement changed")
        objects.append(HazardObject(*actual))  # type: ignore[arg-type]
        world_row = actual[2] // 4
        _require(
            tuple(
                f"{value:02X}"
                for value in world_window[world_row * 6:world_row * 6 + 3]
            )
            == world_ids,
            f"hazard object {actual[0]} disagrees with the captured world grid",
        )

    family_lookup = {family.name: family for family in families}
    object_cells: set[int] = set()
    for hazard_object in objects:
        family = family_lookup[hazard_object.family]
        family.phase(hazard_object.captured_phase)
        visible = _visible_object_cells(hazard_object, family)
        _require(
            len(visible) == 4 * 12,
            f"hazard object {hazard_object.name} is not a complete 4x12 block",
        )
        offsets = {cell[4] for cell in visible}
        _require(
            object_cells.isdisjoint(offsets),
            f"hazard object {hazard_object.name} overlaps another object",
        )
        object_cells.update(offsets)

        matching_source_phases = []
        visible_signatures: set[bytes] = set()
        for phase in family.phases:
            signature = bytes(
                phase.tile(local_row, local_column)
                for local_row, local_column, _, _, _ in visible
            )
            _require(
                signature not in visible_signatures,
                f"{hazard_object.name} has indistinguishable legal phases",
            )
            visible_signatures.add(signature)
            if all(
                source[offset] == phase.tile(local_row, local_column)
                for local_row, local_column, _, _, offset in visible
            ):
                matching_source_phases.append(phase.id)
        _require(
            matching_source_phases
            == [hazard_object.captured_phase],
            f"immutable source no longer has the pinned phase for "
            f"{hazard_object.name}",
        )

    physical_source = _physical_from_packed(source)
    physical_positions = _stage1_hazard_positions(physical_source)
    position_coordinates = {
        divmod(position, PHYSICAL_WIDTH) for position in physical_positions
    }
    _require(
        all(
            row < PACKED_HEIGHT and column < PACKED_WIDTH
            for row, column in position_coordinates
        ),
        "legacy hazard positions escaped the owned 24x24 map",
    )
    positions = {
        row * PACKED_WIDTH + column
        for row, column in position_coordinates
    }
    envelope_coordinates: set[tuple[int, int]] = set()
    for row, column in position_coordinates:
        for envelope_row in range(max(0, row - 1), min(32, row + 2)):
            for envelope_column in range(
                max(0, column - 1), min(32, column + 2)
            ):
                envelope_coordinates.add((envelope_row, envelope_column))
    _require(
        all(
            row < PACKED_HEIGHT and column < PACKED_WIDTH
            for row, column in envelope_coordinates
        ),
        "legacy hazard envelope escaped the owned 24x24 map",
    )
    envelope = {
        row * PACKED_WIDTH + column
        for row, column in envelope_coordinates
    }
    coverage = HazardCoverage(
        legacy_hazard_positions=tuple(sorted(positions)),
        legacy_broad_envelope=tuple(sorted(envelope)),
        exact_object_cells=tuple(sorted(object_cells)),
        exact_object_cells_outside_legacy_envelope=tuple(
            sorted(object_cells - envelope)
        ),
        immutable_guard_cells=tuple(sorted(envelope - object_cells)),
        audited_union_cells=tuple(sorted(envelope | object_cells)),
    )
    coverage_spec = _mapping(root["coverage"], "coverage")
    _exact_keys(coverage_spec, _PINNED_COVERAGE, "coverage")
    fixture_counts = {
        key: _integer(value, f"coverage.{key}")
        for key, value in coverage_spec.items()
    }
    _require(
        coverage.counts() == _PINNED_COVERAGE
        and fixture_counts == _PINNED_COVERAGE,
        "hazard coverage derivation changed",
    )
    provenance_spec = _sequence(root["provenance"], "provenance")
    _require(provenance_spec, "provenance is empty")
    provenance: list[tuple[str, str, str]] = []
    for index, raw_record in enumerate(provenance_spec):
        record = _mapping(raw_record, f"provenance[{index}]")
        _exact_keys(
            record, ("role", "path", "sha256"), f"provenance[{index}]"
        )
        role = _string(record["role"], f"provenance[{index}].role")
        source_path = _string(
            record["path"], f"provenance[{index}].path"
        )
        source_hash = _string(
            record["sha256"], f"provenance[{index}].sha256"
        )
        _require(role and source_path, f"provenance[{index}] is incomplete")
        _require(
            _HEX_SHA256.fullmatch(source_hash) is not None,
            f"provenance[{index}] SHA-256 is malformed",
        )
        provenance.append((role, source_path, source_hash))

    return HazardTileContract(
        fixture_path=path,
        fixture_sha256=digest,
        immutable_source=source,
        immutable_source_sha256=source_digest,
        objects=tuple(objects),
        families=tuple(families),
        coverage=coverage,
        provenance=tuple(provenance),
    )


def derive_phase_from_native_authorities(
    native_rom: bytes | bytearray | memoryview,
    stage1_tables: bytes | bytearray | memoryview,
    family_name: str,
    phase_id: str,
    *,
    contract: HazardTileContract | None = None,
) -> bytes:
    """Re-derive one fixture phase from the pinned stock ROM and SRAM tables.

    This audit API intentionally requires the exact original ROM, not the
    candidate under test.  It is therefore suitable for proving where the
    fixture rows came from, but it cannot become a live self-baseline.
    """
    if contract is None:
        contract = load_contract()
    rom = bytes(native_rom)
    tables = bytes(stage1_tables)
    _require(
        _sha256(rom) == PINNED_NATIVE_ROM_SHA256,
        "native phase derivation did not receive the pinned stock ROM",
    )
    _require(
        len(rom) >= PINNED_NATIVE_WINDOW_OFFSET + PINNED_NATIVE_WINDOW_SIZE
        and _sha256(
            rom[
                PINNED_NATIVE_WINDOW_OFFSET:
                PINNED_NATIVE_WINDOW_OFFSET + PINNED_NATIVE_WINDOW_SIZE
            ]
        )
        == PINNED_NATIVE_WINDOW_SHA256,
        "native animation definition window changed",
    )
    _require(
        len(tables) == 0x800
        and _sha256(tables) == PINNED_STAGE1_TABLES_SHA256
        and _sha256(tables[:0x400]) == PINNED_TILE_TABLE_SHA256,
        "native Stage-1 SRAM tables changed",
    )
    family = contract.family(family_name)
    phase = family.phase(phase_id)
    definitions = tuple(
        rom[offset:offset + 4] for offset in phase.definition_offsets
    )
    _require(
        definitions == phase.metatile_definitions,
        f"native definitions disagree with {family_name}.{phase_id}",
    )

    component_rows = [bytearray() for _ in range(4)]
    tile_table = tables[:0x400]
    for definition in definitions:
        world_rows = [bytearray() for _ in range(4)]
        for metatile_row in range(2):
            for metatile_column in range(2):
                metatile = definition[
                    metatile_row * 2 + metatile_column
                ]
                tile_base = metatile * 4
                tile_quad = tile_table[tile_base:tile_base + 4]
                _require(
                    len(tile_quad) == 4,
                    f"{family_name}.{phase_id} metatile escaped tile table",
                )
                for tile_row in range(2):
                    world_rows[metatile_row * 2 + tile_row].extend(
                        tile_quad[tile_row * 2:tile_row * 2 + 2]
                    )
        for row, world_row in enumerate(world_rows):
            _require(
                len(world_row) == 4,
                f"{family_name}.{phase_id} world ID did not expand to 4x4",
            )
            component_rows[row].extend(world_row)
    derived = bytes().join(bytes(row) for row in component_rows)
    _require(
        len(derived) == family.width * family.height
        and derived == phase.tiles
        and _sha256(derived) == phase.sha256,
        f"native derivation disagrees with {family_name}.{phase_id}",
    )
    return derived


def captured_phase_selection(
    contract: HazardTileContract | None = None,
) -> dict[str, str]:
    """Return the independently authenticated operator-capture phase tuple."""
    if contract is None:
        contract = load_contract()
    return {
        hazard_object.name: hazard_object.captured_phase
        for hazard_object in contract.objects
    }


def _resolve_source(
    source: bytes | bytearray | memoryview | None,
    contract: HazardTileContract,
) -> bytes:
    if source is None:
        return contract.immutable_source
    payload = bytes(source)
    _require(
        len(payload) == PACKED_CELLS,
        "caller-supplied immutable source must be packed 24x24 (576 bytes)",
    )
    digest = _sha256(payload)
    _require(
        digest == PINNED_SOURCE_SHA256
        and payload == contract.immutable_source,
        "caller-supplied immutable source is not the pinned independent "
        f"Scene-$0B source: got {digest}",
    )
    return payload


def render_legal_map(
    phases: Mapping[str, str],
    *,
    layout: str = "packed",
    source: bytes | bytearray | memoryview | None = None,
    contract: HazardTileContract | None = None,
) -> bytes:
    """Render one legal independent phase choice per exact hazard object."""
    if contract is None:
        contract = load_contract()
    expected_names = {hazard_object.name for hazard_object in contract.objects}
    _require(
        set(phases) == expected_names,
        f"phase selection must name exactly {sorted(expected_names)}",
    )
    rendered = bytearray(_resolve_source(source, contract))
    for hazard_object in contract.objects:
        family = contract.family(hazard_object.family)
        phase_id = phases[hazard_object.name]
        _require(
            isinstance(phase_id, str),
            f"phase for {hazard_object.name} must be a string",
        )
        phase = family.phase(phase_id)
        for local_row, local_column, _, _, offset in _visible_object_cells(
            hazard_object, family
        ):
            rendered[offset] = phase.tile(local_row, local_column)
    _require(layout in {"packed", "physical"}, "unknown rendered map layout")
    if layout == "packed":
        return bytes(rendered)
    return _physical_from_packed(bytes(rendered))


def evaluate_scene0b_hazard_tiles(
    observed: bytes | bytearray | memoryview,
    *,
    source: bytes | bytearray | memoryview | None = None,
    contract: HazardTileContract | None = None,
) -> HazardTileEvaluation:
    """Evaluate a packed or physical tile map against exact legal phases."""
    if contract is None:
        contract = load_contract()
    immutable_source = _resolve_source(source, contract)
    packed = _packed_from_observed(observed)

    object_results: list[HazardObjectEvaluation] = []
    for hazard_object in contract.objects:
        family = contract.family(hazard_object.family)
        visible = _visible_object_cells(hazard_object, family)
        mismatch_sets: list[tuple[HazardPhase, tuple[TileMismatch, ...]]] = []
        for phase in family.phases:
            mismatches = tuple(
                TileMismatch(
                    kind="object_phase",
                    row=row,
                    column=column,
                    expected=phase.tile(local_row, local_column),
                    actual=packed[offset],
                    object_name=hazard_object.name,
                    phase=phase.id,
                )
                for local_row, local_column, row, column, offset in visible
                if packed[offset] != phase.tile(local_row, local_column)
            )
            mismatch_sets.append((phase, mismatches))
        exact_matches = [
            phase.id for phase, mismatches in mismatch_sets if not mismatches
        ]
        _require(
            len(exact_matches) <= 1,
            f"{hazard_object.name} ambiguously matches multiple phases",
        )
        best_index = min(
            range(len(mismatch_sets)),
            key=lambda index: (len(mismatch_sets[index][1]), index),
        )
        best_phase, best_mismatches = mismatch_sets[best_index]
        object_results.append(
            HazardObjectEvaluation(
                name=hazard_object.name,
                family=hazard_object.family,
                matched_phase=exact_matches[0] if exact_matches else None,
                best_phase=best_phase.id,
                phase_mismatch_counts=tuple(
                    (phase.id, len(mismatches))
                    for phase, mismatches in mismatch_sets
                ),
                mismatches=best_mismatches,
            )
        )

    guard_offsets = set(contract.coverage.immutable_guard_cells)
    object_offsets = set(contract.coverage.exact_object_cells)
    guard_mismatches = tuple(
        TileMismatch(
            kind="immutable_guard",
            row=offset // PACKED_WIDTH,
            column=offset % PACKED_WIDTH,
            expected=immutable_source[offset],
            actual=packed[offset],
        )
        for offset in contract.coverage.immutable_guard_cells
        if packed[offset] != immutable_source[offset]
    )
    unexpected_hazard_tiles = tuple(
        TileMismatch(
            kind="unexpected_hazard_family_tile",
            row=offset // PACKED_WIDTH,
            column=offset % PACKED_WIDTH,
            expected=immutable_source[offset],
            actual=packed[offset],
        )
        for offset in range(PACKED_CELLS)
        if offset not in object_offsets
        and offset not in guard_offsets
        and packed[offset] != immutable_source[offset]
        and (
            _is_hazard_family_tile(packed[offset])
            or _is_hazard_family_tile(immutable_source[offset])
        )
    )
    return HazardTileEvaluation(
        fixture_sha256=contract.fixture_sha256,
        immutable_source_sha256=contract.immutable_source_sha256,
        objects=tuple(object_results),
        immutable_guard_mismatches=guard_mismatches,
        unexpected_hazard_tiles=unexpected_hazard_tiles,
        coverage=contract.coverage,
    )


def assert_scene0b_hazard_tiles_legal(
    observed: bytes | bytearray | memoryview,
    *,
    source: bytes | bytearray | memoryview | None = None,
    contract: HazardTileContract | None = None,
) -> HazardTileEvaluation:
    """Return the evaluation or raise with a compact deterministic receipt."""
    evaluation = evaluate_scene0b_hazard_tiles(
        observed, source=source, contract=contract
    )
    if not evaluation.legal:
        raise HazardTileAssertionError(evaluation)
    return evaluation
