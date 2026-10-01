"""#14 retained emulator evidence; narrow doorway and floor-priority scope."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from verify_doorway_occlusion import verify
from build_sara_doorway_priority import helper

SHA = '8ff1c98d98f6949d39628c0c9fc86a53aae805f25cb8936484f2a00893af5c3c'


class LatestDoorwayTests(unittest.TestCase):
    def fixture(self, name):
        path = ROOT / 'tmp' / name
        if not path.exists():
            self.skipTest('local emulator evidence unavailable: ' + name)
        return path

    def test_exact_latest_occlusion_and_retained_broken_control(self):
        stock = self.fixture('ceiling-stock-doorway-03')
        latest = verify(stock, self.fixture('title-local-doorway-01'))
        self.assertEqual(latest['candidate']['bindings']['candidate.gb'], SHA)
        self.assertTrue(latest['passed'])
        self.assertEqual(latest['candidate']['nonblack'], 0)
        broken = verify(stock, self.fixture('ceiling-source07-negative-01'))
        self.assertFalse(broken['passed'])
        self.assertEqual(broken['candidate']['nonblack'], 192)

    def test_floor_priority_and_helper_survive_600_moving_frames(self):
        folder = self.fixture('title-local-floor-01')
        self.assertEqual(hashlib.sha256((folder / 'candidate.gb').read_bytes()).hexdigest(), SHA)
        with (folder / 'priority.tsv').open() as stream:
            rows = [r for r in csv.DictReader(stream, delimiter='\t') if int(r['frame']) > 1200]
        self.assertEqual([int(r['frame']) for r in rows], list(range(1201, 1801)))
        expected = helper(combined=True).hex().upper()
        for row in rows:
            self.assertFalse(any(int(row[f'a{i}'], 16) & 128 for i in range(4)), row['frame'])
            self.assertEqual(row['helper'][:len(expected)], expected, row['frame'])


if __name__ == '__main__':
    unittest.main()
