"""The combined boss repair is precisely the disjoint union of two owners."""
from pathlib import Path
import hashlib
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'scripts/diagnostics')]
import compose_boss_repairs_r462 as combined
from arena_bank20_r455 import expected_bank20, expected_boss_repairs_bank20
from arena_palette_storage import arena_palette_table


class CombinedRepairs(unittest.TestCase):
    def test_exact_union_and_palette_inheritance(self):
        path=ROOT/'tmp/attract-blank-r456d/candidate.gb'
        if not path.exists(): self.skipTest('retained immutable base unavailable')
        source=path.read_bytes(); result=combined.build(source)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '5c775d6cdaf259576593c14863410746c8d8077cc231fcf37bd9f604bcbde413')
        self.assertEqual(source[20*16384:21*16384],expected_bank20())
        self.assertEqual(result[20*16384:21*16384],expected_boss_repairs_bank20())
        for bank in range(1,32):
            if bank!=20:
                self.assertEqual(source[bank*16384:(bank+1)*16384],result[bank*16384:(bank+1)*16384])
        self.assertEqual(source[:0x14D],result[:0x14D])
        self.assertEqual(source[0x150:0x4000],result[0x150:0x4000])
        for target in range(9):
            self.assertEqual(arena_palette_table(source,target),arena_palette_table(result,target))
        for offset in (0x14F,0x50000,0x52000,0x52157,0x52300,0x54000):
            wrong=bytearray(source);wrong[offset]^=1
            with self.assertRaises(ValueError): combined.build(wrong)


if __name__=='__main__': unittest.main()
