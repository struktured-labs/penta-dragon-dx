import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage1_coordinate_wait_r427 as b

class CoordinateWait(unittest.TestCase):
    def test_emitted_wait_and_native_stores(self):
        for stage in (0,1,4,6):
            for pending in (0,0x48):
                code=b.CODE;pc=0;reads=0;z=False;a=0;mem={}
                regs={0x7D:0xF0,0x7C:0x04,0x7B:60,0x7A:0}
                for _ in range(100):
                    op=code[pc];pc+=1
                    if op==0xF0:
                        address=code[pc];pc+=1
                        if address==0xBA:a=stage
                        else:
                            self.assertEqual(address,0xC4);reads+=1
                            a=pending if reads<3 else 0
                    elif op==0xB7:z=a==0
                    elif op==0xCB:
                        self.assertEqual(code[pc],0x77);pc+=1;z=not(a&0x40)
                    elif op==0x20:
                        offset=code[pc];pc+=1
                        if not z:pc+=offset if offset<128 else offset-256
                    elif op in regs:a=regs[op]
                    elif op==0xEA:
                        address=code[pc]+256*code[pc+1];pc+=2;mem[address]=a
                        if stage==0 and pending:self.assertGreaterEqual(reads,3)
                    elif op==0x3E:a=code[pc];pc+=1
                    elif op==0xC9:break
                    else:self.fail(hex(op))
                else:self.fail('unterminated')
                self.assertEqual(mem,{0xDC02:0xF0,0xDC03:4,0xDC00:60,0xDC01:0})
                self.assertEqual(reads,(3 if pending else 1) if stage==0 else 0)
                self.assertEqual(a,1)

    def test_wrapper_and_scope(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(b.HOOK,bytes.fromhex('F5 3E 1D CD 47 08 F1 7A C9'))
        allowed={0x14D,0x14E,0x14F}|set(range(0x4284,0x4295))
        allowed.update(range(b.OFFSET,b.OFFSET+len(b.CODE)))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
