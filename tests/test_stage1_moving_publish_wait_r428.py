import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage1_moving_publish_wait_r428 as b

class MovingPublish(unittest.TestCase):
    def test_wait_scope_and_irq_balance(self):
        for stage in range(7):
            for movement in (0,1,3,5,255):
                pc=0;a=0;z=False;ime=False;reads=0;code=b.TAIL
                for _ in range(100):
                    op=code[pc];pc+=1
                    if op==0xF0:
                        address=code[pc];pc+=1
                        if address==0xBA:a=stage
                        elif address==0xCE:a=movement
                        else:
                            self.assertEqual(address,0xC4);self.assertTrue(ime)
                            reads+=1;a=0xC4 if reads<3 else 0
                    elif op==0xB7:z=a==0
                    elif op==0xC0:
                        if not z:break
                    elif op==0xC8:
                        if z:break
                    elif op==0xFB:ime=True
                    elif op==0xF3:ime=False
                    elif op==0xCB:self.assertEqual(code[pc],0x77);pc+=1;z=not(a&0x40)
                    elif op==0x20:
                        offset=code[pc];pc+=1
                        if not z:pc+=offset-256
                    elif op==0xC9:break
                    else:self.fail(hex(op))
                else:self.fail('unterminated')
                self.assertFalse(ime)
                self.assertEqual(reads,3 if stage==0 and movement else 0)

    def test_patch_scope(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        allowed={0x14D,0x14E,0x14F}|set(range(b.PACK_OFFSET+len(b.PACK)-1,b.PACK_OFFSET+len(b.PACK)-1+len(b.TAIL)))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        self.assertEqual(rom[0x4284:0x4295],source[0x4284:0x4295])
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
