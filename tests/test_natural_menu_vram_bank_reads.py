"""Prevent out-of-domain VRAM reads from masquerading as bank-1 evidence."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BankReadTests(unittest.TestCase):
    def test_bank_one_observers_select_and_restore_vbk(self):
        source = (ROOT / 'scripts/diagnostics/probe_stage1_natural_menu_bg.lua').read_text()
        self.assertNotIn('raw_vram:read8(0x2000 +', source)
        self.assertNotIn('raw_vram:read8(0x3000 +', source)
        for name, end, read in (
            ('local function visible_map_signature()', 'local function visible_oam_text()',
             'emu:read8(0x8000 + offset)'),
            ('target_map_mismatch_summary = function(base)', 'local function state_text()',
             'emu:read8(cell.address)'),
            ('local function bank1_art_mismatches()', 'local function dump_plane(',
             'emu:read8(0x9000 + tile * 16 + byte_index)'),
        ):
            body = source.split(name, 1)[1].split(end, 1)[0]
            self.assertIn('emu:write8(0xFF4F, 1)', body)
            self.assertIn('emu:write8(0xFF4F, old_vbk)', body)
            self.assertIn(read, body)


if __name__ == '__main__':
    unittest.main()
