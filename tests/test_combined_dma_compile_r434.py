import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_combined_dma_compile_r434 as builder


class CombinedCompilerTest(unittest.TestCase):
    def test_exact_composition_and_scope(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        offset = builder.bulk.prior.OFFSET
        code = builder.bulk.service()
        allowed = set(range(offset, offset + len(code)))
        allowed.update(range(0x7ACBC, 0x7ACBF))
        allowed.update((0x14D, 0x14E, 0x14F))
        self.assertTrue(all(i in allowed for i, (a, b) in enumerate(zip(source, result)) if a != b))
        self.assertEqual(result[offset:offset + len(code)], code)
        self.assertEqual(result[0x4284:0x4295], source[0x4284:0x4295])
        self.assertEqual(result[0x6AC80:0x6BC00], source[0x6AC80:0x6BC00])
        with self.assertRaises(ValueError):
            builder.build(source[:-1])
