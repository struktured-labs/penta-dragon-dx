"""Issue #27: retain failed cost controls without promoting them as fixes."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'tmp'


class ArenaStage1CostEvidence(unittest.TestCase):
    def receipt(self, directory):
        path = ROOT / directory / 'manifest.json'
        if not path.exists():
            self.skipTest('local diagnostic artifact unavailable: ' + directory)
        return json.loads(path.read_text())

    def test_individual_reversions_do_not_recover_throughput(self):
        for site in ('dispatcher', 'copy-gate', 'semantic'):
            with self.subTest(site=site):
                directory = 'arena-' + site + '-cost-speed-01'
                receipt = self.receipt(directory)
                row = receipt['rows'][0]
                self.assertEqual(receipt['status'], 'fail')
                self.assertFalse(row['route_coverage_ok'])
                self.assertTrue(row['deterministic_replay'])
                self.assertEqual(row['original']['main_loop_hits'], 429)
                self.assertEqual(row['dx']['main_loop_hits'], 422)
                for repeat in ('a', 'b'):
                    trace = ROOT / directory / ('stage1-dx-' + repeat + '-loop-patrol') / 'attr-events.tsv'
                    self.assertEqual(hashlib.sha256(trace.read_bytes()).hexdigest(),
                        'e3856e06147114efd5608ab387cc115166c5a3dac43ad5a650b4db3160fb7db7')

    def test_trace_excludes_resolver_from_measured_hot_path(self):
        receipt = self.receipt('arena-completion-stage1-path-trace-01')
        row = receipt['rows'][0]
        self.assertEqual(receipt['status'], 'fail')
        self.assertTrue(row['deterministic_replay'])
        self.assertEqual(row['dx']['trace_addr_hits'], {
            '0xDABB': 0, '0xDB80': 0, '0xDBA6': 0,
            '0xDBDF': 0, '0xDBDC': 235})
        self.assertEqual(row['dx']['main_loop_hits'], 422)

    def test_detector_misses_are_other_banks_not_alias_work(self):
        receipt = self.receipt('arena-detector-bank-trace-01')
        row = receipt['rows'][0]
        self.assertTrue(row['deterministic_replay'])
        counts = row['dx']['trace_addr_bank_shadow_hits']
        self.assertEqual(counts['0x6F90/FF99=0D'], 1610)
        self.assertEqual(counts.get('0x6F98/FF99=0D', 0), 0)
        self.assertEqual(counts.get('0x6F9F/FF99=0D', 0), 0)
        # Ungrouped address counts would falsely claim 470 detector misses.
        self.assertEqual(row['dx']['trace_addr_hits']['0x6F98'], 470)
        for address, total in row['dx']['trace_addr_hits'].items():
            self.assertEqual(sum(value for key, value in counts.items()
                                 if key.startswith(address + '/')), total)
        self.assertEqual(receipt['status'], 'fail')
        self.assertEqual(row['dx']['main_loop_hits'], 422)
        before = ROOT / 'arena-detector-path-trace-01/stage1-dx-a-loop-patrol/attr-events.tsv'
        after = ROOT / 'arena-detector-bank-trace-01/stage1-dx-a-loop-patrol/attr-events.tsv'
        self.assertEqual(before.read_bytes(), after.read_bytes())


if __name__ == '__main__':
    unittest.main()
