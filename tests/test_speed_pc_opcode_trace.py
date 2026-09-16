from pathlib import Path
import unittest


class PcOpcodeTrace(unittest.TestCase):
    def test_optional_trace_reads_live_bytes_without_writes(self):
        lua=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        self.assertIn('os.getenv("STAGE_SPEED_PC_TRACE") == "1"',lua)
        block=lua.split('if pc_trace and phase == "play" then',1)[1].split('if camera_trace then',1)[0]
        self.assertIn('emu:read8(sampled_pc)',block)
        self.assertIn('emu:read8((sampled_pc + 2) & 65535)',block)
        self.assertNotIn('emu:write',block)
        self.assertNotIn('setKeys',block)
