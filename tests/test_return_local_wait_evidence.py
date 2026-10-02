"""#45 local wait experiment did not fix the late handoff; retain rejection."""
import csv
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def rows(name):
    with (ROOT/'tmp'/name/'return-loader-timing.tsv').open() as f:
        return list(csv.DictReader(f,delimiter='\t'))


class LocalWaitEvidence(unittest.TestCase):
    def setUp(self):
        if not (ROOT/'tmp/return-card-local-wait-trace-01/receipt.json').exists():
            self.skipTest('local trial evidence unavailable')

    def test_restored_wait_entry_scanline_does_not_fix_completion(self):
        control = rows('return-card-wait-control-01')
        prior = rows('return-card-wait-trial-01')
        trial = rows('return-card-local-wait-trace-01')
        def first(data, pc, sp=None):
            return next(r for r in data if r['pc']==pc and (sp is None or r['sp']==sp))
        c = first(control,'4068','DFE7')
        p = first(prior,'4068','DFE5')
        t = first(trial,'63E6')
        self.assertEqual((c['ly'],p['ly'],t['ly']),('152','0','152'))
        self.assertEqual(int(t['cycle'])-int(c['cycle']),32)
        self.assertEqual(first(control,'0F33')['frame'],'189')
        self.assertEqual(first(trial,'5C22')['frame'],'190')
        # Locality removed the scanline wrap but the music request is unchanged.
        self.assertEqual(first(trial,'0038')['cycle'],first(prior,'0038')['cycle'])
        self.assertEqual(first(trial,'0038')['cycle'],'1161391592')

    def test_full_audio_failure_retained(self):
        p = ROOT/'tmp/return-local-wait-audio-pair-01/receipt.json'
        r = json.loads(p.read_text())
        for path, digest in r['identities'].items():
            with Path(path).open('rb') as f:
                self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),digest)
        self.assertEqual(r['status'],'fail')
        self.assertEqual(r['first_different_sample'],9803918)
        self.assertEqual(r['different_sample_frames'],3031848)


if __name__ == '__main__': unittest.main()
