import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import verify_menu_icon_palettes as menu
import verify_stage1_no_bleed as bleed


class CombinedSemanticTables(unittest.TestCase):
    def test_r445c_inherits_semantic_tables(self):
        rom=(ROOT/'tmp/title-nightfall-port/r443e3f2-v6-r445c/candidate.gb').read_bytes()
        old=(ROOT/'tmp/title-nightfall-port/r443e3-v5/candidate.gb').read_bytes()
        for offset in (menu.BANK13_LUT,menu.BANK20_LUT):
            self.assertEqual(rom[offset:offset+256],old[offset:offset+256])
        expected,forbidden=menu.menu_oracle(rom)
        self.assertEqual(len(forbidden),16)
        self.assertEqual(expected,rom[menu.BANK20_LUT:menu.BANK20_LUT+256])
        self.assertEqual(bleed.expected_stage1_table(rom),rom[menu.BANK13_LUT:menu.BANK13_LUT+256])
        for offset in (menu.BANK13_LUT+0x64,menu.BANK20_LUT+0x88,0x72C80,0x150):
            changed=bytearray(rom);changed[offset]^=1
            self.assertFalse(menu.menu_oracle(changed)[1])
            self.assertNotEqual(bleed.expected_stage1_table(changed),changed[menu.BANK13_LUT:menu.BANK13_LUT+256])

    def test_exact_inherited_tables_and_mutation_rejection(self):
        old=(ROOT/'tmp/stage1-subscene-tracking-r442/candidate.gb').read_bytes()
        rom=(ROOT/'tmp/title-nightfall-port/r443e3-v5/candidate.gb').read_bytes()
        for offset in (menu.BANK13_LUT,menu.BANK20_LUT):
            self.assertEqual(rom[offset:offset+256],old[offset:offset+256])
        expected,forbidden=menu.menu_oracle(rom)
        self.assertEqual(len(forbidden),16)
        self.assertEqual(expected,rom[menu.BANK20_LUT:menu.BANK20_LUT+256])
        self.assertEqual(bleed.expected_stage1_table(rom),rom[menu.BANK13_LUT:menu.BANK13_LUT+256])
        for offset in (menu.BANK13_LUT+0x64,menu.BANK20_LUT+0x88,0x150):
            changed=bytearray(rom);changed[offset]^=1
            self.assertFalse(menu.menu_oracle(changed)[1])
            self.assertNotEqual(bleed.expected_stage1_table(changed),changed[menu.BANK13_LUT:menu.BANK13_LUT+256])
