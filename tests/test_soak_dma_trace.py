"""Optional DMA lifetime diagnostics must not alter the game state."""
from pathlib import Path
import unittest


class SoakDmaTraceTests(unittest.TestCase):
    def test_opt_in_bounded_and_read_only(self):
        source = (Path(__file__).resolve().parents[1] /
                  'scripts/diagnostics/probe_later_stage_soak.lua').read_text()
        block = source.split('if os.getenv("SOAK_DMA_TRACE") == "1" then', 1)[1]
        block = block.split('local attr_trace =', 1)[0]
        self.assertIn('play_frame > 1000 or events >= 5000', block)
        self.assertIn('0, 0x2FF', block)
        self.assertIn('0x3280', block)
        self.assertIn('{0x42FC, 0x4324}', block)
        self.assertNotIn(':write8(', block)
        self.assertNotIn(':setKeys(', block)


if __name__ == '__main__':
    unittest.main()
