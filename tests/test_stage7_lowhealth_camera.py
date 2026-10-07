"""#66 geometry guard; does not substitute for live rendering tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from build_stage7_lowhealth_camera import viewport, build


class CameraGeometry(unittest.TestCase):
    def test_all_admitted_views_fit_compiled_region(self):
        for x in range(16):
            for y in range(16):
                self.assertTrue(all(row < 20 and column < 24 for row, column in viewport(x, y)))

    def test_union_includes_partial_edge_tiles(self):
        self.assertIn((19, 21), viewport(15, 15))
        self.assertEqual(len(viewport(0, 0)), 360)
        self.assertEqual(len(viewport(15, 15)), 399)

    def test_outside_domain_can_expose_uncompiled_row(self):
        self.assertTrue(any(row >= 20 for row, column in viewport(0, 17)))
        self.assertTrue(17 & 0xF0)

    def test_unknown_rom_rejected(self):
        with self.assertRaises(ValueError):
            build(bytes(1048576))


if __name__ == '__main__':
    unittest.main()
