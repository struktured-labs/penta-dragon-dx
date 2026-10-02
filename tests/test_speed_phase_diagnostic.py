from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class PhaseDiagnostic(unittest.TestCase):
    def test_default_anchor_and_bounded_receipt(self):
        lua=(ROOT/'scripts/diagnostics/probe_stage_speed.lua').read_text()
        self.assertIn('os.getenv("STAGE_SPEED_SYNC_DELAY") or "0"',lua)
        self.assertIn('SYNC_DELAY <= 3 and SYNC_DELAY % 1 == 0',lua)
        self.assertIn('stable_frames >= 120 + SYNC_DELAY',lua)
        self.assertIn('"sync_delay_frames": %d',lua)
        self.assertIn('end, 0x016C)',lua)
