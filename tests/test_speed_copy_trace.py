from pathlib import Path
import unittest


class CopyTraceContract(unittest.TestCase):
    def test_optional_read_only_and_branch_outcome_sites(self):
        text=(Path(__file__).resolve().parents[1]/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        self.assertIn('os.getenv("STAGE_SPEED_COPY_TRACE") == "1"',text)
        block=text.split('breakpoints_available = pcall(function()',1)[1].split('-- The two stock entries',1)[0]
        for site in ('0x4295','0x435A','0x42A7','0x42BB','0x42ED','0x4302','0x6E00','0x6E05'):
            self.assertIn(site,block)
        self.assertIn('packer-accepted',block)
        self.assertIn('emu:read8(0xFF01)',block)
        self.assertIn('emu:read8(0xFF99) == 24',block)
        self.assertNotIn('write8',block)
        self.assertNotIn('setKeys',block)
        self.assertIn('if copy_trace then copy_trace:close(); copy_trace = nil end',text)
        guard=text.split('local function in_fixed_bank1_cave()',1)[1].split('\nend',1)[0]
        for check in ('0x4295) == 0xFA','0x4296) == 0x0B','0x4297) == 0xDC',
                      '0x42A7) == 0x2E','0x42A8) == 0x00'):
            self.assertIn(check,guard)
