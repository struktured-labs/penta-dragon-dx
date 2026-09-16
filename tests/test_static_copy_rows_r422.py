import unittest
from unittest.mock import patch
import test_staged_tile_gdma_r399 as machine
import build_static_copy_rows_r422 as b

class StaticRows(unittest.TestCase):
    def test_emitted_equivalence(self):
        for page in (0x98,0x9C):
            for args in ({'speed':0,'ly':50}, {'speed':0,'ly':145},
                         {'speed':128}, {'speed':0,'stage':4},
                         {'speed':0,'scene':11}, {'speed':0,'lcd':0}):
                with patch.object(machine.b,'service',b.service):
                    old=machine.execute(page,**args)
                with patch.object(machine.b,'service',lambda:b.service(static_rows=True)):
                    new=machine.execute(page,**args)
                self.assertEqual(new,old)

    def test_edit_scope(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertTrue(all(x==y or i in (0x14D,0x14E,0x14F)
                            or b.OFFSET<=i<b.OFFSET+len(b.service())
                            for i,(x,y) in enumerate(zip(source,rom))))
        self.assertEqual(source[0x42A5:0x42A9],bytes.fromhex('26 98 2E 00'))
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
