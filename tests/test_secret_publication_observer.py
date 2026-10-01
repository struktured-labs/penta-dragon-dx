"""#23 retain failed observer controls; clean event values do not prove neutrality."""
import csv
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def rows(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter='\t'))


class SecretPublicationObserverTests(unittest.TestCase):
    def test_raw_domain_trial_does_not_observe_attribute_bank(self):
        path = ROOT/'tmp/title-local-secret-publication-01/secret-publication.tsv'
        if not path.exists():
            self.skipTest('retained invalid-domain trace unavailable')
        events = rows(path)
        self.assertEqual(len(events), 2190)
        self.assertEqual(sum(bytes.fromhex(r['attrs']) == b'\xff'*768 for r in events), 2080)
        # This is invalid observer output, never a verified game failure.

    def test_serializing_observer_changes_the_route(self):
        base = ROOT/'tmp/title-local-secret-menu-return-01'
        trial = ROOT/'tmp/title-local-secret-publication-02'
        if not all((p/'receipt.json').exists() for p in (base,trial)):
            self.skipTest('retained observer comparison unavailable')
        a, b = rows(base/'trace.tsv'), rows(trial/'trace.tsv')
        self.assertEqual(len(a), 10800)
        self.assertEqual(len(b), 10800)
        self.assertEqual(next(i+1 for i,(x,y) in enumerate(zip(a,b)) if x != y), 3116)
        def return_frame(trace):
            return next(int(r['frame']) for r in trace
                        if int(r['frame']) > 8000 and r['scene']=='02' and r['stage']=='00')
        self.assertEqual((return_frame(a),return_frame(b)), (8548,8463))
        shared = set(p.name for p in base.glob('frame-*.png')) & set(
            p.name for p in trial.glob('frame-*.png'))
        self.assertEqual(len(shared), 98)
        self.assertEqual(sum((base/f).read_bytes() != (trial/f).read_bytes() for f in shared), 65)
        # Keep the original trajectory divergence visible; do not align frames.
