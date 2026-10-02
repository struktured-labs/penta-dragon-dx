"""Execute the pretest's small instruction subset, including actual JR targets."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/diagnostics'))
from build_later_stage_deferred_dma_r443 import isr_pretest


def execute(code,scene,latch):
    pc=0; a=0xA5; z=False
    for _ in range(12):
        op=code[pc]
        if op==0xFA:
            assert code[pc+1:pc+3]==bytes.fromhex('80 D8')
            a=scene; pc+=3
        elif op==0x3D:
            a=(a-1)&255; z=a==0; pc+=1
        elif op==0x28:
            d=code[pc+1]; pc+=2
            if z: pc+=d if d<128 else d-256
        elif op==0xF0:
            assert code[pc+1]==0xC4
            a=latch; pc+=2
        elif op==0xE6:
            a &= code[pc+1]; z=a==0; pc+=2
        elif op==0xCA:
            assert code[pc+1:pc+3]==bytes.fromhex('1D 6F')
            if z: return 'idle'
            pc+=3
        elif op==0x3E:
            a=code[pc+1]; pc+=2
        elif op==0xCD:
            assert code[pc+1:pc+3]==bytes.fromhex('47 08') and a==25
            assert code[pc+3:]==bytes.fromhex('C3 85 74')
            return 'call'
        else:
            raise AssertionError(f'unexpected opcode {op:02X} at offset {pc}')
    raise AssertionError('pretest failed to terminate')


class PretestPaths(unittest.TestCase):
    def test_all_scene_and_latch_paths(self):
        code=isr_pretest()
        for scene in range(256):
            for latch in range(256):
                self.assertEqual(execute(code,scene,latch),
                                 'call' if scene==1 or latch&0x60 else 'idle')

    def test_off_by_one_branch_is_rejected(self):
        code=bytearray(isr_pretest()); code[5]=6
        with self.assertRaises(AssertionError): execute(code,1,0)
