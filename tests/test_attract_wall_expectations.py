from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
from verify_attract_pickup_palettes import room01_wall_expectations


class AttractWallExpectations(unittest.TestCase):
    def test_only_reviewed_wall_roles_override_the_lut(self):
        table = room01_wall_expectations()
        self.assertEqual(len(table), 256)
        self.assertEqual({tile: attr for tile, attr in enumerate(table) if attr != 255},
                         {0x24: 6, 0x25: 6, 0x26: 6, 0x27: 6,
                          0x30: 6, 0x33: 6, 0x35: 6, 0x36: 6})


if __name__ == '__main__':
    unittest.main()
