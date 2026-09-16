from pathlib import Path
import unittest

class MovementTraceTests(unittest.TestCase):
    def test_optional_physical_read_only_trace(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        block=source.split('local movement_trace = nil',1)[1].split('local LIMIT',1)[0]
        self.assertIn('os.getenv("STAGE1_NORTH_MOVEMENT_TRACE") == "1"',block)
        self.assertIn('0x1C00, 0x1C3F',block)
        self.assertIn('wram:read8(offset)',block)
        self.assertNotIn('emu:write',block)
        self.assertNotIn('setKeys',block)
        self.assertIn('movement_trace:close(); movement_trace = nil',source)

if __name__=='__main__':unittest.main()
