"""#34 synthetic loss/sticky/duplicate/missing mutations must be rejected."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_select_delivery import assess


class SelectDeliveryTests(unittest.TestCase):
    def rows(self):
        rows = [dict(frame=str(f), address='FF93', value='04' if f == 721 else '00')
                for f in range(720, 734)]
        rows += [dict(frame='722', address='FF94', value='04', raw='00', held='00')]
        return sorted(rows, key=lambda r: int(r['frame']))

    def test_post_release_delivery(self):
        result = assess(self.rows(), 721, 1)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['post_release_frames'], [722])

    def test_lost_press(self):
        rows = self.rows()
        next(r for r in rows if r['address'] == 'FF94')['value'] = '00'
        self.assertEqual(assess(rows, 721, 1)['status'], 'FAIL')

    def test_duplicate_delivery(self):
        rows = self.rows()
        rows.append(dict(frame='727', address='FF94', value='04', raw='00', held='00'))
        self.assertEqual(assess(rows, 721, 1)['status'], 'FAIL')

    def test_sticky_input(self):
        for field in ('raw', 'held'):
            rows = self.rows()
            next(r for r in rows if r['address'] == 'FF94')[field] = '04'
            self.assertEqual(assess(rows, 721, 1)['status'], 'FAIL')

    def test_missing_or_reordered_raw(self):
        rows = self.rows()
        self.assertEqual(assess(rows[1:], 721, 1)['status'], 'FAIL')
        self.assertEqual(assess(list(reversed(rows)), 721, 1)['status'], 'FAIL')

    def test_lengthened_input_is_not_accepted(self):
        rows = self.rows()
        next(r for r in rows if r['address'] == 'FF93' and r['frame'] == '722')['value'] = '04'
        self.assertEqual(assess(rows, 721, 1)['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
