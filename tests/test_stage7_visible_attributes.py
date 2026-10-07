import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_stage7_visible_attributes import assess


class VisibleAttributes(unittest.TestCase):
    def setUp(self):
        self.raw = bytearray(71680)
        self.rom = bytearray(1048576)
        self.raw[0x5C80], self.raw[0x3B7], self.raw[0x3BA] = 11, 8, 6
        self.raw[0x340] = 0x83
        self.raw[0x4A01] = self.rom[0x5B601] = 3

    def test_valid_visible_map(self):
        self.assertTrue(assess(self.raw, self.rom)['passed'])

    def test_stale_color_fails(self):
        self.raw[0x3C00] = 4
        self.assertFalse(assess(self.raw, self.rom)['passed'])

    def test_missing_color_fails(self):
        self.raw[0x1C00] = 1
        self.assertFalse(assess(self.raw, self.rom)['passed'])
        self.raw[0x3C00] = 3
        self.assertTrue(assess(self.raw, self.rom)['passed'])

    def test_partial_edge_tile_checked(self):
        self.raw[0x343] = self.raw[0x342] = 15
        self.raw[0x3C00+19*32+21] = 4
        self.assertFalse(assess(self.raw, self.rom)['passed'])

    def test_window_rejected(self):
        self.raw[0x340] |= 0x20
        with self.assertRaises(ValueError):
            assess(self.raw, self.rom)


if __name__ == '__main__':
    unittest.main()
