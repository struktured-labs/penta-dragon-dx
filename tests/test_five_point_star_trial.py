"""#22 source-contract checks; live emulator rendering remains required."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('star_trial', ROOT/'scripts/diagnostics/build_five_point_star_trial.py')
star = importlib.util.module_from_spec(spec)
spec.loader.exec_module(star)


class StarTrial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT/'tmp/ted-menu-reinstall-trial-01/candidate.gb'
        if not path.exists():
            raise unittest.SkipTest('exact experimental parent unavailable')
        cls.parent = path.read_bytes()
        cls.result = star.build(cls.parent)

    def test_only_declared_data_changes(self):
        allowed = {0x14E, 0x14F, *(0x37000+t for t in star.TILES)}
        for t in star.TILES:
            allowed.update(range(0x1F000+t*16, 0x1F010+t*16))
        changed = {i for i, (a, b) in enumerate(zip(self.parent, self.result)) if a != b}
        self.assertTrue(changed <= allowed)
        self.assertEqual(len(self.parent), len(self.result))
        self.assertEqual(int.from_bytes(self.result[0x14E:0x150], 'big'),
                         (sum(self.result[:0x14E])+sum(self.result[0x150:])) & 65535)

    def test_interior_only_and_outline_preserved(self):
        changed = 0
        for y in range(16):
            for x in range(16):
                t = star.TILES[y//8*2+x//8]
                off = 0x1F000+t*16+y%8*2
                def pixel(r):
                    return ((r[off] >> (7-x%8)) & 1) + 2*((r[off+1] >> (7-x%8)) & 1)
                before, after = pixel(self.parent), pixel(self.result)
                expected = 1 if before == 0 and 1 <= x < 15 and 1 <= y < 15 else before
                self.assertEqual(after, expected, (x, y))
                changed += before != after
        self.assertGreater(changed, 0)
        self.assertEqual([self.result[0x37000+t] for t in star.TILES], [5]*4)
        self.assertEqual([self.parent[0x37000+t] for t in star.TILES], [0]*4)

    def test_unknown_parent_rejected(self):
        altered = bytearray(self.parent)
        altered[0x1F820] ^= 1
        with self.assertRaises(ValueError):
            star.build(altered)


if __name__ == '__main__':
    unittest.main()
