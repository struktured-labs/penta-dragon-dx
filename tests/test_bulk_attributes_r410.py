import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_bulk_attributes_r410 as b

class BulkTests(unittest.TestCase):
    def test_full_emitted_plane_and_exact_scope(self):
        code=b.bulk();mem=bytearray((i*37+i//13)&255 for i in range(65536));old=bytes(mem)
        pc=0;a=0;c=0;de=0xC1A0;hl=0xD000;carry=False
        while pc<len(code):
            op=code[pc];pc+=1
            if op==0x1A:a=mem[de]
            elif op==0x13:de+=1
            elif op==0x1C:
                self.assertNotEqual(de&255,255);de+=1
            elif op==0x4F:c=a
            elif op==0x0A:a=mem[0xC600+c]
            elif op==0x22:mem[hl]=a;hl+=1
            elif op==0x7D:a=hl&255
            elif op==0xC6:v=a+code[pc];pc+=1;carry=v>255;a=v&255
            elif op==0x6F:hl=(hl&0xFF00)|a
            elif op==0x30:
                n=code[pc];pc+=1
                if not carry:pc+=n
            elif op==0x24:hl+=256
            elif op==0x3E:a=code[pc];pc+=1
            elif op==0xC9:break
            else:self.fail(hex(op))
        expected=bytearray(old)
        for row in range(24):
            for col in range(24):expected[0xD000+32*row+col]=old[0xC600+old[0xC1A0+24*row+col]]
        self.assertEqual(mem,expected);self.assertEqual((de,hl,a),(0xC3E0,0xD300,26))
        source=b.BASE.read_bytes();rom=b.build(source)
        allowed={0x14D,0x14E,0x14F}
        allowed.update(range(b.OFFSET,b.OFFSET+len(code)))
        allowed.update(range(b.prior.prior.OFFSET,b.prior.prior.OFFSET+len(b.prior.prior.helper())))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))

if __name__=='__main__':unittest.main()
