"""#67 no missing/shifted/mutated primary stream may pass a repeat."""
import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
from check_shalamar_repeat import STREAMS, card_failures, differences


class RepeatContract(unittest.TestCase):
    def evidence(self):
        return dict(inputs={'rom': 'rom-a', 'state': 'state-a'},
                    recipe={'ENTRY_KEYS': '1'}, runtime={'core': 'core-a'},
                    adapter='adapter-a', native_bindings={'core': 'core-a'},
                    hashes={name: 'unshifted-'+name for name in STREAMS})

    def test_equal(self):
        self.assertEqual(differences(self.evidence(), self.evidence()), [])

    def test_every_stream_is_required_and_exact(self):
        for name in STREAMS:
            with self.subTest(name=name):
                a=self.evidence(); b=copy.deepcopy(a)
                b['hashes'][name]='shifted-or-changed'
                self.assertIn(name+' differs', differences(a,b))
                b['hashes'].pop(name)
                self.assertIn('missing or extra native streams', differences(a,b))

    def test_two_incomplete_reports_cannot_pass(self):
        a=self.evidence(); a['hashes'].pop('native.video')
        self.assertIn('missing or extra native streams', differences(a,a))

    def test_recipe_and_identity_mismatches(self):
        for key in ('inputs','recipe','runtime','adapter','native_bindings'):
            a=self.evidence(); b=copy.deepcopy(a); b[key]='different'
            self.assertIn(key+' differs', differences(a,b))

    def test_card_mutations_cannot_pass_repeat(self):
        clean=dict(complete=True, first_gameplay=2525, card_frames=164,
                   score_frames=376, card_dirty_frames=0,card_shadow_dirty_frames=0,
                   score_dirty_frames=0,score_shadow_dirty_frames=0,
                   attribute_captures=[dict(nonneutral_cells=[]) for _ in range(19)])
        self.assertEqual(card_failures(clean),[])
        for key,value in (('complete',False),('first_gameplay',None),
                          ('card_frames',0),('score_frames',0),
                          ('card_dirty_frames',1),('card_shadow_dirty_frames',1),
                          ('score_dirty_frames',1),('score_shadow_dirty_frames',1),
                          ('attribute_captures',[]),
                          ('attribute_captures',[dict(nonneutral_cells=[4])]*19)):
            with self.subTest(key=key):
                bad=copy.deepcopy(clean);bad[key]=value
                self.assertTrue(card_failures(bad))


if __name__ == '__main__':
    unittest.main()
