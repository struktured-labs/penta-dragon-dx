from pathlib import Path
import hashlib
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from compose_stage1_wide_copy_r445 import emit, model_new, model_old


class LaterCopyEntry(unittest.TestCase):
    def test_exact_candidate_scope_and_complete_helper(self):
        base=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c-r446/candidate.gb').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         '28921e274c5262516b019652937249896fbe678a0eadbf8ea5168189f1defa3b')
        self.assertEqual(len(rom),len(base))
        self.assertTrue({i for i,(a,b) in enumerate(zip(base,rom)) if a!=b}
                        <= set(range(0x42BB,0x42C3)) | {0x14D,0x14E,0x14F})
        self.assertEqual(rom[0x42BB:0x42C3],bytes.fromhex('3E1C CD4708 C3ED42'))
        self.assertEqual(rom[0x42BB:0x42C3],rom[0x42C7:0x42CF])
        self.assertEqual(rom[0x0847:0x0850],bytes.fromhex('CD6100 CD806C C36100'))
        helper=rom[0x72C80:0x72D70]
        self.assertEqual(helper,emit((5,5,5,5,4)))
        self.assertEqual(model_new(helper),model_old())
        self.assertEqual(rom[0x42ED:0x4330],base[0x42ED:0x4330])
