"""#28 latest candidate: exact-ROM assisted Continue and timeout controls."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_continue_input import verify
from verify_pickup_class_palettes import serialized_state


class LateReturnContinue(unittest.TestCase):
    def test_a_accepts_and_neutral_start_time_out(self):
        for button in ('a','neutral','start'):
            with self.subTest(button=button):
                folder=ROOT/'tmp'/f'late-return-stage2-continue-{button}-01'
                rom=(folder/'candidate.gb').read_bytes()
                state=serialized_state(folder/'entry.ss0')
                self.assertEqual(hashlib.sha256(rom).hexdigest(),
                                 '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
                self.assertEqual(int.from_bytes(state[4:8],'little'),zlib.crc32(rom))
                self.assertEqual(state[16:32],rom[0x134:0x144])
                self.assertEqual((state[0x5C80],state[0x3BA]),(3,1))
                result=verify(folder)
                self.assertTrue(result['passed'])
                self.assertEqual(result['frames'],6000)
                self.assertEqual(result['death_frame'],2352)
                self.assertEqual(result['input_start_frame'],2414)
                self.assertEqual(result['resumed_frame'],2470 if button=='a' else None)
                self.assertEqual(result['title_frame'],None if button=='a' else 3314)
                self.assertEqual(result['native_a_edge'],button=='a')
                self.assertEqual(result,json.loads((folder/'verification.json').read_text()))

    def test_reported_broken_candidate_still_fails(self):
        self.assertFalse(verify(ROOT/'tmp/reported-stage2-continue-up-a-01')['passed'])


if __name__=='__main__':
    unittest.main()
