"""#28 real retained replay controls; no claim of whole-game readiness."""
import hashlib
from pathlib import Path
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_continue_input import verify
from verify_pickup_class_palettes import serialized_state


class Stage2MovementContinue(unittest.TestCase):
    def test_current_input_controls_and_reported_broken_build(self):
        candidate='665a33b6b26d0a8ec1622a7c897d4fc10bdf7c8c5e0e5a2edaae98df0dafe0e7'
        cases=[('secret-sound-alias-fast-stage2-up-a-01',candidate,True,2352,2470,None),
               ('secret-alias-stage2-physical-continue-a-01',candidate,True,2352,2470,None),
               ('secret-alias-stage2-physical-continue-neutral-01',candidate,True,2352,None,3314),
               ('secret-sound-alias-fast-stage2-up-neutral-01',candidate,True,2352,None,3314),
               ('secret-sound-alias-fast-stage2-up-start-01',candidate,True,2352,None,3314),
               ('reported-stage2-continue-up-a-01',
                '4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5',False,1216,None,2125)]
        for name,pin,passed,death,resumed,title in cases:
            with self.subTest(name=name):
                base=ROOT/'tmp'/name
                if not (base/'verification.json').exists(): self.skipTest('local replay unavailable')
                rom=(base/'candidate.gb').read_bytes()
                self.assertEqual(hashlib.sha256(rom).hexdigest(),pin)
                state=serialized_state(base/'entry.ss0')
                self.assertEqual(int.from_bytes(state[4:8],'little'),zlib.crc32(rom)&0xffffffff)
                self.assertEqual(state[16:32],rom[0x134:0x144])
                result=verify(base)
                self.assertEqual((result['passed'],result['death_frame'],result['resumed_frame'],result['title_frame']),
                                 (passed,death,resumed,title))
                self.assertTrue(result['approach_up'])
                self.assertEqual(result['frames'],6000)
