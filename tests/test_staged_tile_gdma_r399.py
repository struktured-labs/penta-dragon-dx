from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_staged_tile_gdma_r399 as b


def execute(page,scene=2,stage=0,*,speed=0x80,ly=145,lcd=0x91):
    code=b.service();pc=0
    r=dict(a=0,b=0x73,c=0x29,d=0xFF,e=0,h=page,l=0)
    mem=bytearray((i*37+i//7)&255 for i in range(65536))
    before=bytes(mem);stack=[];z=False;carry=False;svbk=1;ime=False;stat=0;dma=0
    io={0x40:lcd,0x44:ly,0x4D:speed,0xBA:stage}
    def pair(x,y):return r[x]*256+r[y]
    def setpair(x,y,v):r[x],r[y]=(v>>8)&255,v&255
    def imm():
        nonlocal pc
        v=code[pc];pc+=1;return v
    for _ in range(20000):
        op=imm()
        if op==0xFA:
            addr=imm()+256*imm();assert addr==0xD880;r['a']=scene
        elif op==0xFE:
            v=imm();z=r['a']==v;carry=r['a']<v
        elif op in (0xC2,0xC3,0xCA):
            dest=imm()+256*imm()
            if op==0xC3 or (op==0xC2 and not z) or (op==0xCA and z):pc=dest-0x6C80
        elif op==0xF0:
            addr=imm()
            if addr==0x41:stat^=1;r['a']=3 if stat else 0
            else:r['a']=io.get(addr,0)
        elif op==0xF2:
            assert r['c']==0x41;stat^=1;r['a']=3 if stat else 0
        elif op==0xE0:
            addr=imm();io[addr]=r['a']
            if addr==0x70:svbk=r['a'];assert svbk!=3 or not ime
            if addr==0x55:
                assert svbk==3 and not ime and io[0x4F]==0 and r['a']==47
                source=io[0x51]*256+(io[0x52]&0xF0)
                dest=0x8000+(io[0x53]&31)*256+(io[0x54]&0xF0)
                mem[dest:dest+768]=mem[source:source+768];dma+=1
        elif op==0xF3:ime=False
        elif op==0xFB:assert svbk==1;ime=True
        elif op==0xC5:assert svbk==1;stack.append(pair('b','c'))
        elif op==0xF5:assert svbk==1;stack.append((r['a'],z,carry))
        elif op==0xF1:assert svbk==1;r['a'],z,carry=stack.pop()
        elif op==0xC1:assert svbk==1;setpair('b','c',stack.pop())
        elif op==0x4C:r['c']=r['h']
        elif op==0x51:r['d']=r['c']
        elif op in (0x11,0x21):
            v=imm()+256*imm();setpair(*(('d','e') if op==0x11 else ('h','l')),v)
        elif op in (0x06,0x0E,0x1E,0x2E,0x3E):r[{6:'b',14:'c',30:'e',46:'l',62:'a'}[op]]=imm()
        elif op==0x1A:r['a']=mem[pair('d','e')]
        elif op==0x22:
            addr=pair('h','l')
            if 0x8000<=addr<0xA000:assert not ime
            mem[addr]=r['a'];setpair('h','l',addr+1)
        elif op==0x13:setpair('d','e',pair('d','e')+1)
        elif op==0x1C:
            assert r['e']!=255,'INC E must never cross a source page'
            r['e']=(r['e']+1)&255;z=r['e']==0
        elif op in (0x24,0x14,0x3C):
            reg={0x24:'h',0x14:'d',0x3C:'a'}[op];r[reg]=(r[reg]+1)&255;z=r[reg]==0
        elif op==0x05:r['b']=(r['b']-1)&255;z=r['b']==0
        elif op==0x3D:r['a']=(r['a']-1)&255;z=r['a']==0
        elif op==0x0D:r['c']=(r['c']-1)&255;z=r['c']==0
        elif op in (0x7D,0x7B,0x79):r['a']=r[{0x7D:'l',0x7B:'e',0x79:'c'}[op]]
        elif op in (0x6F,0x5F,0x67):r[{0x6F:'l',0x5F:'e',0x67:'h'}[op]]=r['a']
        elif op==0xC6:
            v=r['a']+imm();carry=v>255;r['a']=v&255;z=r['a']==0
        elif op==0xE6:r['a']&=imm();z=r['a']==0;carry=False
        elif op==0xAF:r['a']=0;z=True;carry=False
        elif op==0xB7:z=r['a']==0;carry=False
        elif op==0x0F:
            carry=bool(r['a']&1);r['a']=(r['a']>>1)|(128 if carry else 0);z=False
        elif op==0xCB:assert imm()==0x7F;z=not(r['a']&128)
        elif op in (0x18,0x20,0x28,0x30,0x38):
            d=imm();d=d-256 if d>127 else d
            if {0x18:True,0x20:not z,0x28:z,0x30:not carry,0x38:carry}[op]:pc+=d
        elif op==0xC9:
            assert not stack and svbk==1
            return r,z,mem,before,dma
        else:raise AssertionError(hex(op))
    raise AssertionError('did not terminate')


class StagedTileTests(unittest.TestCase):
    def test_emitted_transfer_preserves_padding_and_caller_contract(self):
        for page in (0x98,0x9C):
            r,z,mem,old,dma=execute(page)
            expected=bytearray(old)
            for row in range(24):
                start=page*256+row*32
                expected[start:start+24]=old[0xC1A0+row*24:0xC1A0+(row+1)*24]
            self.assertEqual(mem[0x9800:0xA000],expected[0x9800:0xA000])
            self.assertEqual(mem[0xC1A0:0xC3E0],old[0xC1A0:0xC3E0])
            self.assertEqual((r['h'],r['l'],r['d'],r['e'],r['b'],r['c'],r['a'],z,dma),
                             (page+3,0,0xC3,0xE0,0x73,0,1,False,1))

    def test_nonstage1_has_no_memory_effect(self):
        for scene,stage in ((0,0),(2,4),(11,0)):
            r,z,mem,old,dma=execute(0x98,scene,stage)
            self.assertEqual(mem,old);self.assertTrue(z);self.assertEqual(dma,0)

    def test_exact_base_and_unmodified_clean_exit(self):
        source=b.BASE.read_bytes();rom=b.build(source)
        self.assertEqual(rom[0x13C0:0x13DE],source[0x13C0:0x13DE])
        self.assertEqual(rom[0x42C3:0x42C6],source[0x42C3:0x42C6])


if __name__=='__main__':unittest.main()
