import sys
from pathlib import Path
import unittest
import re
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from check_low_health_semantic_hazards import analyze, expected


class SemanticHazardCrosscheck(unittest.TestCase):
    def test_live_body_classifier_includes_reviewed_terminal_caps(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/'scripts/diagnostics/probe_low_health_flicker.lua').read_text()
        body = source.split('and (tile == 0x60 or tile == 0x61 or tile == 0x62', 1)[1].split('expected_hazard = 0x05', 1)[0]
        actual = {0x60,0x61,0x62} | {int(t,16) for t in re.findall(r'tile == 0x([0-9A-F]+)',body)}
        self.assertEqual(actual, {t for t in range(256) if expected(t)==5})
        sys.path.insert(0, str(root/'scripts'))
        from stage1_hazard_art import load_stage1_hazard_config
        config = load_stage1_hazard_config()
        self.assertEqual(actual, config.ring_tiles | config.body_tiles | config.connector_tiles | config.terminal_tiles)
        self.assertEqual(config.terminal_palette, 5)

    def test_materials_and_negative_controls(self):
        self.assertEqual([expected(t) for t in (1,0x64,0x75,0x6B,0x7F,0x6A)], [0,15,15,5,5,6])
        row = dict(stimulus_phase='scene0b', frame='7', tile_bytes='0164756b7f6a', attr_bytes='000f0f050506')
        self.assertEqual(analyze([row])['scene0b']['mismatch_cells'], 0)
        for attrs in ('070f0f050506','00070f050506','000f0f060506'):
            self.assertEqual(analyze([dict(row, attr_bytes=attrs)])['scene0b']['mismatch_cells'], 1)
        with self.assertRaises(ValueError):
            analyze([dict(row, attr_bytes='00')])
