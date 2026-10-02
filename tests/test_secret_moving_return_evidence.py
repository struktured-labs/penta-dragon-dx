"""#26: distinguish a stalled route from a verified secret-area return."""
import csv
import hashlib
import json
import mmap
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MovingReturnEvidence(unittest.TestCase):
    def test_scroll_endpoint_death_is_damage_not_successful_return(self):
        traced = ROOT / 'tmp/secret-expiry-death-trace-01'
        control = ROOT / 'tmp/secret-expiry-death-control-01'
        if not (control / 'receipt.json').exists():
            self.skipTest('local endpoint death evidence unavailable')
        receipts = [json.loads((p / 'receipt.json').read_text()) for p in (traced, control)]
        self.assertEqual(receipts[0]['source_state_sha256'], receipts[1]['source_state_sha256'])
        for receipt in receipts:
            self.assertEqual(receipt['status'], 0)
            self.assertFalse(receipt['observer_memory_writes'])
            self.assertEqual(receipt['rom_sha256'],
                             '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306')
        for suffix in ('s16le', 'video', 'states', 'timeline.tsv'):
            paths = [Path(r['native_capture_directory']) / ('native.' + suffix) for r in receipts]
            self.assertEqual(hashlib.sha256(paths[0].read_bytes()).digest(),
                             hashlib.sha256(paths[1].read_bytes()).digest())
        writes = (traced / 'death-writes.tsv').read_text()
        self.assertIn('86\tDCBB\t1032\t01\t59\t27\t', writes)
        self.assertIn('86\tD880\t0087\t01\t0B\t00\t474AD85B', writes)
        self.assertIn('87\tD880\t4A52\t01\t00\t17\tD85B', writes)
        with (control / 'trace.tsv').open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual(len(rows), 180)
        self.assertTrue(all(r['stage'] == '07' for r in rows))

    def test_both_variants_remain_in_secret_area(self):
        cases = (
            ('secret-alias-chunk-moving-return-01',
             '2b797a6af30598141d874a8a272e9a7c77012044fe82f649f1b3e9142d31f306'),
            ('secret-fast-moving-return-control-01',
             '665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'),
        )
        for name, pin in cases:
            base = ROOT / 'tmp' / name
            if not (base / 'receipt.json').exists():
                self.skipTest('local moving-route evidence unavailable')
            receipt = json.loads((base / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 0)
            self.assertEqual(hashlib.sha256((base / 'candidate.gb').read_bytes()).hexdigest(), pin)
            with (base / 'trace.tsv').open() as stream:
                rows = list(csv.DictReader(stream, delimiter='\t'))
            self.assertEqual(len(rows), 2400)
            self.assertTrue(all(r['stage'] == '07' for r in rows))
            self.assertTrue(all((r['world_x'], r['world_y']) == ('104', '792')
                                for r in rows[239:]))
            # Use native states: item-action.tsv has an unflushed partial tail.
            path = Path(receipt['native_capture_directory']) / 'native.states'
            with path.open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as states:
                self.assertEqual(len(states), 2400 * 71680)
                for frame in range(239, 2400):
                    state = states[frame * 71680:(frame + 1) * 71680]
                    self.assertEqual(state[0x3ba], 7)
                    # Timer runs once per 60 frames; stationary is not frozen.
                    expected_timer = 59 - ((frame + 1 - 202) // 60)
                    self.assertEqual(state[0x60f1], expected_timer)

    def test_failed_restores_are_not_capture_passes(self):
        for name in ('secret-alias-chunk-moving-neutral-01',
                     'secret-alias-chunk-moving-left-01'):
            base = ROOT / 'tmp' / name
            if not (base / 'receipt.json').exists():
                self.skipTest('local failed-restore evidence unavailable')
            receipt = json.loads((base / 'receipt.json').read_text())
            self.assertEqual(receipt['status'], 74)
            self.assertNotIn('native_capture', receipt)
            self.assertEqual((base / 'trace.tsv').stat().st_size, 0)


if __name__ == '__main__':
    unittest.main()
