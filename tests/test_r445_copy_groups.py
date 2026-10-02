import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from compose_stage1_wide_copy_r445 import emit, model_new, model_old


class FiveTileGroups(unittest.TestCase):
    def test_exit_restores_clone_c_register(self):
        code=emit((5,5,5,5,4))
        self.assertTrue(code.endswith(bytes.fromhex('0E 00 3E 01 C9')))
        # The compatibility build differs only by the off-critical-path
        # register restore; it must not change any wait or copy instruction.
        old=emit((5,5,5,5,4),exit_c0=False)
        self.assertEqual(code[:-5],old[:-3])
        self.assertEqual(model_new(code),model_new(old))

    def test_emitted_five_tile_groups_and_branch_boundaries(self):
        code=emit((5,5,5,5,4))
        self.assertEqual(model_new(code),model_old())
        sizes={0x11:3,0x0E:2,0xF3:1,0xFA:3,0xFE:2,0x20:2,
               0xF0:2,0xE6:2,0x28:2,0xF2:1,0x0F:1,0x38:2,
               0x1A:1,0x22:1,0x13:1,0x1C:1,0xFB:1,0x7D:1,
               0xC6:2,0x6F:1,0x30:2,0x24:1,0x3E:2,0xC9:1,
               0xF5:1,0xF1:1,0x3D:1,0xC3:3}
        pc=0; boundaries=set(); jumps=[]; groups=[]; tiles=0; cycles=0; last_write=0
        while pc<len(code):
            boundaries.add(pc);op=code[pc]
            self.assertIn(op,sizes)
            if op in (0x20,0x28,0x38,0x30):
                d=code[pc+1];jumps.append(pc+2+(d if d<128 else d-256))
            elif op==0xC3:
                jumps.append((code[pc+1]+256*code[pc+2])-0x6C80)
            if op==0x1A: tiles+=1;cycles+=2
            elif op==0x22: cycles+=2;last_write=cycles
            elif op in (0x1C,0x13): cycles+=1 if op==0x1C else 2
            elif op==0xFB:
                groups.append(tiles)
                # Include first mode0 sample following the mode3 gate, not
                # merely the shorter steady-state polling period.
                self.assertLessEqual(11+last_write,(87+80)/4)
                tiles=0;cycles=0;last_write=0
            pc+=sizes[op]
        self.assertEqual(groups,[5,5,5,5,4])
        self.assertTrue(all(target in boundaries for target in jumps))
