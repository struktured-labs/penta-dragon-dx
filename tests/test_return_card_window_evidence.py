"""Issue #45: retained exact-ROM window trace and observer neutrality."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReturnCardWindowEvidence(unittest.TestCase):
    def test_window_trace_is_neutral_and_final_card_wait_is_retained(self):
        trace = ROOT / 'tmp/return-card-window-trial-10'
        control = ROOT / 'tmp/return-fade-sound-trial-control-10'
        if not (trace / 'receipt.json').exists():
            self.skipTest('local trace unavailable')
        receipts = [json.loads((p / 'receipt.json').read_text()) for p in (trace, control)]
        self.assertEqual(receipts[0]['rom_sha256'], receipts[1]['rom_sha256'])
        self.assertEqual(receipts[0]['source_state_sha256'], receipts[1]['source_state_sha256'])
        for receipt in receipts:
            base = Path(receipt['native_capture_directory'])
            for name, expected in receipt['native_capture']['hashes'].items():
                self.assertEqual(hashlib.sha256((base / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(receipts[0]['native_capture']['hashes'], receipts[1]['native_capture']['hashes'])
        self.assertEqual((trace / 'inputs.tsv').read_bytes(), (control / 'inputs.tsv').read_bytes())
        intervals = []
        first = None
        with (trace / 'menu-critical.tsv').open() as stream:
            for row in csv.DictReader(stream, delimiter='\t'):
                if row['event'] == 'pair_before' and first is None:
                    first = row
                elif row['event'] == 'pair_after':
                    self.assertIsNotNone(first)
                    intervals.append((int(first['frame']), int(row['frame']),
                                      int(first['ly'], 16), int(row['ly'], 16),
                                      int(row['cycle']) - int(first['cycle'])))
                    first = None
        self.assertIsNone(first)
        self.assertEqual(len(intervals), 9)
        self.assertEqual(intervals[4], (100, 101, 2, 144, 129560))


if __name__ == '__main__':
    unittest.main()
