import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from check_secret_publication import check
from verify_pickup_class_palettes import serialized_state


class SecretPublicationTests(unittest.TestCase):
    def event(self):
        return dict(frame='1',cycle='100',lcdc='8B',menu='00',scene='09',stage='07',
                    tiles='00'*768,attrs='00'*768)

    def test_mutated_visible_attribute_fails(self):
        row = self.event()
        self.assertEqual(check([row])['status'],'PASS_OBSERVED_PUBLICATIONS')
        row['attrs'] = '00'*767+'01'
        result = check([row])
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['failures'][0]['differences'],[767])

    def test_empty_short_and_wrong_scene_fail(self):
        self.assertEqual(check([])['status'],'FAIL')
        for key,value in (('tiles','00'),('attrs','00'),('scene','02')):
            row = self.event();row[key]=value
            self.assertEqual(check([row])['status'],'FAIL')

    def test_retains_non_gameplay_observations_without_qualifying_them(self):
        row=self.event();row['menu']='01'
        result=check([row])
        self.assertEqual(result['events'],1)
        self.assertEqual(result['eligible_events'],0)
        self.assertEqual(result['status'],'FAIL')

    def test_retained_broken_control_and_candidate(self):
        for name,events,eligible,failures in (
            ('reported-secret-publication-03',2198,1731,1731),
            ('title-local-secret-publication-03',2190,1723,0),
            ('star-secret-publication-01',2190,1723,0)):
            with self.subTest(name=name):
                path=ROOT/'tmp'/name/'secret-publication.tsv'
                if not path.exists():self.skipTest('local publication trace unavailable')
                with path.open() as stream: result=check(csv.DictReader(stream,delimiter='\t'))
                self.assertEqual((result['events'],result['eligible_events'],len(result['failures'])),
                                 (events,eligible,failures))
                self.assertEqual(result['status'],'FAIL' if failures else 'PASS_OBSERVED_PUBLICATIONS')

    def test_direct_observer_preserves_retained_trace_images_and_states(self):
        base=ROOT/'tmp/title-local-secret-menu-return-01'
        observed=ROOT/'tmp/title-local-secret-publication-03'
        if not (observed/'receipt.json').exists():self.skipTest('local observer pair unavailable')
        self.assertEqual((base/'trace.tsv').read_bytes(),(observed/'trace.tsv').read_bytes())
        names={p.name for p in base.glob('frame-*.png')}
        self.assertEqual(len(names),103)
        self.assertEqual(names,{p.name for p in observed.glob('frame-*.png')})
        for name in names:
            self.assertEqual((base/name).read_bytes(),(observed/name).read_bytes())
            state=Path(name).with_suffix('.ss0')
            self.assertEqual(serialized_state(base/state),serialized_state(observed/state))
        # No native PCM was captured here: do not claim full audio neutrality.

    def test_star_candidate_observer_pair_and_cram_timing(self):
        import hashlib
        import json
        from check_cram_timing import check as check_cram
        base=ROOT/'tmp/star-secret-menu-return-01'
        observed=ROOT/'tmp/star-secret-publication-01'
        if not (observed/'receipt.json').exists():
            self.skipTest('local star candidate observer pair unavailable')
        for folder in (base, observed):
            self.assertEqual(hashlib.sha256((folder/'candidate.gb').read_bytes()).hexdigest(),
                             'd744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5')
            self.assertEqual(json.loads((folder/'receipt.json').read_text())['status'],0)
            with (folder/'cram-timing.tsv').open() as stream:
                result=check_cram(csv.DictReader(stream,delimiter='\t'))
            self.assertEqual(result['status'],'PASS_OBSERVED_WRITES')
            self.assertEqual(result['writes'],3760)
        self.assertEqual((base/'trace.tsv').read_bytes(),(observed/'trace.tsv').read_bytes())
        names={p.name for p in base.glob('frame-*.png')}
        self.assertEqual(len(names),103)
        self.assertEqual(names,{p.name for p in observed.glob('frame-*.png')})
        for name in names:
            self.assertEqual((base/name).read_bytes(),(observed/name).read_bytes())
            state=Path(name).with_suffix('.ss0')
            self.assertEqual(serialized_state(base/state),serialized_state(observed/state))
        # This compares saved frames/states and trace, not continuous PCM/video.
