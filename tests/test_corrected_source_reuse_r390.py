"""Reuse experiment must retain the corrected loop and exact base identity."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_corrected_source_reuse_r390 as builder
from test_source_row_reset_r389 import outer_target


class ReuseTests(unittest.TestCase):
    def test_only_cache_hit_branch_changes(self):
        source = builder.BASE.read_bytes()
        candidate = builder.build(source)
        changes = {i for i, (a, b) in enumerate(zip(source, candidate)) if a != b}
        self.assertEqual(changes - {0x14D, 0x14E, 0x14F}, {0x42B2})
        self.assertEqual(candidate[0x42B1:0x42B3], bytes.fromhex('28 10'))
        self.assertEqual(candidate[0x42C3:0x42C6], bytes.fromhex('C3 C0 13'))
        code, _, target = outer_target(candidate)
        self.assertEqual(code[target:target+3], bytes.fromhex('0E 0B C5'))

    def test_wrong_base_rejected(self):
        source = bytearray(builder.BASE.read_bytes())
        source[0x42B2] ^= 1
        with self.assertRaises(ValueError):
            builder.build(source)


if __name__ == '__main__':
    unittest.main()
