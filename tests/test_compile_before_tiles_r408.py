import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_compile_before_tiles_r408 as b

def run(atomic=1,cached=0,room=1):
    code=b.helper();pc=0;r=dict(a=0,b=0x73,c=0x29,h=0x98,l=0,d=0,e=0)
    io={1:atomic,0xE0:cached,0xB7:2,0xE5:room,0x70:1}
    mem=bytearray((i*19+i//11)&255 for i in range(65536));old=bytes(mem)
    z=False;carry=False;ime=False;stack=[];calls=0
    def imm():
        nonlocal pc
        v=code[pc];pc+=1;return v
    for _ in range(1000):
        op=imm()
        if op==0xF0:r['a']=io[imm()]
        elif op==0xE0:io[imm()]=r['a']
        elif op==0xFA:assert imm()+256*imm()==0xD880;r['a']=2
        elif op==0xEA:mem[imm()+256*imm()]=r['a']
        elif op==0xFE:n=imm();z=r['a']==n
        elif op==0xE6:r['a']&=imm();z=r['a']==0
        elif op==0x3E:r['a']=imm()
        elif op==0x06:r['b']=imm()
        elif op==0x3D:r['a']=(r['a']-1)&255;z=r['a']==0
        elif op==0xF3:ime=False
        elif op in (0xC5,0xE5):
            assert io[0x70]==1;stack.append((r['b'],r['c']) if op==0xC5 else (r['h'],r['l']))
        elif op in (0xC1,0xE1):
            assert io[0x70]==1;x,y=('b','c') if op==0xC1 else ('h','l');r[x],r[y]=stack.pop()
        elif op in (0x11,0x21):
            lo,hi=imm(),imm();x,y=('d','e') if op==0x11 else ('h','l');r[x],r[y]=hi,lo
        elif op==0xCD:
            assert imm()+256*imm()==0xD400
            assert io[0x70]==3 and not ime;calls+=1
            for _ in range(24):
                source=256*r['d']+r['e'];dest=256*r['h']+r['l'];r['c']=mem[source]
                mem[dest]=mem[256*r['b']+r['c']]
                r['d'],r['e']=divmod(source+1,256);r['h'],r['l']=divmod(dest+1,256)
        elif op==0x7D:r['a']=r['l']
        elif op==0xC6:v=r['a']+imm();carry=v>255;r['a']=v&255
        elif op==0x6F:r['l']=r['a']
        elif op==0x24:r['h']+=1
        elif op in (0x20,0x28,0x30):
            delta=imm();delta=delta if delta<128 else delta-256
            if {0x20:not z,0x28:z,0x30:not carry}[op]:pc+=delta
        elif op in (0xC8,0xC9):
            if op==0xC9 or z:
                assert not stack and io[0x70]==1
                return r,io,mem,old,calls
        else:raise AssertionError(hex(op))
    raise AssertionError('loop')

class PrecompileTests(unittest.TestCase):
    def test_full_plane_padding_and_registers(self):
        for room in (1,5):
            r,io,mem,old,calls=run(room=room)
            expected=bytearray(old)
            for tile in (0x24,0x27,0x30,0x33):expected[0xC600+tile]=6 if room==1 else 0
            for row in range(24):
                for col in range(24):expected[0xD000+row*32+col]=expected[0xC600+old[0xC1A0+row*24+col]]
            self.assertEqual(mem,expected);self.assertEqual(calls,24)
            self.assertEqual((r['b'],r['c'],r['h'],r['l'],io[0xE0]),(0x73,0x29,0x98,0,3))
    def test_skip_and_exact_build(self):
        for args in ({'atomic':0},{'cached':3}):
            _,_,mem,old,calls=run(**args);self.assertEqual(mem,old);self.assertEqual(calls,0)
        b.build(b.BASE.read_bytes())

if __name__=='__main__':unittest.main()
