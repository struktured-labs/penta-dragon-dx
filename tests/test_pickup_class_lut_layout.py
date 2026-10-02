#!/usr/bin/env python3
"""Narrow acceptance controls for the reviewed Stage-1 tooth-bank LUT."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagnostics.verify_pickup_class_palettes import (  # noqa: E402
    COMPILED_TOOTH_BANK_TILES,
    EXPECTED_TABLE,
    reviewed_stage1_table,
    semantic_stage1_table,
)


class PickupClassLutLayoutTests(unittest.TestCase):
    def test_exact_base_and_reviewed_tooth_bank_pass(self) -> None:
        variant = bytearray(EXPECTED_TABLE)
        for tile in COMPILED_TOOTH_BANK_TILES:
            variant[tile] |= 0x08
        self.assertTrue(reviewed_stage1_table(EXPECTED_TABLE))
        self.assertTrue(reviewed_stage1_table(bytes(variant)))
        self.assertEqual(semantic_stage1_table(bytes(variant)), EXPECTED_TABLE)

    def test_unreviewed_bank_bit_and_palette_change_fail(self) -> None:
        unreviewed = bytearray(EXPECTED_TABLE)
        unreviewed[0x63] |= 0x08
        self.assertFalse(reviewed_stage1_table(bytes(unreviewed)))
        wrong_palette = bytearray(EXPECTED_TABLE)
        wrong_palette[COMPILED_TOOTH_BANK_TILES[0]] = 0x06
        self.assertFalse(reviewed_stage1_table(bytes(wrong_palette)))


if __name__ == "__main__":
    unittest.main()
