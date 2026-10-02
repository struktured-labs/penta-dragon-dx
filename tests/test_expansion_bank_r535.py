from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
import expansion_bank_ownership_r456 as ownership
import build_stage1_menu_close_trial_r535 as menu
import build_title_tile_retire_trial_r535 as title
import build_stage_card_blank_trial_r535 as card


class ExpansionBankR535Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "tmp/stage4-cache-key-r534/candidate.gb").read_bytes()

    def test_old_and_new_full_bank_owners_reconstruct_exactly(self):
        for rom, mode in (
                (self.source, "reconstructed-r534"),
                (menu.build(self.source, True, True), "reconstructed-r535-menu-close"),
                (card.build(title.build(self.source)), "reconstructed-r535-loading-retirement")):
            with self.subTest(mode=mode):
                result = ownership.inspect_tail(rom)
                self.assertTrue(result["exact"])
                self.assertEqual(result["mode"], mode)
                self.assertEqual(set(result["banks"]), {str(i) for i in range(21,32)})

    def test_mutated_helpers_other_banks_and_padding_fail(self):
        rom = card.build(title.build(self.source))
        for offset in (21*16384, 30*16384+100, menu.HOOK, menu.CAVE,
                       card.FALLBACK, card.MUX, card.HELPER, 32*16384-1):
            changed = bytearray(rom)
            changed[offset] ^= 1
            with self.subTest(offset=hex(offset)):
                self.assertFalse(ownership.inspect_tail(changed)["exact"])


if __name__ == "__main__":
    unittest.main()
