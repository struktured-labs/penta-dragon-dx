import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
import build_secret_bg0_dedup_trial as trial


def route(stage,a,flags):
    code=trial.CODE;pc=0;stack=[]
    for _ in range(12):
        op=code[pc];pc+=1
        if op==0xF5: stack.append((a,flags))
        elif op==0xF0:
            assert code[pc]==0xBA;pc+=1;a=stage
        elif op==0xFE:
            value=code[pc];pc+=1
            flags=64|(128 if a==value else 0)|(16 if a<value else 0)|(32 if (a&15)<(value&15) else 0)
        elif op==0x28:
            offset=code[pc];pc+=1
            if flags&128: pc+=offset
        elif op==0xF1: a,flags=stack.pop()
        elif op==0xC3:
            return int.from_bytes(code[pc:pc+2],'little'),a,flags,stack
        elif op==0xC9: return 'return',a,flags,stack
        else: raise AssertionError(op)
    raise AssertionError('No exit')


class DedupTests(unittest.TestCase):
    def test_only_stage7_returns_and_af_is_preserved(self):
        for stage in range(256):
            for flags in range(0,256,16):
                self.assertEqual(route(stage,0x80,flags),
                                 ('return' if stage==7 else 0x7FE0,0x80,flags,[]))

    def test_patch_scope(self):
        path=ROOT/'tmp/secret-sound-alias-fast-trial-01/candidate.gb'
        if not path.exists(): self.skipTest('Exact parent unavailable')
        parent=path.read_bytes();changed=trial.build(parent)
        allowed={0x14E,0x14F}|set(range(trial.HOOK,trial.HOOK+3))|set(range(trial.CAVE,trial.CAVE+len(trial.CODE)))
        self.assertEqual(len(parent),len(changed))
        self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(parent,changed))))
        with self.assertRaises(ValueError): trial.build(b'wrong')
