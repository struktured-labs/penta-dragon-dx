import sys
import unittest
import csv
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_menu_row_stack import check


class MenuRowStackTests(unittest.TestCase):
    def test_recorded_rows_and_corrupted_restore(self):
        path = Path(__file__).resolve().parents[1] / 'tmp/menu-fast-stack-01/menu-stack.tsv'
        if not path.exists():
            self.skipTest('local recorded trace unavailable')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '2a2081e26cdaabf33f5c7a8c56b17dfa533cac3da40485052c8b16099cbdebfe')
        with path.open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        result = check(rows)
        self.assertFalse(result['errors'])
        self.assertEqual(result['complete_rows'], 678)
        self.assertEqual(result['lowest_sp'], 0xDFC3)
        next(row for row in rows if row['event'] == 'exit')['sp'] = 'DFF0'
        self.assertIn('incorrect restored sp', check(rows)['errors'])

    def rows(self):
        return [dict(event='enter', sp='DFEB', bc='060A', de='C000', hl='9800', svbk='01'),
                dict(event='lowest', sp='DFBD', bc='0000', de='0000', hl='9813', svbk='01'),
                dict(event='exit', sp='DFEB', bc='060A', de='C014', hl='9814', svbk='01')]

    def test_balanced_row(self):
        self.assertFalse(check(self.rows())['errors'])

    def test_mutated_registers_fail(self):
        for reg in ('sp', 'bc', 'de', 'hl'):
            rows = self.rows()
            rows[-1][reg] = '0000'
            self.assertTrue(check(rows)['errors'], reg)

    def test_depth_bank_interrupt_and_truncation_fail(self):
        for key, value in (('sp', 'DFBF'), ('svbk', '06'), ('event', 'timer_inside')):
            rows = self.rows()
            rows[1][key] = value
            self.assertTrue(check(rows)['errors'])
        self.assertTrue(check(self.rows()[:-1])['errors'])
        self.assertTrue(check([])['errors'])
