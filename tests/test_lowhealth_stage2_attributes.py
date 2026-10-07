"""#59: reject trailing lake color and missing material on either physical map."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_lowhealth_stage2_attributes import assess


class LowHealthStage2Attributes(unittest.TestCase):
    def setUp(self):
        self.raw = bytearray(71680)
        self.raw[0x5C80], self.raw[0x3BA], self.raw[0x3B7] = 11, 1, 3
        for tile in (0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7):
            self.raw[0x4A00 + tile] = 2

    def test_clean_maps_and_water_material(self):
        for page in range(2):
            for col, tile in enumerate((0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7)):
                cell = page * 0x400 + col
                self.raw[0x1C00 + cell] = tile
                self.raw[0x3C00 + cell] = 2
        result = assess(self.raw)
        self.assertTrue(result['passed'])
        self.assertEqual(result['checked_cells'], 1152)

    def test_every_checked_cell_rejects_trailing_water_color(self):
        for page in range(2):
            for row in range(24):
                for col in range(24):
                    offset = 0x3C00 + page * 0x400 + row * 32 + col
                    self.raw[offset] = 2
                    with self.subTest(page=page, row=row, col=col):
                        with self.assertRaisesRegex(ValueError, 'stale/missing attribute'):
                            assess(self.raw)
                    self.raw[offset] = 0

    def test_missing_water_color_on_both_pages(self):
        for page in range(2):
            offset = 0x1C00 + page * 0x400 + 23 * 32 + 23
            self.raw[offset] = 0xAE
            with self.assertRaisesRegex(ValueError, 'stale/missing attribute'):
                assess(self.raw)
            self.raw[offset] = 0

    def test_wrong_scene_stage_or_native_identity_rejected(self):
        for offset in (0x5C80, 0x3BA, 0x3B7):
            old = self.raw[offset]
            self.raw[offset] = 0
            with self.assertRaisesRegex(ValueError, 'low-health Stage2 gameplay'):
                assess(self.raw)
            self.raw[offset] = old

    def test_wrong_material_policy_rejected_even_with_matching_maps(self):
        self.raw[0x4A00 + 0xAE] = 0
        with self.assertRaisesRegex(ValueError, 'material policy'):
            assess(self.raw)


if __name__ == '__main__':
    unittest.main()
