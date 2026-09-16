#!/usr/bin/env python3
"""Offline controls for the low-health physical-map publication oracle.

These tests inspect the Lua/Python gate sources only.  They deliberately do
not load a ROM, a savestate, or an emulator, so an oracle regression is caught
before the comparatively expensive live receipt runs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "scripts/diagnostics/probe_low_health_flicker.lua"
VERIFIER_PATH = ROOT / "scripts/diagnostics/verify_low_health_flicker.py"
sys.path.insert(0, str(VERIFIER_PATH.parent))


def source_block(source: str, start: str, end: str) -> str:
    """Return one uniquely delimited source block, failing on drift."""
    if source.count(start) != 1 or source.count(end) != 1:
        raise AssertionError(
            f"expected unique source delimiters: {start!r}, {end!r}"
        )
    return source.split(start, 1)[1].split(end, 1)[0]


class LowHealthPublicationOracleContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.probe = PROBE_PATH.read_text()
        cls.verifier = VERIFIER_PATH.read_text()
        cls.arm = source_block(
            cls.probe,
            "local function arm_resident_compiler_receipt()",
            "local function inspect_resident_compiler_row()",
        )
        cls.capture = source_block(
            cls.probe,
            "local function inspect_resident_compiler_row()",
            "local function publish_expected_plane()",
        )
        cls.promote = source_block(
            cls.probe,
            "local function publish_expected_plane()",
            "-- The fixture is a mid-game Stage-1 state",
        )
        cls.visible = source_block(
            cls.probe,
            "local function visible_bg_receipt()",
            "local function resident_runtime()",
        )

        spec = importlib.util.spec_from_file_location(
            "verify_low_health_flicker_publication_contract",
            VERIFIER_PATH,
        )
        assert spec is not None and spec.loader is not None
        cls.verifier_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.verifier_module)

    def test_destination_decode_accepts_only_exact_dirty_tags(self) -> None:
        """Reject aliases such as 9A/9B/9E/9F, not just unknown pages."""
        self.assertNotIn("& 0xFC", self.arm)
        self.assertRegex(
            self.arm,
            r"compiler_pending_latch\s*==\s*0x99[\s\S]*?0x9800",
        )
        self.assertRegex(
            self.arm,
            r"compiler_pending_latch\s*==\s*0x9D[\s\S]*?0x9C00",
        )
        for tag in range(0x100):
            decoded = 0x9800 if tag == 0x99 else (
                0x9C00 if tag == 0x9D else 0
            )
            with self.subTest(tag=f"{tag:02X}"):
                self.assertEqual(decoded != 0, tag in {0x99, 0x9D})

    def test_compiler_capture_uses_packed_source_and_map_stride(self) -> None:
        self.assertIn("0xC1A0 + row * 0x18", self.capture)
        self.assertIn("row * 0x20", self.capture)
        self.assertIn("de == 0xC1A0 + row * 0x18", self.capture)
        self.assertIn("hl == 0xD000 + row * 0x20", self.capture)
        self.assertNotIn("hl == 0xD000 + row * 0x18", self.capture)
        self.assertEqual(
            [(0xC1A0 + row * 0x18, 0xD000 + row * 0x20)
             for row in (0, 1, 23)],
            [(0xC1A0, 0xD000), (0xC1B8, 0xD020), (0xC3C8, 0xD2E0)],
        )

    def test_capture_and_promotion_are_on_exact_instruction_boundaries(
        self,
    ) -> None:
        self.assertIn(
            "setBreakpoint(inspect_resident_compiler_row, 0x4313, 1) > 0",
            self.probe,
        )
        self.assertIn(
            "setBreakpoint(publish_expected_plane, 0x4354, 1) > 0",
            self.probe,
        )
        self.assertNotIn(
            "setBreakpoint(publish_expected_plane, 0x4353", self.probe
        )

        decision_callback = source_block(
            self.probe,
            "emu:setBreakpoint(function()\n      local scene =",
            "    emu:setBreakpoint(function()\n      source_ret_hits",
        )
        self.assertIn("end, 0x3485)", decision_callback)
        self.assertNotIn("expected_plane", decision_callback)
        self.assertNotIn("published_expected", decision_callback)

    def test_promotion_requires_completed_dma_and_restored_banks(self) -> None:
        self.assertRegex(
            self.promote, r"emu:read8\(0xFF55\)\s*~=\s*0xFF"
        )
        self.assertRegex(
            self.promote,
            r"emu:read8\(0xFF4F\)\s*&\s*0x01\)\s*~=\s*0",
        )
        self.assertRegex(
            self.promote,
            r"emu:read8\(0xFF70\)\s*&\s*0x07\)\s*~=\s*0x01",
        )
        self.assertLess(
            self.promote.index("emu:read8(0xFF55)"),
            self.promote.index("published_expected_planes"),
        )

    def test_expected_plane_is_not_derived_from_mutable_or_actual_attrs(
        self,
    ) -> None:
        """The oracle may observe tiles, but must not bless observed attrs."""
        expectation_path = self.arm + self.capture + self.promote
        self.assertNotIn("0xC600", expectation_path)
        self.assertNotRegex(
            expectation_path,
            r"expected[^\n]*=\s*emu:read8\(",
        )
        self.assertNotRegex(
            expectation_path,
            r"emu:read8\((?:0x9800|0x9C00|destination|pending\.destination)",
        )
        self.assertNotIn("emu:read8(0xC600", self.visible)
        self.assertIn("publication.expected[offset]", self.visible)

    def test_visible_hazards_are_geometry_scoped_and_cover_edge_tiles(
        self,
    ) -> None:
        self.assertIn(
            "local hazard_cells = hazard_positions(function(column, row)",
            self.visible,
        )
        self.assertRegex(
            self.visible,
            r"if\s+hazard_cells\[offset\][\s\S]*?"
            r"tile\s*>=\s*0x64[\s\S]*?tile\s*<=\s*0x79",
        )
        tooth_branch = source_block(
            self.visible,
            "local expected_hazard = nil",
            "-- Never derive the hazard oracle from mutable C600.",
        )
        self.assertIn("hazard_cells[offset]", tooth_branch)
        self.assertNotRegex(
            tooth_branch,
            r"(?:if|elseif)\s+\(?(?:tile\s*[><=]|\(tile\s*[><=])",
            "a tile-ID hazard branch must first require hazard_cells[offset]",
        )
        self.assertIn(
            "local visible_rows = (scy & 0x07) == 0 and 18 or 19",
            self.visible,
        )
        self.assertIn(
            "local visible_columns = (scx & 0x07) == 0 and 20 or 21",
            self.visible,
        )
        self.assertEqual(self.visible.count("row = 0, visible_rows - 1"), 2)
        self.assertEqual(
            self.visible.count("column = 0, visible_columns - 1"), 2
        )

    def test_verifier_rejects_missing_publication_owner(self) -> None:
        self.assertIn("publication_owner_missing_frames = [", self.verifier)
        for predicate in (
            'row.get("map_owner_valid") != "1"',
            'int(row.get("oracle_missing", "1")) != 0',
            'int(row.get("map_owner_epoch", "0")) <= 0',
            'int(row.get("map_owner_frame", "0")) > int(row["frame"])',
        ):
            self.assertIn(predicate, self.verifier)
        self.assertIn("not publication_owner_missing_frames", self.verifier)

        helper = self.verifier_module.publication_owner_handoffs
        prior = {
            "sample": "10",
            "room": "01",
            "map": "9800",
            "tile_bytes": "AA",
            "attr_bytes": "BB",
            "map_owner_valid": "1",
            "map_owner_epoch": "7",
            "unexpected_mismatches": "0",
        }
        missing = dict(prior, sample="11", room="05", map_owner_valid="0")
        self.assertFalse(helper([prior, missing])["exact"])

    def test_room_handoff_rejects_an_epoch_change_without_map_change(
        self,
    ) -> None:
        helper = self.verifier_module.publication_owner_handoffs
        prior = {
            "sample": "20",
            "room": "01",
            "map": "9C00",
            "tile_bytes": "0102",
            "attr_bytes": "0606",
            "map_owner_valid": "1",
            "map_owner_epoch": "11",
            "unexpected_mismatches": "0",
        }
        changed = dict(
            prior, sample="21", room="05", map_owner_epoch="12"
        )
        receipt = helper([prior, changed])
        self.assertEqual(receipt["count"], 1)
        self.assertFalse(receipt["exact"])


if __name__ == "__main__":
    unittest.main()
