"""#27 bounded scene resolver and exact layout contracts; no readiness claim."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_arena_direct_scene_trial as trial


def execute(raw,canonical):
    code=trial.RESOLVER;pc=0;a=0;z=c=False
    for _ in range(20):
        op=code[pc];pc+=1
        if op==0xFA:
            assert code[pc:pc+2]==bytes.fromhex('80D8');pc+=2;a=raw
        elif op==0xF0:
            assert code[pc]==0xB7;pc+=1;a=canonical
        elif op in (0xC0,0xC9):
            if op==0xC9 or not z:return a
        elif op in (0xFE,0xD6,0xC6,0x3E):
            v=code[pc];pc+=1
            if op==0x3E:a=v;continue
            n=a+v if op==0xC6 else a-v;z=(n&255)==0;c=n<0 or n>255
            if op!=0xFE:a=n&255
        elif op==0x38:
            v=code[pc];pc+=1
            if c:pc+=v if v<128 else v-256
        else:raise AssertionError(f'unhandled {op:02x}')
    raise AssertionError('no return')


class DirectScene(unittest.TestCase):
    def test_all_scene_pairs(self):
        for raw in range(256):
            for canonical in range(256):
                expected=canonical if raw==11 and 12<=canonical<=20 else raw
                self.assertEqual(execute(raw,canonical),expected,(raw,canonical))

    def test_stale_cache_examples_no_longer_control_resolution(self):
        for raw,canonical in ((9,9),(2,2),(11,2),(24,9)):
            self.assertEqual(execute(raw,canonical),raw)
        self.assertEqual(execute(11,12),12)

    def test_layout_and_legacy_tail(self):
        path=ROOT/'tmp/arena-alias-source-01/candidate.gb'
        if not path.exists():self.skipTest('local exact parent unavailable')
        parent=path.read_bytes();new=trial.build(parent)
        def runtime(rom,bank):
            return b''.join(rom[trial.offset(bank,a):trial.offset(bank,a)+n] for a,n in trial.FRAGMENTS)
        body=runtime(new,13)
        self.assertEqual(body[56:75],trial.RESOLVER)
        self.assertEqual(0xDBAF+body[10],0xDBD5)
        self.assertEqual(0xDBB4+body[15],0xDBD5)
        self.assertEqual(body[49:52],bytes.fromhex('AFE1C9'))
        self.assertEqual(runtime(new,16)[5:],runtime(parent,16)[5:])
        self.assertEqual(new[0x4357:0x435A],bytes.fromhex('C39734'))
        for bank in (13,16):
            for address in (0x7C7A,0x569C,0x563A):
                off=trial.offset(bank,address)
                self.assertEqual(new[off:off+3],bytes.fromhex('CDDCDB' if bank==13 else 'FA80D8'))


if __name__=='__main__':unittest.main()
