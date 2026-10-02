import unittest
from unittest.mock import patch
import test_staged_tile_gdma_r399 as machine
import build_six_tile_groups_r405 as b

class SixTileTests(unittest.TestCase):
    def test_identity_and_observer_addresses(self):
        from verify_stage1_spike_palettes import publication_boundary
        rom=b.build(b.BASE.read_bytes());code=b.service()
        self.assertEqual(publication_boundary(rom)['variant'],'r405-six-tiles-79e83ac5')
        self.assertEqual(code[0x6C9C-0x6C80],0xC5)
        self.assertEqual(code[0x7BF0-0x6C80:],bytes.fromhex('AF 3E 01 C9'))
        changed=bytearray(rom);changed[b.OFFSET+100]^=1
        with self.assertRaises(RuntimeError):publication_boundary(changed)

    def test_copy_and_crossings(self):
        for page in (0x98,0x9C):
            for ly in (50,145):
                with patch.object(machine.b,'service',b.service):
                    r,z,mem,old,dma=machine.execute(page,speed=0,ly=ly)
                expected=bytearray(old)
                for row in range(24):
                    start=page*256+row*32
                    expected[start:start+24]=old[0xC1A0+row*24:0xC1A0+(row+1)*24]
                self.assertEqual(mem,expected)
                self.assertEqual((r['h'],r['l'],r['d'],r['e'],r['b'],r['c'],r['a'],z,dma),
                                 (page+3,0,0xC3,0xE0,0x73,0,1,False,0))
    def test_fallback_scope_and_bound(self):
        for args in ({'scene':0,'speed':0},{'stage':1,'speed':0},{'speed':128},{'lcd':0,'speed':0}):
            with patch.object(machine.b,'service',b.service):
                _,z,mem,old,_=machine.execute(0x98,**args)
            self.assertEqual(mem,old);self.assertTrue(z)
        code=b.service()
        self.assertEqual(code.count(bytes.fromhex('1A 13 22')),2)
        self.assertEqual(code.count(bytes.fromhex('1A 1C 22')),574)
        self.assertLess(6*20+4+24+12,165)
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertTrue(all(x==y or b.OFFSET<=i<b.OFFSET+len(code) or i in (0x14D,0x14E,0x14F)
                            for i,(x,y) in enumerate(zip(source,rom))))

if __name__=='__main__':unittest.main()
