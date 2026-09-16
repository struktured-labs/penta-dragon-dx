from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_compact_vblank_copy_r444b as builder


class CompactVblankTests(unittest.TestCase):
    def test_preserves_complete_timing_and_write_path(self):
        self.assertEqual(builder.NEW[1:], builder.OLD[8:])
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        self.assertEqual(result[0x42CF:0x42ED],source[0x42CF:0x42ED])
        self.assertEqual(result[0x4330:0x4330+len(builder.NEW)],builder.NEW)

    def test_relative_branches_target_same_instructions(self):
        code = builder.NEW
        for operand, expected in ((8,bytes.fromhex('C3 CF 42')),
                                  (16,bytes.fromhex('F0 41')),
                                  (22,bytes.fromhex('F0 41'))):
            target = operand+1+int.from_bytes(code[operand:operand+1],'little',signed=True)
            self.assertEqual(code[target:target+len(expected)],expected)

    def test_wrong_source_rejected(self):
        with self.assertRaisesRegex(AssertionError,'wrong exact'):
            builder.build(bytes(0x80000))


if __name__ == '__main__':unittest.main()
