import sys
from pathlib import Path
import unittest
import csv
import hashlib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_secret_dma_safety import check


class DmaSafetyTests(unittest.TestCase):
    def test_exact_row_yield_trace_and_candidate_selectors(self):
        from build_secret_combined_copy_trial import code
        root = Path(__file__).resolve().parents[1]
        folder = root / 'tmp/secret-row-yield-dma-safety-01'
        if not folder.exists():
            self.skipTest('local row-yield DMA evidence unavailable')
        rom = (folder / 'candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '886485509bc0fd33f6515b139e8ab78d5e4e0f940339b9120e22f42a0c3a9c05')
        body = code(6, True)
        self.assertEqual(rom[36*0x4000:36*0x4000+len(body)], body)
        selectors = {('24', f'{0x4000+i+4:04X}') for i in range(len(body))
                     if body[i:i+4] == bytes.fromhex('3e06e070')}
        self.assertEqual(len(selectors), 26)
        trace = folder / 'dma-safety.tsv'
        self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                         'e82ee32b03a4072a7cf5d166997bd1c19e4e825a7025a8936803e41fdcdaa7fa')
        with trace.open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        result = check(rows, selectors=selectors)
        self.assertFalse(result['errors'])
        self.assertEqual(result['dma_pairs'], 31824)
        self.assertEqual(result['interrupt_entries'], 14192)
        self.assertTrue(check(rows)['errors'])  # Old addresses must not qualify this ROM.

    def rows(self):
        base = dict(svbk='06', stat='C0', hdma5='FF', a='01', bank='24')
        return [dict(base, kind='before', pc='5B65', cycle='100'),
                dict(base, kind='after', pc='5B67', cycle='248'),
                dict(base, kind='irq', pc='0040', cycle='300', svbk='01')]

    def test_valid_observation(self):
        self.assertFalse(check(self.rows())['errors'])

    def test_rendering_dma_negative_control(self):
        rows = self.rows()
        rows[0]['stat'] = 'C3'
        self.assertTrue(check(rows)['errors'])

    def test_irq_on_scratch_negative_control(self):
        rows = self.rows()
        rows[2]['svbk'] = '06'
        self.assertTrue(check(rows)['errors'])

    def test_truncated_and_empty_fail(self):
        self.assertTrue(check(self.rows()[:1])['errors'])
        self.assertTrue(check([])['errors'])
