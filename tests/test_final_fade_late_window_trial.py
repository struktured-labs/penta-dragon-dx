import hashlib
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_final_fade_late_window_trial import payload,build,BASE


class FinalFadeLateWindow(unittest.TestCase):
    def test_instruction_budget_and_full_restore(self):
        code,labels=payload()
        self.assertEqual(code[:4],bytes.fromhex('F068F5F3'))
        self.assertEqual(code[labels['sample_ly']-BASE:labels['fallback']-BASE],
                         bytes.fromhex('F044FE903806FE9730021805'))
        self.assertEqual(code[labels['upload']-BASE:labels['write_start']-BASE],
                         bytes.fromhex('3E07E0703E80E0682100DF0E69'))
        writes=code[labels['write_start']-BASE:labels['write_end']-BASE]
        self.assertEqual(writes,bytes.fromhex('2AE2')*64)
        # Normal-speed CPU T-cycles from start of LY read through last write.
        # DI precedes the sample. At LY150's end at least lines151..153 remain.
        detect=12+8+8+8+8+12
        setup=8+12+8+12+12+8
        copy=64*(8+8)
        self.assertEqual(detect+setup+copy,1140)
        self.assertLess(detect+setup+copy,3*456)
        # HL advances through every backed-up byte; no shade transforms/masks.
        memory=bytes(range(64));hl=0;emitted=[]
        for i in range(0,len(writes),2):
            a=memory[hl];hl+=1;emitted.append(a)
        self.assertEqual(bytes(emitted),memory)

    def test_only_final_call_and_owned_new_body_change(self):
        parent=(ROOT/'tmp/fixed-fade-route-trial-01/candidate.gb').read_bytes()
        rom,_=build(parent);code,_=payload()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '46eb95a0c0f770fb3cf8c3211b8030a9e881f59077e558b93703ba08da71d3fb')
        allowed={0x14E,0x14F}|set(range(0x5165D,0x51660))|set(range(0x52314,0x52314+len(code)))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(parent,rom)) if a!=b))


if __name__=='__main__':unittest.main()
