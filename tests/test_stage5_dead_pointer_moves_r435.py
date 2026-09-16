import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_stage5_dead_pointer_moves_r435 as builder


class DeadMovesTest(unittest.TestCase):
    def test_scope_and_branch_targets(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        code = builder.optimize(source[builder.SITE:builder.SITE + 0x4B])
        self.assertEqual(len(code), 0x47)
        for pc, target in ((0x33, 0x0F), (0x41, 0x0D)):
            self.assertEqual(code[pc], 0x20)
            self.assertEqual(pc + 2 + code[pc+1] - 256, target)
        allowed = set(range(builder.SITE, builder.SITE + 0x4B)) | {0x14D, 0x14E, 0x14F}
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(source, result)) if a != b))
        self.assertEqual(code[:0x12], source[builder.SITE:builder.SITE + 0x12])
        self.assertEqual(code[0x12:0x1E], builder.NEW)
