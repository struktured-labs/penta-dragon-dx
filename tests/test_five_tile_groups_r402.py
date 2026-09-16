import unittest
from unittest.mock import patch
import test_staged_tile_gdma_r399 as machine
import build_five_tile_groups_r402 as b


class FiveTileTests(unittest.TestCase):
    def test_profile_guard_addresses_are_instruction_boundaries(self):
        code = b.service()
        self.assertEqual(code[0x6C95 - 0x6C80:0x6C99 - 0x6C80],
                         bytes.fromhex('C5 11 A0 C1'))
        self.assertEqual(code[0x6D82 - 0x6C80:], bytes.fromhex('AF 3E 01 C9'))

    def test_full_emitted_copy_across_all_source_page_crossings(self):
        for page in (0x98,0x9C):
            for ly,lcd in ((145,0x91),(50,0x91),(0,0)):
                with patch.object(machine.b,'service',b.service):
                    r,z,mem,old,dma=machine.execute(page,speed=0,ly=ly,lcd=lcd)
                expected=bytearray(old)
                for row in range(24):
                    start=page*256+row*32
                    expected[start:start+24]=old[0xC1A0+row*24:0xC1A0+(row+1)*24]
                self.assertEqual(mem,expected)
                self.assertEqual((r['h'],r['l'],r['d'],r['e'],r['b'],r['c'],r['a'],z,dma),
                                 (page+3,0,0xC3,0xE0,0x73,0,1,False,0))

    def test_guard_and_bound(self):
        for args in ({'scene':0,'speed':0},{'stage':1,'speed':0},{'speed':128}):
            with patch.object(machine.b,'service',b.service):
                _,z,mem,old,_=machine.execute(0x98,**args)
            self.assertEqual(mem,old);self.assertTrue(z)
        # Worst group begins odd: three INC DE and two INC E.
        self.assertLess(5*16+3*8+2*4+28+16,165)
        code=b.service()
        self.assertEqual(code.count(bytes.fromhex('F2 E6 03 20')),5)
        b.build(b.BASE.read_bytes())


if __name__=='__main__':unittest.main()
