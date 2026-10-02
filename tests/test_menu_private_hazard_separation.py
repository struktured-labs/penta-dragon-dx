import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import verify_menu_icon_palettes as menu


class MenuHazardSeparation(unittest.TestCase):
    def test_exact_table_and_all_native_groups(self):
        rom = (ROOT/'tmp/stage2-seven-rows-r441/candidate.gb').read_bytes()
        expected, forbidden = menu.menu_oracle(rom)
        self.assertEqual(len(forbidden), 16)
        self.assertEqual(expected, rom[menu.BANK20_LUT:menu.BANK20_LUT+256])
        report = menu.parse_report(ROOT/'tmp/astra-r441-release-opening-icons/artifacts/menu-icon-palettes/run-1.txt')
        self.assertFalse(menu.audit_report(report, expected, True, forbidden)[0])
        # Even matching tile/source/attribute data cannot admit dungeon art.
        bad = dict(report)
        for plane, value in (('tiles', '64'), ('packed', '64'), ('attrs', '07')):
            key = 'page0_'+plane+'0'
            bad[key] = value + bad[key][2:]
        self.assertTrue(menu.audit_report(bad, expected, True, forbidden)[0])
        corrupted = bytearray(expected);corrupted[0x88] ^= 1
        self.assertTrue(menu.audit_report(report, bytes(corrupted), True, forbidden)[0])
        changed = bytearray(rom);changed[0x150] ^= 1
        unknown, reserved = menu.menu_oracle(bytes(changed))
        self.assertFalse(reserved)
        self.assertNotEqual(unknown, expected)
