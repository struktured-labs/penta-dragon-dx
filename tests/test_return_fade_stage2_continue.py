"""#28 current fade candidate: A accepts, neutral/Start time out."""
from pathlib import Path
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_continue_input import verify
from verify_pickup_class_palettes import serialized_state


class FadeStage2Continue(unittest.TestCase):
    def test_current_controls_and_known_broken_build(self):
        for button in ('a','neutral','start'):
            p=ROOT/'tmp'/f'return-fade16-stage2-continue-{button}-01'
            if not (p/'receipt.json').exists():self.skipTest('local Continue evidence unavailable')
            rom=(p/'candidate.gb').read_bytes();s=serialized_state(p/'entry.ss0')
            self.assertEqual(int.from_bytes(s[4:8],'little'),zlib.crc32(rom)&0xffffffff)
            self.assertEqual(s[16:32],rom[0x134:0x144])
            self.assertEqual((s[0x5c80],s[0x3ba]),(3,1))
            r=verify(p)
            self.assertEqual(r['rom_sha256'],'126dd0b7fff1e03eb6b224f818b85398593c7109ffb676cc538c1bd90742304b')
            self.assertTrue(r['passed']);self.assertEqual(r['frames'],6000)
            self.assertEqual(r['death_frame'],2352)
            self.assertEqual(r['resumed_frame'],2470 if button=='a' else None)
            self.assertEqual(r['title_frame'],None if button=='a' else 3314)
            self.assertEqual(r['native_a_edge'],button=='a')
        broken=ROOT/'tmp/reported-stage2-continue-up-a-01'
        if (broken/'receipt.json').exists():self.assertFalse(verify(broken)['passed'])


if __name__=='__main__':unittest.main()
