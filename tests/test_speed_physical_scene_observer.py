"""Guard physical-bank scene observation against PC-window mismatch waivers."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SceneObserverTests(unittest.TestCase):
    def test_probe_requires_physical_wram_and_never_invents_expected_scene(self):
        source = (ROOT / 'scripts/diagnostics/probe_stage_speed.lua').read_text()
        body = source.split('local function scene_sample()', 1)[1].split('\nend', 1)[0]
        self.assertIn('assert(emu.memory and emu.memory.wram', body)
        self.assertIn('wram:read8(0x1880)', body)
        self.assertIn('return value, false, pc, svbk', body)
        self.assertNotIn('EXPECTED_SCENE', body)
        self.assertNotIn('COMPILER_BANK', body)
        self.assertNotIn('emu:read8(0xD880)', body)

    def test_raw_domain_offset_selects_scene_bank_not_staging_bank(self):
        # CGB mGBA WRAM domain: 4KiB segments, segmentStart=$D000.
        offset = 0x1880
        segment = offset // 0x1000
        address = 0xC000 + offset % 0x1000 + (0x1000 if segment else 0)
        self.assertEqual((segment, address), (1, 0xD880))
        # DMG has one 8KiB domain; raw segment0 upper WRAM maps to bank1.
        self.assertEqual(0xC000 + offset, 0xD880)


if __name__ == '__main__':
    unittest.main()
