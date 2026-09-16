import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import build_stage1_subscene_tracking_r442 as patch


class Stage1SubsceneTracking(unittest.TestCase):
    def test_current_verifier_abis(self):
        import verify_low_health_flicker as low
        import verify_stage1_spike_palettes as spike
        import verify_stage1_no_bleed as bleed
        import verify_menu_icon_palettes as menu
        rom=patch.build(patch.BASE.read_bytes())
        self.assertEqual(low.owner_address(rom),0xFF01)
        self.assertEqual(low.bulk_compiler_profile(rom),'r426-bulk-v1')
        self.assertEqual(low.publication_route_profile(rom),'r440-bounded-room03')
        self.assertTrue(spike.semantic_expansion_is_exact(rom))
        self.assertEqual(bleed.expected_stage1_table(rom),rom[0x37000:0x37100])
        self.assertEqual(menu.menu_oracle(rom)[0],rom[0x50100:0x50200])

    def test_scoped_change_and_preserved_guards(self):
        source = patch.BASE.read_bytes()
        result = patch.build(source)
        allowed = {0x14D,0x14E,0x14F}
        for offset in patch.SITES:
            allowed.update(range(offset,offset+5))
            self.assertEqual(result[offset:offset+5],patch.NEW)
            self.assertEqual(result[offset+5:offset+16],source[offset+5:offset+16])
        self.assertTrue({i for i,(a,b) in enumerate(zip(source,result)) if a!=b} <= allowed)
        bad=bytearray(source);bad[0x150]^=1
        with self.assertRaises(ValueError):patch.build(bad)
