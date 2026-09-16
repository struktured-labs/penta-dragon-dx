import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/diagnostics'))
import build_stage2_seven_rows_r441 as b


class SevenRows(unittest.TestCase):
    def test_stage1_observer_abi_is_preserved(self):
        from verify_stage1_spike_palettes import semantic_expansion_is_exact
        from verify_low_health_flicker import publication_route_profile, bulk_compiler_profile
        rom=b.build(b.BASE.read_bytes())
        self.assertTrue(semantic_expansion_is_exact(rom))
        self.assertEqual(publication_route_profile(rom),'r440-bounded-room03')
        self.assertEqual(bulk_compiler_profile(rom),'r426-bulk-v1')

    def test_exact_scope_and_transfer_extent(self):
        source=b.BASE.read_bytes();result=b.build(source)
        changed={i for i,(a,c) in enumerate(zip(source,result)) if a!=c}
        expected=set()
        for offset,old,new in b.patches():
            expected|={offset+i for i,(a,c) in enumerate(zip(old,new)) if a!=c}
        self.assertEqual(len(expected),2)
        self.assertEqual(changed-{0x14D,0x14E,0x14F},expected)
        # FFE0=24..18 are compiled; next call at 17 publishes 14 blocks.
        self.assertEqual(24-0x11,7)
        self.assertEqual(((0x8D & 0x7F)+1)*16,7*32)
        with self.assertRaises(ValueError):b.build(source+b'x')
