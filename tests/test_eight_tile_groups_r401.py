import unittest
from unittest.mock import patch
import test_staged_tile_gdma_r399 as machine
import build_eight_tile_groups_r401 as b


class EightTileTests(unittest.TestCase):
    def test_emitted_copy_and_register_contract(self):
        for page in (0x98,0x9C):
            for ly,lcd in ((145,0x91),(50,0x91),(0,0)):
                with patch.object(machine.b,'service',b.service):
                    r,z,mem,old,dma=machine.execute(page,ly=ly,lcd=lcd)
                expected=bytearray(old)
                for row in range(24):
                    start=page*256+row*32
                    expected[start:start+24]=old[0xC1A0+row*24:0xC1A0+(row+1)*24]
                self.assertEqual(mem,expected)
                self.assertEqual((r['h'],r['l'],r['d'],r['e'],r['b'],r['c'],r['a'],z,dma),
                                 (page+3,0,0xC3,0xE0,0x73,0,1,False,0))

    def test_guarded_fallback(self):
        for args in ({'scene':0},{'stage':1},{'speed':0}):
            with patch.object(machine.b,'service',b.service):
                _,z,mem,old,dma=machine.execute(0x98,**args)
            self.assertEqual(mem,old);self.assertTrue(z);self.assertEqual(dma,0)

    def test_write_group_timing_and_instruction_identity(self):
        code=b.service();group=bytes.fromhex('1A 13 22')*8
        self.assertEqual(code.count(group),1)
        start=code.index(group)
        self.assertEqual(code[start+len(group)],0xFB)
        # Conservative poll/branch cost64T plus eight24T transfers:128dots
        # in double speed, below Pan Docs'165dot mode0+mode2 lower bound.
        self.assertLess((64+8*24)/2,165)
        self.assertIn(bytes.fromhex('F0 4D CB 7F CA'),code)
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x42ED:0x4330],source[0x42ED:0x4330])


if __name__=='__main__':unittest.main()
