import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from check_cram_timing import check


class CramTimingTests(unittest.TestCase):
    def row(self, mode=0, lcdc='80', cycle=1):
        return dict(mode=str(mode), lcdc=lcdc, cycle=str(cycle), port='FF6B')

    def test_safe_periods(self):
        self.assertEqual(check([self.row(m, cycle=m+1) for m in (0,1,2)])['status'],
                         'PASS_OBSERVED_WRITES')
        self.assertEqual(check([self.row(3, '00')])['status'], 'PASS_OBSERVED_WRITES')

    def test_blocked_write_is_not_hidden(self):
        rows = [self.row(cycle=1), self.row(3, cycle=2)]
        result = check(rows)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['blocked_writes'], [rows[1]])

    def test_missing_and_invalid_observations(self):
        for rows in ([], [self.row(4)], [self.row(), self.row()]):
            self.assertEqual(check(rows)['status'], 'FAIL')

    def test_retained_title_failures_remain_visible(self):
        for name in ('select02-cram-secret-return-01', 'handheld-palette-cram-return-01'):
            with self.subTest(name=name):
                path = ROOT/'tmp'/name/'cram-timing.tsv'
                if not path.exists():
                    self.skipTest('local timing evidence unavailable')
                with path.open() as stream:
                    result = check(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(result['writes'], 3784)
                self.assertEqual(len(result['blocked_writes']), 333)
                self.assertEqual({r['pc'] for r in result['blocked_writes']}, {'6A5C'})
