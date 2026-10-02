import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from stage_card_palette_handoff import inspect_stage_card_palette_handoff as inspect


class DealiasHandoff(unittest.TestCase):
    def test_exact_compositions_and_negative_controls(self):
        for directory in ('r443e3-v5','r443e3f2-v6','r443e3f2-v6-r445c'):
            rom=(ROOT/'tmp/title-nightfall-port'/directory/'candidate.gb').read_bytes()
            result=inspect(rom)
            self.assertTrue(result['installed'],directory)
            self.assertTrue(result['vblank_atomic_installed'])
            for offset in (0x37701,0x37719,0x37D18,0x37407,0x3740F,0x37457,0x3746D,0x150):
                bad=bytearray(rom);bad[offset]^=1
                self.assertFalse(inspect(bad)['installed'],(directory,offset))
