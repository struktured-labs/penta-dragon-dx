from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import _bg_table  # noqa: E402
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_variants,
    load_stage1_hazard_config,
)


TERMINAL_TILES = frozenset({0x6B, 0x6F, 0x7B, 0x7F})
TERMINAL_NATIVE_ART_SHA256 = (
    "b06f4b0aec4a06c41a57c470f6b63f1c8d519ad609033b85bd95cf36b4edecf3"
)


class Stage1HazardTerminalPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_stage1_hazard_config()
        cls.stock = (ROOT / "rom/Penta Dragon (J).gb").read_bytes()

    def test_operator_reported_terminal_cells_are_a_dedicated_role(self) -> None:
        self.assertEqual(self.config.terminal_tiles, TERMINAL_TILES)
        self.assertEqual(self.config.terminal_palette, self.config.body_palette)
        self.assertTrue(TERMINAL_TILES.isdisjoint(self.config.support_tiles))

    def test_exact_terminal_cells_select_fire_material(self) -> None:
        table = bytes(_bg_table())
        self.assertEqual(
            {tile: table[tile] for tile in sorted(TERMINAL_TILES)},
            {tile: 5 for tile in sorted(TERMINAL_TILES)},
        )

    def test_terminal_recolor_preserves_native_cap_art(self) -> None:
        variants = compile_stage1_hazard_variants(self.stock, self.config)
        self.assertTrue(TERMINAL_TILES.isdisjoint(variants))
        native_art = b"".join(
            self.stock[
                self.config.source_offset + tile * 16 :
                self.config.source_offset + (tile + 1) * 16
            ]
            for tile in sorted(TERMINAL_TILES)
        )
        self.assertEqual(hashlib.sha256(native_art).hexdigest(), TERMINAL_NATIVE_ART_SHA256)

    def test_remaining_gray_cells_are_only_cast_shadow_and_support(self) -> None:
        self.assertEqual(
            self.config.support_tiles,
            frozenset({0x63, 0x6A, 0x73, 0x7A}),
        )


if __name__ == "__main__":
    unittest.main()
