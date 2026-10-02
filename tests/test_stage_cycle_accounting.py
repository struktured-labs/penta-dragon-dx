"""#27 diagnostic accounting keeps every complete period and failed gate."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]/'tmp'


class CycleAccounting(unittest.TestCase):
    def test_object_workload_is_not_matched_between_roms(self):
        import csv
        observed = {}
        for name, expected_periods, expected_2a in (
                ('arena-stage1-object-trace-01', 421, 376),
                ('arena-parent-stage1-object-trace-01', 430, 0)):
            base = ROOT/name
            if not (base/'manifest.json').exists():
                self.skipTest('local object trace unavailable')
            manifest = json.loads((base/'manifest.json').read_text())
            self.assertEqual(manifest['status'], 'fail')
            self.assertTrue(manifest['rows'][0]['deterministic_replay'])
            with (base/'stage1-dx-a-loop-patrol/result.json.copies.tsv').open() as f:
                rows = list(csv.DictReader(f, delimiter='\t'))
            slots = {}
            for row in rows:
                if row['event'] == 'service-2222' and int(row['loop']) <= expected_periods:
                    slots[int(row['loop'])] = tuple(int(row['slot'+str(i)]) for i in range(5))
            self.assertEqual(set(slots), set(range(1, expected_periods+1)))
            self.assertEqual(sum(42 in values for values in slots.values()), expected_2a)
            observed[name] = slots
        self.assertNotEqual(list(observed.values())[0], list(observed.values())[1])
        parent = ROOT/'stream-presentation-source-01/candidate.gb'
        candidate = ROOT/'arena-completion-safe-trial-01/candidate.gb'
        if parent.exists() and candidate.exists():
            self.assertEqual(parent.read_bytes()[0x2222:0x27f4],
                             candidate.read_bytes()[0x2222:0x27f4])

    def test_full_periods_partition_without_hiding_slow_intervals(self):
        for name, hits in (('arena-stage1-tail-trace-01', 422),
                           ('arena-parent-stage1-tail-trace-01', 431)):
            with self.subTest(run=name):
                base = ROOT/name
                path = base/'stage1-dx-a-loop-patrol/cycle-analysis.json'
                if not path.exists():
                    self.skipTest('local cycle evidence unavailable')
                report = json.loads(path.read_text())
                manifest = json.loads((base/'manifest.json').read_text())
                self.assertEqual(manifest['status'], 'fail')
                self.assertTrue(manifest['rows'][0]['deterministic_replay'])
                self.assertEqual(report['loop_hits'], hits)
                self.assertEqual(len(report['periods']), hits-1)
                self.assertEqual(report['summary']['total'],
                                 sum(r['cycles'] for r in report['periods']))
                for row in report['periods']:
                    self.assertEqual(row['cycles'],
                                     row['pre_copy']+row['copy_cycles']+row['post_copy'])
                    self.assertEqual(row['cycles'],
                                     row['first_return']+row['return_span']+row['after_last_return'])
                    self.assertGreater(row['cycles'], 0)
                self.assertEqual(sum(report['summary']['frame_gaps'].values()), hits-1)
                self.assertEqual(report['compiled']['count']+report['no_compile']['count'], hits-1)
                before = ROOT/('arena-stage1-physical-assistance-01' if hits==422
                               else 'arena-completion-parent-stage1-speed-01')
                self.assertEqual((base/'stage1-dx-a-loop-patrol/attr-events.tsv').read_bytes(),
                                 (before/'stage1-dx-a-loop-patrol/attr-events.tsv').read_bytes())


if __name__ == '__main__':
    unittest.main()
