from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
from verify_ted_expanded_integration import (native_pose_bank_matches,
                                             title_safe_copy_entry,
                                             nightfall_menu_prelude, build, menu_icons)
from prototype_ted_expanded_bank import build_native_pose_bank


class TedIntegrationLayouts(unittest.TestCase):
    def test_prelude_transforms_only_reviewed_spans(self):
        base = menu_icons._menu_owned_prelude(build.build_colorize_prelude())
        expected = nightfall_menu_prelude(base)
        self.assertEqual(len(base), len(expected))
        differences = {i + 0x6E80 for i, (a, b) in enumerate(zip(base, expected)) if a != b}
        allowed = set(range(0x6E9D, 0x6EA6)) | {0x6EB5} | set(range(0x6EC4, 0x6EF4))
        self.assertTrue(differences <= allowed)
        wrong_base = bytearray(base)
        wrong_base[0x6EC4 - 0x6E80] = 1
        with self.assertRaises(AssertionError):
            nightfall_menu_prelude(wrong_base)

    def test_only_reviewed_epoch_operand_may_differ(self):
        expected = build_native_pose_bank()
        actual = bytearray(expected)
        actual[0x365] = 0x72
        self.assertTrue(native_pose_bank_matches(actual, expected, 0xC0))
        self.assertFalse(native_pose_bank_matches(actual, expected, 0x80))
        actual[0x366] ^= 1
        self.assertFalse(native_pose_bank_matches(actual, expected, 0xC0))

    def test_title_entry_requires_exact_instructions(self):
        for entry in (0x4357, 0x435A):
            rom = bytearray(0x8000)
            rom[entry:entry + 7] = bytes.fromhex("26 98 AF 6F CD 82 34")
            self.assertEqual(title_safe_copy_entry(rom), entry)
            rom[entry + 6] ^= 1
            self.assertIsNone(title_safe_copy_entry(rom))
