"""#59: visible palette oracle must catch trailing water, including map wrap."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_stage2_scrolling import assess, WATER


class Stage2Scrolling(unittest.TestCase):
    def setUp(self):
        self.raw = bytearray(71680)
        self.raw[0x5C80], self.raw[0x3BA], self.raw[0x3B7] = 11, 1, 3
        self.raw[0x340] = 0x80
        for tile in WATER:
            self.raw[0x4A00 + tile] = 2

    def test_aligned_and_wrapped_viewport_extent(self):
        self.assertEqual(assess(self.raw)['checked_cells'], 360)
        self.raw[0x342] = self.raw[0x343] = 255
        self.assertEqual(assess(self.raw)['checked_cells'], 399)

    def test_every_visible_cell_catches_trailing_lake_on_both_maps(self):
        for page in (0, 0x400):
            self.raw[0x340] = 0x88 if page else 0x80
            for y in range(18):
                for x in range(20):
                    offset = 0x3C00 + page + y * 32 + x
                    self.raw[offset] = 2
                    self.assertFalse(assess(self.raw)['passed'])
                    self.raw[offset] = 0

    def test_wrapped_edge_rejects_missing_water(self):
        self.raw[0x342] = self.raw[0x343] = 255
        for page in (0, 0x400):
            self.raw[0x340] = 0x88 if page else 0x80
            cell = page + 31 * 32 + 31
            self.raw[0x1C00 + cell] = WATER[0]
            self.assertFalse(assess(self.raw)['passed'])
            self.raw[0x3C00 + cell] = 2
            self.assertTrue(assess(self.raw)['passed'])

    def test_palette_scope_does_not_reinterpret_priority_as_color(self):
        self.raw[0x3C00] = 0x80
        self.assertTrue(assess(self.raw)['passed'])

    def test_lcd_off_window_wrong_scene_and_policy_fail_closed(self):
        for offset, value in ((0x340, 0), (0x340, 0xA0), (0x5C80, 0),
                              (0x3BA, 0), (0x4A00 + WATER[0], 0)):
            with self.subTest(offset=offset, value=value):
                raw = self.raw.copy()
                raw[offset] = value
                with self.assertRaises(ValueError):
                    assess(raw)


if __name__ == '__main__':
    unittest.main()
