import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage1_bulk_compile_r425 as b

def execute(stage,scene,*,banked_scene=None):
    code=b.service();pc=0;sp=0xDFE0
    a,c,h,l,de,z=24,24,0xD0,0,0xC1A0,False
    mem=bytearray((i*37+i//7)&255 for i in range(65536))
    mem[sp:sp+4]=bytes.fromhex('4D 08 0E 43')
    before=bytes(mem)
    def imm():
        nonlocal pc
        value=code[pc];pc+=1;return value
    for _ in range(5000):
        op=imm()
        if op==0x00:pass
        elif op==0xF0:
            address=imm();assert address in (0xBA,0xB7)
            a=stage if address==0xBA else scene
        elif op==0xFA:
            assert imm()+256*imm()==0xD880
            a=scene if banked_scene is None else banked_scene
        elif op==0xB7:z=a==0
        elif op==0xFE:z=a==imm()
        elif op==0xC2:
            dest=imm()+256*imm()
            if not z:pc=dest-0x6D00
        elif op==0x1A:a=mem[de]
        elif op==0x13:de+=1
        elif op==0x1C:
            assert de&255!=255;de+=1;z=(de&255)==0
        elif op==0x4F:c=a
        elif op==0x0A:a=mem[0xC600+c]
        elif op==0x22:
            address=h*256+l;mem[address]=a;h,l=divmod(address+1,256)
        elif op==0x2E:l=imm()
        elif op==0x24:h+=1;z=h==0
        elif op==0xE5:
            sp-=2;mem[sp:sp+2]=bytes((l,h))
        elif op==0xF8:h,l=divmod(sp+imm(),256)
        elif op==0x36:mem[h*256+l]=imm()
        elif op==0x23:h,l=divmod(h*256+l+1,256)
        elif op==0xE1:l,h=mem[sp:sp+2];sp+=2
        elif op==0xAF:a=0;z=True
        elif op==0xE0:mem[0xFF00+imm()]=a
        elif op==0x3E:a=imm()
        elif op==0xC9:
            assert mem[sp:sp+2]==bytes.fromhex('4D 08');sp+=2
            return (a,c,h,l,de,z,sp),mem,before
        else:raise AssertionError(hex(op))
    raise AssertionError('unterminated')

class BulkCompile(unittest.TestCase):
    def test_exact_plane_padding_and_return_stack(self):
        regs,mem,before=execute(0,2);expected=bytearray(before)
        for row in range(24):
            for col in range(24):
                expected[0xD000+row*32+col]=before[0xC600+before[0xC1A0+row*24+col]]
        expected[0xDFDE:0xDFE0]=bytes.fromhex('00 D3')
        expected[0xDFE2:0xDFE4]=bytes.fromhex('24 43')
        expected[0xFFE0]=0
        self.assertEqual(mem,expected)
        self.assertEqual(regs,(1,before[0xC3DF],0xD3,0,0xC3E0,True,0xDFE2))

    def test_fallback_and_patch_scope(self):
        for stage,scene in ((0,11),(0,0),(1,2),(4,6),(6,8)):
            regs,mem,before=execute(stage,scene)
            self.assertEqual(mem,before)
            self.assertEqual(regs[:5],(1,24,0xD0,0,0xC1A0))
        source=b.BASE.read_bytes();rom=b.build(source)
        allowed={0x14D,0x14E,0x14F}|set(range(0x7ACBC,0x7ACBF))
        allowed.update(range(b.OFFSET,b.OFFSET+len(b.service())))
        self.assertTrue(all(x==y or i in allowed for i,(x,y) in enumerate(zip(source,rom))))
        with self.assertRaises(ValueError):b.build(rom)

if __name__=='__main__':unittest.main()
