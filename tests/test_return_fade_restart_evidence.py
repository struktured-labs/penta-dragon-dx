"""#18/#45: current fade candidate preserves complete restart sequences."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_gameover_restart import validate,validate_stage_cards
from gameover_sequence import validate_sequence


class FadeRestartEvidence(unittest.TestCase):
    def test_both_restart_routes_on_exact_candidate(self):
        for name,hazard in (('return-fade16-restart-sequence-01',True),
                            ('return-fade16-restart-natural-01',False)):
            base=ROOT/'tmp'/name
            if not (base/'receipt.json').exists():self.skipTest('local restart captures unavailable')
            r=json.loads((base/'receipt.json').read_text())
            rom=base/'runtime/candidate.gb'
            self.assertEqual(hashlib.sha256(rom.read_bytes()).hexdigest(),
                             '126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
            self.assertEqual(r['status'],'pass')
            self.assertEqual(r['hazard_death'],hazard)
            for filename,digest in r['artifacts'].items():
                self.assertEqual(hashlib.sha256((base/filename).read_bytes()).hexdigest(),digest)
            validate(base)
            if hazard:validate_stage_cards(base,True)
            self.assertEqual(validate_sequence(base),dict(title_frame_pairs=482,gameover_frames=102))


if __name__=='__main__':unittest.main()
