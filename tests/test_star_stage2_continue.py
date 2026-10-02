"""#28 exact combined-build Continue acceptance and timeout controls."""
from pathlib import Path
import sys
import unittest
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from verify_continue_input import verify
from verify_pickup_class_palettes import serialized_state

PIN='d744124d3d161247e0584bb39e8db1243ade4e428cbc15f82a85c10d0a4ac4d5'


class Stage2Continue(unittest.TestCase):
    def test_current_continue_and_timeout(self):
        for button in ('a','neutral','start'):
            with self.subTest(button=button):
                base=ROOT/f'tmp/star-source-stage2-continue-{button}-01'
                if not (base/'receipt.json').exists(): self.skipTest('local Continue evidence unavailable')
                rom=(base/'candidate.gb').read_bytes()
                raw=serialized_state(base/'entry.ss0')
                self.assertEqual(int.from_bytes(raw[4:8],'little'),zlib.crc32(rom)&0xffffffff)
                self.assertEqual(raw[16:32],rom[0x134:0x144])
                self.assertEqual((raw[0x5c80],raw[0x3ba]),(3,1))
                result=verify(base)
                self.assertEqual(result['rom_sha256'],PIN)
                self.assertTrue(result['passed'])
                self.assertEqual(result['death_frame'],1204)
                self.assertEqual(result['native_a_edge'],button=='a')
                self.assertEqual(result['resumed_frame'],1436 if button=='a' else None)
                self.assertEqual(result['title_frame'],None if button=='a' else 2120)

    def test_known_broken_stage2_control_rejected(self):
        base=ROOT/'tmp/source06-stage2-continue-negative-01'
        if not (base/'receipt.json').exists(): self.skipTest('retained broken control unavailable')
        result=verify(base)
        self.assertFalse(result['passed'])
        self.assertFalse(result['native_a_edge'])


if __name__=='__main__': unittest.main()
