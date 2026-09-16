import unittest
from unittest.mock import patch
import test_staged_tile_gdma_r399 as machine
import build_private_stationary_copy_r417 as b

class PrivateCopyTests(unittest.TestCase):
    def test_memory_stack_and_pointer_contract(self):
        for page in (0x98,0x9C):
            for ly in (50,145):
                with patch.object(machine.b,'service',b.service):
                    r,z,mem,old,dma=machine.execute(page,speed=0,ly=ly)
                expected=bytearray(old)
                for row in range(24):
                    start=page*256+row*32
                    expected[start:start+24]=old[0xC1A0+row*24:0xC1A0+(row+1)*24]
                self.assertEqual(mem,expected)
                self.assertEqual((r['h'],r['l'],r['d'],r['e'],r['b'],r['c'],r['a'],dma),(page+3,0,0xC3,0xE0,0x73,0,1,0))
    def test_shared_copier_restored(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x42CF:0x42DB],bytes.fromhex('1A 13 22 1A 13 22 1A 13 22 1A 13 22'))
        self.assertEqual(rom[0x13C0:0x13DE],source[0x13C0:0x13DE])

if __name__=='__main__':unittest.main()
