"""Controls for comparable native-gameplay entry and SRAM observation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NorthGameplayEntryTests(unittest.TestCase):
    def test_boot_flag_trace_is_bounded_and_read_only(self):
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        self.assertIn('os.getenv("NORTH_BOOT_FLAG_TRACE") == "1"', probe)
        trace = probe.split('  if boot_trace and frame <= 1000 then',1)[1].split('  if first_gameplay >= 0',1)[0]
        self.assertIn('physical:read8(0x1F5D)',trace)
        self.assertIn('boot_trace:close()',trace)
        self.assertNotIn('write8',trace)
        self.assertNotIn('setKeys',trace)

    def test_native_loop_clock_preserves_early_visual_stream(self):
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        self.assertIn('unknown native gameplay loop', probe)
        self.assertIn('end, 0x016C)', probe)
        self.assertIn('scene == 0x02 and active == 1 then', probe)
        self.assertIn('native_gameplay_start = frame', probe)

    def test_sram_capture_requires_enabled_native_routine(self):
        probe = (ROOT / 'scripts/diagnostics/probe_stage1_north_integrity.lua').read_text()
        self.assertIn('unknown SRAM enable routine', probe)
        self.assertIn('end, 0x09D5)', probe)
        self.assertEqual(probe.count('"/metatiles-at-entry.bin"'), 1)
        self.assertIn('first_gameplay < 0 or entry_table_captured', probe)

    def test_exact_table_and_timing_checks_remain(self):
        verifier = (ROOT / 'scripts/diagnostics/verify_stage1_north_integrity.py').read_text()
        self.assertIn('metatile_table_ok = metatile_differences == 0', verifier)
        self.assertIn('"gameplay_frame_lag":', verifier)
        self.assertIn('missing native gameplay timing boundary', verifier)
        self.assertIn('int(candidate_report["native_gameplay_frames"])', verifier)


if __name__ == '__main__':
    unittest.main()
