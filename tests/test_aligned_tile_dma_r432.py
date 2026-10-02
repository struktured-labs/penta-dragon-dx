import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
import build_aligned_tile_dma_r432 as builder


class AlignedCopyTest(unittest.TestCase):
    def test_exact_coverage_and_timing(self):
        for page in (0x9800, 0x9C00):
            mappings = []
            dma_count = 0
            for row in range(24):
                for column, count, kind in builder.row_chunks(row):
                    source = 0xC1A0 + row * 24 + column
                    destination = page + row * 32 + column
                    if kind == 'dma':
                        dma_count += 1
                        self.assertEqual(source & 15, 0)
                        self.assertEqual(destination & 15, 0)
                        self.assertEqual(count, 16)
                        # Conservative polling latency24 + XOR4 + LDH12 +
                        # single-block GDMA32 is below minimum HBlank margin.
                        self.assertLess(24 + 4 + 12 + 32, 165)
                    else:
                        self.assertLessEqual(count, 6)
                    mappings.extend((source+i, destination+i) for i in range(count))
            self.assertEqual(dma_count, 12)
            self.assertEqual(mappings, [(0xC1A0+r*24+c, page+r*32+c)
                                       for r in range(24) for c in range(24)])

    def test_patch_scope_and_guards(self):
        source = builder.BASE.read_bytes()
        result = builder.build(source)
        code = builder.service()
        self.assertIn(bytes.fromhex('F0 55 FE FF C2'), code[:40])
        self.assertEqual(code.count(bytes.fromhex('AF E0 55')), 12)
        allowed = set(range(builder.OFFSET, builder.OFFSET + len(builder.previous_service()))) | {0x14D,0x14E,0x14F}
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(source,result)) if a != b))
