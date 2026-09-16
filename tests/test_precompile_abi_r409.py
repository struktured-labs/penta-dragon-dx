import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_precompile_abi_r409 as b

def execute(scene,stage,marker,tile):
    code=b.helper();pc=0;a=0;z=False;regs={'b':5,'c':0,'hl':0x9F00};ime=True
    def imm():
        nonlocal pc
        v=code[pc];pc+=1;return v
    for _ in range(40):
        op=imm()
        if op==0xF3:ime=False
        elif op==0xF0:a={0xE0:marker,0xBA:stage}[imm()]
        elif op==0xFA:a={0xD880:scene,0xC3DF:tile}[imm()+256*imm()]
        elif op==0xFE:z=a==imm()
        elif op==0xB7:z=a==0
        elif op==0xAF:a=0;z=True
        elif op==0x3E:a=imm()
        elif op==0x4F:regs['c']=a
        elif op==0x06:regs['b']=imm()
        elif op==0x21:regs['hl']=imm()+256*imm()
        elif op==0xE0:assert imm()==0xE0;marker=a
        elif op in (0x18,0x20):
            n=imm();n=n if n<128 else n-256
            if op==0x18 or not z:pc+=n
        elif op==0xC9:return z,marker,regs,ime,a
        else:raise AssertionError(hex(op))
    raise AssertionError('loop')
class AbiTests(unittest.TestCase):
    def test_all_markers_and_scene_stage_guards(self):
        for marker in range(256):
            for scene,stage in ((2,0),(2,4),(11,0)):
                z,m,r,ime,a=execute(scene,stage,marker,0x71)
                self.assertEqual(z,marker==3);self.assertFalse(ime);self.assertEqual(a,1)
                changed=marker==3 and scene==2 and stage==0
                self.assertEqual(m,0 if changed else marker)
                self.assertEqual(r,{'b':0xC6,'c':0x71,'hl':0xD300} if changed else {'b':5,'c':0,'hl':0x9F00})
        b.build(b.BASE.read_bytes())
if __name__=='__main__':unittest.main()
