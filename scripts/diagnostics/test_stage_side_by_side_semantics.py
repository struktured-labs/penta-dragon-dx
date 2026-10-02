#!/usr/bin/env python3
"""Offline controls for later-stage semantic palette containment."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).with_name("capture_stage_side_by_side.py")
SPEC = importlib.util.spec_from_file_location("capture_stage_side_by_side", MODULE_PATH)
assert SPEC and SPEC.loader
CAPTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPTURE)


def row(tile: int = 0x02, palette: int = 5) -> dict:
    return {
        "frame": 240,
        "tilemap_hex": bytes([tile] * 360).hex().upper(),
        "attribute_hex": bytes([palette] * 360).hex().upper(),
    }


class StageSemanticPaletteTests(unittest.TestCase):
    def test_clean_stage5_pickups_pass(self) -> None:
        sample = row()
        tiles = bytearray.fromhex(sample["tilemap_hex"])
        attrs = bytearray.fromhex(sample["attribute_hex"])
        for index, tile in enumerate((0x88, 0x89, 0x96, 0x98, 0x99)):
            tiles[index] = tile
            attrs[index] = 1
        for index, tile in enumerate(
            (0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7), start=8
        ):
            tiles[index] = tile
            attrs[index] = 2
        sample["tilemap_hex"] = tiles.hex().upper()
        sample["attribute_hex"] = attrs.hex().upper()
        result = CAPTURE.audit_stage_semantic_palettes(5, [sample])
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["failures"], [])

    def test_detached_pickup_palette_trail_fails(self) -> None:
        sample = row(tile=0x02, palette=1)
        result = CAPTURE.audit_stage_semantic_palettes(5, [sample])
        self.assertEqual(result["status"], "fail")
        self.assertIn("non-pickup 02 retains semantic BG1", result["failures"][0])

    def test_uncolored_pickup_face_fails(self) -> None:
        sample = row(tile=0x88, palette=5)
        result = CAPTURE.audit_stage_semantic_palettes(5, [sample])
        self.assertEqual(result["status"], "fail")
        self.assertIn("pickup 88 uses BG5, expected BG1", result["failures"][0])

    def test_other_stages_are_not_claimed_by_stage5_contract(self) -> None:
        result = CAPTURE.audit_stage_semantic_palettes(4, [row()])
        self.assertEqual(result["status"], "not-applicable")


if __name__ == "__main__":
    unittest.main()
