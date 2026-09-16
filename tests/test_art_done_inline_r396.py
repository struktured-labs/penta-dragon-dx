from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_art_done_inline_r396 as b


def calls(code, art, enabled):
    pc=0; a=0; z=False; called=False
    while pc<len(code):
        op=code[pc];pc+=1
        if op==0xFA:
            address=int.from_bytes(code[pc:pc+2],'little');pc+=2
            a={0xDF5B:art,0xDCFD:enabled}[address]
        elif op==0x3C: a=(a+1)&255;z=a==0
        elif op==0xE6: a&=code[pc];pc+=1;z=a==0
        elif op==0xB7: z=a==0
        elif op==0x28:
            offset=code[pc];pc+=1
            if z:pc+=offset
        elif op==0xC4:
            assert code[pc:pc+2]==bytes.fromhex('0E 6A');pc+=2
            if not z:called=True
        elif op==0xC3:
            assert code[pc:pc+2]==bytes.fromhex('00 71')
            return called
        else:raise AssertionError(hex(op))
    raise AssertionError('missing tail')


class InlineArtTests(unittest.TestCase):
    def test_all_art_and_enable_states_preserve_loading_work(self):
        code=b.stub()
        for art in range(256):
            for enabled in range(256):
                self.assertEqual(calls(code,art,enabled), bool(enabled and (art+1)&3))

    def test_patch_only_early_stub_and_checksums(self):
        source=b.BASE.read_bytes();candidate=b.build(source)
        changed={i for i,(x,y) in enumerate(zip(source,candidate)) if x!=y}
        self.assertTrue(changed<=set(range(b.START,b.START+len(b.stub())))|{0x14D,0x14E,0x14F})


if __name__=='__main__':
    unittest.main()
