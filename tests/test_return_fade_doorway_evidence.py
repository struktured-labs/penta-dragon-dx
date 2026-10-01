"""#14 current replay evidence: failed alignment is not occlusion acceptance."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_sara_doorway_priority import helper
from verify_doorway_occlusion import verify
from verify_pickup_class_palettes import serialized_state


class DoorwayEvidence(unittest.TestCase):
    def folder(self, name):
        p = ROOT / 'tmp' / name
        if not (p / 'receipt.json').exists():
            self.skipTest('local capture unavailable: ' + name)
        return p

    def test_current_replay_is_not_position_matched(self):
        current = self.folder('return-fade16-doorway-01')
        parent = self.folder('return-fade16-doorway-parent-01')
        self.assertEqual(hashlib.sha256((current / 'candidate.gb').read_bytes()).hexdigest(),
                         '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
        self.assertEqual(hashlib.sha256((parent / 'candidate.gb').read_bytes()).hexdigest(),
                         '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7')
        for folder, y in ((current, 1352), (parent, 1356)):
            state = serialized_state(folder / 'frame-1216.ss0')
            self.assertEqual(int.from_bytes(state[0x6002:0x6004], 'little'), y)
        stock = ROOT / 'tmp/ceiling-stock-doorway-03'
        self.assertTrue(verify(stock, parent)['passed'])
        with self.assertRaisesRegex(ValueError, 'position/scene'):
            verify(stock, current)

    def test_floor_control(self):
        p = self.folder('return-fade16-floor-01')
        with (p / 'priority.tsv').open() as stream:
            rows = [r for r in csv.DictReader(stream, delimiter='\t') if int(r['frame']) > 1200]
        self.assertEqual([int(r['frame']) for r in rows], list(range(1201, 1801)))
        expected = helper(combined=True).hex().upper()
        for row in rows:
            self.assertFalse(any(int(row[f'a{i}'], 16) & 128 for i in range(4)))
            self.assertTrue(row['helper'].startswith(expected))


if __name__ == '__main__':
    unittest.main()
