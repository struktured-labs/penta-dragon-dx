from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_source_reload_r395 as b
from test_source_row_reset_r389 import outer_target


def execute(code, new, old, advance):
    pc=0; a=0; bc=0xA0FF; hl=0xC1FF; equal=False; writes={}
    while pc < len(code):
        op=code[pc]; pc+=1
        if op==0x0A:
            a = new if bc == 0xA0FF else new ^ 255
        elif op==0xBE: equal = a == old
        elif op==0x28:
            delta=code[pc]; pc+=1
            if equal: pc+=delta
        elif op==0x3E: a=code[pc]; pc+=1
        elif op==0xEA:
            addr=int.from_bytes(code[pc:pc+2],'little'); pc+=2
            writes[addr]=a
        elif op in (0x22,0x77):
            writes[hl]=a
            if op==0x22: hl+=1
            if advance:
                assert code[pc]==0x03
                bc+=1
            return a,bc,hl,writes
        else: raise AssertionError(hex(op))
    raise AssertionError('missing store')


class ReloadTests(unittest.TestCase):
    def test_emitted_stores_keep_source_until_reload(self):
        source=b.BASE.read_bytes()
        code=b.clone(source[b.FALLBACK:b.FALLBACK+75])
        starts=[i for i in range(len(code)) if code[i:i+3]==bytes.fromhex('0A BE 28')]
        self.assertEqual(len(starts),4)
        for start,advance in zip(starts,(True,True,True,False)):
            for new in range(256):
                for old in (new,new^255,0,255):
                    expected={0xC1FF:new}
                    if new!=old: expected.update({0xDF53:255,0xDF57:255})
                    self.assertEqual(execute(code[start:],new,old,advance),
                                     (new,0xA0FF+advance,0xC1FF+advance,expected))

    def test_row_reset_and_patch_scope(self):
        source=b.BASE.read_bytes(); candidate=b.build(source)
        code,_,target=outer_target(candidate)
        self.assertEqual(code[target:target+3],bytes.fromhex('0E 0B C5'))
        changed={i for i,(x,y) in enumerate(zip(source,candidate)) if x!=y}
        self.assertTrue(changed <= set(range(b.CLONE,b.CLONE+256))|{0x14D,0x14E,0x14F})
        self.assertEqual(candidate[b.FALLBACK:b.FALLBACK+75],source[b.FALLBACK:b.FALLBACK+75])


if __name__=='__main__':
    unittest.main()
