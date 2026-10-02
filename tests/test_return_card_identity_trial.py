"""#45 identity rewrite experiment is not a timing/audio fix."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_return_card_identity_trial import build


class CardIdentityTrial(unittest.TestCase):
    def test_patch_is_one_call_target_and_checksum(self):
        path=ROOT/'tmp/return-cgb-fade-trial-10/candidate.gb'
        if not path.exists():self.skipTest('parent unavailable')
        parent=path.read_bytes()
        trial,site,target=build(parent)
        self.assertEqual((site,target),(0x516c3,0x5682))
        self.assertEqual(hashlib.sha256(trial).hexdigest(),'ab899c87ac3dda6d56dbc19ced52a9830ea6ed051e1c20990396465c02482c51')
        self.assertTrue(all(i in {site+1,site+2,0x14e,0x14f} for i,(a,b) in enumerate(zip(parent,trial)) if a!=b))
        with self.assertRaises(ValueError):build(trial)

    def test_no_telemetry_or_silence_improvement(self):
        paths=[ROOT/'tmp'/f'return-cgb-fade-exit-{n}'/'trace.tsv' for n in ('10','11')]
        if not all(p.exists() for p in paths):self.skipTest('local replay unavailable')
        self.assertEqual(paths[0].read_bytes(),paths[1].read_bytes())
        for n in ('10','11'):
            p=ROOT/'tmp'/f'return-cgb-fade-audio-pair-{n}'/'receipt.json'
            r=json.loads(p.read_text())
            self.assertEqual(r['status'],'fail')
            self.assertIn([10486614,10538418],r['candidate']['digital_silence_at_least_20ms'])


if __name__=='__main__':unittest.main()
