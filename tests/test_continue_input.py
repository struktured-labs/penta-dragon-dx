"""Issue #28 structural tests; live acceptance/timeout replay remains separate."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_continue_input as builder


class ContinueInputTests(unittest.TestCase):
    def setUp(self):
        parent=bytearray(b'\xff'*0x100000)
        parent[0x34000:0x38000]=bytes(0x4000)
        parent[0x37189:0x37193]=builder.TAIL
        parent[0x36F3D:0x36F68]=builder.SAMPLER
        parent[0x847:0x850]=bytes.fromhex('CD6100 CD806C C36100')
        parent[0x371DB:0x371E4]=bytes.fromhex('3E0D F5 3E14 CD6100 E1')
        self.parent=bytes(parent)
        pins=patch.object(builder,'PARENT',builder.digest(self.parent))
        pins.start()
        self.addCleanup(pins.stop)

    def test_patch_bounds_and_checksum(self):
        result=builder.build(self.parent)
        changed={i for i,(a,b) in enumerate(zip(result,self.parent)) if a!=b}
        allowed={0x14E,0x14F}|set(range(0x37189,0x37193))|set(range(0x8C000,0x90000))
        self.assertLessEqual(changed,allowed)
        self.assertEqual(len(result),len(self.parent))
        self.assertEqual(int.from_bytes(result[0x14E:0x150],'big'),
                         (sum(result[:0x14E])+sum(result[0x150:]))&65535)

    def test_mirror_preserves_visual_dependencies_and_returns_to_mirror(self):
        result=builder.build(self.parent)
        mirror=result[0x8C000:0x90000]
        helper=bytes.fromhex('CD3065 CDD069')+builder.SAMPLER+bytes.fromhex('3E0D C9')
        self.assertEqual(mirror[0x2C80:0x2C80+len(helper)],helper)
        self.assertEqual(mirror[0x31DC],35)
        changes={i for i,(a,b) in enumerate(zip(mirror,self.parent[0x34000:0x38000])) if a!=b}
        self.assertLessEqual(changes,{0x31DC}|set(range(0x2C80,0x2C80+len(helper))))
        self.assertEqual(result[0x37189:0x37193],bytes.fromhex('3E23 CD4708 E1 C38C6F 00'))

    def test_settled_window_gate_branch_destinations(self):
        result=builder.build(self.parent,settled_window=True)
        gate=bytes.fromhex('F040 E620 2806 F047 FEE4 2803 3E0D C9')
        start=0x8EC80+6
        self.assertEqual(result[start:start+len(gate)],gate)
        # Window disabled returns; settled BGP jumps over return into sampler.
        self.assertEqual(6+gate[5],12)
        self.assertEqual(12+gate[11],len(gate))
        self.assertEqual(result[start+12:start+15],bytes.fromhex('3E0D C9'))
        self.assertEqual(result[start+15:start+15+len(builder.SAMPLER)],builder.SAMPLER)

    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            builder.build(self.parent[:-1]+b'\0')

    def test_after_visuals_leaves_palette_call_timing_unchanged(self):
        result=builder.build(self.parent,after_visuals=True)
        self.assertEqual(result[0x37189:0x3718F],self.parent[0x37189:0x3718F])
        self.assertEqual(result[0x3718F:0x37195],bytes.fromhex('3E23 C34708 00'))
        helper=builder.SAMPLER+bytes.fromhex('E1 D1 118C6F D5 E5 3E0D C9')
        self.assertEqual(result[0x8EC80:0x8EC80+len(helper)],helper)
        # Stack at private-helper entry: far-call return, death-service return,
        # saved HL/DE/BC, wrapper caller. Adapter replaces only service return.
        stack=[0x084D,0x6F23,0x1234,0x5678,0x9ABC,0x0830]
        hl=stack.pop(0)
        stack.pop(0)
        stack.insert(0,0x6F8C)
        stack.insert(0,hl)
        self.assertEqual(stack.pop(0),0x084D)
        self.assertEqual(stack.pop(0),0x6F8C)
        self.assertEqual(stack,[0x1234,0x5678,0x9ABC,0x0830])
        changes={i for i,(a,b) in enumerate(zip(result,self.parent)) if a!=b}
        self.assertLessEqual(changes,{0x14E,0x14F}|set(range(0x3718F,0x37195))|
                             set(range(0x8EC80,0x8EC80+len(helper))))

    def test_after_visuals_rejects_occupied_padding(self):
        parent=bytearray(self.parent)
        parent[0x37193]=1
        with patch.object(builder,'PARENT',builder.digest(parent)):
            with self.assertRaises(ValueError):
                builder.build(parent,after_visuals=True)

    def test_repin_does_not_bypass_structural_preimages(self):
        for offset in (0x37189,0x36F3D,0x847,0x371DB,0x8C000):
            with self.subTest(offset=offset):
                changed=bytearray(self.parent)
                changed[offset]^=1
                with patch.object(builder,'PARENT',builder.digest(changed)):
                    with self.assertRaises(ValueError):
                        builder.build(changed)


if __name__=='__main__':
    unittest.main()
