from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_hazard_terminal_silhouette_r343 as r343  # noqa: E402
from diagnostics.verify_pickup_class_palettes import (  # noqa: E402
    BG_TABLE_OFFSET,
)
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_terminal_variants,
    decode_tile,
    load_stage1_hazard_config,
)


class Stage1HazardTerminalSilhouetteR343Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not r343.BASE.is_file() or not r343.BASE_RECEIPT.is_file():
            raise unittest.SkipTest("exact r342 build fixtures are absent from repo tmp/")
        cls.base = r343.BASE.read_bytes()
        cls.candidate, cls.receipt = r343.build(
            cls.base,
            r343.BASE_RECEIPT.read_bytes(),
        )
        cls.stock = r343.STOCK.read_bytes()
        cls.config = load_stage1_hazard_config()
        cls.variants = compile_stage1_hazard_terminal_variants(
            cls.stock, cls.config
        )

    def test_build_is_exactly_derived_from_r342(self) -> None:
        self.assertEqual(hashlib.sha256(self.base).hexdigest(), r343.BASE_SHA256)
        self.assertEqual(
            hashlib.sha256(self.candidate).hexdigest(), r343.R343_SHA256
        )
        self.assertEqual(self.receipt["candidate_sha256"], r343.R343_SHA256)
        self.assertEqual(self.receipt["free_tip_tiles"], ["6B", "7B"])
        self.assertEqual(
            self.receipt["wall_terminal_tiles_preserved"], ["6F", "7F"]
        )

    def test_free_tip_art_is_bounded_by_the_reviewed_diagonal(self) -> None:
        for tile in r343.FREE_TIP_TILES:
            start = self.config.source_offset + tile * 16
            native = decode_tile(self.stock[start:start + 16])
            corrected = decode_tile(self.variants[tile])
            self.assertNotEqual(corrected, native)
            for y, span in self.config.terminal_row_spans[tile].items():
                for x in range(8):
                    pixel = corrected[y * 8 + x]
                    if x < span[0]:
                        self.assertEqual(
                            pixel, 0,
                            f"tile {tile:02X} ({x},{y}) can become yellow",
                        )
                    else:
                        self.assertEqual(
                            pixel,
                            native[y * 8 + x],
                            f"tile {tile:02X} changed inside its cap",
                        )

    def test_free_tip_cells_use_fire_palette_not_gray_support_palette(self) -> None:
        table = self.candidate[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 0x100]
        for tile in r343.FREE_TIP_TILES:
            self.assertEqual(
                table[tile],
                self.config.terminal_palette,
                f"free-tip tile {tile:02X} can render gray",
            )
            self.assertNotEqual(table[tile], self.config.support_palette)

    def test_wall_contact_cells_use_fire_palette_not_gray_support_palette(self) -> None:
        table = self.candidate[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 0x100]
        for tile in r343.WALL_TERMINAL_TILES:
            self.assertEqual(
                table[tile],
                self.config.terminal_palette,
                f"wall-contact tile {tile:02X} can render gray",
            )
            self.assertNotEqual(table[tile], self.config.support_palette)

    def test_candidate_installs_exact_free_tip_variants_only(self) -> None:
        for tile in r343.FREE_TIP_TILES:
            start = self.config.source_offset + tile * 16
            self.assertEqual(
                self.candidate[start:start + 16], self.variants[tile]
            )
        for tile in r343.WALL_TERMINAL_TILES:
            start = self.config.source_offset + tile * 16
            self.assertEqual(
                self.candidate[start:start + 16],
                self.stock[start:start + 16],
            )

    def test_stale_state_admission_uploads_both_corrected_tiles(self) -> None:
        helper = r343.art_helper()
        helper_offset = r343.bank31_offset(r343.ART_HELPER_ADDR)
        self.assertEqual(
            self.candidate[helper_offset:helper_offset + len(helper)], helper
        )
        payload = b"".join(
            self.variants[tile] for tile in r343.FREE_TIP_TILES
        )
        payload_offset = r343.bank31_offset(r343.ART_PAYLOAD_ADDR)
        self.assertEqual(
            self.candidate[payload_offset:payload_offset + len(payload)],
            payload,
        )
        self.assertIn(
            bytes.fromhex("3E 16 E0 53 3E B0 E0 54"), helper
        )
        self.assertIn(
            bytes.fromhex("3E 17 E0 53 3E B0 E0 54"), helper
        )

    def test_r342_terminal_attr_repair_is_retained_before_art_upload(self) -> None:
        stream_start, r342_size, _ = r343._r342_cave_layout()
        cave_offset = r343.bank31_offset(r343.r342.CAVE_ADDR)
        cave = self.candidate[cave_offset:cave_offset + r342_size + 5]
        old_stream = r343.r342.terminal_repair_stream()
        expected = old_stream[:-3] + r343.admission_call() + old_stream[-3:]
        self.assertEqual(
            cave[stream_start:stream_start + len(expected)], expected
        )
        self.assertEqual(
            expected.count(
                r343.r342.PATCH_HELPER_ADDR.to_bytes(2, "little")
            ),
            8,
        )


if __name__ == "__main__":
    unittest.main()
