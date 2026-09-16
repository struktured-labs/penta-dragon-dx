from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_hazard_terminal_caps_r341 as r341  # noqa: E402
import verify_stage1_scene0b_captured_menu_receipt as scene0b_receipt  # noqa: E402
import verify_stage1_scene0b_live_menu_roundtrip as scene0b_live  # noqa: E402
from build_v301_gdma import _bg_table  # noqa: E402
from build_v302_title_fix import build_stage1_entry_attr_patch  # noqa: E402
from stage1_hazard_semantic_row import build_lut  # noqa: E402


R341_SHA256 = "30ba055bc4cdd7468994d8dbe017a9c73ec82d09184f792e690ffd22a95e73cf"
R341_STAGE1_LUT_SHA256 = (
    "3b2d1224bb47c68263ff862f1a1c68d8b20f055fe2fcae0fa1028659d492961a"
)


class Stage1HazardTerminalCapsR341Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not r341.BASE.is_file() or not r341.BASE_RECEIPT.is_file():
            raise unittest.SkipTest("exact r336 build fixtures are absent from repo tmp/")
        cls.base = r341.BASE.read_bytes()
        cls.candidate, cls.receipt = r341.build(
            cls.base,
            r341.BASE_RECEIPT.read_bytes(),
        )

    def test_build_is_exact_and_terminal_only(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), R341_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], R341_SHA256)
        self.assertEqual(self.receipt["terminal_tiles"], ["6B", "6F", "7B", "7F"])
        self.assertEqual(self.receipt["terminal_palette"], 5)
        self.assertTrue(self.receipt["native_art_preserved"])

    def test_all_three_runtime_luts_select_terminal_bg5(self) -> None:
        immutable = bytes(_bg_table())
        semantic = build_lut(immutable)
        room01 = r341.room01.build_room01_lut(semantic)
        for offset, expected in (
            (r341.BG_TABLE_OFFSET, immutable),
            (r341.SEMANTIC_LUT_OFFSET, semantic),
            (r341.ROOM01_LUT_OFFSET, room01),
        ):
            self.assertEqual(self.candidate[offset : offset + 0x100], expected)
            self.assertEqual(
                {tile: self.candidate[offset + tile] for tile in r341.TERMINAL_TILES},
                {tile: 5 for tile in r341.TERMINAL_TILES},
            )

    def test_cold_entry_publishes_6f_7f_as_bg5(self) -> None:
        _, tail, finish, _ = build_stage1_entry_attr_patch(bytes(_bg_table()))
        self.assertEqual(
            self.candidate[r341.ENTRY_TAIL_OFFSET : r341.ENTRY_TAIL_OFFSET + len(tail)],
            tail,
        )
        self.assertEqual(
            self.candidate[
                r341.ENTRY_FINISH_OFFSET : r341.ENTRY_FINISH_OFFSET + len(finish)
            ],
            finish,
        )
        self.assertIn(bytes.fromhex("3E 05"), tail)
        self.assertIn(bytes.fromhex("2E 8B 77 2E AB 77"), finish)

    def test_terminal_source_art_is_byte_identical_to_r336(self) -> None:
        for tile in r341.TERMINAL_TILES:
            start = 0x1D000 + tile * 16
            self.assertEqual(
                self.candidate[start : start + 16],
                self.base[start : start + 16],
            )

    def test_captured_wall_gates_pin_the_terminal_corrected_lut(self) -> None:
        lut = self.candidate[
            scene0b_live.STAGE1_LUT_OFFSET:
            scene0b_live.STAGE1_LUT_OFFSET + 0x100
        ]
        self.assertEqual(hashlib.sha256(lut).hexdigest(), R341_STAGE1_LUT_SHA256)
        self.assertEqual(
            scene0b_live.STAGE1_RELEASE_LUT_SHA256,
            R341_STAGE1_LUT_SHA256,
        )
        self.assertEqual(
            scene0b_receipt.STAGE1_RELEASE_LUT_SHA256,
            R341_STAGE1_LUT_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
