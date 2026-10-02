import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_compiled_tooth_bank_r438 as builder


class CompiledToothBank(unittest.TestCase):
    def test_only_twelve_tooth_bank_bits_change(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        changed = {i for i,(a,b) in enumerate(zip(source,result)) if a != b}
        teeth = {builder.TABLE+t for t in builder.TEETH}
        self.assertEqual(changed - {0x14D,0x14E,0x14F}, teeth)
        self.assertTrue(all(result[i] == 15 and result[i] ^ source[i] == 8 for i in teeth))
        with self.assertRaises(ValueError):
            builder.build(source + b'mutation')
