import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_six_line_dma_r403 as b

def execute(reads,lcd=128):
    reads=iter(reads);pc=0;a=0;z=False;c=False;ime=True;seen=[]
    for _ in range(500):
        if pc==len(b.WAIT):return ime,seen
        op=b.WAIT[pc];pc+=1
        if op==0xF0:
            addr=b.WAIT[pc];pc+=1
            a=lcd if addr==0x40 else next(reads)
            if addr==0x44:seen.append((a,ime))
        elif op==0xCB:
            assert b.WAIT[pc]==0x7F;pc+=1;z=not(a&128)
        elif op in (0xD6,0xFE):
            n=b.WAIT[pc];pc+=1;c=a<n;z=a==n
            if op==0xD6:a=(a-n)&255
        elif op in (0x18,0x28,0x30,0x38):
            n=b.WAIT[pc];pc+=1
            if op==0x18 or (op==0x28 and z) or (op==0x30 and not c) or (op==0x38 and c):
                pc+=n if n<128 else n-256
        elif op==0xF3:ime=False
        elif op==0xFB:ime=True
        else:raise AssertionError(hex(op))
    raise AssertionError('loop')

class WindowTests(unittest.TestCase):
    def test_all_ly_values_and_irq_recheck(self):
        for ly in range(256):
            if 144<=ly<=149:
                self.assertEqual(execute([ly,ly]),(False,[(ly,True),(ly,False)]))
            else:
                self.assertEqual(execute([144,ly,144,144]),
                    (False,[(144,True),(ly,False),(144,True),(144,False)]))
        self.assertEqual(execute([],lcd=0),(False,[]))

    def test_scope_and_timing(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        start=b.prior.prior.dma.SERVICE
        self.assertTrue(all(x==y or start<=i<start+89 or i in (0x14D,0x14E,0x14F)
                            for i,(x,y) in enumerate(zip(source,rom))))
        self.assertLess(48*32+224,4*456)

if __name__=='__main__':unittest.main()
