"""#45: preserve measured non-return fade timing regression, not acceptance."""
import csv
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SecretFadeTiming(unittest.TestCase):
    def test_exit_branch_bank_and_stack_ownership(self):
        p = ROOT/'tmp/secret-return-callers-02'
        if not (p/'secret-fade-timing.tsv').exists(): self.skipTest('return trace unavailable')
        with (p/'secret-fade-timing.tsv').open() as f:
            rows = {r['pc']: r for r in csv.DictReader(f, delimiter='\t')}
        self.assertEqual((rows['1482']['scene'], rows['1482']['stage']), ('09','07'))
        self.assertEqual((rows['1498']['bank'], rows['149B']['bank']), ('0D','01'))
        self.assertEqual(rows['149B']['stage'], '00')
        self.assertEqual(rows['149B']['sp'], 'DFED')
        self.assertEqual(rows['1473']['sp'], 'DFED')
        self.assertEqual(rows['75F0']['sp'], 'DFE9')
        self.assertEqual(rows['15DA']['sp'], 'DFEB')
        self.assertEqual((p/'trace.tsv').read_bytes(),
                         (ROOT/'tmp/secret-return-callers-01/trace.tsv').read_bytes())

    def test_native_fallback_changes_display_phase(self):
        records = []
        for name, control in (
            ('secret-fade-native-timing-01', 'initial-map-native-control-entry-01'),
            ('secret-fade-fastpath-timing-01', 'initial-map-fastpath-entry-01'),
        ):
            folder, prior = ROOT/'tmp'/name, ROOT/'tmp'/control
            if not (folder/'secret-fade-timing.tsv').exists():
                self.skipTest('local timing captures unavailable')
            with (folder/'secret-fade-timing.tsv').open() as f:
                records.append({r['pc']: r for r in csv.DictReader(f, delimiter='\t')})
            # Read-only observer does not change measured route or captured pictures.
            self.assertEqual((folder/'trace.tsv').read_text().splitlines(),
                             (prior/'trace.tsv').read_text().splitlines()[:2701])
            for pic in folder.glob('frame-*.png'):
                if (prior/pic.name).exists():
                    self.assertEqual(pic.read_bytes(), (prior/pic.name).read_bytes())
        parent, trial = records
        self.assertEqual(parent['75F0']['cycle'], trial['75F0']['cycle'])
        self.assertEqual(int(trial['0F33']['cycle'])-int(parent['0F33']['cycle']), 1880)
        self.assertEqual(int(parent['0F7A']['cycle'])-int(parent['15DA']['cycle']), 48)
        self.assertEqual(int(trial['0F7A']['cycle'])-int(trial['15DA']['cycle']), 1216)
        self.assertEqual((parent['15DD']['frame'],trial['15DD']['frame']), ('2652','2649'))
        for record in records:
            self.assertEqual(record['0F7A']['stage'], '07')
            self.assertEqual(record['0F7A']['scene'], '09')
            self.assertEqual(record['15DD']['sp'], 'DFEB')


if __name__ == '__main__': unittest.main()
