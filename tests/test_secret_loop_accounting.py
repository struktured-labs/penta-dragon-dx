"""#26 keep every measured period and repeated-boundary interval visible."""
import hashlib
import csv
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SecretLoopAccounting(unittest.TestCase):
    def test_map_phase_partition_retains_every_period(self):
        order = ['loop', 'animation_end', 'de9_end', 'e7c_end',
                 'map_prepare', 'map_expand', 'map_copy', 'map_commit',
                 'map_return', 'service55bb', 'objects', 'service4f5d', 'tail']
        for name, control, count in (
                ('secret-stock-map-phases-01', 'secret-stock-startup-gated-off-01', 132),
                ('secret-fast-map-phases-01', 'secret-fast-gated-audio-01', 128)):
            base = ROOT / 'tmp' / name
            if not base.exists(): self.skipTest('local map phase trace unavailable')
            with self.subTest(run=name):
                receipt = json.loads((base/'receipt.json').read_text())
                self.assertEqual(hashlib.sha256((base/'probe.lua').read_bytes()).hexdigest(), receipt['probe_sha256'])
                with (base/'loop-work.tsv').open() as stream:
                    rows = list(csv.DictReader(stream, delimiter='\t'))
                indices = [i for i, row in enumerate(rows) if row['event'] == 'loop']
                self.assertEqual(len(indices)-1, count)
                for a, b in zip(indices, indices[1:]):
                    first = {}
                    for row in rows[a:b]:
                        first.setdefault(row['event'], int(row['cycle']))
                    self.assertEqual(list(first), order)
                    times = list(first.values()) + [int(rows[b]['cycle'])]
                    self.assertEqual(times, sorted(times))
                    self.assertEqual(sum(y-x for x,y in zip(times,times[1:])), times[-1]-times[0])
                for suffix in ('s16le', 'video', 'states', 'timeline.tsv', 'wav'):
                    hashes = []
                    for run in (name, control):
                        with (Path('/mnt/data/tmp')/f'penta-{run}-av'/f'native.{suffix}').open('rb') as stream:
                            hashes.append(hashlib.file_digest(stream, 'sha256').hexdigest())
                    self.assertEqual(*hashes)

    def test_complete_partition_and_source_bindings(self):
        path = ROOT / 'tmp/secret-loop-work-accounting-01.json'
        if not path.exists(): self.skipTest('local accounting evidence unavailable')
        result = json.loads(path.read_text())
        self.assertEqual(hashlib.sha256((ROOT/'tmp/analyze_secret_loop_work.py').read_bytes()).hexdigest(),
                         result['analyzer_sha256'])
        for report, count, repeated in zip(result['reports'], (132, 128), (1, 4)):
            with self.subTest(run=report['name']):
                for name, digest in report['source_hashes'].items():
                    self.assertEqual(hashlib.sha256((ROOT/'tmp'/report['name']/name).read_bytes()).hexdigest(), digest)
                self.assertEqual(report['complete_periods'], count)
                self.assertEqual(len(report['periods']), count)
                self.assertTrue(report['prefix'])
                self.assertTrue(report['suffix'])
                self.assertEqual(sum(len(p['all_events']) > 7 for p in report['periods']), repeated)
                for period in report['periods']:
                    self.assertEqual(period['cycles'], sum(period['segments'].values()))
                    self.assertEqual(period['cycles'], int(period['end']['cycle'])-int(period['begin']['cycle']))
                    self.assertGreaterEqual(min(period['segments'].values()), 0)
        first, second = result['reports']
        self.assertNotEqual([first['periods'][0]['object_entry'][f'slot{i}'] for i in range(5)],
                            [second['periods'][0]['object_entry'][f'slot{i}'] for i in range(5)])


if __name__ == '__main__': unittest.main()
