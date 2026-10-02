"""The outer source-expansion loop must reset its eleven-column counter."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_source_row_reset_r389 as builder


def outer_target(rom):
    code = rom[builder.CLONE:builder.CLONE+256]
    operand = code.index(builder.OUTER)+len(builder.OUTER)
    target = operand+1+int.from_bytes(code[operand:operand+1], 'little', signed=True)
    return code, operand, target


class RowTests(unittest.TestCase):
    def test_outer_loop_resets_counter_before_pushing_it(self):
        source = builder.BASE.read_bytes()
        candidate = builder.build(source)
        before, operand, old_target = outer_target(source)
        after, _, target = outer_target(candidate)
        self.assertEqual(before[old_target], 0xC5)  # failing negative control
        self.assertEqual(after[target:target+3], bytes.fromhex('0E 0B C5'))
        self.assertEqual(target, old_target-2)
        changed = {i for i, (a, b) in enumerate(zip(source, candidate)) if a != b}
        self.assertEqual(changed-{0x14D, 0x14E, 0x14F}, {builder.CLONE+operand})


if __name__ == '__main__':
    unittest.main()
