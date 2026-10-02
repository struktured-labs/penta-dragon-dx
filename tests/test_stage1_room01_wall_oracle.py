#!/usr/bin/env python3
"""Offline controls for the reviewed Stage-1 room-01 wall oracle."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

from stage1_room01_wall_oracle import (  # noqa: E402
    VIEW_CELLS,
    VIEW_WIDTH,
    load_reviewed_wall_contract,
    reviewed_stage1_wall_oracle,
)


FIXTURE = DIAGNOSTICS / "fixtures/stage1_room01_wall_oracle.json"


class Stage1Room01WallOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_reviewed_wall_contract(FIXTURE)

    def wall_specs(self) -> list[tuple[int, int]]:
        specs = []
        for row in self.contract["room01_checkpoint"]["wall_rows"]:
            y = int(row["y"])
            specs.extend(
                (y * VIEW_WIDTH + int(x), int(tile))
                for x, tile in row["cells"]
            )
        self.assertEqual(len(specs), 64)
        return specs

    @staticmethod
    def record(selector: dict[str, int], gameplay_frame: int) -> dict[str, object]:
        return {
            **selector,
            "gameplay_frame": gameplay_frame,
            "tiles": bytes([0xFE]) * VIEW_CELLS,
            "attrs": bytes(VIEW_CELLS),
        }

    def known_good_records(
        self, wall_attrs: bytes | None = None
    ) -> list[dict[str, object]]:
        wall = self.contract["room01_checkpoint"]
        floor = self.contract["room05_patterned_floor_control"]
        specs = self.wall_specs()
        if wall_attrs is None:
            wall_attrs = bytes([int(wall["expected_attr"])]) * len(specs)
        self.assertEqual(len(wall_attrs), len(specs))
        records = []
        for gameplay_frame in (1065, 1066, 1068):
            row = self.record(wall["selector"], gameplay_frame)
            tiles = bytearray(row["tiles"])
            attrs = bytearray(row["attrs"])
            for (view_index, tile), attr in zip(specs, wall_attrs, strict=True):
                tiles[view_index] = tile
                attrs[view_index] = attr
            row["tiles"] = bytes(tiles)
            row["attrs"] = bytes(attrs)
            records.append(row)
        for gameplay_frame in (1, 2):
            row = self.record(floor["selector"], gameplay_frame)
            tiles = bytearray(row["tiles"])
            attrs = bytearray(row["attrs"])
            # Exercise the entire declared 2A-2E/3A-3D class even though the
            # archived north route exposes only 2C/2D/3C at its fixed cells.
            for view_index, tile in enumerate(floor["patterned_floor_tile_ids"]):
                tiles[view_index] = int(tile)
                attrs[view_index] = int(floor["expected_attr"])
            for cell in floor["control_cells"]:
                view_index = int(cell["view_index"])
                tiles[view_index] = int(cell["tile"])
                attrs[view_index] = int(floor["expected_attr"])
            row["tiles"] = bytes(tiles)
            row["attrs"] = bytes(attrs)
            records.append(row)
        return records

    def test_known_good_reviewed_positions_pass(self) -> None:
        result = reviewed_stage1_wall_oracle(
            self.known_good_records(), self.contract
        )
        self.assertTrue(result["exact"])
        self.assertEqual(result["room01"]["checked_cell_instances"], 192)
        self.assertEqual(
            result["room05_patterned_floor_control"]
            ["observed_patterned_tile_ids"],
            [42, 43, 44, 45, 46, 58, 59, 60, 61],
        )

    def test_archived_r290_and_r292_checkpoints_reject(self) -> None:
        archives = self.contract["archived_negative_controls"]
        for name in ("r290", "r292"):
            with self.subTest(archive=name):
                wall_attrs = bytes.fromhex(archives[name]["wall_attrs_hex"])
                result = reviewed_stage1_wall_oracle(
                    self.known_good_records(wall_attrs), self.contract
                )
                self.assertFalse(result["exact"])
                # Each archived checkpoint has 32 bad cells, repeated across
                # the three semantically selected records.
                self.assertEqual(result["room01"]["attr_mismatches"], 96)
                self.assertEqual(result["room01"]["tile_mismatches"], 0)

    def test_one_room01_full_attr_mutation_rejects(self) -> None:
        records = self.known_good_records()
        mutant = copy.deepcopy(records)
        view_index, _ = self.wall_specs()[0]
        attrs = bytearray(mutant[0]["attrs"])
        attrs[view_index] = 0x86
        mutant[0]["attrs"] = bytes(attrs)
        result = reviewed_stage1_wall_oracle(mutant, self.contract)
        self.assertFalse(result["exact"])
        self.assertEqual(result["room01"]["attr_mismatches"], 1)
        self.assertEqual(result["room01"]["first_mismatch"]["actual_attr"], 0x86)

    def test_different_fixed_set_cannot_self_validate(self) -> None:
        records = self.known_good_records()
        mutant = copy.deepcopy(records)
        required_index, _ = self.wall_specs()[1]
        attrs = bytearray(mutant[0]["attrs"])
        attrs[required_index] = 0x00
        attrs[0] = 0x06
        mutant[0]["attrs"] = bytes(attrs)
        result = reviewed_stage1_wall_oracle(mutant, self.contract)
        self.assertFalse(result["exact"])
        self.assertEqual(result["room01"]["attr_mismatches"], 1)

    def test_room05_patterned_floor_to_six_mutation_rejects(self) -> None:
        records = self.known_good_records()
        mutant = copy.deepcopy(records)
        floor_index = 3
        attrs = bytearray(mutant[floor_index]["attrs"])
        attrs[98] = 0x06
        mutant[floor_index]["attrs"] = bytes(attrs)
        result = reviewed_stage1_wall_oracle(mutant, self.contract)
        floor = result["room05_patterned_floor_control"]
        self.assertFalse(result["exact"])
        self.assertEqual(floor["control_attr_mismatches"], 1)
        self.assertEqual(floor["patterned_attr_mismatches"], 1)


if __name__ == "__main__":
    unittest.main()
